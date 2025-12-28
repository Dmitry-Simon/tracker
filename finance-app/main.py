import streamlit as st
import pandas as pd
from src import auth, parsers, db, ai

# Page Config
st.set_page_config(
    page_title="FinTracker IL",
    page_icon="💰",
    layout="wide"
)

# Authentication
if not auth.require_auth():
    st.stop()

st.title("💰 Israeli Finance Tracker")

# Sidebar - Upload
with st.sidebar:
    st.header("Upload Files")
    uploaded_files = st.file_uploader(
        "Choose files (PDF, CSV, XLSX)", 
        accept_multiple_files=True,
        type=['pdf', 'csv', 'xlsx']
    )
    
    process_btn = st.button("Process Files", type="primary")

# Main Area
if process_btn and uploaded_files:
    total_processed = 0
    total_added = 0
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    all_transactions = []
    
    # 1. Parsing Phase
    for i, file_obj in enumerate(uploaded_files):
        status_text.text(f"Parsing {file_obj.name}...")
        
        # Determine parser
        txs = parsers.detect_and_parse(file_obj, file_obj.name)
        
        if txs:
            for tx in txs:
                tx['source_file'] = file_obj.name
            all_transactions.extend(txs)
            st.toast(f"Parsed {len(txs)} transactions from {file_obj.name}")
        else:
            st.error(f"Could not parse {file_obj.name}")
            
        progress_bar.progress((i + 1) / len(uploaded_files) * 0.3) # Allocated 30% for parsing

    # 2. Deduplication & AI Phase
    if all_transactions:
        status_text.text(f"Processing {len(all_transactions)} transactions...")
        
        new_transactions = []
        
        # Check Deduplication
        # We can optimize this by batch checking, but for now simple iteration
        for i, tx in enumerate(all_transactions):
            # Optimistic check? DB check happens in add_transaction, 
            # but we want to know if it's new BEFORE AI cost.
            # db.add_transaction does the check and add atomically-ish.
            # But we want to categorize ONLY if new.
            # Modify db.add_transaction to support "check_only"? 
            # Or just duplicate logic here?
            # Let's add a `exists()` check in db module ideally, 
            # but currently `add_transaction` does both.
            # We'll update logic: Check existence -> If new -> AI -> Add.
            
            # Since `add_transaction` is implemented to check then add,
            # we can't easily inject AI in between without modifying it.
            # Let's modify the flow:
            # 1. Generate Hash
            # 2. Check DB
            # 3. If missing -> AI -> Add
            
            # Using the logic available in db.py:
            # We will rely on `db.generate_hash_id` exposed? It is.
            
            hash_id = db.generate_hash_id(tx['date'], tx['amount'], tx['description'])
            doc_ref = db.get_db().collection('transactions').document(hash_id)
            doc = doc_ref.get()
            
            if not doc.exists:
                # categorize
                status_text.text(f"Categorizing: {tx['description']}")
                cat_result = ai.categorize_transaction(tx['description'], tx['amount'])
                tx.update(cat_result)
                
                # Add
                db.add_transaction(tx) # This will check again, harmless but slightly inefficient.
                new_transactions.append(tx)
                total_added += 1
            
            # Update progress
            # map remaining 70% range
            prog = 0.3 + ((i + 1) / len(all_transactions) * 0.7)
            progress_bar.progress(prog)

        st.success(f"Processing Complete! Added {total_added} new transactions.")
        
        if new_transactions:
            st.dataframe(pd.DataFrame(new_transactions))
    else:
        st.warning("No transactions found in uploaded files.")

# Dashboard View
st.divider()
st.subheader("Recent Transactions")

recent_txs = db.get_recent_transactions(limit=10)
if recent_txs:
    df_recent = pd.DataFrame(recent_txs)
    # Reorder columns
    cols = ['date', 'description', 'amount', 'category', 'sub_category', 'source', 'source_file']
    # Filter only existing cols
    cols = [c for c in cols if c in df_recent.columns]
    st.dataframe(df_recent[cols], use_container_width=True)
    
    # Simple metric
    total_spent = df_recent[df_recent['amount'] < 0]['amount'].sum()
    st.metric("Total Expenses (Last 50)", f"{total_spent:.2f} ILS")
else:
    st.info("No transactions in database.")
