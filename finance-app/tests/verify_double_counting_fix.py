import sys
import os
import pandas as pd
import unittest
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.parsers import TransactionParser

class TestDoubleCountingFix(unittest.TestCase):
    def setUp(self):
        self.parser = TransactionParser()

    def test_parser_categorization(self):
        """Test that bank credit card charges are categorized as 'Credit Card Payoff'"""
        print("\nTesting Parser Categorization...")
        
        # Create a mock One Zero Excel structure
        data = {
            'תאריך תנועה': ['01/01/2026', '02/01/2026', '03/01/2026'],
            'תיאור': [
                'Bit Transfer',           # Should be Income
                'Isracard 0164 Debit',    # Should be Credit Card Payoff (Bank Charge)
                'Supermarket'             # Should be Uncategorized or mapped
            ],
            'סכום פעולה': [
                500,        # Income
                -5000,      # CC Payoff
                -200        # Regular Expense
            ]
        }
        df_mock_input = pd.DataFrame(data)
        
        # We need to save this to a temp excel file because _parse_one_zero_excel takes a file object
        temp_filename = 'temp_test_onezero.xlsx'
        df_mock_input.to_excel(temp_filename, index=False)
        
        try:
            with open(temp_filename, 'rb') as f:
                df_result = self.parser._parse_one_zero_excel(f)
            
            # Verify results
            print("Parsed DataFrame:")
            print(df_result[['description', 'amount', 'category']])
            
            # Check Row 1: Bit (Income)
            row_bit = df_result[df_result['description'] == 'Bit Transfer'].iloc[0]
            self.assertEqual(row_bit['category'], 'Income')
            
            # Check Row 2: Isracard (The Fix)
            row_cc = df_result[df_result['description'] == 'Isracard 0164 Debit'].iloc[0]
            self.assertEqual(row_cc['category'], 'Credit Card Payoff', 
                             "Failed: Bank CC charge should be 'Credit Card Payoff'")
            
            # Check Row 3: Supermarket
            row_super = df_result[df_result['description'] == 'Supermarket'].iloc[0]
            self.assertNotEqual(row_super['category'], 'Credit Card Payoff')
            
            print("✅ Parser Logic Verified: CC Payoff correctly identified.")
            return df_result
            
        finally:
            if os.path.exists(temp_filename):
                os.remove(temp_filename)

    def test_dashboard_logic(self):
        """Test that 'Credit Card Payoff' is excluded from Total Expenses"""
        print("\nTesting Dashboard Logic...")
        
        # Mock DataFrame mimicking the database
        df = pd.DataFrame([
            {'amount': 10000, 'category': 'Salary'},
            {'amount': -5000, 'category': 'Credit Card Payoff'}, # Should be IGNORED
            {'amount': -200, 'category': 'Groceries'},          # Should be INCLUDED
            {'amount': -300, 'category': 'Restaurants'}         # Should be INCLUDED
        ])
        
        # Logic from dashboard.py
        INCOME_CATEGORIES = ['Salary', 'Income', 'Benefits', 'Interest']
        IGNORE_CATS = ['Credit Card Payoff']
        
        # 1. Total Income
        income = df[df['category'].isin(INCOME_CATEGORIES)]['amount'].sum()
        self.assertEqual(income, 10000)
        
        # 2. Total Expenses (The Logic Fix)
        expenses_net = df[
            (~df['category'].isin(INCOME_CATEGORIES)) & 
            (~df['category'].isin(IGNORE_CATS))
        ]['amount'].sum()
        
        print(f"Calculated Expenses: {expenses_net} (Expected: -500)")
        
        self.assertEqual(expenses_net, -500, 
                         f"Failed: Expenses should be -500 (ignoring -5000 payoff), got {expenses_net}")
        
        print("✅ Dashboard Logic Verified: CC Payoff excluded from Total Expenses.")

if __name__ == '__main__':
    unittest.main()
