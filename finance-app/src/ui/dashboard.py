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

    # Convert to DataFrame
    df = pd.DataFrame(transactions)
    
    # Ensure correct data types
    df['amount'] = pd.to_numeric(df['amount'])
    df['date'] = pd.to_datetime(df['date'])
    
    # Fill missing categories if 'category' column exists, otherwise create it
    if 'category' not in df.columns:
        df['category'] = "Uncategorized"
    else:
        df['category'] = df['category'].fillna("Uncategorized")
        
    if 'spender' not in df.columns:
        df['spender'] = "Joint"
    else:
        df['spender'] = df['spender'].fillna("Joint")
        
    # 2. KPI Metrics
    # Income: Strict Category Filter
    INCOME_CATEGORIES = ['Salary', 'Income', 'Benefits', 'Interest']
    # Excluded from Expenses (Payoffs to avoid double counting)
    IGNORE_CATS = ['Credit Card Payoff']
    
    # Calculate Income (Sum of positive amounts in Income Categories)
    income = df[df['category'].isin(INCOME_CATEGORIES)]['amount'].sum()
    
    # Calculate Expenses (Sum of ALL transactions NOT in Income Categories AND NOT Ignored)
    # This automatically handles Refunds (positive amounts in non-income categories)
    # as they will reduce the negative sum.
    expenses_net = df[
        (~df['category'].isin(INCOME_CATEGORIES)) & 
        (~df['category'].isin(IGNORE_CATS))
    ]['amount'].sum()
    
    # Expenses should be displayed as a positive number (Absolute)
    # Note: expenses_net is typically negative.
    
    net_savings = income + expenses_net
    
    # Savings Rate
    savings_rate = 0
    if income > 0:
        savings_rate = (net_savings / income) * 100
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Income", f"₪{income:,.2f}", delta_color="normal")
    col2.metric("Total Expenses", f"₪{abs(expenses_net):,.2f}", delta="-", delta_color="inverse")
    col3.metric("Net Savings", f"₪{net_savings:,.2f}", delta_color="normal")
    col4.metric("Savings Rate", f"{savings_rate:.1f}%", delta=None)
    
    st.markdown("---")
    
    # Selected Category State
    selected_category = None

    # 3. Visualizations
    col_charts1, col_charts2 = st.columns(2)
    
    with col_charts1:
        with styles.card():
            st.subheader("Expenses by Category")
            # Filter for expenses only AND exclude payofs
            df_expenses = df[
                (df['amount'] < 0) & 
                (~df['category'].isin(IGNORE_CATS))
            ].copy()
            
            if not df_expenses.empty:
                df_expenses['abs_amount'] = df_expenses['amount'].abs()
                # Group by category
                cat_breakdown = df_expenses.groupby('category')['abs_amount'].sum().reset_index()
                
                # Interactive Selection
                select_category = alt.selection_point(fields=['category'], name="category_select")
                
                # Altair Donut Chart
                base = alt.Chart(cat_breakdown).encode(
                    theta=alt.Theta("abs_amount", stack=True)
                )
                
                pie = base.mark_arc(outerRadius=120, innerRadius=80).encode(
                    color=alt.Color("category"),
                    order=alt.Order("abs_amount", sort="descending"),
                    tooltip=["category", alt.Tooltip("abs_amount", format=",.2f")],
                    opacity=alt.condition(select_category, alt.value(1), alt.value(0.3))
                ).add_params(select_category)
                
                # Render and Capture Selection (Text layer removed due to Streamlit limitation on interactive layered charts)
                chart_event = st.altair_chart(pie, use_container_width=True, on_select="rerun")
                
                # Extract Selection
                if len(chart_event.selection.category_select) > 0:
                    # Returns list of dicts: [{'category': 'Food'}]
                    selected_category = chart_event.selection.category_select[0]['category']

            else:
                st.caption("No expenses recorded this period.")

    with col_charts2:
        with styles.card():
            st.subheader("Balance Trend")
            
            chart_data = None
            x_axis = ""
            
            # Filter source for chart to avoid double dips
            df_chart_source = df[~df['category'].isin(IGNORE_CATS)]
            
            if view_period == "Monthly":
                # Daily trend
                chart_data = df_chart_source.groupby('date')['amount'].sum().cumsum().reset_index()
                x_axis = "date"
            else:
                # Group by Month
                df_chart_source['Month'] = df_chart_source['date'].dt.to_period('M').astype(str)
                chart_data = df_chart_source.groupby('Month')['amount'].sum().reset_index()
                x_axis = "Month"

            # Altair Area Chart
            area = alt.Chart(chart_data).mark_area(
                line={'color':'#2980b9'},
                color=alt.Gradient(
                    gradient='linear',
                    stops=[alt.GradientStop(color='#2980b9', offset=0),
                           alt.GradientStop(color='rgba(41, 128, 185, 0.1)', offset=1)],
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
        st.subheader("Transaction Details")
        
        # Interactive Filter Banner
        if selected_category:
            st.info(f"🔍 Filtering details by Category: **{selected_category}**")
        
        # Search Filter
        search_term = st.text_input("🔍 Search Transactions", placeholder="Type to search description or category...")
        
        # Build display columns - include source tracking if available
        base_cols = ['date', 'spender', 'description', 'category', 'amount']
        optional_cols = ['source_file', 'uploaded_from']
        display_cols = base_cols + [col for col in optional_cols if col in df.columns]
        
        display_df = df[display_cols].sort_values(by='date', ascending=False)
        
        # Apply Category Filter if selected
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
                "date": st.column_config.DateColumn("Date", format="YYYY-MM-DD"),
                "spender": st.column_config.TextColumn("Spender"),
                "description": st.column_config.TextColumn("Description"),
                "category": st.column_config.TextColumn("Category"),
                "amount": st.column_config.NumberColumn("Amount", format="₪%.2f")
            },
            hide_index=True
        )
