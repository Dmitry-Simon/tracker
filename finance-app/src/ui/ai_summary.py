import streamlit as st
import pandas as pd
from src import db, ai
import plotly.express as px
import plotly.graph_objects as go
from collections import defaultdict

def render_ai_summary(filters):
    """
    Renders the AI Summary page with intelligent financial insights.
    
    Args:
        filters (dict): Output from sidebar.render_sidebar()
    """
    st.header(f"🤖 AI Financial Summary")
    st.markdown(f"**Period:** {filters['period_label']}")
    
    # Get transactions for the period
    transactions = db.get_transactions_by_range(filters['start_date'], filters['end_date'])
    
    if not transactions:
        st.info("📭 No transactions found for this period. Upload some data to get started!")
        return
    
    # Calculate consistent metrics using shared utility
    from src import utils, ai_summary_cache
    metrics = utils.calculate_metrics(transactions)
    
    total_income = metrics['income']
    total_expenses = metrics['expenses']
    net = metrics['net']
    tx_count = metrics['count']
    
    # --- Overview Metrics ---
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            label="💰 Income",
            value=f"₪{total_income:,.2f}",
            delta=None
        )
    
    with col2:
        st.metric(
            label="💸 Expenses",
            value=f"₪{total_expenses:,.2f}",
            delta=None
        )
    
    with col3:
        net_color = "normal" if net >= 0 else "inverse"
        st.metric(
            label="📊 Net",
            value=f"₪{net:,.2f}",
            delta=f"{'Positive' if net >= 0 else 'Negative'}",
            delta_color=net_color
        )
    
    with col4:
        st.metric(
            label="🔢 Transactions",
            value=f"{tx_count}",
            delta=None
        )
    
    st.divider()
    
    # --- AI Insights Section ---
    st.subheader("💡 AI-Generated Insights")
    
    # Caching Logic
    period_key = f"{filters['view_period']}_{filters['selected_year']}_{filters.get('selected_month', 'Q' + str((int(filters['start_date'].split('-')[1])-1)//3 + 1))}"
    data_hash = ai_summary_cache.get_data_hash(transactions)
    
    # Check if we should force regeneration
    force_refresh = st.session_state.get('force_ai_refresh', False)
    
    cached_result = None
    if not force_refresh:
        cached_result = ai_summary_cache.get_cached_summary(period_key, data_hash)
    
    if cached_result:
        summary_data = cached_result['summary_data']
        generated_at = datetime.fromisoformat(cached_result['generated_at']).strftime("%Y-%m-%d %H:%M")
        st.caption(f"⏱️ Cached summary from {generated_at}")
        error = None
    else:
        # Generate AI Summary with historical context
        with st.spinner("🤖 Analyzing your financial data with AI..."):
            summary_data, error = ai.generate_financial_summary(transactions, filters['period_label'], filters)

            
        if not error and summary_data:
            ai_summary_cache.save_summary_to_cache(period_key, data_hash, summary_data)
            # Reset force refresh flag
            st.session_state['force_ai_refresh'] = False
    
    if error:
        st.error(f"❌ {error}")
        st.info("💡 Showing basic statistics instead.")
        # Show basic fallback
        _render_basic_stats(transactions)
        return
    
    if not summary_data:
        st.warning("⚠️ AI summary generation failed. Please try again.")
        _render_basic_stats(transactions)
        return
    
    # Display Summary
    st.markdown(f"**📝 Summary:**")
    st.info(summary_data.get('summary', 'No summary available'))
    
    # Display Insights
    insights = summary_data.get('insights', [])
    if insights:
        st.markdown("**🔍 Key Insights:**")
        for idx, insight in enumerate(insights, 1):
            st.markdown(f"- {insight}")
    
    st.divider()
    
    # --- Unusual Expenses Section ---
    unusual_expenses = summary_data.get('unusual_expenses', [])
    if unusual_expenses:
        st.subheader("🚨 Unusual Transactions")
        st.markdown("These transactions stood out based on your typical spending patterns:")
        
        # Create DataFrame for unusual expenses
        unusual_df = pd.DataFrame(unusual_expenses)
        if not unusual_df.empty:
            # Format for display
            display_df = unusual_df.copy()
            if 'amount' in display_df.columns:
                display_df['amount'] = display_df['amount'].apply(lambda x: f"₪{abs(x):,.2f}")
            
            st.dataframe(
                display_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "description": "Transaction",
                    "amount": "Amount",
                    "reason": "Why It's Unusual"
                }
            )
    
    st.divider()
    
    # --- Category Breakdown ---
    st.subheader("📈 Category Analysis")
    
    col_left, col_right = st.columns([1, 1])
    
    with col_left:
        # Category spending chart (Align with dashboard.py - exclude IGNORE_CATS)
        IGNORE_CATS = ['Credit Card Payoff']
        by_category = defaultdict(float)
        for t in transactions:
            if t['amount'] < 0:  # Expenses only
                cat = t.get('category', 'Uncategorized')
                if cat in IGNORE_CATS:
                    continue
                by_category[cat] += abs(t['amount'])
        
        if by_category:
            cat_df = pd.DataFrame([
                {'Category': cat, 'Amount': amt}
                for cat, amt in sorted(by_category.items(), key=lambda x: x[1], reverse=True)
            ])
            
            fig = px.pie(
                cat_df,
                values='Amount',
                names='Category',
                title='Spending by Category',
                hole=0.4
            )
            fig.update_traces(textposition='inside', textinfo='percent+label')
            st.plotly_chart(fig, use_container_width=True)
    
    with col_right:
        # AI Category Notes
        category_notes = summary_data.get('category_notes', {})
        if category_notes:
            st.markdown("**🤖 AI Category Commentary:**")
            for category, note in category_notes.items():
                if category in by_category:  # Only show notes for categories that exist
                    with st.expander(f"💬 {category} - ₪{by_category[category]:,.2f}", expanded=False):
                        st.markdown(note)

        else:
            st.info("No category-specific insights generated.")
    
    st.divider()
    
    # --- Recommendations Section ---
    recommendations = summary_data.get('recommendations', [])
    if recommendations:
        st.subheader("✅ Recommendations")
        st.markdown("AI-suggested actions to improve your financial health:")
        
        for idx, rec in enumerate(recommendations, 1):
            st.success(f"**{idx}.** {rec}")
    
    # --- Personalized Joke Section ---
    joke = summary_data.get('joke')
    if joke:
        st.divider()
        st.markdown("### 🎭 Just for Laughs")
        st.info(f"*{joke}*")

    st.divider()
    if st.button("🔄 Regenerate Summary", type="secondary"):
        st.session_state['force_ai_refresh'] = True
        st.rerun()

from datetime import datetime



def _render_basic_stats(transactions):
    """Fallback: Render basic statistics when AI fails."""
    st.subheader("📊 Basic Statistics")
    
    # Category breakdown
    by_category = defaultdict(lambda: {'total': 0, 'count': 0})
    for t in transactions:
        cat = t.get('category', 'Uncategorized')
        by_category[cat]['total'] += abs(t['amount'])
        by_category[cat]['count'] += 1
    
    # Sort by total spending
    sorted_cats = sorted(by_category.items(), key=lambda x: x[1]['total'], reverse=True)
    
    st.markdown("**Top Spending Categories:**")
    for cat, data in sorted_cats[:5]:
        st.markdown(f"- **{cat}**: ${data['total']:,.2f} ({data['count']} transactions)")
