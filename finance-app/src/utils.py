import pandas as pd
from datetime import datetime
from src.constants import INCOME_CATEGORIES, SAVINGS_CATEGORIES, IGNORE_CATS_METRIC

def calculate_metrics(transactions):
    """
    Calculates consistent financial metrics across the application.
    
    Args:
        transactions (list): List of transaction dictionaries.
        
    Returns:
        dict: Dictionary containing income, expenses, net, savings, and count.
    """
    if not transactions:
        return {
            'income': 0.0,
            'expenses': 0.0,
            'savings': 0.0,
            'net': 0.0,
            'count': 0
        }
        
    df = pd.DataFrame(transactions)
    df['amount'] = pd.to_numeric(df['amount'])
    
    IGNORE_CATS = IGNORE_CATS_METRIC
    
    # Calculate Income
    income = df[df['category'].isin(INCOME_CATEGORIES)]['amount'].sum()
    
    # Calculate Savings (Gross - only deposits/negative values)
    # We want to show how much was PUT into savings, ignoring withdrawals for this metric
    savings_df = df[df['category'].isin(SAVINGS_CATEGORIES)]
    savings_amount = savings_df[savings_df['amount'] < 0]['amount'].sum()
    savings = abs(savings_amount)
    
    # Calculate Expenses (exclude income, ignored cats, and savings)
    expenses_net = df[
        (~df['category'].isin(INCOME_CATEGORIES)) & 
        (~df['category'].isin(IGNORE_CATS)) &
        (~df['category'].isin(SAVINGS_CATEGORIES))
    ]['amount'].sum()
    
    # Net calculation: Income - Expenses
    # Savings are already excluded from expenses, so net represents total available
    # (which includes both explicit savings and leftover money)
    net = income + expenses_net  # expenses_net is negative, so this is Income - Expenses
    
    return {
        'income': float(income),
        'expenses': float(abs(expenses_net)),
        'savings': float(savings),
        'net': float(net),
        'count': len(transactions)
    }

def calculate_category_averages(transactions, period_type='Monthly'):
    """
    Calculates average spending per category based on the period type.
    
    Args:
        transactions (list): List of all historical transactions.
        period_type (str): 'Monthly', 'Quarterly', 'Half Year', or 'Yearly'.
        
    Returns:
        dict: {category: average_amount}
    """
    if not transactions:
        return {}
        
    df = pd.DataFrame(transactions)
    df['amount'] = pd.to_numeric(df['amount'])
    df['date'] = pd.to_datetime(df['date'])
    
    IGNORE_CATS = IGNORE_CATS_METRIC + INCOME_CATEGORIES
    df_expenses = df[
        (df['amount'] < 0) & 
        (~df['category'].isin(IGNORE_CATS))
    ].copy()
    
    if df_expenses.empty:
        return {}
        
    df_expenses['abs_amount'] = df_expenses['amount'].abs()
    
    # Group by period to get totals per period
    if period_type == 'Monthly':
        df_expenses['period'] = df_expenses['date'].dt.to_period('M')
    elif period_type == 'Quarterly':
        df_expenses['period'] = df_expenses['date'].dt.to_period('Q')
    elif period_type == 'Half Year':
        # Custom period for Half Year not directly supported by pandas period, use string
        df_expenses['period'] = df_expenses['date'].apply(lambda x: f"{x.year}-H{1 if x.month <= 6 else 2}")
    elif period_type == 'Yearly':
        df_expenses['period'] = df_expenses['date'].dt.to_period('Y')
    else:
        df_expenses['period'] = df_expenses['date'].dt.to_period('M') # Default
        
    # Calculate total per category per period
    cat_period_totals = df_expenses.groupby(['category', 'period'])['abs_amount'].sum().reset_index()
    
    # Filter out the CURRENT period from the average calculation to avoid skewing with incomplete data
    # e.g. If we are in Jan 2026, the 2026 yearly total is tiny, dragging down the average.
    now = datetime.now()
    current_period = None
    
    if period_type == 'Monthly':
        current_period = pd.Period(now, freq='M')
    elif period_type == 'Quarterly':
        current_period = pd.Period(now, freq='Q')
    elif period_type == 'Yearly':
        current_period = pd.Period(now, freq='Y')
    elif period_type == 'Half Year':
        current_period = f"{now.year}-H{1 if now.month <= 6 else 2}"
        
    if current_period is not None:
        # Check if we have data other than the current period
        # If we ONLY have the current period, we must keep it (otherwise average is 0/empty)
        # If we have history + current, we exclude current.
        
        # Create a mask for exclusion
        if period_type == 'Half Year':
             mask = cat_period_totals['period'] != current_period
        else:
             mask = cat_period_totals['period'] != current_period
             
        filtered_totals = cat_period_totals[mask]
        
        # If filtering leaves us with data, use it. Otherwise (new user case), revert to original.
        if not filtered_totals.empty:
            cat_period_totals = filtered_totals

    # Calculate average across all periods found
    cat_averages = cat_period_totals.groupby('category')['abs_amount'].mean().to_dict()
    
    return cat_averages
