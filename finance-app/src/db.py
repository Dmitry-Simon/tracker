import hashlib
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

def generate_hash_id(date_iso: str, amount: float, description: str) -> str:
    """
    Formula: hash_id = SHA256( f"{date_iso}_{abs(amount):.2f}_{normalized_description}" )
    """
    normalized_desc = normalize_description(description)
    abs_amount_str = f"{abs(amount):.2f}"
    
    raw_string = f"{date_iso}_{abs_amount_str}_{normalized_desc}"
    return hashlib.sha256(raw_string.encode('utf-8')).hexdigest()

def add_transaction(transaction: dict) -> bool:
    """
    Adds transaction to Firestore if it doesn't exist.
    Returns True if added, False if skipped (duplicate).
    """
    db = get_db()
    
    # Generate Hash
    hash_id = generate_hash_id(
        transaction['date'],
        transaction['amount'],
        transaction['description']
    )
    
    doc_ref = db.collection('transactions').document(hash_id)
    doc = doc_ref.get()
    
    if doc.exists:
        return False
    
    # Prepare data
    data = transaction.copy()
    data['_id'] = hash_id
    data['is_fixed'] = data.get('is_fixed', False) # Default
    data['uploaded_at'] = firestore.SERVER_TIMESTAMP
    
    doc_ref.set(data)
    return True

def get_recent_transactions(limit=50):
    db = get_db()
    docs = db.collection('transactions').order_by('date', direction=firestore.Query.DESCENDING).limit(limit).stream()
    return [d.to_dict() for d in docs]
