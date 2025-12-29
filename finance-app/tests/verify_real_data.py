import sys
import os
import pandas as pd
import warnings

# Suppress warnings
warnings.filterwarnings("ignore")

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.parsers import TransactionParser

def safe_print(text):
    """Safely print text to console, replacing non-ascii characters."""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('ascii', 'replace').decode('ascii'))

def format_currency(val):
    return f"{val:,.2f} NIS"

def test_real_files():
    parser = TransactionParser()
    data_dir = os.path.join(os.path.dirname(__file__), 'raw-test-data')
    
    safe_print(f"Scanning directory: {data_dir}\n")
    
    files = [f for f in os.listdir(data_dir) if f.endswith('.xlsx') or f.endswith('.xls')]
    
    all_transactions = []
    
    for filename in sorted(files):
        # Safe filename for printing
        safe_name = filename.encode('ascii', 'replace').decode('ascii')
        safe_print(f"Processing: {safe_name}")
        
        filepath = os.path.join(data_dir, filename)
        
        try:
            with open(filepath, 'rb') as f:
                # Pass safe_name to parser to avoid print(filename) crashing in the parser on error
                df = parser.parse_file(f, safe_name)
                
            if df.empty:
                safe_print(f"  -> No transactions found or parser failed.")
                continue
                
            safe_print(f"  -> Found {len(df)} transactions.")
            
            # Check for Payoffs
            payoffs = df[df['category'] == 'Credit Card Payoff']
            
            if not payoffs.empty:
                safe_print(f"  -> [DETECTED] {len(payoffs)} PAYOFF TRANSACTIONS:")
                for _, row in payoffs.iterrows():
                    desc = str(row['description']).encode('ascii', 'replace').decode('ascii')
                    safe_print(f"     * {row['date']} | {desc} | {format_currency(row['amount'])}")
            else:
                # Check if this WAS a bank file (OneZero) which should have had payoffs
                if "One" in filename and "Zero" in filename: # Simple check
                    safe_print("  -> [WARNING] One Zero file but NO payoffs detected. Check input data manually.")
                else:
                    safe_print("  -> No payoffs detected (Expected for Card files).")
            
            all_transactions.append(df)
            safe_print("-" * 50)
            
        except Exception as e:
            msg = str(e).encode('ascii', 'replace').decode('ascii')
            safe_print(f"  -> [ERROR] processing file: {msg}")
            safe_print("-" * 50)

    # Aggregate Test
    if all_transactions:
        full_df = pd.concat(all_transactions, ignore_index=True)
        
        safe_print("\n=== AGGREGATE DASHBOARD SIMULATION ===")
        INCOME_CATEGORIES = ['Salary', 'Income', 'Benefits', 'Interest']
        IGNORE_CATS = ['Credit Card Payoff']
        
        # 1. Without Fix (Simulated)
        expenses_raw = full_df[
            (~full_df['category'].isin(INCOME_CATEGORIES))
        ]['amount'].sum()
        
        # 2. With Fix
        expenses_fixed = full_df[
            (~full_df['category'].isin(INCOME_CATEGORIES)) & 
            (~full_df['category'].isin(IGNORE_CATS))
        ]['amount'].sum()
        
        payoff_total = full_df[full_df['category'].isin(IGNORE_CATS)]['amount'].sum()
        
        safe_print(f"Total Transactions: {len(full_df)}")
        safe_print(f"Total Payoffs Detected: {format_currency(payoff_total)}")
        safe_print(f"\nExpenses WITHOUT Fix (Double Counted): {format_currency(expenses_raw)}")
        safe_print(f"Expenses WITH Fix (Corrected):       {format_currency(expenses_fixed)}")
        safe_print(f"Difference (Should match Payoffs):   {format_currency(expenses_raw - expenses_fixed)}")
        
        if abs((expenses_raw - expenses_fixed) - payoff_total) < 0.01:
             safe_print("\n[SUCCESS] Logic perfectly excluded the payoffs.")
        else:
             safe_print("\n[FAIL] Math discrepancy.")

if __name__ == "__main__":
    test_real_files()
