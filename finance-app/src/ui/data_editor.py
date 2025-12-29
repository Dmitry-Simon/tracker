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
    
    # We need a safe string for filename, handling potential None for selected_month
    month_str = str(filters.get('selected_month', 'all'))

    st.header(f"Edit Data: {period_label}")
    
    # --- Manual Categorizer (Global) ---
    with styles.card():
        with st.expander("🛠️ Manual Categorizer (All 'Unknowns' in Database)", expanded=False):
            st.info("This tool fetches 'Uncategorized' transactions from the ENTIRE database (ignoring the date filter above).")
            
            # Fetch up to 1000 uncategorized
            unknown_txs = db.get_uncategorized_transactions(limit=1000)
            
            if not unknown_txs:
                st.success("🎉 No uncategorized transactions found! Great job.")
            else:
                st.write(f"Found **{len(unknown_txs)}** uncategorized transactions.")
                
                df_unknown = pd.DataFrame(unknown_txs)
                
                if 'spender' not in df_unknown.columns:
                    df_unknown['spender'] = "Joint"
                else:
                    df_unknown['spender'] = df_unknown['spender'].fillna("Joint")
                
                # Ensure columns exist before selecting
                cols_unk = ['category', 'description', 'amount', 'date', 'spender', '_id']
                cols_unk = [c for c in cols_unk if c in df_unknown.columns]
                
                df_unknown_edit = df_unknown[cols_unk].copy()
                
                edited_unknown = st.data_editor(
                    df_unknown_edit,
                    key="editor_unknowns",
                    use_container_width=True,
                    num_rows="fixed",
                    disabled=['description', 'amount', 'date', '_id'],
                    column_config={
                        "_id": st.column_config.TextColumn("ID", disabled=True),
                        "amount": st.column_config.NumberColumn("Amount", format="₪%.2f"),
                        "spender": st.column_config.SelectboxColumn("Spender", options=["Joint", "Dmitry", "Yaara"]),
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
                
                if st.button("💾 Save Categorization Updates", type="primary"):
                    changes_unk = st.session_state["editor_unknowns"].get("edited_rows", {})
                    
                    if not changes_unk:
                        st.warning("No changes made.")
                    else:
                        upd_count = 0
                        for idx, updates in changes_unk.items():
                            # Map displayed index back to dataframe ID
                            row_id = df_unknown_edit.iloc[idx]['_id']
                            if db.update_transaction(row_id, updates):
                                upd_count += 1
                                
                        if upd_count > 0:
                            st.success(f"Updated {upd_count} transactions!")
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error("Failed to update.")
    
    st.divider()

    # Reload data for freshness
    edit_txs = db.get_transactions_by_range(start_date, end_date)
    
    if not edit_txs:
        st.info("No data available to edit.")
    else:
        df_edit = pd.DataFrame(edit_txs)
        
        # Ensure 'spender' exists for legacy records
        if 'spender' not in df_edit.columns:
            df_edit['spender'] = "Joint"
        else:
            df_edit['spender'] = df_edit['spender'].fillna("Joint")
        
        # Ensure ID is available (hidden in editor but present)
        if '_id' not in df_edit.columns:
            st.error("Transaction IDs missing. Cannot edit.")
        else:
            # Config for editor
            # Reorder for better UX
            cols_order = ['date', 'amount', 'spender', 'category', 'description', 'is_fixed', 'sub_category', '_id']
            # Filter cols that exist
            cols_order = [c for c in cols_order if c in df_edit.columns]
            
            # Show the editor
            edited_df = st.data_editor(
                df_edit[cols_order],
                key="data_editor",
                use_container_width=True,
                num_rows="fixed", # No adding/deleting rows
                disabled=['date', 'amount', '_id', 'is_fixed', 'sub_category'], # Lock these
                column_config={
                    "_id": st.column_config.TextColumn("ID", disabled=True, width=None, help="Unique ID"),
                    "amount": st.column_config.NumberColumn("Amount", format="₪%.2f"),
                    "date": st.column_config.DatetimeColumn("Date", format="YYYY-MM-DD"),
                    "spender": st.column_config.SelectboxColumn(
                        "Spender",
                        options=["Joint", "Dmitry", "Yaara"],
                        required=True,
                        help="Who made this transaction"
                    )
                }
            )
            
            # Layout: Save Button and Download
            col_actions1, col_actions2 = st.columns([1, 4])
            
            with col_actions1:
                if st.button("💾 Save Changes", type="primary"):
                    changes = st.session_state["data_editor"].get("edited_rows", {})
                    
                    if not changes:
                        st.warning("No changes detected.")
                    else:
                        updated_count = 0
                        # Iterate through changes
                        for idx, updates in changes.items():
                            row_id = df_edit.iloc[idx]['_id']
                            if db.update_transaction(row_id, updates):
                                updated_count += 1
                        
                        if updated_count > 0:
                            st.success(f"Successfully updated {updated_count} transactions!")
                            st.rerun()
                        else:
                            st.error("Failed to update transactions.")

            with col_actions2:
                # CSV Download
                csv = edited_df.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="⬇️ Download CSV",
                    data=csv,
                    file_name=f"transactions_{selected_year}_{month_str}.csv",
                    mime="text/csv"
                )
                st.divider()

    # --- Danger Zone ---
    st.markdown("### 🚨 Danger Zone")
    with st.expander("Reset Database (Delete All Data)"):
        st.warning("This action cannot be undone. All transactions will be permanently deleted.")
        if st.button("🔥 Delete Everything", type="primary"):
            count = db.delete_all_transactions()
            st.success(f"Deleted {count} transactions. Database is empty.")
            time.sleep(1)
            st.rerun()

    st.subheader("🧹 Deduplication Tool")
    
    if "dupe_groups" not in st.session_state:
        st.session_state["dupe_groups"] = None
        
    if st.button("🔍 Scan Entire Database for Duplicates"):
        with st.spinner("Scanning entire history..."):
            st.session_state["dupe_groups"] = db.find_potential_duplicates()
            
    if st.session_state["dupe_groups"] is not None:
        dupe_groups = st.session_state["dupe_groups"]
        
        if not dupe_groups:
            st.success("No potential duplicates found in the entire database.")
            if st.button("Clear Results"):
                 st.session_state["dupe_groups"] = None
                 st.rerun()
        else:
            st.warning(f"Found {len(dupe_groups)} sets of potential duplicates.")
            if st.button("Clear Results", key="clear_res"):
                 st.session_state["dupe_groups"] = None
                 st.rerun()
            
            for i, group in enumerate(dupe_groups):
                # Check if group is still valid (has >1 element)
                if len(group) < 2:
                    continue
                    
                st.markdown(f"**Group {i+1}:** {group[0]['date']} | ₪{group[0]['amount']}")
                
                cols = st.columns(len(group))
                for idx, tx in enumerate(group):
                    with cols[idx]:
                        # Description might be long
                        st.info(f"{tx['description']}\n\nSpender: {tx.get('spender', 'Unknown')}\nCategory: {tx.get('category', 'Uncategorized')}")
                        
                        if st.button(f"🗑️ Delete", key=f"del_{tx['_id']}"):
                            if db.delete_transaction(tx['_id']):
                                st.success("Deleted!")
                                dupe_groups[i].pop(idx)
                                st.session_state["dupe_groups"] = dupe_groups
                                time.sleep(0.5)
                                st.rerun()
                            else:
                                st.error("Failed to delete.")
                st.divider()
