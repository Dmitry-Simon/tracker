import hashlib
import calendar
import difflib
from datetime import datetime, timedelta
import firebase_admin
from firebase_admin import credentials, firestore
import streamlit as st
import json
import re

# Initialize Firebase app (singleton)
MOCK_MODE = False
if not firebase_admin._apps:
    # Use secrets for credentials
    if "gcp_service_account" in st.secrets:
        cred_dict = dict(st.secrets["gcp_service_account"])
        # Fix private key newline issue if present
        if "private_key" in cred_dict:
            cred_dict["private_key"] = cred_dict["private_key"].replace("\\n", "\n")
            
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)
    else:
        # Fallback to Mock Mode if no secrets found
        print("Warning: No secrets found for Firebase. Switching to MOCK_MODE.")
        MOCK_MODE = True

def get_db():
    if MOCK_MODE:
        return None
    return firestore.client()

def normalize_description(description: str) -> str:
    """Lowercase string, strip whitespace, remove multiple spaces."""
    s = str(description).lower().strip()
    # Remove multiple spaces
    s = re.sub(r'\s+', ' ', s)
    return s

def generate_hash_id(date_iso: str, amount: float, description: str, ref_id: str = None) -> str:
    """
    Formula: hash_id = SHA256( f"{date_iso}_{amount:.2f}_{normalized_description}_{ref_id}" )
    If ref_id is None, it falls back to the old formula (for backward compatibility or missing refs).
    """
    normalized_desc = normalize_description(description)
    # UPDATED: Use actual amount (preserving sign) so +100 and -100 are different
    amount_str = f"{float(amount):.2f}"
    
    # Using underscore as standard separator
    if ref_id:
        raw_string = f"{date_iso}_{amount_str}_{normalized_desc}_{ref_id}"
    else:
        raw_string = f"{date_iso}_{amount_str}_{normalized_desc}"
        
    return hashlib.sha256(raw_string.encode('utf-8')).hexdigest()

def check_transaction_exists(transaction: dict) -> bool:
    """
    Checks if a transaction already exists in Firestore using its hash_id.
    Returns True if exists, False otherwise.
    """
    db = get_db()
    hash_id = generate_hash_id(
        transaction['date'],
        transaction['amount'],
        transaction['description'],
        transaction.get('ref_id')
    )
    doc_ref = db.collection('transactions').document(hash_id)
    # Use get() with field_paths=[] to make it cheaper (metadata only check ideally, but Firestore get() reads 1 doc)
    # valid way to check existence
    doc = doc_ref.get() 
    return doc.exists

def _clear_transaction_cache():
    """Clear cached transaction data after mutations."""
    get_all_transactions.clear()
    get_transactions_by_range.clear()

def add_transaction(transaction: dict) -> str:
    """
    Adds or updates transaction in Firestore.
    Returns 'added' if new, 'updated' if metadata changed, 'skipped' if identical.
    """
    # Generate Hash
    hash_id = generate_hash_id(
        transaction['date'],
        transaction['amount'],
        transaction['description'],
        transaction.get('ref_id')  # Pass optional reference ID
    )
    
    if MOCK_MODE:
        try:
            with open('mock_db.json', 'r') as f:
                data = json.load(f)
            
            existing = next((tx for tx in data if tx['_id'] == hash_id), None)
            
            if existing:
                new_uploaded_from = transaction.get('uploaded_from')
                if new_uploaded_from and existing.get('uploaded_from') != new_uploaded_from:
                    existing['uploaded_from'] = new_uploaded_from
                    with open('mock_db.json', 'w') as f:
                        json.dump(data, f, indent=4)
                    return 'updated'
                else:
                    return 'skipped'
            
            # Prepare data for new transaction
            new_tx = transaction.copy()
            new_tx['_id'] = hash_id
            if 'category' not in new_tx:
                new_tx['category'] = 'Uncategorized'
            new_tx['uploaded_at'] = datetime.now().isoformat()
            
            data.append(new_tx)
            with open('mock_db.json', 'w') as f:
                json.dump(data, f, indent=4)
            return 'added'
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return 'skipped'

    db = get_db()
    
    doc_ref = db.collection('transactions').document(hash_id)
    doc = doc_ref.get()
    
    if doc.exists:
        # Check if any fields need updating (enrichment)
        existing_data = doc.to_dict()
        updates = {}
        
        # Fields that can be enriched on existing transactions
        enrichable_fields = [
            'uploaded_from',
            'bank_category',      # סוג פעולה - bank's categorization
            'transaction_type',   # חיוב/זיכוי - debit/credit indicator
            'spender',            # Who made the transaction
        ]
        
        for field in enrichable_fields:
            new_val = transaction.get(field)
            existing_val = existing_data.get(field)
            
            # Update if new value exists and either:
            # 1. Existing value is missing/None, OR
            # 2. Field is 'uploaded_from' and values differ (existing behavior)
            if new_val and (existing_val is None or (field == 'uploaded_from' and existing_val != new_val)):
                updates[field] = new_val
        
        if updates:
            doc_ref.update(updates)
            _clear_transaction_cache()
            return 'updated'
        else:
            return 'skipped'
    
    # Prepare data for new transaction
    data = transaction.copy()
    data['_id'] = hash_id
    # Remove is_fixed field if present (legacy cleanup)
    data.pop('is_fixed', None)
    if 'category' not in data:
        data['category'] = 'Uncategorized'
        
    data['uploaded_at'] = firestore.SERVER_TIMESTAMP
    
    doc_ref.set(data)
    _clear_transaction_cache()
    return 'added'


def get_recent_transactions(limit=50):
    if MOCK_MODE:
        try:
            with open('mock_db.json', 'r') as f:
                data = json.load(f)
            return sorted(data, key=lambda x: x['date'], reverse=True)[:limit]
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return []
    db = get_db()
    docs = db.collection('transactions').order_by('date', direction=firestore.Query.DESCENDING).limit(limit).stream()
    return [d.to_dict() for d in docs]

@st.cache_data(ttl=60)
def get_all_transactions():
    """
    Fetches ALL transactions from the database.
    """
    if MOCK_MODE:
        try:
            with open('mock_db.json', 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return []

    db = get_db()
    docs = db.collection('transactions').stream()
    return [doc.to_dict() for doc in docs]

@st.cache_data(ttl=60)
def get_transactions_by_range(start_date: str, end_date: str):
    """
    Fetches transactions within a date range (inclusive).
    start_date and end_date should be strings in YYYY-MM-DD format.
    """
    if MOCK_MODE:
        try:
            with open('mock_db.json', 'r') as f:
                data = json.load(f)
            # Filter by date
            filtered = [
                tx for tx in data 
                if start_date <= tx['date'] <= end_date
            ]
            return filtered
        except Exception as e:
            print(f"Error reading mock_db.json: {e}")
            return []

    db = get_db()
    
    docs = db.collection('transactions') \
             .where('date', '>=', start_date) \
             .where('date', '<=', end_date) \
             .stream()
             
    return [doc.to_dict() for doc in docs]

def get_transactions_by_month(year: int, month: int):
    """
    Fetches transactions for a specific month and year.
    Now wraps get_transactions_by_range.
    """
    # Calculate start and end of the month
    start_date = f"{year}-{month:02d}-01"
    
    # Get last day of the month
    _, last_day = calendar.monthrange(year, month)
    end_date = f"{year}-{month:02d}-{last_day}"
    
    return get_transactions_by_range(start_date, end_date)

def update_transaction(transaction_id: str, updates: dict) -> bool:
    """
    Updates a specific transaction document in Firestore.
    """
    if MOCK_MODE:
        try:
            with open('mock_db.json', 'r') as f:
                data = json.load(f)
            for tx in data:
                if tx['_id'] == transaction_id:
                    tx.update(updates)
                    break
            with open('mock_db.json', 'w') as f:
                json.dump(data, f, indent=4)
            return True
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return False

    try:
        db = get_db()
        doc_ref = db.collection('transactions').document(transaction_id)
        doc_ref.update(updates)
        _clear_transaction_cache()
        return True
    except Exception as e:
        print(f"Error updating transaction {transaction_id}: {e}")
        return False

def get_uncategorized_transactions(limit=100):
    """
    Fetches raw transactions that need categorization.
    """
    if MOCK_MODE:
        try:
            with open('mock_db.json', 'r') as f:
                data = json.load(f)
            return [tx for tx in data if tx.get('category') == 'Uncategorized'][:limit]
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return []

    db = get_db()
    docs = db.collection('transactions') \
             .where('category', '==', 'Uncategorized') \
             .limit(limit) \
             .stream()
    return [doc.to_dict() for doc in docs]

def update_transaction_batch(updates_list: list) -> int:
    """
    Updates multiple transactions efficiently.
    updates_list: list of dicts, each must have '_id' and fields to update.
    Returns: count of successfully updated docs.
    """
    if MOCK_MODE:
        count = 0
        for update_data in updates_list:
            doc_id = update_data.get('_id')
            if not doc_id:
                continue
            clean_update = {k: v for k, v in update_data.items() if k != '_id'}
            if update_transaction(doc_id, clean_update):
                count += 1
        return count

    db = get_db()
    batch = db.batch()
    count = 0
    updated_count = 0
    
    for update_data in updates_list:
        doc_id = update_data.get('_id')
        if not doc_id:
            continue
            
        doc_ref = db.collection('transactions').document(doc_id)
        
        # Remove _id from the actual update payload
        clean_update = {k: v for k, v in update_data.items() if k != '_id'}
        batch.update(doc_ref, clean_update)
        count += 1
        
        # Firestore batch limit is 500
        if count >= 400:
            batch.commit()
            updated_count += count
            batch = db.batch()
            count = 0
            
    if count > 0:
        batch.commit()
        updated_count += count

    if updated_count > 0:
        _clear_transaction_cache()
    return updated_count
        
def delete_transaction(transaction_id: str) -> bool:
    """
    Deletes a specific transaction from Firestore.
    """
    if MOCK_MODE:
        try:
            with open('mock_db.json', 'r') as f:
                data = json.load(f)
            data = [tx for tx in data if tx['_id'] != transaction_id]
            with open('mock_db.json', 'w') as f:
                json.dump(data, f, indent=4)
            return True
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return False

    try:
        db = get_db()
        db.collection('transactions').document(transaction_id).delete()
        _clear_transaction_cache()
        return True
    except Exception as e:
        print(f"Error deleting transaction {transaction_id}: {e}")
        return False

def find_potential_duplicates():
    """
    Finds potential duplicates based on:
    1. Same Date
    2. Same Amount (or within 5% tolerance)
    3. Description Similarity > 60%
    4. Cross-source awareness (Bank + CC overlap)
    
    Returns a list of groups. Each group is a dict with:
    - 'transactions': list of duplicate transactions
    - 'confidence': float 0.0-1.0
    - 'reason': string explaining why flagged
    """
    if MOCK_MODE:
        try:
            with open('mock_db.json', 'r') as f:
                transactions = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return []
    else:
        db = get_db()
        docs = db.collection('transactions').stream()
        transactions = [doc.to_dict() for doc in docs]
    
    # Group by (date, abs(amount))
    grouped = {}
    for tx in transactions:
        amount = tx.get('amount', 0)
        key = (tx.get('date'), abs(amount))
        if key not in grouped:
            grouped[key] = []
        grouped[key].append(tx)
        
    potential_dupes = []
    
    for key, group in grouped.items():
        if len(group) < 2:
            continue
        
        # Check all pairs in the group
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                tx1, tx2 = group[i], group[j]
                
                # Check explicit ignore list
                if tx2['_id'] in tx1.get('not_duplicate_of', []) or \
                   tx1['_id'] in tx2.get('not_duplicate_of', []):
                    continue
                
                confidence, reason = calculate_duplicate_confidence(tx1, tx2)
                
                if confidence >= 0.6:
                    # Check if this pair belongs to existing group
                    existing_group = None
                    for pg in potential_dupes:
                        if tx1 in pg['transactions'] or tx2 in pg['transactions']:
                            existing_group = pg
                            break
                    
                    if existing_group:
                        if tx1 not in existing_group['transactions']:
                            existing_group['transactions'].append(tx1)
                        if tx2 not in existing_group['transactions']:
                            existing_group['transactions'].append(tx2)
                        if confidence > existing_group['confidence']:
                            existing_group['confidence'] = confidence
                            existing_group['reason'] = reason
                    else:
                        potential_dupes.append({
                            'transactions': [tx1, tx2],
                            'confidence': confidence,
                            'reason': reason
                        })
    
    potential_dupes.sort(key=lambda x: x['confidence'], reverse=True)
    return potential_dupes

def mark_as_not_duplicate(tx_ids: list[str]) -> bool:
    """
    Marks a list of transactions as explicitly NOT duplicates of each other.
    """
    if len(tx_ids) < 2: return True
    
    if MOCK_MODE:
        try:
            with open('mock_db.json', 'r') as f:
                data = json.load(f)
            
            id_set = set(tx_ids)
            for tx in data:
                if tx['_id'] in id_set:
                    others = list(id_set - {tx['_id']})
                    current = tx.get('not_duplicate_of', [])
                    tx['not_duplicate_of'] = list(set(current + others))
            
            with open('mock_db.json', 'w') as f:
                json.dump(data, f, indent=4)
            return True
        except Exception as e:
            print(f"Mock update failed: {e}")
            return False

    try:
        db = get_db()
        batch = db.batch()
        
        for tx_id in tx_ids:
            others = [oid for oid in tx_ids if oid != tx_id]
            ref = db.collection('transactions').document(tx_id)
            batch.update(ref, {"not_duplicate_of": firestore.ArrayUnion(others)})
        
        batch.commit()
        return True
    except Exception as e:
        print(f"Error marking not duplicates: {e}")
        return False



def calculate_duplicate_confidence(tx1: dict, tx2: dict) -> tuple:
    """
    Calculates confidence score (0.0-1.0) that two transactions are duplicates.
    Returns (confidence: float, reason: str).
    """
    score = 0.0
    reasons = []
    
    # 1. Same date: +30%
    if tx1.get('date') == tx2.get('date'):
        score += 0.30
        reasons.append("same date")
    
    # 2. Amount comparison
    amt1 = abs(float(tx1.get('amount', 0)))
    amt2 = abs(float(tx2.get('amount', 0)))
    
    if amt1 == amt2:
        score += 0.35
        reasons.append("exact amount")
    elif amt1 > 0 and abs(amt1 - amt2) / amt1 < 0.05:
        score += 0.25
        reasons.append("amount ~5%")
    
    # 3. Description similarity
    desc1 = normalize_description(tx1.get('description', ''))
    desc2 = normalize_description(tx2.get('description', ''))
    desc_sim = difflib.SequenceMatcher(None, desc1, desc2).ratio()
    
    if desc_sim > 0.8:
        score += 0.25
        reasons.append(f"desc {int(desc_sim*100)}%")
    elif desc_sim > 0.6:
        score += 0.15
        reasons.append(f"desc {int(desc_sim*100)}%")
    
    # 4. Cross-source bonus
    overlap_type = is_bank_cc_overlap(tx1, tx2)
    if overlap_type:
        score += 0.20
        reasons.append(overlap_type)
    
    # 5. Same spender
    if tx1.get('spender') == tx2.get('spender') and tx1.get('spender'):
        score += 0.05
        reasons.append("same owner")
    
    return (min(score, 1.0), "; ".join(reasons))


def is_bank_cc_overlap(tx1: dict, tx2: dict) -> str:
    """
    Checks if two transactions represent Bank + Credit Card overlap.
    Returns descriptive string if true, None otherwise.
    """
    bank_sources = ['OneZero_Table', 'OneZero_Excel']
    cc_sources = ['Isracard', 'Max_Card', 'Isracard_PDF_Fixed']
    
    src1 = tx1.get('source_file', '')
    src2 = tx2.get('source_file', '')
    cat1 = tx1.get('category', '')
    cat2 = tx2.get('category', '')
    
    # Bank CC payoff vs CC statement
    if src1 in bank_sources and src2 in cc_sources:
        if cat1 == 'Credit Card Payoff':
            return "bank↔cc overlap"
    elif src2 in bank_sources and src1 in cc_sources:
        if cat2 == 'Credit Card Payoff':
            return "bank↔cc overlap"
    
    # Same source, different formats
    if src1 in bank_sources and src2 in bank_sources and src1 != src2:
        return "multi-format"
    if src1 in cc_sources and src2 in cc_sources and src1 != src2:
        return "multi-format"
    
    return None


def check_for_near_duplicates(transaction: dict, threshold: float = 0.7) -> list:
    """
    Checks if a transaction has near-duplicates already in the database.
    Used BEFORE inserting to warn the user.
    
    Returns: [{'existing': tx_dict, 'confidence': float, 'reason': str}, ...]
    """
    date = transaction.get('date')
    if not date:
        return []
    
    try:
        dt = datetime.strptime(date, '%Y-%m-%d')
        start = (dt - timedelta(days=3)).strftime('%Y-%m-%d')
        end = (dt + timedelta(days=3)).strftime('%Y-%m-%d')
    except (ValueError, TypeError):
        return []
    
    existing_txs = get_transactions_by_range(start, end)
    
    matches = []
    for existing in existing_txs:
        confidence, reason = calculate_duplicate_confidence(transaction, existing)
        if confidence >= threshold:
            matches.append({
                'existing': existing,
                'confidence': confidence,
                'reason': reason
            })
    
    matches.sort(key=lambda x: x['confidence'], reverse=True)
    return matches


def mark_as_duplicate(transaction_id: str, duplicate_of_id: str) -> bool:
    """
    Marks a transaction as a duplicate of another.
    """
    return update_transaction(transaction_id, {
        'duplicate_of': duplicate_of_id,
        'is_duplicate': True
    })

def delete_all_transactions():
    """
    Deletes ALL documents in the transactions collection.
    Warning: This cannot be undone.
    """
    if MOCK_MODE:
        try:
            with open('mock_db.json', 'w') as f:
                json.dump([], f)
            return 0 # Or actual count if needed
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return 0

    db = get_db()
    docs = db.collection('transactions').stream()
    count = 0
    batch = db.batch()
    
    for doc in docs:
        batch.delete(doc.reference)
        count += 1
        
        if count % 400 == 0:
            batch.commit()
            batch = db.batch()
            
    if count > 0:
        batch.commit()

    _clear_transaction_cache()
    return count

def get_uncategorized_count():
    """
    Returns the total number of uncategorized transactions.
    """
    if MOCK_MODE:
        try:
            with open('mock_db.json', 'r') as f:
                data = json.load(f)
            return sum(1 for tx in data if tx.get('category') == 'Uncategorized')
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return 0

    db = get_db()
    try:
        # standard firestore count query
        query = db.collection('transactions').where('category', '==', 'Uncategorized')
        count_query = query.count()
        results = count_query.get()
        return results[0][0].value
    except Exception:
        # Fallback for older SDKs or if aggregation fails: manual count (slower but safe)
        try:
             docs = db.collection('transactions').where('category', '==', 'Uncategorized').stream()
             return sum(1 for _ in docs)
        except Exception:
             return 0

def get_budget() -> float:
    """
    Retrieves the monthly budget limit.
    """
    if MOCK_MODE:
        try:
            with open('mock_settings.json', 'r') as f:
                settings = json.load(f)
            return settings.get('monthly_budget', 0.0)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return 0.0

    db = get_db()
    try:
        doc = db.collection('settings').document('global').get()
        if doc.exists:
            return doc.to_dict().get('monthly_budget', 0.0)
        return 0.0
    except Exception:
        return 0.0

def set_budget(amount: float) -> bool:
    """
    Sets the monthly budget limit.
    """
    if MOCK_MODE:
        try:
            settings = {}
            try:
                with open('mock_settings.json', 'r') as f:
                    settings = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError, OSError):
                pass # File doesn't exist yet
            
            settings['monthly_budget'] = float(amount)
            
            with open('mock_settings.json', 'w') as f:
                json.dump(settings, f, indent=4)
            return True
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return False

    try:
        db = get_db()
        db.collection('settings').document('global').set({'monthly_budget': float(amount)}, merge=True)
        return True
    except Exception as e:
        print(f"Error setting budget: {e}")
        return False