import streamlit as st
import pandas as pd
import altair as alt
from src import db
from src.ui import styles

def render_dashboard(filters):
    """
    Renders the Dashboard Tab.
    Args:
        filters (dict): Output from sidebar.render_sidebar()
    """
    start_date = filters['start_date']
    end_date = filters['end_date']
    period_label = filters['period_label']
    view_period = filters['view_period']

    st.markdown(f"### Overview for {period_label}")
    
    # 1. Fetch Data
    transactions = db.get_transactions_by_range(start_date, end_date)
    
    if not transactions:
        st.info(f"No transactions found for {period_label}.")
        return

    df = pd.DataFrame(transactions)
    df['amount'] = pd.to_numeric(df['amount'])
    df['date'] = pd.to_datetime(df['date'])
    df['category'] = df['category'].fillna("Uncategorized") if 'category' in df.columns else "Uncategorized"
    df['spender'] = df['spender'].fillna("Joint") if 'spender' in df.columns else "Joint"
        
    # 2. KPI Metrics Calculations
    INCOME_CATEGORIES = ['Salary', 'Income', 'Benefits', 'Interest']
    IGNORE_CATS = ['Credit Card Payoff']
    
    income = df[df['category'].isin(INCOME_CATEGORIES)]['amount'].sum()
    expenses_net = df[(~df['category'].isin(INCOME_CATEGORIES)) & (~df['category'].isin(IGNORE_CATS))]['amount'].sum()
    net_savings = income + expenses_net
    savings_rate = (net_savings / income * 100) if income > 0 else 0
    
    # Metrics in a more spaced layout
    m_col1, m_col2 = st.columns(2)
    with m_col1:
        c1, c2 = st.columns(2)
        c1.metric("Total Income", f"₪{income:,.2f}")
        c2.metric("Total Expenses", f"₪{abs(expenses_net):,.2f}", delta="-", delta_color="inverse")
    with m_col2:
        c3, c4 = st.columns(2)
        c3.metric("Net Savings", f"₪{net_savings:,.2f}")
        c4.metric("Savings Rate", f"{savings_rate:.1f}%")
    
    styles.divider()
    
    selected_category = None

    # 3. Visualizations
    col_charts1, col_charts2 = st.columns(2)
    
    with col_charts1:
        with styles.card():
            st.subheader("📊 Expenses by Category")
            df_expenses = df[(df['amount'] < 0) & (~df['category'].isin(IGNORE_CATS))].copy()
            
            if not df_expenses.empty:
                df_expenses['abs_amount'] = df_expenses['amount'].abs()
                cat_breakdown = df_expenses.groupby('category')['abs_amount'].sum().reset_index()
                select_category = alt.selection_point(fields=['category'], name="category_select")
                
                pie = alt.Chart(cat_breakdown).mark_arc(outerRadius=120, innerRadius=80).encode(
                    theta=alt.Theta("abs_amount", stack=True),
                    color=alt.Color("category", scale=alt.Scale(scheme='tableau10')),
                    order=alt.Order("abs_amount", sort="descending"),
                    tooltip=["category", alt.Tooltip("abs_amount", format=",.2f")],
                    opacity=alt.condition(select_category, alt.value(1), alt.value(0.3))
                ).add_params(select_category)
                
                chart_event = st.altair_chart(pie, use_container_width=True, on_select="rerun")
                if len(chart_event.selection.category_select) > 0:
                    selected_category = chart_event.selection.category_select[0]['category']
            else:
                st.caption("No expenses recorded this period.")

    with col_charts2:
        with styles.card():
            st.subheader("📈 Balance Trend")
            df_chart_source = df[~df['category'].isin(IGNORE_CATS)]
            
            if view_period == "Monthly":
                chart_data = df_chart_source.groupby('date')['amount'].sum().cumsum().reset_index()
                x_axis = "date"
            else:
                df_chart_source['Month'] = df_chart_source['date'].dt.to_period('M').astype(str)
                chart_data = df_chart_source.groupby('Month')['amount'].sum().reset_index()
                x_axis = "Month"

            area = alt.Chart(chart_data).mark_area(
                line={'color':'#FF4B4B'},
                color=alt.Gradient(
                    gradient='linear',
                    stops=[alt.GradientStop(color='#FF4B4B', offset=0),
                           alt.GradientStop(color='rgba(255, 75, 75, 0.1)', offset=1)],
                    x1=1, x2=1, y1=1, y2=0
                )
            ).encode(
                x=alt.X(x_axis, title="Date"),
                y=alt.Y('amount', title="Balance / Net Flow"),
                tooltip=[x_axis, alt.Tooltip('amount', format=",.2f")]
            )
            st.altair_chart(area, use_container_width=True)

    # 4. Detailed Transaction Table
    with styles.card():
        st.subheader("🔍 Transaction Details")
        
        # Interactive Filter Banner
        if selected_category:
            st.info(f"Filtering by: **{selected_category}** (Click chart to clear)")
        
        # Search Filter Row
        s_col1, s_col2 = st.columns([2, 1])
        with s_col1:
            search_term = st.text_input("Search", placeholder="Search description, category, or spender...", label_visibility="collapsed")
        
        # Build display columns
        base_cols = ['date', 'spender', 'description', 'category', 'amount']
        optional_cols = ['source_file', 'uploaded_from']
        display_cols = base_cols + [col for col in optional_cols if col in df.columns]
        
        display_df = df[display_cols].sort_values(by='date', ascending=False)
        
        if selected_category:
            display_df = display_df[display_df['category'] == selected_category]
        
        if search_term:
            display_df = display_df[
                display_df['description'].str.contains(search_term, case=False, na=False) |
                display_df['category'].str.contains(search_term, case=False, na=False) |
                display_df['spender'].str.contains(search_term, case=False, na=False)
            ]
            
        st.dataframe(
            display_df,
            use_container_width=True,
            column_config={
                "date": st.column_config.DateColumn("Date", format="YYYY-MM-DD", width="small"),
                "spender": st.column_config.TextColumn("Owner", width="small"),
                "description": st.column_config.TextColumn("Description", width="large"),
                "category": st.column_config.TextColumn("Category", width="medium"),
                "amount": st.column_config.NumberColumn("Amount", format="₪%.2f", width="small")
            },
            hide_index=True
        )

