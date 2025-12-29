import streamlit as st
import pandas as pd
from src import parsers, db

def render_upload():
    """
    Renders the Upload Data Tab.
    """
    st.header("Upload Statements")
    
    # Bulk upload support
    uploaded_files = st.file_uploader(
        "Choose files (PDF, CSV, Excel)", 
        type=['pdf', 'csv', 'xlsx', 'xls'],
        accept_multiple_files=True,
        help="You can select multiple files at once for bulk upload"
    )

    if uploaded_files:
        st.info(f"Processing {len(uploaded_files)} file(s)...")
        
        # Statistics tracking
        total_added = 0
        total_skipped = 0
        file_results = []
        
        # Overall progress
        overall_progress = st.progress(0)
        st.text("Overall progress:")
        
        for file_idx, uploaded_file in enumerate(uploaded_files):
            st.divider()
            st.subheader(f"📄 {uploaded_file.name}")
            
            try:
                # Detect and Parse
                new_transactions = parsers.detect_and_parse(uploaded_file, uploaded_file.name)
                
                if not new_transactions:
                    st.warning(f"⚠️ No transactions found or file format not recognized.")
                    file_results.append({
                        'file': uploaded_file.name,
                        'status': '⚠️ No Data',
                        'added': 0,
                        'skipped': 0
                    })
                else:
                    st.success(f"✓ Found {len(new_transactions)} transactions")
                    
                    # Add to DB
                    added_count = 0
                    skipped_count = 0
                    
                    # Progress for this file
                    file_progress = st.progress(0)
                    
                    for i, tx in enumerate(new_transactions):
                        # Placeholder for Phase 2: AI Categorization would happen here
                        # tx = enrich_transaction_with_ai(tx) 
                        
                        success = db.add_transaction(tx)
                        if success:
                            added_count += 1
                        else:
                            skipped_count += 1
                        
                        # Update progress bar
                        file_progress.progress((i + 1) / len(new_transactions))
                    
                    # Results for this file
                    col1, col2 = st.columns(2)
                    with col1:
                        st.metric("Added", added_count, delta=None)
                    with col2:
                        st.metric("Skipped (Duplicates)", skipped_count, delta=None)
                    
                    total_added += added_count
                    total_skipped += skipped_count
                    
                    file_results.append({
                        'file': uploaded_file.name,
                        'status': '✓ Complete',
                        'added': added_count,
                        'skipped': skipped_count
                    })
                    
            except Exception as e:
                st.error(f"❌ Error processing file: {str(e)}")
                file_results.append({
                    'file': uploaded_file.name,
                    'status': f'❌ Error: {str(e)[:50]}',
                    'added': 0,
                    'skipped': 0
                })
            
            # Update overall progress
            overall_progress.progress((file_idx + 1) / len(uploaded_files))
        
        # Final Summary
        st.divider()
        st.header("📊 Upload Summary")
        
        summary_col1, summary_col2, summary_col3 = st.columns(3)
        with summary_col1:
            st.metric("Files Processed", len(uploaded_files))
        with summary_col2:
            st.metric("Total Added", total_added)
        with summary_col3:
            st.metric("Total Skipped", total_skipped)
        
        # Detailed results table
        if file_results:
            st.subheader("Detailed Results")
            results_df = pd.DataFrame(file_results)
            st.dataframe(results_df, use_container_width=True, hide_index=True)
