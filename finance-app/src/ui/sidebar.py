import streamlit as st
from datetime import datetime
import calendar

def render_sidebar():
    """
    Renders the sidebar and returns the selected filter configuration.
    Returns:
        dict: {
            'view_period': str,
            'start_date': str,
            'end_date': str,
            'period_label': str,
            'current_year': int,
            'current_month': int
        }
    """
    
    # Theme Toggle
    from src.ui import theme_manager
    current_theme = theme_manager.get_current_theme()
    
    # Icon based on NEXT state (e.g. if Light, show Moon to go Dark)
    btn_label = "🌙 Dark Mode" if current_theme == "light" else "☀️ Light Mode"
    
    if st.sidebar.button(btn_label, use_container_width=True):
        theme_manager.toggle_theme()
        st.rerun()
        
    st.sidebar.divider()

    current_year = datetime.now().year
    current_month = datetime.now().month

    # --- 1. Dashboard Settings (Period Type First) ---

    st.sidebar.header("Dashboard Settings")
    
    # View Period Selector - Moved up so Navigation can react to it
    view_period = st.sidebar.pills(
        "Period Type", 
        ["Monthly", "Quarterly", "Half Year", "Yearly"],
        default=st.session_state.get('view_period', 'Monthly'),
        selection_mode="single",
        key="period_selector_pills"
    )
    if not view_period:
        view_period = st.session_state.get('view_period', 'Monthly')
    
    # Sync with session state immediately
    st.session_state['view_period'] = view_period

    st.sidebar.divider()

    # --- 2. Main Navigation ---
    st.sidebar.title("Navigation")
    
    base_views = ["Dashboard", "Data Editor", "Upload Data"]
    
    # Only show AI Summary for Monthly/Quarterly (cost optimization)
    if view_period in ["Monthly", "Quarterly"]:
        nav_options = ["Dashboard", "AI Summary", "Data Editor", "Upload Data"]
    else:
        nav_options = base_views
    
    selected_view = st.sidebar.pills(
        "Go to",
        nav_options,
        default="Dashboard",
        selection_mode="single",
        label_visibility="collapsed"
    )
    if not selected_view:
        selected_view = "Dashboard"

    st.sidebar.divider()

    # --- 3. Time Selection ---
    st.sidebar.markdown("### Time Selection")

    
    # Year Selector (Full Width)
    selected_year = st.sidebar.selectbox("Year", range(current_year - 2, current_year + 2), index=1)

    # Variables for return
    start_date = ""
    end_date = ""
    period_label = ""
    selected_month = None
    
    # Dynamic Options based on Period
    if view_period == "Monthly":
         months_short = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
         default_month_index = current_month - 1
         
         selected_month_short = st.sidebar.pills(
            "Month", 
            months_short,
            default=months_short[default_month_index],
            selection_mode="single"
        )
         
         # Fallback if unselected
         if not selected_month_short:
             selected_month_short = months_short[default_month_index]

         month_map = {
            "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
            "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12
        }
         selected_month = month_map[selected_month_short]
         selected_month_full_name = calendar.month_name[selected_month] # For label

    elif view_period == "Quarterly":
         selected_quarter = st.sidebar.pills(
             "Quarter", 
             ["Q1", "Q2", "Q3", "Q4"], 
             default="Q1",
             selection_mode="single"
        )
         if not selected_quarter:
             selected_quarter = "Q1"

    elif view_period == "Half Year":
         selected_half = st.sidebar.pills(
             "Half", 
             ["H1", "H2"], 
             default="H1", 
             selection_mode="single"
        )
         if not selected_half:
             selected_half = "H1"

    # --- 3. Logic Calculation ---
    if view_period == "Monthly":
        _, last_day = calendar.monthrange(selected_year, selected_month)
        start_date = f"{selected_year}-{selected_month:02d}-01"
        end_date = f"{selected_year}-{selected_month:02d}-{last_day}"
        period_label = f"{selected_month_full_name} {selected_year}"

    elif view_period == "Quarterly":
        q_map = {
            "Q1": (1, 3), "Q2": (4, 6), "Q3": (7, 9), "Q4": (10, 12)
        }
        start_m, end_m = q_map[selected_quarter]
        _, last_day = calendar.monthrange(selected_year, end_m)
        start_date = f"{selected_year}-{start_m:02d}-01"
        end_date = f"{selected_year}-{end_m:02d}-{last_day}"
        period_label = f"{selected_quarter} {selected_year}"

    elif view_period == "Half Year":
        if selected_half == "H1":
            start_date = f"{selected_year}-01-01"
            end_date = f"{selected_year}-06-30"
        else:
            start_date = f"{selected_year}-07-01"
            end_date = f"{selected_year}-12-31"
        period_label = f"{selected_half} {selected_year}"

    elif view_period == "Yearly":
        start_date = f"{selected_year}-01-01"
        end_date = f"{selected_year}-12-31"
        period_label = f"Year {selected_year}"

    return {
        'selected_view': selected_view,
        'view_period': view_period,
        'start_date': start_date,
        'end_date': end_date,
        'period_label': period_label,
        'selected_year': selected_year,
        'selected_month': selected_month
    }


