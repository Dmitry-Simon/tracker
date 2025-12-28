# -*- coding: utf-8 -*-
"""
Test real data files WITHOUT mocking - requires actual dependencies installed
"""
import sys
import os

# Set UTF-8 encoding for stdout
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    import pandas as pd
    import pdfplumber
    print("✓ Required libraries available")
except ImportError as e:
    print(f"✗ Missing library: {e}")
    print("Please run: pip install pandas openpyxl pdfplumber")
    sys.exit(1)

# Test files from raw-test-data
test_data_dir = os.path.join(os.path.dirname(__file__), 'raw-test-data')

if os.path.exists(test_data_dir):
    files = os.listdir(test_data_dir)
    print(f"\nFound {len(files)} test files:\n")
    
    for filename in files:
        print(f"{'='*80}")
        print(f"File: {filename}")
        print(f"{'='*80}")
        filepath = os.path.join(test_data_dir, filename)
        
        try:
            # XLSX files - peek at structure
            if filename.endswith('.xlsx'):
                print("\n[1] Peeking at file structure (first 15 rows):")
                df_peek = pd.read_excel(filepath, header=None, nrows=15)
                print(df_peek.to_string(max_colwidth=50))
                
                print("\n[2] Looking for detection keywords:")
                file_content_str = df_peek.to_string()
                
                # Check Max detection
                if "שם בית העסק" in file_content_str and "4 ספרות אחרונות" in file_content_str:
                    print("  → Detected as MAX IT FINANCE")
                # Check Isracard detection  
                elif "תאריך רכישה" in file_content_str and "שם בית עסק" in file_content_str:
                    print("  → Detected as ISRACARD/MASTERCARD")
                else:
                    print("  → UNKNOWN FORMAT (no matching headers)")
                    print(f"    Content sample: {file_content_str[:200]}")
                    
            # PDF files - peek at text
            elif filename.endswith('.pdf'):
                print("\n[1] Extracting PDF text (first page, first 1000 chars):")
                with pdfplumber.open(filepath) as pdf:
                    if pdf.pages:
                        text = pdf.pages[0].extract_text()
                        print(text[:1000] if text else "(No text extracted)")
                        
                        print("\n[2] Looking for One Zero pattern:")
                        import re
                        pattern = re.compile(r'"([\d,]+\.?\d*)"\s*,\s*"([\d,]+\.?\d*)"\s*,\s*"([\d,]+\.?\d*)"\s*,\s*"(.*?)"\s*,\s*"(\d{2}/\d{2}/\d{4})"\s*,\s*"(\d{2}/\d{2}/\d{4})"')
                        matches = pattern.findall(text[:2000] if text else "")
                        if matches:
                            print(f"  → Found {len(matches)} matches in first 2000 chars")
                        else:
                            print("  → NO MATCHES found (PDF might have different format)")
                            
        except Exception as e:
            print(f"\n[ERROR] {e}")
            import traceback
            traceback.print_exc()
        
        print("\n")
else:
    print(f"[ERROR] Directory not found: {test_data_dir}")
