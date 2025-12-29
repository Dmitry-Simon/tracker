import streamlit as st
import time
from src import ai
from src import db

from src.ui import styles

def render_ai_assistant():
    """
    Renders the AI Assistant Tab.
    """
    # Initialize session state for loop
    if "autopilot_running" not in st.session_state:
        st.session_state["autopilot_running"] = False
    
    st.markdown("""
    <style>
    .big-stat { font-size: 2.5rem; font-weight: 700; color: #4CAF50; }
    .stButton button { width: 100%; border-radius: 8px; height: 50px; font-weight: 600; }
    </style>
    """, unsafe_allow_html=True)
    
    with styles.card():
        st.title("🤖 AI Financial Genius")
        st.markdown("Your personal CFO, powered by **Gemini 3 Flash**.")

    # 1. Status Check
    total_uncategorized = db.get_uncategorized_count()
    
    col_status1, col_status2 = st.columns([2, 1])
    with col_status1:
        with styles.card():
            st.subheader("Current Status")
            if total_uncategorized == 0:
                 st.markdown("### 🎉 All Caught Up!")
                 st.caption("You have 0 uncategorized transactions. Amazing!")
            else:
                 st.markdown(f"You have **{total_uncategorized}** transactions pending categorization.")
                 st.progress(0, text="Waiting to start...")
    
    with col_status2:
        with styles.card():
            st.metric("Pending Items", total_uncategorized, delta=None if total_uncategorized == 0 else f"{total_uncategorized}", delta_color="inverse")

    if total_uncategorized > 0:
        st.divider()
        st.subheader("Actions")
        
        c1, c2 = st.columns(2)
        
        with c1:
            # Single Batch Button
            if st.button("✨ Process Next Batch (50)", help="Safely process just the next 50 items."):
                with st.spinner("AI is thinking..."):
                    count, error = ai.enrich_uncategorized_data()
                    if error:
                        st.error(error)
                    else:
                        st.success(f"Categorized {count} transactions!")
                        time.sleep(1)
                        st.rerun()

        with c2:
            # AUTO PILOT BUTTON
            if st.button("🚀 RUN AUTOPILOT (Process All)", type="primary", help="Loop until everything is categorized."):
                st.session_state["autopilot_running"] = True
        
        # AUTOPILOT LOGIC
        if st.session_state["autopilot_running"]:
            
            progress_bar = st.progress(0, text="Initializing Autopilot...")
            status_text = st.empty()
            processed_total = 0
            
            # Estimate iterations
            # We process 50 at a time.
            # total_uncategorized is the starting point.
            
            current_pending = total_uncategorized
            
            with st.container():
                st.info("Autopilot engaged. Please do not close this tab.")
                
                while current_pending > 0:
                    # Update status
                    pct = min(1.0, processed_total / total_uncategorized) if total_uncategorized > 0 else 0
                    progress_bar.progress(pct, text=f"Processed {processed_total} / {total_uncategorized} items...")
                    status_text.write(f"🧠 AI is categorizing batch... ({current_pending} remaining)")
                    
                    # Run Batch
                    count, error = ai.enrich_uncategorized_data()
                    
                    if error:
                        st.error(f"Autopilot stopped due to error: {error}")
                        st.session_state["autopilot_running"] = False
                        break
                    
                    if count == 0:
                        # No more updates possible? (Maybe some are stuck as Uncategorized permanently?)
                        # Or done.
                        break
                        
                    processed_total += count
                    
                    # Check new pending count (for safety and progress accuracy)
                    current_pending = db.get_uncategorized_count()
                    time.sleep(0.5) # Breathe
                
                # Done
                progress_bar.progress(1.0, text="Done!")
                status_text.success(f"🚀 Autopilot Complete! {processed_total} transactions categorized.")
                st.balloons()
                st.session_state["autopilot_running"] = False
                time.sleep(3)
                st.rerun()
