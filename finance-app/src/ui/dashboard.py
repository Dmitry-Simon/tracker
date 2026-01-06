import streamlit as st
import pandas as pd
import altair as alt
import plotly.express as px
from src import db
import src.ui.styles as styles
from collections import defaultdict

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
    budget_limit = filters.get('budget_limit', 0)
    
    # Calculate Budget Multiplier based on view
    multiplier = 1
    if view_period == "Quarterly":
        multiplier = 3
    elif view_period == "Half Year":
        multiplier = 6
    elif view_period == "Yearly":
        multiplier = 12
        
    period_budget = budget_limit * multiplier

    st.markdown(f"### Overview for {period_label}")
    
    # 1. Fetch Data
    transactions = db.get_transactions_by_range(start_date, end_date)
    
    # Fetch ALL historical data for averages calculation (could be optimized to fetch only relevant history)
    # For now, we'll fetch all to ensure accurate averages. 
    # In a production app with massive data, we'd want to aggregate this in the DB.
    all_transactions = db.get_all_transactions() 
    
    if not transactions:
        st.info(f"No transactions found for {period_label}.")
        return

    df = pd.DataFrame(transactions)
    df['amount'] = pd.to_numeric(df['amount'])
    df['date'] = pd.to_datetime(df['date'])
    df['category'] = df['category'].fillna("Uncategorized") if 'category' in df.columns else "Uncategorized"
    df['spender'] = df['spender'].fillna("Joint") if 'spender' in df.columns else "Joint"
        
    # 2. KPI Metrics Calculations
    from src import utils
    metrics = utils.calculate_metrics(transactions)
    
    income = metrics['income']
    expenses_net = metrics['expenses']
    savings = metrics['savings']
    net_savings = metrics['net']
    savings_rate = (net_savings / income * 100) if income > 0 else 0
    
    # Metrics in a 2x2 layout
    row1_col1, row1_col2 = st.columns(2)
    row2_col1, row2_col2 = st.columns(2)
    
    with row1_col1:
        st.metric("💰 Total Income", f"₪{income:,.2f}")
    with row1_col2:
        if period_budget > 0:
            remaining = period_budget - expenses_net
            delta_val = f"{remaining:,.2f} remaining"
            delta_color = "normal" # Green if positive (remaining), Red if negative (over budget)
            st.metric("💸 Total Expenses", f"₪{expenses_net:,.2f}", delta=delta_val, delta_color=delta_color)
        else:
            st.metric("💸 Total Expenses", f"₪{expenses_net:,.2f}", delta="-", delta_color="inverse")
            
    with row2_col1:
        st.metric("🏦 Savings", f"₪{savings:,.2f}", help="Amount transferred to savings accounts")
    with row2_col2:
        # Savings Rate is good if positive (Green), bad if negative (Red). 
        # So we always want "normal" behavior.
        st.metric("📊 Net Cash Flow", f"₪{net_savings:,.2f}", delta=f"{savings_rate:.1f}% Savings Rate", delta_color="normal", help="Income - Expenses (includes unspent cash)")

    
    styles.divider()
    
    # --- 3. Enhanced Analytics Section ---
    
    # Calculate Averages
    cat_averages = utils.calculate_category_averages(all_transactions, view_period)
    
    # Prepare Data for Charts
    # We want to include Savings in the breakdown now -> REVERTED: User wants charts to match "Total Expenses" KPI
    # So we must EXCLUDE Savings from these charts.
    IGNORE_CATS = ['Credit Card Payoff', 'Transfer', 'Savings']
    df_expenses = df[(df['amount'] < 0) & (~df['category'].isin(IGNORE_CATS))].copy()
    
    # --- Row 1: Category Analysis (Ported from AI Summary style) ---
    st.subheader("📈 Category Analysis")
    
    col_cat_chart, col_cat_metrics = st.columns([1.2, 1])
    
    with col_cat_chart:
        if not df_expenses.empty:
            df_expenses['abs_amount'] = df_expenses['amount'].abs()
            cat_breakdown = df_expenses.groupby('category')['abs_amount'].sum().reset_index()
            
            fig = px.pie(
                cat_breakdown,
                values='abs_amount',
                names='category',
                title=f'Spending by Category ({view_period})',
                hole=0.4,
                color_discrete_sequence=px.colors.qualitative.Prism
            )
            fig.update_traces(textposition='inside', textinfo='percent+label')
            fig.update_layout(margin=dict(t=40, b=0, l=0, r=0))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No expenses to analyze.")

    with col_cat_metrics:
        st.markdown(f"**Category Performance vs {view_period} Average**")
        if not df_expenses.empty:
            # Sort by current spend
            sorted_cats = cat_breakdown.sort_values('abs_amount', ascending=False)
            
            # Scrollable container for metrics
            with st.container(height=350):
                for _, row in sorted_cats.iterrows():
                    cat = row['category']
                    amount = row['abs_amount']
                    avg = cat_averages.get(cat, 0)
                    
                    delta = None
                    delta_color = "off"
                    if avg > 0:
                        diff = amount - avg
                        pct_diff = (diff / avg) * 100
                        delta = f"{pct_diff:+.1f}% vs avg (₪{avg:,.0f})"
                        delta_color = "inverse" # Red if higher than average (bad for expenses)
                    
                    st.metric(
                        label=cat,
                        value=f"₪{amount:,.2f}",
                        delta=delta,
                        delta_color=delta_color
                    )
                    st.divider()

    styles.divider()

    # --- Row 2: Trends & Comparisons ---
    col_trend, col_income_exp = st.columns(2)
    
    with col_trend:
        st.subheader("📉 Spending Trend")
        # Line chart of daily/monthly spending
        if not df_expenses.empty:
            if view_period == "Monthly":
                trend_data = df_expenses.groupby('date')['abs_amount'].sum().reset_index()
                x_axis = 'date'
                title = "Daily Spending"
            else:
                df_expenses['month_year'] = df_expenses['date'].dt.to_period('M').astype(str)
                trend_data = df_expenses.groupby('month_year')['abs_amount'].sum().reset_index()
                x_axis = 'month_year'
                title = "Monthly Spending"
                
            fig_trend = px.area(
                trend_data, 
                x=x_axis, 
                y='abs_amount', 
                title=title,
                labels={'abs_amount': 'Amount', x_axis: 'Date'},
                color_discrete_sequence=['#FF4B4B']
            )
            st.plotly_chart(fig_trend, use_container_width=True)
            
    with col_income_exp:
        st.subheader("⚖️ Income vs Expenses")
        # Bar chart comparison
        # Group by appropriate time unit
        df_all = df[~df['category'].isin(IGNORE_CATS)].copy()
        df_all['type'] = df_all['amount'].apply(lambda x: 'Income' if x > 0 else 'Expense')
        df_all['abs_amount'] = df_all['amount'].abs()
        
        if view_period == "Monthly":
            # Weekly aggregation for monthly view
            df_all['period'] = df_all['date'].dt.isocalendar().week
            x_label = "Week"
        else:
            # Monthly aggregation for others
            df_all['period'] = df_all['date'].dt.to_period('M').astype(str)
            x_label = "Month"
            
        comp_data = df_all.groupby(['period', 'type'])['abs_amount'].sum().reset_index()
        
        fig_comp = px.bar(
            comp_data,
            x='period',
            y='abs_amount',
            color='type',
            barmode='group',
            title="Income vs Expenses Flow",
            color_discrete_map={'Income': '#00CC96', 'Expense': '#EF553B'},
            labels={'abs_amount': 'Amount', 'period': x_label}
        )
        st.plotly_chart(fig_comp, use_container_width=True)

    # --- Row 3: Top Spenders ---
    st.subheader("🏆 Top Spenders")
    if not df_expenses.empty:
        top_spenders = df_expenses.groupby('spender')['abs_amount'].sum().reset_index().sort_values('abs_amount', ascending=False).head(10)
        
        fig_spenders = px.bar(
            top_spenders,
            x='abs_amount',
            y='spender',
            orientation='h',
            title="Top 10 Merchants/Spenders",
            labels={'abs_amount': 'Total Spent', 'spender': 'Merchant'},
            color='abs_amount',
            color_continuous_scale='Reds'
        )
        fig_spenders.update_layout(yaxis={'categoryorder':'total ascending'})
        st.plotly_chart(fig_spenders, use_container_width=True)


    styles.divider()

    # 4. Detailed Transaction Table
    with styles.card():
        st.subheader("🔍 Transaction Details")
        
        # Search Filter Row
        search_term = st.text_input("Search", placeholder="Search description, category, or spender...", label_visibility="collapsed")
        
        # Build display columns
        base_cols = ['date', 'spender', 'description', 'category', 'amount']
        optional_cols = ['source_file', 'uploaded_from']
        display_cols = base_cols + [col for col in optional_cols if col in df.columns]
        
        display_df = df[display_cols].sort_values(by='date', ascending=False)
        
        if search_term:
            display_df = display_df[
                display_df['description'].str.contains(search_term, case=False, na=False) |
                display_df['category'].str.contains(search_term, case=False, na=False) |
                display_df['spender'].str.contains(search_term, case=False, na=False)
            ]
            
        # Apply styling
        def color_amount(val):
            color = 'red' if val < 0 else 'green'
            return f'color: {color}'
            
        st.dataframe(
            display_df.style.map(color_amount, subset=['amount']),
            use_container_width=True,
            column_config={
                "date": st.column_config.DateColumn("Date", format="MMM DD, YYYY", width="small"),
                "spender": st.column_config.TextColumn("Owner", width="small"),
                "description": st.column_config.TextColumn("Description", width="large"),
                "category": st.column_config.TextColumn("Category", width="medium"),
                "amount": st.column_config.NumberColumn("Amount", format="₪%.2f", width="small")
            },
            hide_index=True
        )

