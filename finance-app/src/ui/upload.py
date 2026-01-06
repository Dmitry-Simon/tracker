import streamlit as st
import pandas as pd
from src import parsers, db
from src.ui import styles

def render_upload():
    """
    Renders the Upload Data Tab with proper two-phase upload flow.
    Phase 1: Parse file and check for duplicates (show preview)
    Phase 2: Insert after user confirms
    """
    
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

    # Initialize session state for upload workflow
    if "upload_phase" not in st.session_state:
        st.session_state["upload_phase"] = "idle"  # idle, preview, done
    if "parsed_transactions" not in st.session_state:
        st.session_state["parsed_transactions"] = []
    if "duplicate_warnings" not in st.session_state:
        st.session_state["duplicate_warnings"] = []
    if "upload_filename" not in st.session_state:
        st.session_state["upload_filename"] = ""

    # --- Uploader Section ---
    with styles.card():
        uploaded_files = st.file_uploader(
            "Drop your bank/card statements here", 
            type=['pdf', 'csv', 'xlsx', 'xls'],
            accept_multiple_files=True,
            help="You can drag and drop multiple files at once",
            key="file_uploader"
        )

    # Reset state when files change
    if not uploaded_files and st.session_state["upload_phase"] != "idle":
        st.session_state["upload_phase"] = "idle"
        st.session_state["parsed_transactions"] = []
        st.session_state["duplicate_warnings"] = []
        st.session_state["upload_filename"] = ""

    if uploaded_files:
        # PHASE 1: Parse and Preview
        if st.session_state["upload_phase"] == "idle":
            st.subheader(f"⚙️ Analyzing {len(uploaded_files)} File{'s' if len(uploaded_files)>1 else ''}...")
            
            all_transactions = []
            near_duplicates = []  # Similar transactions (fuzzy match)
            exact_duplicates = []  # Already in DB (same hash)
            truly_new = []  # Not in DB at all
            file_info = []
            
            parse_progress = st.progress(0, text="Parsing files...")
            
            for file_idx, uploaded_file in enumerate(uploaded_files):
                try:
                    new_transactions = parsers.detect_and_parse(uploaded_file, uploaded_file.name)
                    
                    if new_transactions:
                        for tx in new_transactions:
                            tx['_source_file'] = uploaded_file.name  # Track source
                        all_transactions.extend(new_transactions)
                        file_info.append({'file': uploaded_file.name, 'count': len(new_transactions)})
                    else:
                        file_info.append({'file': uploaded_file.name, 'count': 0, 'error': 'No transactions found'})
                        
                except Exception as e:
                    file_info.append({'file': uploaded_file.name, 'count': 0, 'error': str(e)[:50]})
                
                parse_progress.progress((file_idx + 1) / len(uploaded_files))
            
            # Check each transaction for exact and near duplicates
            check_progress = st.progress(0, text="Checking for duplicates...")
            for i, tx in enumerate(all_transactions):
                # Check for EXACT duplicate (same hash already in DB)
                is_exact_dupe = db.check_transaction_exists(tx)
                
                if is_exact_dupe:
                    # Check if this duplicate can be enriched with new fields
                    can_enrich = _check_can_enrich(tx)
                    if can_enrich:
                        # Track as "enrichable" - will be updated with new metadata
                        exact_duplicates.append({'tx': tx, 'enrichable': True})
                    else:
                        exact_duplicates.append({'tx': tx, 'enrichable': False})
                else:
                    # Check for NEAR duplicates (similar but not exact)
                    near_dupes = db.check_for_near_duplicates(tx, threshold=0.75)
                    if near_dupes:
                        near_duplicates.append({
                            'new_tx': tx,
                            'matches': near_dupes
                        })
                    else:
                        truly_new.append(tx)
                
                check_progress.progress((i + 1) / len(all_transactions))
            
            # Save to session state
            st.session_state["parsed_transactions"] = all_transactions
            st.session_state["exact_duplicates"] = exact_duplicates
            st.session_state["near_duplicates"] = near_duplicates
            st.session_state["truly_new"] = truly_new
            st.session_state["upload_phase"] = "preview"
            st.session_state["upload_filename"] = ", ".join([f.name for f in uploaded_files])
            st.rerun()  # Rerun to show preview phase
        
        # PHASE 2: Show Preview and Confirmation
        elif st.session_state["upload_phase"] == "preview":
            transactions = st.session_state["parsed_transactions"]
            exact_duplicates = st.session_state.get("exact_duplicates", [])
            near_duplicates = st.session_state.get("near_duplicates", [])
            truly_new = st.session_state.get("truly_new", [])
            
            # Split exact duplicates into enrichable and pure duplicates
            enrichable = [d for d in exact_duplicates if d.get('enrichable', False)]
            pure_dupes = [d for d in exact_duplicates if not d.get('enrichable', False)]
            
            # Split near-duplicates by confidence
            AUTO_SKIP_THRESHOLD = 0.85
            auto_skip_near = [d for d in near_duplicates if d['matches'][0]['confidence'] >= AUTO_SKIP_THRESHOLD]
            review_near = [d for d in near_duplicates if d['matches'][0]['confidence'] < AUTO_SKIP_THRESHOLD]
            
            # Calculate counts
            total_count = len(transactions)
            enrichable_count = len(enrichable)
            pure_dupe_count = len(pure_dupes)
            auto_skip_count = len(auto_skip_near)
            review_count = len(review_near)
            new_count = len(truly_new)
            
            st.subheader(f"📋 Preview: {total_count} transactions parsed")
            
            # Show summary
            with styles.card():
                st.markdown(f"**File(s):** {st.session_state['upload_filename']}")
                
                # Visual breakdown - 5 columns now
                c1, c2, c3, c4, c5 = st.columns(5)
                c1.metric("🆕 New", new_count)
                c2.metric("� Enrich", enrichable_count, help="Existing records missing bank_category or transaction_type")
                c3.metric("📋 Dupes", pure_dupe_count, help="Identical records, nothing to update")
                c4.metric("🤖 Near", auto_skip_count, help="High confidence similar (≥85%)")
                c5.metric("⚠️ Review", review_count, help="Lower confidence similar (75-84%)")
                
                st.divider()
                
                # Messages for each category
                if enrichable_count > 0:
                    st.success(f"🔄 **{enrichable_count}** existing records can be enriched with bank_category/transaction_type!")
                
                if pure_dupe_count > 0:
                    st.info(f"📋 **{pure_dupe_count}** exact duplicates - nothing to update.")
                
                if auto_skip_count > 0:
                    st.info(f"🤖 **{auto_skip_count}** high-confidence near-duplicates - will be skipped.")
                
                # Show uncertain duplicates for review
                if review_near:
                    st.warning(f"⚠️ Found **{review_count}** uncertain near-duplicates (75-84%) - please review:")
                    
                    dupe_data = []
                    for warn in review_near:
                        existing = warn['matches'][0]['existing']
                        conf = warn['matches'][0]['confidence']
                        dupe_data.append({
                            'New Description': warn['new_tx']['description'][:50],
                            'New Amount': f"₪{warn['new_tx']['amount']:.2f}",
                            'Existing Match': existing['description'][:50],
                            'Confidence': f"{int(conf*100)}%"
                        })
                    
                    st.dataframe(pd.DataFrame(dupe_data), use_container_width=True, hide_index=True)
                
                if new_count > 0 and enrichable_count == 0 and pure_dupe_count == 0 and auto_skip_count == 0 and review_count == 0:
                    st.success("✅ All transactions are new!")
            
            # Action buttons
            st.divider()
            
            # Determine what can be processed
            can_process = new_count > 0 or enrichable_count > 0 or review_count > 0
            
            if can_process:
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    # Primary action: Import new + enrich existing
                    total_to_process = new_count + enrichable_count
                    if review_near:
                        total_to_process += review_count
                        btn_text = f"✅ Process {total_to_process} (New + Enrich + Uncertain)"
                    else:
                        btn_text = f"✅ Process {total_to_process} ({new_count} New + {enrichable_count} Enrich)"
                    
                    if st.button(btn_text, type="primary", use_container_width=True):
                        # Import truly_new + enrichable + optional review_near
                        to_import = truly_new + [d['tx'] for d in enrichable]
                        if review_near:
                            to_import += [d['new_tx'] for d in review_near]
                        _insert_transactions_direct(to_import)

                with col2:
                    if review_near:
                        # Option to skip uncertain ones
                        btn_text = f"🛡️ Skip Uncertain ({new_count} New + {enrichable_count} Enrich)"
                        if st.button(btn_text, use_container_width=True):
                            to_import = truly_new + [d['tx'] for d in enrichable]
                            _insert_transactions_direct(to_import)
                
                with col3:
                    if st.button("❌ Cancel Upload", use_container_width=True):
                        _reset_upload_state()
            else:
                # Nothing to import
                st.info("ℹ️ All transactions are already in the database and up-to-date.")
                if st.button("↩️ Go Back", use_container_width=True):
                    _reset_upload_state()
        
        # PHASE 3: Done - show results
        elif st.session_state["upload_phase"] == "done":
            results = st.session_state.get("upload_results", {})
            
            st.divider()
            with styles.card():
                st.subheader("📊 Upload Complete!")
                s1, s2, s3 = st.columns(3)
                s1.metric("New", results.get('added', 0), delta=None)
                s2.metric("Updated", results.get('updated', 0), delta=None) 
                s3.metric("Skipped", results.get('skipped', 0), delta=None)
                
                if results.get('skipped', 0) > 0:
                    st.caption("ℹ️ Skipped = exact duplicates already in database (same hash)")
            
            if st.button("📤 Upload More Files"):
                st.session_state["upload_phase"] = "idle"
                st.session_state["parsed_transactions"] = []
                st.session_state["duplicate_warnings"] = []
                st.rerun()


def _insert_transactions(transactions: list, skip_duplicates: bool = False, duplicates: list = None):
    """
    Helper function to insert transactions into the database.
    """
    added, updated, skipped = 0, 0, 0
    
    # Build skip set if needed
    skip_set = set()
    if skip_duplicates and duplicates:
        for warn in duplicates:
            tx = warn['new_tx']
            skip_key = f"{tx['date']}_{tx['amount']}_{tx['description']}"
            skip_set.add(skip_key)
    
    progress = st.progress(0, text="Inserting transactions...")
    
    for i, tx in enumerate(transactions):
        tx_key = f"{tx['date']}_{tx['amount']}_{tx['description']}"
        
        # Clean up internal tracking field
        tx.pop('_source_file', None)
        
        if tx_key in skip_set:
            skipped += 1
        else:
            status = db.add_transaction(tx)
            if status == 'added':
                added += 1
            elif status == 'updated':
                updated += 1
            else:
                skipped += 1
        
        progress.progress((i + 1) / len(transactions))
    
    # Save results and transition to done phase
    st.session_state["upload_results"] = {
        'added': added,
        'updated': updated,
        'skipped': skipped
    }
    st.session_state["upload_phase"] = "done"
    st.rerun()


def _reset_upload_state():
    """Reset all upload-related session state."""
    st.session_state["upload_phase"] = "idle"
    st.session_state["parsed_transactions"] = []
    st.session_state["exact_duplicates"] = []
    st.session_state["near_duplicates"] = []
    st.session_state["truly_new"] = []
    st.session_state["upload_filename"] = ""
    st.rerun()


def _insert_transactions_direct(transactions: list):
    """
    Directly insert a list of transactions (already validated as not exact duplicates).
    """
    added, updated, skipped = 0, 0, 0
    
    if not transactions:
        st.session_state["upload_results"] = {'added': 0, 'updated': 0, 'skipped': 0}
        st.session_state["upload_phase"] = "done"
        st.rerun()
        return
    
    progress = st.progress(0, text="Inserting transactions...")
    
    for i, tx in enumerate(transactions):
        # Clean up internal tracking field
        tx_clean = tx.copy()
        tx_clean.pop('_source_file', None)
        
        status = db.add_transaction(tx_clean)
        if status == 'added':
            added += 1
        elif status == 'updated':
            updated += 1
        else:
            skipped += 1
        
        progress.progress((i + 1) / len(transactions))
    
    # Save results and transition to done phase
    st.session_state["upload_results"] = {
        'added': added,
        'updated': updated,
        'skipped': skipped
    }
    st.session_state["upload_phase"] = "done"
    st.rerun()


def _check_can_enrich(tx: dict) -> bool:
    """
    Check if an existing transaction in the DB can be enriched with new metadata
    from this transaction (e.g., bank_category, transaction_type, spender).
    """
    # Generate hash to find existing doc
    hash_id = db.generate_hash_id(
        tx['date'],
        tx['amount'],
        tx['description'],
        tx.get('ref_id')
    )
    
    firestore_db = db.get_db()
    if not firestore_db:
        return False
        
    doc = firestore_db.collection('transactions').document(hash_id).get()
    if not doc.exists:
        return False
    
    existing_data = doc.to_dict()
    
    # Check enrichable fields
    enrichable_fields = ['bank_category', 'transaction_type', 'spender']
    
    for field in enrichable_fields:
        new_val = tx.get(field)
        existing_val = existing_data.get(field)
        
        # If new value exists and existing is missing, can enrich
        if new_val and existing_val is None:
            return True
    
    return False
