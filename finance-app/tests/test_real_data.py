# -*- coding: utf-8 -*-
import sys
import os
import io
from unittest.mock import MagicMock

# Set UTF-8 encoding for stdout
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

# MOCK Dependencies BEFORE import
sys.modules['pdfplumber'] = MagicMock()
sys.modules['firebase_admin'] = MagicMock()
sys.modules['firebase_admin.credentials'] = MagicMock()
sys.modules['firebase_admin.firestore'] = MagicMock()
sys.modules['google.generativeai'] = MagicMock()
sys.modules['streamlit'] = MagicMock()
sys.modules['openpyxl'] = MagicMock()

# Ensure streamlit secrets dict exists in mock
sys.modules['streamlit'].secrets = {}

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src import parsers
import pandas as pd

# Test files from raw-test-data
test_data_dir = os.path.join(os.path.dirname(__file__), 'raw-test-data')

if os.path.exists(test_data_dir):
    files = os.listdir(test_data_dir)
    print(f"Found {len(files)} test files:\n")
    
    for filename in files:
        try:
            # Use repr to safely print filename
            print(f"Testing: {repr(filename)}")
            filepath = os.path.join(test_data_dir, filename)
            
            # First, peek at the file structure
            if filename.endswith('.xlsx'):
                df_peek = pd.read_excel(filepath, header=None, nrows=10)
                print("  First 10 rows (header=None):")
                print(df_peek.to_string(max_colwidth=40))
                print()
                
            # Now try parser
            with open(filepath, 'rb') as f:
                transactions = parsers.detect_and_parse(f, filename)
                
            print(f"  [OK] Parsed {len(transactions)} transactions")
            
            if transactions:
                # Show first 3 transactions
                for i, tx in enumerate(transactions[:3]):
                    desc = tx['description'][:40] if len(tx['description']) > 40 else tx['description']
                    print(f"    {i+1}. {tx['date']} | {desc:40s} | {tx['amount']:>10.2f}")
                
                # Show summary stats
                expenses = [t for t in transactions if t['amount'] < 0]
                income = [t for t in transactions if t['amount'] > 0]
                
                total_expense = sum(t['amount'] for t in expenses)
                total_income = sum(t['amount'] for t in income)
                
                print(f"  Summary: {len(expenses)} expenses ({total_expense:.2f}), {len(income)} income ({total_income:.2f})")
            else:
                print("  [WARNING] No transactions found - check detection logic")
                
        except Exception as e:
            print(f"  [ERROR] {e}")
            import traceback
            traceback.print_exc()
        
        print("\n" + "="*80 + "\n")
else:
    print(f"[ERROR] Directory not found: {test_data_dir}")
