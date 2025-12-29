import streamlit as st
import pandas as pd
from src import parsers, db
from src.ui import styles

def render_upload():
    """
    Renders the Upload Data Tab.
    """
    st.markdown("### 📤 Data Ingestion")
    
    # --- Instructions Panel ---
    with styles.card():
        st.subheader("💡 Tips for Best Results")
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown("### 📄 PDFs\nBest for card statements (Isracard, Max). Supports RTL/Hebrew text detection.")
        with c2:
            st.markdown("### 📊 Excel/CSV\nPreferred for Bank statements (One Zero, Max Finance). Faster processing.")
        with c3:
            st.markdown("### ✨ Sign Magic\nWe automatically detect refunds and adjust signs (+/-) for accurate tracking.")

    styles.divider()

    # --- Uploader Section ---
    with styles.card():
        uploaded_files = st.file_uploader(
            "Drop your bank/card statements here", 
            type=['pdf', 'csv', 'xlsx', 'xls'],
            accept_multiple_files=True,
            help="You can drag and drop multiple files at once"
        )

    if uploaded_files:
        st.subheader(f"⚙️ Processing {len(uploaded_files)} File{'s' if len(uploaded_files)>1 else ''}")
        
        total_added = 0
        total_updated = 0
        total_skipped = 0
        file_results = []
        
        overall_progress = st.progress(0, text="Starting ingestion...")
        
        for file_idx, uploaded_file in enumerate(uploaded_files):
            with st.expander(f"Processing: {uploaded_file.name}", expanded=True):
                try:
                    new_transactions = parsers.detect_and_parse(uploaded_file, uploaded_file.name)
                    
                    if not new_transactions:
                        st.warning("⚠️ No transactions detected in this file.")
                        file_results.append({'file': uploaded_file.name, 'status': '⚠️ Empty'})
                    else:
                        added, updated, skipped = 0, 0, 0
                        file_prog = st.progress(0)
                        
                        for i, tx in enumerate(new_transactions):
                            status = db.add_transaction(tx)
                            if status == 'added': added += 1
                            elif status == 'updated': updated += 1
                            else: skipped += 1
                            file_prog.progress((i + 1) / len(new_transactions))
                        
                        st.success(f"✓ {len(new_transactions)} transactions processed.")
                        total_added += added
                        total_updated += updated
                        total_skipped += skipped
                        file_results.append({
                            'file': uploaded_file.name, 
                            'status': '✅ Success',
                            'added': added,
                            'updated': updated,
                            'skipped': skipped
                        })
                except Exception as e:
                    st.error(f"❌ Failed: {str(e)}")
                    file_results.append({'file': uploaded_file.name, 'status': f'❌ Error: {str(e)[:30]}'})
            
            overall_progress.progress((file_idx + 1) / len(uploaded_files), text=f"Finished {file_idx + 1} / {len(uploaded_files)}")
        
        # --- Final Summary ---
        st.divider()
        with styles.card():
            st.subheader("📊 Session Summary")
            s1, s2, s3, s4 = st.columns(4)
            s1.metric("Files", len(uploaded_files))
            s2.metric("New", total_added)
            s3.metric("Updated", total_updated)
            s4.metric("Skipped", total_skipped)
            
            if file_results:
                st.dataframe(pd.DataFrame(file_results), use_container_width=True, hide_index=True)

