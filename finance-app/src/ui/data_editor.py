import streamlit as st
import pandas as pd
import time
from src import db
from src.ui import styles

def render_data_editor(filters):
    """
    Renders the Data Editor Tab.
    Args:
        filters (dict): Output from sidebar.render_sidebar()
    """
    start_date = filters['start_date']
    end_date = filters['end_date']
    period_label = filters['period_label']
    selected_year = filters['selected_year']
    month_str = str(filters.get('selected_month', 'all'))

    st.markdown(f"### ✍️ {period_label}")
    
    # --- 1. Manual Categorizer (Global) ---
    # No card wrapping here to avoid the "bulky grey bar" look when closed
    with st.expander("🛠️ Manual Categorizer (Batch Update Unknowns)", expanded=False):
        st.info("Finds 'Uncategorized' transactions from the ENTIRE database.")
        unknown_txs = db.get_uncategorized_transactions(limit=1000)
        
        if not unknown_txs:
            st.success("🎉 All clear! No uncategorized transactions.")
        else:
            df_unknown = pd.DataFrame(unknown_txs)
            df_unknown['spender'] = df_unknown.get('spender', 'Joint').fillna("Joint")
            cols_unk = ['category', 'description', 'amount', 'date', 'spender', '_id']
            df_unknown_edit = df_unknown[[c for c in cols_unk if c in df_unknown.columns]].copy()
            
            edited_unknown = st.data_editor(
                df_unknown_edit,
                key="editor_unknowns",
                use_container_width=True,
                disabled=['description', 'amount', 'date', '_id'],
                column_config={
                    "_id": st.column_config.TextColumn("ID", disabled=True),
                    "amount": st.column_config.NumberColumn("Amount", format="₪%.2f"),
                    "category": st.column_config.SelectboxColumn(
                        "Category",
                        options=[
                            "Food", "Transport", "Shopping", "Bills", 
                            "Salary", "Health", "Entertainment", 
                            "Transfer", "Rent/Mortgage", "Uncategorized", "Groceries", "Restaurants", "Credit Card Payoff", "Other"
                        ],
                        required=True
                    )
                }
            )
            
            if st.button("💾 Save Bulk Categorization", type="primary"):
                changes_unk = st.session_state["editor_unknowns"].get("edited_rows", {})
                if changes_unk:
                    upd_count = 0
                    for idx, updates in changes_unk.items():
                        row_id = df_unknown_edit.iloc[idx]['_id']
                        if db.update_transaction(row_id, updates):
                            upd_count += 1
                    if upd_count > 0:
                        st.success(f"Updated {upd_count} transactions!")
                        time.sleep(1)
                        st.rerun()

    # --- 2. Filtered Data Editor (The Main Table) ---
    styles.divider()
    edit_txs = db.get_transactions_by_range(start_date, end_date)
    
    if not edit_txs:
        st.info("No data available for this period.")
    else:
        df_edit = pd.DataFrame(edit_txs)
        df_edit['spender'] = df_edit.get('spender', 'Joint').fillna("Joint")
        
        if '_id' not in df_edit.columns:
            st.error("Transaction IDs missing. Cannot edit.")
        else:
            cols_order = ['date', 'amount', 'spender', 'category', 'description', 'source_file', 'uploaded_from', '_id']
            cols_order = [c for c in cols_order if c in df_edit.columns]
            
            with styles.card():
                st.subheader(f"Transactions for {period_label}")
                edited_df = st.data_editor(
                    df_edit[cols_order],
                    key="data_editor",
                    use_container_width=True,
                    num_rows="fixed",
                    disabled=['date', 'amount', '_id', 'source_file', 'uploaded_from'],
                    column_config={
                        "_id": st.column_config.TextColumn("ID", width="small"),
                        "amount": st.column_config.NumberColumn("Amount", format="₪%.2f", width="small"),
                        "date": st.column_config.DatetimeColumn("Date", format="YYYY-MM-DD", width="small"),
                        "source_file": st.column_config.TextColumn("Source", width="small"),
                        "uploaded_from": st.column_config.TextColumn("File", width="small"),
                        "description": st.column_config.TextColumn("Description", width="large"),
                        "spender": st.column_config.SelectboxColumn("Owner", options=["Joint", "Dmitry", "Yaara"], required=True)
                    },
                    hide_index=True
                )
                
                col_actions1, col_actions2 = st.columns([1, 4])
                with col_actions1:
                    if st.button("💾 Save Table Changes", type="primary"):
                        changes = st.session_state["data_editor"].get("edited_rows", {})
                        if changes:
                            updated_count = 0
                            for idx, updates in changes.items():
                                row_id = df_edit.iloc[idx]['_id']
                                if db.update_transaction(row_id, updates):
                                    updated_count += 1
                            if updated_count > 0:
                                st.success(f"Updated {updated_count} rows!")
                                st.rerun()
                with col_actions2:
                    csv = edited_df.to_csv(index=False).encode('utf-8')
                    st.download_button("⬇️ Download CSV", csv, f"tracker_{selected_year}_{month_str}.csv", "text/csv")

    # --- 3. AI Assistant Section (Moved to Bottom) ---
    styles.divider()
    from src import ai
    if "autopilot_running" not in st.session_state:
        st.session_state["autopilot_running"] = False
    
    with styles.card():
        st.subheader("🤖 AI Financial Genius")
        total_uncategorized = db.get_uncategorized_count()
        
        if total_uncategorized == 0:
            st.success("🎉 All transactions are categorized. AI is resting!")
        else:
            col_ai1, col_ai2 = st.columns([2, 1])
            with col_ai1:
                st.markdown(f"**{total_uncategorized}** pending items.")
                st.progress(0, text="Ready...")
            with col_ai2:
                st.metric("Pending", total_uncategorized, delta_color="inverse")
            
            st.divider() # Internal divider within card is fine as st.divider, but let's use premium?
            # Actually st.divider inside a card is okay, but I'll use ours.
            styles.divider()
            c1, c2 = st.columns(2)
            with c1:
                if st.button("✨ Batch Process (50)"):
                    with st.spinner("AI Categorizing..."):
                        count, err = ai.enrich_uncategorized_data()
                        if not err:
                            st.success(f"Processed {count}!"); time.sleep(1); st.rerun()
            with c2:
                if st.button("🚀 Run Autopilot", type="primary"):
                    st.session_state["autopilot_running"] = True

            if st.session_state["autopilot_running"]:
                progress_bar = st.progress(0)
                status_text = st.empty()
                processed = 0
                while total_uncategorized > 0:
                    pct = min(1.0, processed / total_uncategorized) if total_uncategorized > 0 else 0
                    progress_bar.progress(pct, f"Processed {processed}...")
                    count, err = ai.enrich_uncategorized_data()
                    if err or count == 0: break
                    processed += count
                    total_uncategorized = db.get_uncategorized_count()
                    time.sleep(0.5)
                st.balloons()
                st.session_state["autopilot_running"] = False
                st.rerun()

    # --- 4. Danger Zone (Last) ---
    styles.divider()
    with st.container():
        st.markdown("### 🚨 Danger Zone")
        
        # Deduplication
        with st.expander("🧹 Deduplication Tool (Clean Duplicates)", expanded=False):
            if "dupe_groups" not in st.session_state:
                st.session_state["dupe_groups"] = None
            if st.button("🔍 Scan for Duplicates"):
                st.session_state["dupe_groups"] = db.find_potential_duplicates()
            
            if st.session_state["dupe_groups"]:
                dupe_groups = st.session_state["dupe_groups"]
                st.warning(f"Found {len(dupe_groups)} potential duplicate sets.")
                for i, group in enumerate(dupe_groups):
                    if len(group) < 2: continue
                    descs = [tx.get('description', '').strip() for tx in group]
                    is_collision = len(set(descs)) > 1
                    
                    st.markdown(f"**Group {i+1}:** {group[0]['date']} | ₪{group[0]['amount']}")
                    if is_collision:
                        st.error("🚨 HASH COLLISION detected. Review carefully.")
                    
                    if not is_collision:
                        if st.button(f"🗑️ Delete All {len(group)}", key=f"bulk_{i}"):
                            for tx in group: db.delete_transaction(tx['_id'])
                            st.rerun()
                    
                    cols = st.columns(len(group))
                    for idx, tx in enumerate(group):
                        with cols[idx]:
                            st.info(f"**{tx['description']}**\n\n👤 {tx.get('spender')}\n📄 {tx.get('source_file')}")
                            if st.button("🗑️ Delete Single", key=f"ds_{tx['_id']}"):
                                db.delete_transaction(tx['_id']); st.rerun()
                if st.button("Clear Results"):
                    st.session_state["dupe_groups"] = None; st.rerun()

        # Reset
        with st.expander("🗑️ Reset Database (Delete All Data)"):
            st.error("This will permanently wipe all transactions!")
            if st.button("🔥 WIPE DATABASE", type="primary"):
                db.delete_all_transactions()
                st.success("Wiped!"); time.sleep(1); st.rerun()
