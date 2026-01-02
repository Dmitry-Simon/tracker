import pandas as pd

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
    
    # Define categories
    INCOME_CATEGORIES = ['Salary', 'Income', 'Benefits', 'Interest']
    IGNORE_CATS = ['Credit Card Payoff']
    SAVINGS_CATEGORIES = ['Savings']
    
    # Calculate Income
    income = df[df['category'].isin(INCOME_CATEGORIES)]['amount'].sum()
    
    # Calculate Savings (take absolute value to show as positive)
    savings_amount = df[df['category'].isin(SAVINGS_CATEGORIES)]['amount'].sum()
    savings = abs(savings_amount)  # Show as positive number
    
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
