import json
import statistics
from collections import defaultdict

def test_summary_logic():
    transactions = [
        {'date': '2025-12-01', 'description': 'Rent', 'amount': -1500.0, 'category': 'Housing'},
        {'date': '2025-12-05', 'description': 'Salary', 'amount': 5000.0, 'category': 'Salary'},
        {'date': '2025-12-10', 'description': 'Groceries', 'amount': -200.0, 'category': 'Food'},
        {'date': '2025-12-11', 'description': 'Groceries', 'amount': -150.0, 'category': 'Food'},
        {'date': '2025-12-12', 'description': 'Groceries', 'amount': -180.0, 'category': 'Food'},
        {'date': '2025-12-15', 'description': 'Restaurant', 'amount': -2500.0, 'category': 'Food'}, # Very Unusual
    ]

    
    total_income = sum(t['amount'] for t in transactions if t['amount'] > 0)
    total_expenses = abs(sum(t['amount'] for t in transactions if t['amount'] < 0))
    net = total_income - total_expenses
    
    by_category = defaultdict(lambda: {'total': 0, 'count': 0})
    for t in transactions:
        cat = t.get('category', 'Uncategorized')
        by_category[cat]['total'] += abs(t['amount'])
        by_category[cat]['count'] += 1
    
    category_summary = {
        cat: f"${data['total']:.2f} ({data['count']} txs)" 
        for cat, data in sorted(by_category.items(), key=lambda x: x[1]['total'], reverse=True)
    }
    
    expense_amounts = [abs(t['amount']) for t in transactions if t['amount'] < 0]
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
        if t['amount'] < 0 and abs(t['amount']) > threshold
    ]
    
    print("Category Summary:", json.dumps(category_summary, indent=2))
    print("Unusual Txs:", json.dumps([{'desc': u['description'], 'amount': u['amount']} for u in unusual_txs[:5]], indent=2))
    
    prompt = f"""
    Unusual Expenses:
    {json.dumps([{'desc': u['description'], 'amount': u['amount']} for u in unusual_txs[:5]], indent=2)}
    """
    print("Prompt snippet:", prompt)

if __name__ == "__main__":
    test_summary_logic()
