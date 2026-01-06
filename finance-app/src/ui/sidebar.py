import streamlit as st
from datetime import datetime
import calendar
from src import db

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
    
    current_year = datetime.now().year
    current_month = datetime.now().month

    # --- 1. Main Navigation (Moved to Top) ---
    st.sidebar.title("Navigation")
    
    # Determine available views based on period (will be updated after period selection, 
    # but we need to render nav first. We'll use session state for persistence)
    view_period = st.session_state.get('view_period', 'Monthly')
    
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

    # --- 2. Dashboard Settings ---

    st.sidebar.header("Dashboard Settings")
    
    # View Period Selector
    view_period = st.sidebar.pills(
        "Period Type", 
        ["Monthly", "Quarterly", "Half Year", "Yearly"],
        default=view_period,
        selection_mode="single",
        key="period_selector_pills"
    )
    if not view_period:
        view_period = st.session_state.get('view_period', 'Monthly')
    
    # Sync with session state immediately
    st.session_state['view_period'] = view_period

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

    st.sidebar.divider()

    # --- 4. Budget Settings ---
    # Load budget from DB
    current_budget = db.get_budget()
    
    def update_budget():
        new_val = st.session_state.budget_input
        db.set_budget(new_val)
        
    with st.sidebar.expander("💰 Budget Goals", expanded=False):
        budget_limit = st.number_input(
            "Monthly Expense Limit (₪)", 
            min_value=0.0, 
            value=float(current_budget), 
            step=500.0, 
            help="Set a target for your monthly expenses to see progress.",
            key="budget_input",
            on_change=update_budget
        )

    # --- 5. Logic Calculation ---
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
        'selected_month': selected_month,
        'budget_limit': budget_limit
    }


