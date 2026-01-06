import google.generativeai as genai
import streamlit as st
import json
import time
from src import db

# Configure API Key (Global try, but we also check in function)
if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
elif "gemini" in st.secrets and "api_key" in st.secrets["gemini"]:
    genai.configure(api_key=st.secrets["gemini"]["api_key"])

def categorize_transactions(transactions: list) -> tuple[list, str]:
    """
    Uses Gemini to categorize a list of transactions.
    
    Args:
        transactions: List of dicts, must contain 'description', 'amount', '_id'.
    
    Returns:
        (results_list, error_message)
        results_list is list of dicts with keys: '_id', 'category', 'description' (normalized).
    """
    if not transactions:
        return [], None

    # Model Selection Strategy
    # User requested "Gemini 3 Flash".
    # We try: 3.0 Flash -> 2.0 Flash -> 1.5 Flash
    models_to_try = [
        'gemini-3-flash-preview',
        'gemini-2.0-flash-exp',
        'gemini-1.5-flash'
    ]
    
    # Start with primary
    current_model_name = models_to_try[0]
    model = genai.GenerativeModel(current_model_name)

    # Prepare batch
    BATCH_SIZE = 25
    results = []
    
    for i in range(0, len(transactions), BATCH_SIZE):
        batch = transactions[i:i+BATCH_SIZE]
        
        # Lightweight JSON payload
        payload = [
            {"id": t['_id'], "desc": t['description'], "amount": t['amount']} 
            for t in batch
        ]
        
        prompt = f"""
        You are a financial assistant.
        1. Categorize these transactions into: [Food, Groceries, Transport, Shopping, Bills, Salary, Income, Health, Entertainment, Transfer, Rent/Mortgage, Savings].
        2. Clean the merchant name (e.g. "MCDONALDS 889 TLV" -> "McDonald's").
        
        CRITICAL RULES:
        - DO NOT TRANSLATE the description. Keep it in the original language (e.g. Hebrew).
        - If the description is "רמי לוי", keep it "רמי לוי". Do NOT change it to "Rami Levy".
        - Only remove transaction IDs, dates, or city names that clutter the merchant name.
        - FIX REVERSED HEBREW: If the text looks like reversed Hebrew (e.g. "תרוכשמ" -> "משכורת", "ג\"פוק" -> "קופ\"ג"), REVERSE IT back to readable Hebrew in the 'clean_desc' field.
        
        CATEGORY RULES:
        - "Groceries": Supermarkets (Shufersal, Rami Levy, Osher Ad, Mega, Victory, Yochananof, Tiv Taam, AM:PM, Super, Market, Makolet).
        - "Food": Restaurants, Cafes, Takeout, Wolt, Ten Bis.
        - "Income": Salary, Benefits, Interest, Refunds, "Crossix", "Solo", "Citi Bank Crossix".
        
        SAVINGS CATEGORY RULES:
        - Deposits to savings accounts (פיקדון, deposit) -> "Savings"
        - Regular savings orders (הוראת קבע לחיסכון, חיסכון) -> "Savings"
        - Provident funds/Pensions (קופת גמל, קופ"ג, ג"פוק, תודקפה) -> "Savings"
        - Stock purchases (company names like "Veea Systems", stock tickers) -> "Savings"
        - Investment contributions (Meitav, מיטב, Altshuler, Psagot) -> "Savings"
        - Internal transfers between checking accounts -> "Transfer"

        TRANSFER vs EXPENSE RULES:
        - "BIT" and "PAYBOX": If description is just "BIT" or "PAYBOX", categorize as "Shopping" (assume expense).
        - "משיכה מבנקט" (ATM Withdrawal): Categorize as "Shopping" (assume cash spending).
        - "העברה" (Transfer): If generic, keep as "Transfer".
        
        Return STRICT JSON array of objects: {{"id": "...", "category": "...", "clean_desc": "..."}}.
        NO Markdown. NO Backticks.
        
        Input:
        {json.dumps(payload)}
        """
        
        try:
            response = model.generate_content(prompt)
            clean_text = response.text.replace("```json", "").replace("```", "").strip()
            
            parsed = json.loads(clean_text)
            
            # Map back to internal format
            for item in parsed:
                results.append({
                    '_id': item['id'],
                    'category': item.get('category', 'Uncategorized'),
                    'description': item.get('clean_desc', item.get('desc', '')) 
                })
                
        except Exception as e:
            err_str = str(e)
            
            # Logic: If 404/Not Found, try fallbacks for this specific batch
            # Logic: If 404/Not Found, try fallbacks for this specific batch
            if "404" in err_str or "not found" in err_str.lower():
                # Safe fallback logging
                try:
                    st.toast(f"Model {current_model_name} failed. Trying fallbacks...", icon="⚠️")
                except:
                    pass
                
                success_fallback = False
                for fallback_name in models_to_try:
                    if fallback_name == current_model_name: continue # Skip failed one
                    
                    try:
                        # st.write(f"Trying fallback model: {fallback_name}")
                        fb_model = genai.GenerativeModel(fallback_name)
                        response = fb_model.generate_content(prompt)
                        clean_text = response.text.replace("```json", "").replace("```", "").strip()
                        parsed = json.loads(clean_text)
                        
                        for item in parsed:
                            results.append({
                                '_id': item['id'],
                                'category': item.get('category', 'Uncategorized'),
                                'description': item.get('clean_desc', item.get('desc', '')) 
                            })
                            
                        # If success, update the main model for next batches to avoid retrying
                        model = fb_model
                        current_model_name = fallback_name
                        success_fallback = True
                        break # Exit fallback loop
                        
                    except Exception as e2:
                        continue
                
                if success_fallback:
                    time.sleep(1) # Rate limit safety
                    continue # Continue to next batch
            
            # If fallbacks failed or it was another error
            error_msg = f"AI Error batch {i}: {str(e)[:100]}" # Truncate to avoid huge errors
            return [], error_msg
            
        # Rate limit safety
        time.sleep(1)
        
    return results, None

def enrich_uncategorized_data():
    """
    Orchestrator: Fetches uncategorized, AI processes, updates DB.
    Returns: (count, error_message)
    """
    # 1. Get API Key
    api_key = None
    if "GEMINI_API_KEY" in st.secrets:
        api_key = st.secrets["GEMINI_API_KEY"]
    elif "gemini" in st.secrets and "api_key" in st.secrets["gemini"]:
        api_key = st.secrets["gemini"]["api_key"]
        
    if not api_key:
        return 0, "Missing GEMINI_API_KEY or [gemini] api_key in secrets.toml"

    # Re-configure to be safe
    genai.configure(api_key=api_key)

    # 2. Fetch Data
    raw_txs = db.get_uncategorized_transactions(limit=50)
    
    if not raw_txs:
        return 0, "No uncategorized transactions found."
        
    # 3. Call AI
    updated_data, error = categorize_transactions(raw_txs)
    
    if error:
        return 0, error
        
    # 4. Save Updates
    if updated_data:
        saved_count = db.update_transaction_batch(updated_data)
        return saved_count, None
    
    return 0, "No data updated."

def _get_previous_period_label(filters: dict) -> str:
    """Generate human-readable label for previous period."""
    from datetime import datetime
    from dateutil.relativedelta import relativedelta
    
    if filters['view_period'] == 'Monthly':
        current_date = datetime.strptime(f"{filters['selected_year']}-{filters['selected_month']:02d}-01", "%Y-%m-%d")
        prev_date = current_date - relativedelta(months=1)
        return prev_date.strftime('%B %Y')
    elif filters['view_period'] == 'Quarterly':
        # Calculate previous quarter
        current_year = filters['selected_year']
        current_month = int(filters['start_date'].split('-')[1])
        current_quarter = (current_month - 1) // 3 + 1
        
        if current_quarter == 1:
            prev_quarter = 4
            prev_year = current_year - 1
        else:
            prev_quarter = current_quarter - 1
            prev_year = current_year
            
        return f"Q{prev_quarter} {prev_year}"
    
    return "Previous Period"

def _get_previous_period_transactions(filters: dict) -> list:
    """Fetch transactions from the previous period based on current filters."""
    from datetime import datetime
    from dateutil.relativedelta import relativedelta
    
    if filters['view_period'] == 'Monthly':
        # Get previous month
        current_date = datetime.strptime(f"{filters['selected_year']}-{filters['selected_month']:02d}-01", "%Y-%m-%d")
        prev_date = current_date - relativedelta(months=1)
        
        # Calculate start and end of previous month
        start_date = prev_date.strftime('%Y-%m-01')
        end_date = (prev_date + relativedelta(months=1) - relativedelta(days=1)).strftime('%Y-%m-%d')
        
    elif filters['view_period'] == 'Quarterly':
        # Calculate previous quarter dates
        current_month = int(filters['start_date'].split('-')[1])
        current_quarter = (current_month - 1) // 3 + 1
        current_year = filters['selected_year']
        
        if current_quarter == 1:
            prev_quarter = 4
            prev_year = current_year - 1
        else:
            prev_quarter = current_quarter - 1
            prev_year = current_year
        
        # Calculate start and end of previous quarter
        prev_start_month = (prev_quarter - 1) * 3 + 1
        start_date = f"{prev_year}-{prev_start_month:02d}-01"
        
        end_month = prev_start_month + 2
        end_date_obj = datetime.strptime(f"{prev_year}-{end_month:02d}-01", "%Y-%m-%d")
        end_date = (end_date_obj + relativedelta(months=1) - relativedelta(days=1)).strftime('%Y-%m-%d')
    else:
        return []
    
    # Fetch transactions for previous period
    return db.get_transactions_by_range(start_date, end_date)

def generate_financial_summary(transactions: list, period_label: str, filters: dict = None) -> tuple[dict, str]:
    """
    Uses Gemini to generate an intelligent financial summary for a period with historical context.
    
    Args:
        transactions: List of transaction dicts with date, amount, description, category
        period_label: Human-readable period (e.g., "December 2025", "Q4 2025")
        filters: Optional filters dict from sidebar to fetch previous period data
    
    Returns:
        (summary_dict, error_message)
        summary_dict contains: summary, insights, unusual_expenses, category_notes, recommendations, joke
    """
    if not transactions:
        return {
            'summary': 'No transactions found for this period.',
            'insights': [],
            'unusual_expenses': [],
            'category_notes': {},
            'recommendations': [],
            'joke': 'No data, no jokes. Add some transactions!'
        }, None
    
    # Get API Key
    api_key = None
    if "GEMINI_API_KEY" in st.secrets:
        api_key = st.secrets["GEMINI_API_KEY"]
    elif "gemini" in st.secrets and "api_key" in st.secrets["gemini"]:
        api_key = st.secrets["gemini"]["api_key"]
        
    if not api_key:
        return {}, "Missing GEMINI_API_KEY in secrets.toml"
    
    genai.configure(api_key=api_key)
    
    # Model Selection Strategy - Gemini 3 Flash with fallbacks
    models_to_try = [
        'gemini-3-flash-preview',
        'gemini-2.0-flash-exp',
        'gemini-1.5-flash'
    ]
    
    # Prepare summary data
    import statistics
    from collections import defaultdict
    from datetime import datetime, timedelta
    from dateutil.relativedelta import relativedelta
    
    total_income = sum(t['amount'] for t in transactions if t['amount'] > 0)
    total_expenses = abs(sum(t['amount'] for t in transactions if t['amount'] < 0))
    net = total_income - total_expenses
    
    # Fetch previous period data for comparison if filters provided
    prev_period_data = None
    if filters:
        prev_transactions = _get_previous_period_transactions(filters)
        if prev_transactions:
            prev_income = sum(t['amount'] for t in prev_transactions if t['amount'] > 0)
            prev_expenses = abs(sum(t['amount'] for t in prev_transactions if t['amount'] < 0))
            prev_net = prev_income - prev_expenses
            
            # Calculate changes
            income_change = ((total_income - prev_income) / prev_income * 100) if prev_income > 0 else 0
            expense_change = ((total_expenses - prev_expenses) / prev_expenses * 100) if prev_expenses > 0 else 0
            
            prev_period_data = {
                'income': prev_income,
                'expenses': prev_expenses,
                'net': prev_net,
                'income_change': income_change,
                'expense_change': expense_change,
                'label': _get_previous_period_label(filters)
            }
    
    # Category breakdown (Align with dashboard.py - exclude IGNORE_CATS and Savings)
    IGNORE_CATS = ['Credit Card Payoff', 'Savings']
    by_category = defaultdict(lambda: {'total': 0, 'count': 0})
    for t in transactions:
        cat = t.get('category', 'Uncategorized')
        if cat in IGNORE_CATS:
            continue
        by_category[cat]['total'] += abs(t['amount'])
        by_category[cat]['count'] += 1
    
    category_summary = {
        cat: f"₪{data['total']:.2f} ({data['count']} txs)" 
        for cat, data in sorted(by_category.items(), key=lambda x: x[1]['total'], reverse=True)
    }
    
    # Statistical analysis for anomalies
    expense_amounts = [abs(t['amount']) for t in transactions if t['amount'] < 0 and t.get('category') not in IGNORE_CATS]
    if expense_amounts:
        mean_expense = statistics.mean(expense_amounts)
        std_expense = statistics.stdev(expense_amounts) if len(expense_amounts) > 1 else 0
        threshold = mean_expense + 2 * std_expense
        
        unusual_txs = [
            {
                'date': t['date'],
                'description': t['description'],
                'amount': t['amount'],
                'category': t.get('category', 'Uncategorized')
            }
            for t in transactions 
            if t['amount'] < 0 and abs(t['amount']) > threshold and t.get('category') not in IGNORE_CATS
        ]
    else:
        unusual_txs = []
    
    # Prepare transaction sample (limit to avoid token overflow)
    tx_sample = transactions[:50] if len(transactions) > 50 else transactions
    tx_list_str = "\n".join([
        f"- {t['date']}: {t['description']} ₪{t['amount']:.2f} [{t.get('category', 'Uncategorized')}]"
        for t in tx_sample
    ])
    
    if len(transactions) > 50:
        tx_list_str += f"\n... and {len(transactions) - 50} more transactions"
    
    # Build prompt
    prompt_parts = [
        f"""You are a personal financial advisor analyzing spending for {period_label}.
Context: You are advising a couple, Yaara (a student) and Dmitry (a software engineer), who live in Kiryat Ono, Israel.

Current Period Data Summary:
- Total Income: ₪{total_income:.2f}
- Total Expenses: ₪{total_expenses:.2f}
- Net (Income - Expenses): ₪{net:.2f}
- Total Transactions: {len(transactions)}
- Categories: {json.dumps(category_summary, indent=2)}
"""
    ]
    
    # Add historical comparison if available
    if prev_period_data:
        income_trend = "↑" if prev_period_data['income_change'] > 0 else "↓" if prev_period_data['income_change'] < 0 else "→"
        expense_trend = "↑" if prev_period_data['expense_change'] > 0 else "↓" if prev_period_data['expense_change'] < 0 else "→"
        
        prompt_parts.append(f"""
Previous Period ({prev_period_data['label']}) Comparison:
- Previous Income: ₪{prev_period_data['income']:.2f}
- Previous Expenses: ₪{prev_period_data['expenses']:.2f}
- Previous Net: ₪{prev_period_data['net']:.2f}

Trends:
- Income Change: {income_trend} {abs(prev_period_data['income_change']):.1f}% ({"+₪" if prev_period_data['income_change'] > 0 else "-₪"}{abs(total_income - prev_period_data['income']):.2f})
- Expense Change: {expense_trend} {abs(prev_period_data['expense_change']):.1f}% ({"+₪" if prev_period_data['expense_change'] > 0 else "-₪"}{abs(total_expenses - prev_period_data['expenses']):.2f})
""")
    
    prompt_parts.append(f"""
Sample Transactions:
{tx_list_str}

Detected Unusual Expenses (>2 std deviations):
{json.dumps([{'desc': u['description'], 'amount': u['amount']} for u in unusual_txs[:5]], indent=2)}

Tasks:
1. Provide 3-5 key insights about spending patterns (e.g., trends, comparisons, observations)
2. {"Compare current period with previous period and highlight significant changes" if prev_period_data else "Analyze the unusual expenses and explain why they might be significant"}
3. Review each major spending category and provide brief commentary
4. Suggest 3-5 actionable recommendations to improve financial health{"based on the trends observed" if prev_period_data else ""}
5. Add a clever joke at the end about their data and their personalities (Dmitry the dev, Yaara the student, living in Kiryat Ono).

CRITICAL RULES:
- Be conversational and helpful, not robotic
- Use specific numbers from the data
- {"Focus on TRENDS and CHANGES from the previous period" if prev_period_data else "If expenses are unusually high in a category, mention it"}
- Keep descriptions in original language (don't translate Hebrew/other languages)
- Focus on actionable insights, not generic advice

Return ONLY valid JSON in this exact format (NO markdown, NO backticks):
{{
  "summary": "2-3 sentence overview of the period{"with comparison to previous period" if prev_period_data else ""}",
  "insights": ["insight 1", "insight 2", "insight 3", ...],
  "unusual_expenses": [{{"description": "...", "amount": -123.45, "reason": "why it's unusual"}}, ...],
  "category_notes": {{"Food": "commentary", "Transport": "commentary", ...}},
  "recommendations": ["recommendation 1", "recommendation 2", ...],
  "joke": "A personalized joke about their finances and life"
}}
""")
    
    prompt = "".join(prompt_parts)
    
    # Try models with fallback logic
    for model_name in models_to_try:
        try:
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.3,
                    max_output_tokens=2048
                )
            )
            
            # Clean response
            clean_text = response.text.replace("```json", "").replace("```", "").strip()
            
            # Parse JSON
            summary_data = json.loads(clean_text)
            
            # Validate structure
            required_keys = ['summary', 'insights', 'unusual_expenses', 'category_notes', 'recommendations', 'joke']
            if all(key in summary_data for key in required_keys):
                return summary_data, None

            else:
                # Missing keys, try next model
                continue
                
        except json.JSONDecodeError as e:
            # JSON parsing failed, try next model
            continue
        except Exception as e:
            err_str = str(e)


            # If 404/not found, try next model
            if "404" in err_str or "not found" in err_str.lower():
                continue
            else:
                # Other error, return it
                return {}, f"AI Error: {str(e)[:200]}"
    
    # All models failed
    return {}, "All AI models failed to generate summary. Please try again later."
