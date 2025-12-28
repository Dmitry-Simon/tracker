# -*- coding: utf-8 -*-
import sys
import os

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src import parsers
import pandas as pd

# Test Isracard file specifically
filepath = os.path.join(os.path.dirname(__file__), 'raw-test-data', '0164_01_2026.xlsx')

print("Testing Isracard parser debugging:")
print("="*80)

df = pd.read_excel(filepath, header=None)
print(f"Total rows: {len(df)}")

# Find header
for idx, row in df.iterrows():
    row_str = " ".join([str(x) for x in row.values])
    if "תאריך רכישה" in row_str and "שם בית עסק" in row_str:
        print(f"\nFound header at row {idx}:")
        print(row.values)
        
        # Test few rows after header  
        print(f"\nFirst 5 data rows after header:")
        for i in range(idx+1, min(idx+6, len(df))):
            row_data = df.iloc[i]
            print(f"Row {i}: {list(row_data.values)[:6]}")
            
            #  Try parsing date
            if not pd.isna(row_data[0]):
                date_val = str(row_data[0]).strip()
                print(f"  Date value: '{date_val}'")
                parsed = parsers.parse_date(date_val)
                print(f"  Parsed: {parsed}")
        break
