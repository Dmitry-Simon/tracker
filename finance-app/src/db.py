import hashlib
import calendar
import firebase_admin
from firebase_admin import credentials, firestore
import streamlit as st
import json
import re

# Initialize Firebase app (singleton)
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
        # Fallback or explicit path if needed (though constraint said via secrets usually)
        print("Warning: No secrets found for Firebase.")

def get_db():
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

def add_transaction(transaction: dict) -> str:
    """
    Adds or updates transaction in Firestore.
    Returns 'added' if new, 'updated' if metadata changed, 'skipped' if identical.
    """
    db = get_db()
    
    # Generate Hash
    hash_id = generate_hash_id(
        transaction['date'],
        transaction['amount'],
        transaction['description'],
        transaction.get('ref_id')  # Pass optional reference ID
    )
    
    doc_ref = db.collection('transactions').document(hash_id)
    doc = doc_ref.get()
    
    if doc.exists:
        # Check if uploaded_from needs updating
        existing_data = doc.to_dict()
        new_uploaded_from = transaction.get('uploaded_from')
        
        if new_uploaded_from and existing_data.get('uploaded_from') != new_uploaded_from:
            # Update only the uploaded_from field
            doc_ref.update({'uploaded_from': new_uploaded_from})
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
    return 'added'


def get_recent_transactions(limit=50):
    db = get_db()
    docs = db.collection('transactions').order_by('date', direction=firestore.Query.DESCENDING).limit(limit).stream()
    return [d.to_dict() for d in docs]

def get_transactions_by_range(start_date: str, end_date: str):
    """
    Fetches transactions within a date range (inclusive).
    start_date and end_date should be strings in YYYY-MM-DD format.
    """
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
    try:
        db = get_db()
        doc_ref = db.collection('transactions').document(transaction_id)
        doc_ref.update(updates)
        return True
    except Exception as e:
        print(f"Error updating transaction {transaction_id}: {e}")
        return False

def get_uncategorized_transactions(limit=100):
    """
    Fetches raw transactions that need categorization.
    """
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
        
    return updated_count
        
from datetime import datetime, timedelta
import difflib

def delete_transaction(transaction_id: str) -> bool:
    """
    Deletes a specific transaction from Firestore.
    """
    try:
        db = get_db()
        db.collection('transactions').document(transaction_id).delete()
        return True
    except Exception as e:
        print(f"Error deleting transaction {transaction_id}: {e}")
        return False

def find_potential_duplicates():
    """
    Finds potential duplicates based on:
    1. Same Date
    2. Same Amount
    3. Similarity > 0.6 in Description
    
    Returns a list of groups. Each group is a list of duplicate transactions.
    """
    db = get_db()
    
    # Fetch ALL transactions (no date filter)
    docs = db.collection('transactions').stream()
             
    transactions = [doc.to_dict() for doc in docs]
    
    # Group by (date, abs(amount))
    # Key: (date, abs(amount)), Value: list of txs
    grouped = {}
    for tx in transactions:
        amount = tx.get('amount', 0)
        # Use abs(amount) to catch +50 vs -50
        key = (tx.get('date'), abs(amount))
        
        if key not in grouped:
            grouped[key] = []
        grouped[key].append(tx)
        
    potential_dupes = []
    
    for key, group in grouped.items():
        if len(group) < 2:
            continue
            
        # Check descriptions
        # Simple N^2 comparison for small groups (usually 2-3 items)
        # We assume if A matches B, they are duplicates.
        # We return the whole group if any similarity is found to let the user decide.
        
        has_similarity = False
        descriptions = [t.get('description', '') for t in group]
        
        for i in range(len(descriptions)):
            for j in range(i + 1, len(descriptions)):
                ratio = difflib.SequenceMatcher(None, descriptions[i], descriptions[j]).ratio()
                if ratio > 0.6: # 60% similarity threshold
                    has_similarity = True
                    break
            if has_similarity:
                break
        
        if has_similarity:
            potential_dupes.append(group)
            
    return potential_dupes

def delete_all_transactions():
    """
    Deletes ALL documents in the transactions collection.
    Warning: This cannot be undone.
    """
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
        
    return count

def get_uncategorized_count():
    """
    Returns the total number of uncategorized transactions.
    """
    db = get_db()
    try:
        # standard firestore count query
        query = db.collection('transactions').where('category', '==', 'Uncategorized')
        count_query = query.count()
        results = count_query.get()
        return results[0][0].value
    except:
        # Fallback for older SDKs or if aggregation fails: manual count (slower but safe)
        try:
             docs = db.collection('transactions').where('category', '==', 'Uncategorized').stream()
             return sum(1 for _ in docs)
        except:
             return 0