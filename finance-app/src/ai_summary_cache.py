import hashlib
import json
from datetime import datetime
from src import db

def get_data_hash(transactions):
    """
    Generates a unique hash for a set of transactions to detect changes.
    """
    if not transactions:
        return "empty"
    
    # Sort by ID and include amount/category to detect any changes
    tx_data = sorted([
        f"{t.get('_id', '')}_{t.get('amount', 0)}_{t.get('category', '')}" 
        for t in transactions
    ])
    return hashlib.sha256("".join(tx_data).encode()).hexdigest()

def get_cached_summary(period_key, data_hash):
    """
    Retrieves a cached AI summary from Firestore if the data hash matches.
    """
    client = db.get_db()
    if not client:
        return None
        
    doc_ref = client.collection('ai_summaries').document(period_key)
    doc = doc_ref.get()
    
    if doc.exists:
        cache_data = doc.to_dict()
        if cache_data.get('data_hash') == data_hash:
            return cache_data
            
    return None

def save_summary_to_cache(period_key, data_hash, summary_data):
    """
    Saves an AI summary to Firestore cache.
    """
    client = db.get_db()
    if not client:
        return
        
    cache_data = {
        'summary_data': summary_data,
        'data_hash': data_hash,
        'generated_at': datetime.now().isoformat()
    }
    
    client.collection('ai_summaries').document(period_key).set(cache_data)

def clear_cache(period_key):
    """
    Removes a cached summary to force regeneration.
    """
    client = db.get_db()
    if not client:
        return
        
    client.collection('ai_summaries').document(period_key).delete()
