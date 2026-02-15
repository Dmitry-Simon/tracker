import pdfplumber
import pandas as pd
import re
from datetime import datetime
from src import db  # Import db to use the exact same hash function
from src.constants import get_card_patterns

class TransactionParser:
    def __init__(self, default_spender="Joint"):
        self.default_spender = default_spender
        self.card_patterns = get_card_patterns()
    
    def detect_spender(self, description):
        """
        Detects the spender from card patterns in the description.
        Returns the spender name if a pattern is found, otherwise returns the default spender.
        """
        if not description:
            return self.default_spender
        
        desc_str = str(description)
        
        # Check for each card pattern in the description
        for card_num, spender in self.card_patterns.items():
            if card_num in desc_str:
                return spender
        
        # No pattern found, return default
        return self.default_spender
        
    def detect_file_owner(self, content_str):
        """
        Scans the entire file content to guess the owner.
        Used to set the default spender for the file if not explicitly provided.
        """
        if not content_str:
            return None
            
        counts = {}
        for card, spender in self.card_patterns.items():
            counts[spender] = counts.get(spender, 0) + content_str.count(card)
            
        # Filter to found patterns
        found = {k: v for k, v in counts.items() if v > 0}
        
        if not found:
            return None
            
        # If only one spender found, that's the owner
        if len(found) == 1:
            return list(found.keys())[0]
            
        # If mixed, check if one is significantly dominant?
        # Or just return None (Joint)
        # For now, simplistic check: if we have mixed, treat as Joint/Default
        return "Joint"

    def generate_hash_id(self, row):
        """
        Creates a unique fingerprint using the central logic in db.py.
        """
        return db.generate_hash_id(
            row['date'], 
            row['amount'], 
            row['description'],
            row.get('ref_id') # Pass ref_id if available
        )

    def parse_date(self, date_str):
        """
        Tries multiple common Israeli date formats.
        """
        if not isinstance(date_str, str):
            return date_str
            
        formats = [
            "%d/%m/%Y", "%d-%m-%Y", 
            "%d.%m.%Y", "%d.%m.%y",
            "%d/%m/%y",  # Added for Isracard PDF format (DD/MM/YY)
            "%Y-%m-%d"
        ]
        
        date_str = str(date_str).strip()
        
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt).strftime('%Y-%m-%d')
            except ValueError:
                continue
        return None

    def clean_amount(self, val_str):
        """
        Cleans currency strings with heavy Hebrew/Formatting noise.
        """
        if pd.isna(val_str) or val_str is None:
            return 0.0
            
        s = str(val_str).strip()
        
        # Specific fix for One Zero "Zero" artifact "ס ש""ח" or "ס"
        if s.startswith('ס') or 'ס ש' in s:
            if not any(char.isdigit() for char in s):
                return 0.0

        # Remove currency symbols and noise
        s = s.replace('ש""ח', '').replace('ש"ח', '').replace('₪', '').replace('ח"ש', '')
        s = s.replace(',', '').replace('"', '').replace("'", "")
        
        # Remove any remaining non-numeric chars (except dot and minus)
        s = re.sub(r'[^\d\.\-]', '', s)
        
        if not s:
            return 0.0
            
        try:
            return float(s)
        except (ValueError, TypeError):
            return 0.0

    def parse_file(self, file_obj, filename):
        """
        Router: Detects file type and delegates to specific parser.
        """
        filename_lower = filename.lower()
        
        try:
            if filename_lower.endswith('.pdf'):
                # Heuristic to distinguish PDF types using first page text
                try:
                    with pdfplumber.open(file_obj) as pdf:
                        if not pdf.pages:
                            return pd.DataFrame()
                        first_page_text = pdf.pages[0].extract_text() or ""
                        
                        if "isracard" in first_page_text.lower() or "ישראכרט" in first_page_text:
                             file_obj.seek(0)
                             df_result = self._parse_isracard_pdf(file_obj)
                        else:
                             # Default to One Zero for now if not explicitly Isracard
                             file_obj.seek(0)
                             df_result = self._parse_one_zero_pdf(file_obj)
                        
                        # Add uploaded_from field
                        if not df_result.empty:
                            df_result['uploaded_from'] = filename
                        return df_result
                except Exception as e:
                    print(f"Error detecting PDF type for {filename}: {e}")
                    return pd.DataFrame()
            
            # Excel/CSV Router
            try:
                # Try reading as CSV first
                try:
                    df_temp = pd.read_csv(file_obj, header=None, names=list(range(30)), encoding='utf-8')
                except Exception:
                    file_obj.seek(0)
                    df_temp = pd.read_excel(file_obj, header=None)
                
                content_str = df_temp.to_string()
                
                # Check signatures (Priority: One Zero -> Max -> Isracard)
                # 1. One Zero Excel (New - Prioritize)
                if "תאריך תנועה" in content_str and "סכום פעולה" in content_str:
                    file_obj.seek(0)
                    df_result = self._parse_one_zero_excel(file_obj)
                
                # 2. Max Finance
                elif "שם בית העסק" in content_str and "4 ספרות אחרונות" in content_str:
                    file_obj.seek(0)
                    df_result = self._parse_max_finance(file_obj)
                
                # 3. Isracard
                elif "תאריך רכישה" in content_str or "שם בית עסק" in content_str:
                    file_obj.seek(0)
                    df_result = self._parse_isracard(file_obj)
                
                else:
                    print(f"Unknown CSV format for {filename}")
                    return pd.DataFrame()
                    
                # Add uploaded_from field
                if not df_result.empty:
                    df_result['uploaded_from'] = filename
                return df_result

            except Exception as e:
                print(f"Error reading {filename}: {e}")
                return pd.DataFrame()

        except Exception as e:
            print(f"Critical error parsing {filename}: {e}")
            return pd.DataFrame()


    def _parse_one_zero_pdf(self, file_obj):
        """
        Parses One Zero PDF using Table Extraction.
        More robust against RTL and Balance/Amount confusion.
        """
        transactions = []
        
        with pdfplumber.open(file_obj) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables()
                
                for table in tables:
                    # 1. Column Detection
                    # We need to find which index corresponds to what.
                    # Standard OneZero Header (RTL turned to List): ['Date', 'Value Date', 'Description', 'Ref', 'Debit', 'Credit', 'Balance'] (Approx)
                    # Hebrew Headers: תאריך, תאריך ערך, תיאור, אסמכתא, חובה, זכות, יתרה
                    
                    headers = None
                    col_map = {}
                    
                    # Try to find header row
                    for row_idx, row in enumerate(table):
                        # Clean row for check
                        row_clean = [str(c).replace('\n', ' ').strip() for c in row if c]
                        row_str = " ".join(row_clean)
                        
                        if 'תאריך' in row_str and ('חובה' in row_str or 'זכות' in row_str or 'יתרה' in row_str):
                            headers = row
                            break
                    
                    # Map columns if header found
                    if headers:
                        for idx, cell in enumerate(headers):
                            if not cell: continue
                            val = str(cell).replace('\n', ' ').strip()
                            if 'תאריך' in val and 'ערך' not in val: col_map['date'] = idx
                            elif 'תיאור' in val or 'פעולה' in val: col_map['desc'] = idx
                            elif 'חובה' in val: col_map['debit'] = idx # Expense
                            elif 'זכות' in val: col_map['credit'] = idx # Income
                            elif 'יתרה' in val: col_map['balance'] = idx
                            elif 'אסמכתא' in val: col_map['ref'] = idx # Reference ID
                    
                    # Default Mapping fallback (based on visual inspection of common RTL PDF tables)
                    # Often: [Date, ValueDate, Description, Ref, Debit, Credit, Balance]
                    # BUT RTL sometimes reverses: [Balance, Credit, Debit, Ref, Description, ValueDate, Date]
                    # We will try to infer from data if map is empty/incomplete.
                    
                    # Iterate Data Rows
                    row_idx = row_idx if headers else -1
                    start_row = row_idx + 1
                    
                    for i in range(start_row, len(table)):
                        row = table[i]
                        # Skip empty rows
                        if not any(row): continue
                        
                        # Data Extraction
                        date_val = None
                        desc_val = ""
                        amount_val = 0.0
                        
                        # 1. GET DATE
                        if 'date' in col_map:
                            date_val = row[col_map['date']]
                        else:
                            # Heuristic: Find the column looking like a date
                            for idx, cell in enumerate(row):
                                if cell and re.match(r'\d{2}[/.]\d{2}[/.]\d{4}', str(cell).strip()):
                                    date_val = cell
                                    col_map['date'] = idx # Learn for next rows
                                    break
                        
                        if not date_val: continue # Skip if no date found
                        
                        # 2. GET AMOUNT
                        # We prefer calculating from Debit/Credit columns if known
                        debit = 0.0
                        credit = 0.0
                        
                        if 'debit' in col_map and 'credit' in col_map:
                            d_cell = row[col_map['debit']]
                            c_cell = row[col_map['credit']]
                            debit = self.clean_amount(d_cell)
                            credit = self.clean_amount(c_cell)
                            
                            # Logic: Debit is negative, Credit is positive
                            # If both exist (rare), sum them? Usually one is empty/zero.
                            if debit != 0:
                                amount_val = -1 * abs(debit)
                            elif credit != 0:
                                amount_val = abs(credit)
                                
                        else:
                            # No explicit cols found? Fallback to Heuristic Number Search
                            # BUT explicit requested to ignore Balance.
                            # We must identify Balance by position if possible? 
                            # If we can't map columns, this fallback is risky as per the bug report.
                            # Let's try to assume standard layout if no headers found.
                            # Standard RTL OneZero: cols 4=Debit, 5=Credit usually? 
                            # Let's skip fallback and ensure we find columns or skip.
                            # Actually, let's look for numbers.
                            # If we have 3 numbers, usually Debit, Credit, Balance.
                            # Balance is usually the LAST (or FIRST in RTL) column with a number.
                            pass

                        # If amount is still 0 (maybe no column map), try finding numbers and guessing.
                        # OneZero Bug Assumption: Balance was being picked up.
                        # If we have a map, we are safe.
                        # If we don't, we are risky.
                        if amount_val == 0.0 and 'debit' not in col_map:
                             # Try to find columns compatible with money
                             potential_nums = []
                             for idx, cell in enumerate(row):
                                 if idx == col_map.get('date'): continue
                                 # Clean
                                 v = self.clean_amount(cell)
                                 if v != 0:
                                    potential_nums.append((idx, v))
                             
                             # If we have numbers, which is which?
                             # In OneZero, Debit and Credit are usually adjacent. Balance is distinct.
                             # If we have 1 number -> could be anything.
                             # If we have 2 numbers -> likely Amount and Balance.
                             # If user says "Balance often comes first visually", in list it might be last index (RTL)?
                             # Or index 0?
                             # Let's skip rows where we can't identify Debit/Credit cols with certainty to avoid the bug.
                             # But this might skip everything if header parsing fails.
                             # Let's try to infer from header row again or just fail safely.
                             pass

                        if amount_val == 0.0 and abs(debit) < 0.001 and abs(credit) < 0.001:
                            continue # Skip empty transaction

                        # 3. GET DESCRIPTION
                        if 'desc' in col_map:
                            desc_val = row[col_map['desc']]
                        else:
                            # Concatenate text columns that aren't date or numbers
                            parts = []
                            for idx, cell in enumerate(row):
                                if idx in col_map.values(): continue # Skip known cols
                                if not cell: continue
                                s = str(cell).strip()
                                if re.match(r'^-?[\d,.]+$', s): continue # Skip numbers
                                parts.append(s)
                            desc_val = " ".join(parts)

                        # Clean Description
                        if desc_val:
                            desc_val = str(desc_val).replace('\n', ' ')
                            # Remove artifacts
                            for noise in ['ש"ח', 'ש”ח', '00.0', 'NIS', '/']:
                                desc_val = desc_val.replace(noise, ' ')
                            # Remove Ref numbers (long digits)
                            desc_val = re.sub(r'\b\d{5,}\b', '', desc_val)
                            desc_val = " ".join(desc_val.split()) # Collapse spaces

                        if not desc_val or len(desc_val) < 2:
                             desc_val = "OneZero Transaction"

                        # 4. CATEGORIZATION (Preserved Logic)
                        category = 'Uncategorized'
                        desc_lower = desc_val.lower()
                        
                        if 'משכורת' in desc_val or 'ממופ"ת' in desc_val or 'salary' in desc_lower:
                            category = 'Salary'
                        elif 'ביטוח לאומי' in desc_val:
                            category = 'Benefits'
                        elif amount_val > 0 and ('העברה' in desc_val or 'bit' in desc_lower or 'paybox' in desc_lower):
                            category = 'Income'
                        
                        elif amount_val < 0:
                            # Detect Credit Card Payoff (Bank charges)
                            keywords = ['isracard', 'ישראכרט', 'max', 'מקס', 'cal', 'כאל', 'visa', 'ויזה', 'amex', '0164', '1973']
                            if any(k in desc_lower for k in keywords):
                                category = 'Credit Card Payoff'

                        # 5. GET REF ID
                        ref_val = None
                        if 'ref' in col_map:
                            ref_str = str(row[col_map['ref']]).strip()
                            if ref_str and ref_str != 'nan':
                                ref_val = ref_str

                        # Parse Date
                        parsed_date = self.parse_date(date_val)
                        if parsed_date:
                            # Detect spender from card pattern
                            spender = self.detect_spender(desc_val)
                            
                            transactions.append({
                                'date': parsed_date,
                                'description': desc_val,
                                'amount': amount_val,
                                'category': category,
                                'currency': 'ILS',
                                'source_file': 'OneZero_Table',
                                'spender': spender,
                                'ref_id': ref_val
                            })
        
        df = pd.DataFrame(transactions)
        if not df.empty:
            df['hash_id'] = df.apply(self.generate_hash_id, axis=1)
            
        return df

    def _parse_one_zero_excel(self, file_obj):
        """
        Parses One Zero Excel Export (.xlsx or .xls).
        Handles Excel serial dates and pre-signed amounts.
        """
        transactions = []
        
        try:
            file_obj.seek(0)
            df = pd.read_excel(file_obj)
            
            # Auto-detect file owner from content
            detected_owner = self.detect_file_owner(df.astype(str).to_string())
            if detected_owner and detected_owner != "Joint":
                self.default_spender = detected_owner
            
            # Column Detection
            # Hebrew Headers: תאריך תנועה, תאריך ערך, סוג פעולה, תיאור, סכום פעולה, מטבע, חיוב/זיכוי, יתרה, אסמכתא
            date_col = None
            desc_col = None
            amount_col = None
            debit_credit_col = None
            ref_col = None
            bank_category_col = None  # סוג פעולה - Bank's transaction type
            
            for col in df.columns:
                col_str = str(col).strip()
                if 'תאריך' in col_str:
                    if 'תנועה' in col_str and not date_col:  # Prefer תאריך תנועה
                        date_col = col
                    elif not date_col and 'ערך' not in col_str:  # Fallback
                        date_col = col
                if 'תיאור' in col_str:
                    desc_col = col
                if 'סכום' in col_str:
                    if 'פעולה' in col_str:  # Prefer סכום פעולה
                        amount_col = col
                    elif not amount_col:  # Fallback to any סכום
                        amount_col = col
                if 'חיוב' in col_str or 'זיכוי' in col_str:
                    debit_credit_col = col
                if 'אסמכתא' in col_str:
                    ref_col = col
                if 'סוג פעולה' in col_str or 'סוג' in col_str and 'פעולה' in col_str:
                    bank_category_col = col
            
            if not (date_col and desc_col and amount_col):
                print(f"One Zero Excel: Missing required columns")
                print(f"  date_col: {date_col}")
                print(f"  desc_col: {desc_col}")
                print(f"  amount_col: {amount_col}")
                return pd.DataFrame()
            
            for _, row in df.iterrows():
                # Skip empty rows
                if pd.isna(row[desc_col]):
                    continue
                
                # 1. DATE - Handle Excel Serial Numbers OR Datetime Objects
                date_val = row[date_col]
                parsed_date = None
                
                if pd.notna(date_val):
                    # Check if it's already a datetime object
                    if isinstance(date_val, pd.Timestamp):
                        parsed_date = date_val.strftime('%Y-%m-%d')
                    # Check if it's a float (Excel serial)
                    elif isinstance(date_val, (int, float)):
                        try:
                            # Convert Excel serial to datetime
                            dt = pd.to_datetime(date_val, unit='D', origin='1899-12-30')
                            parsed_date = dt.strftime('%Y-%m-%d')
                        except (ValueError, TypeError):
                            pass
                    else:
                        # Try parsing as string
                        parsed_date = self.parse_date(str(date_val))
                
                if not parsed_date:
                    continue
                
                # 2. AMOUNT
                amount_val = self.clean_amount(row[amount_col])
                
                # CRITICAL: OneZero Excel exports already have signed amounts!
                # Debit transactions are already negative (-720.78)
                # Credit transactions are already positive (164.9)
                # We should NOT modify the sign based on חיוב/זיכוי column
                # The column exists but is redundant/confirmation only.
                
                # If the file format changes and amounts become unsigned, 
                # the logic below can be uncommented:
                '''
                if debit_credit_col and pd.notna(row[debit_credit_col]):
                    direction = str(row[debit_credit_col]).strip()
                    if 'חיוב' in direction:
                        # Debit - ensure negative
                        amount_val = -1 * abs(amount_val)
                    elif 'זיכוי' in direction:
                        # Credit - ensure positive
                        amount_val = abs(amount_val)
                '''
                
                # The amounts are already correctly signed, so just keep them as-is
                
                # 3. DESCRIPTION
                desc_val = str(row[desc_col]).strip()
                
                # Handling Reversed Hebrew (Visual Encoding in Excel)
                # The analysis showed that One Zero Excel exports often have reversed Hebrew: 'תרוכשמ' instead of 'משכורת'.
                # However, English words might be correct in the raw string.
                # Heuristic: Create a "working" description for searching, but try to fix the display description if needed.
                
                desc_reversed = desc_val[::-1]
                
                # Check which one looks "more correct" for Hebrew?
                # If we find valid Hebrew words in the reversed string, we use that for categorization.
                
                # Clean artifacts
                for noise in ['ש"ח', 'ש"ח', 'NIS', '/']:
                    desc_val = desc_val.replace(noise, ' ')
                    desc_reversed = desc_reversed.replace(noise[::-1], ' ').replace(noise, ' ') # Remove reversed noise too
                    
                desc_val = re.sub(r'\b\d{5,}\b', '', desc_val)
                desc_val = " ".join(desc_val.split())
                
                if not desc_val or len(desc_val) < 2:
                    desc_val = "OneZero Transaction"
                
                # 4. AUTO-CATEGORIZATION
                category = 'Uncategorized'
                
                # Search keywords in BOTH raw and reversed strings to cover all cases
                search_text = (desc_val + " " + desc_reversed).lower()
                
                # 1. Salary
                if 'משכורת' in search_text or 'salary' in search_text or 'ממופ"ת' in search_text or 'מופ"ת' in search_text or 'מופת' in search_text:
                    category = 'Salary'
                # 2. Benefits / Reserves
                elif 'ביטוח לאומי' in search_text or 'בטוח לאומי' in search_text or 'ב"ל' in search_text or 'מילואים' in search_text or 'מענק' in search_text:
                    category = 'Benefits'
                # 3. Pension / Provident Funds
                elif 'משהבט' in search_text or 'קופ"ג' in search_text or 'פנסיה' in search_text:
                    category = 'Income'  # Pension withdrawals
                # 4. Interest
                elif 'ריבית' in search_text:
                     category = 'Interest'
                # 5. General Income (Transfers/Bit) - Only if positive
                elif amount_val > 0:
                    # 5a. Credit Card Refunds
                    if 'כרטיס' in search_text or 'ישראכרט' in search_text or '0164' in search_text or '4610' in search_text:
                        category = 'Refund'
                    # 5b. Internal Bank Transfers
                    elif 'הפועלים' in search_text or 'מזרחי' in search_text or 'לחשבון' in search_text or 'withdrawal' in search_text:
                        category = 'Transfer'
                    # 5c. General transfers/payments
                    elif 'העברה' in search_text or 'bit' in search_text or 'paybox' in search_text:
                        category = 'Income'
                    # 5d. Savings withdrawals
                    elif 'משיכה מחיסכון' in search_text or 'פירעון' in search_text:
                        category = 'Income'
                    # 5e. Catch remaining positive amounts as miscellaneous income
                    else:
                        category = 'Income'

                # 6. Credit Card Payoff (Bank Side Expenses)
                elif amount_val < 0:
                     keywords = ['isracard', 'ישראכרט', 'max', 'מקס', 'cal', 'כאל', 'visa', 'ויזה', 'amex', '0164', '1973']
                     if any(k in search_text for k in keywords):
                         category = 'Credit Card Payoff'

                # Fix Description for Display if it was reversed
                # If we found keywords in the REVERSED string but not the normal one, chances are the whole string is reversed.
                # Exception: Mixed English/Hebrew. 
                # Let's start simple: if the reversed description contains clearly readable Hebrew keywords, use it?
                # But English "Withdrawal" became "lawardhtiW" in reversed.
                # Compromise: Use the Raw description for display (so English is readable), 
                # unless it is PURE Hebrew trash. 
                # For now, keeping Raw description for display to avoid breaking English names (Amazon, Google, etc).
                # But adding a small fix: if Raw description looks like complete gibberish (only Hebrew chars, but no common words), maybe swap.
                # Let's stick to Raw for display, relying on Categorization for value.
                
                # Detect spender from card pattern in description
                spender = self.detect_spender(desc_val)
                
                # 5. Extract REF ID
                ref_val = None
                if ref_col and pd.notna(row[ref_col]):
                    ref_val = str(row[ref_col]).strip().split('.')[0] # Remove decimal if present (Excel)
                
                # 6. Extract Bank Category (סוג פעולה) - helps AI categorization
                bank_cat_val = None
                if bank_category_col and pd.notna(row[bank_category_col]):
                    bank_cat_val = str(row[bank_category_col]).strip()
                
                # 7. Extract Debit/Credit type (חיוב/זיכוי) - helps AI understand flow direction
                tx_type_val = None
                if debit_credit_col and pd.notna(row[debit_credit_col]):
                    tx_type_val = str(row[debit_credit_col]).strip()
                
                transactions.append({
                    'date': parsed_date,
                    'description': desc_val,
                    'amount': amount_val,
                    'category': category,
                    'currency': 'ILS',
                    'source_file': 'OneZero_Excel',
                    'spender': spender,
                    'ref_id': ref_val,
                    'bank_category': bank_cat_val,  # Original bank categorization (סוג פעולה)
                    'transaction_type': tx_type_val  # Debit/Credit indicator (חיוב/זיכוי)
                })
        
        except Exception as e:
            print(f"Error parsing One Zero Excel: {e}")
            return pd.DataFrame()
        
        df_result = pd.DataFrame(transactions)
        if not df_result.empty:
            df_result['hash_id'] = df_result.apply(self.generate_hash_id, axis=1)
            
            # REMOVED AGGRESSIVE DEDUPLICATION
            # Uniqueness is now guaranteed by Hash ID (Date+Amount+Desc+Ref)
            # If Ref is missing, we still rely on description uniqueness.
            # But dropping purely same-data rows is incorrect for things like bus tickets.
            # df_result = df_result.drop_duplicates(subset=['date', 'description', 'amount'], keep='first')
        
        return df_result

    def _parse_max_finance(self, file_obj):
        """
        Parses Max It Finance.
        Now supports multiple sheets (including foreign currency transactions).
        """
        all_transactions = []
        
        # Try to read as Excel file (which may have multiple sheets)
        try:
            file_obj.seek(0)
            xl_file = pd.ExcelFile(file_obj)
            sheet_names = xl_file.sheet_names
            
            # Auto-detect file owner from first sheet content
            df_raw_first = pd.read_excel(file_obj, sheet_name=0, header=None)
            detected_owner = self.detect_file_owner(df_raw_first.astype(str).to_string())
            if detected_owner and detected_owner != "Joint":
                self.default_spender = detected_owner
            
            # Parse each sheet
            for sheet_name in sheet_names:
                file_obj.seek(0)
                sheet_transactions = self._parse_max_finance_sheet(file_obj, sheet_name)
                all_transactions.extend(sheet_transactions)
                
        except Exception:
            # Not an Excel file, try CSV
            file_obj.seek(0)
            all_transactions = self._parse_max_finance_sheet(file_obj, sheet_name=None)
        
        # Convert to DataFrame
        df_clean = pd.DataFrame(all_transactions)
        
        if not df_clean.empty:
            # Generate hash_ids
            df_clean['hash_id'] = df_clean.apply(self.generate_hash_id, axis=1)
            
            # REMOVED AGGRESSIVE DEDUPLICATION
        
        return df_clean
    
    def _parse_max_finance_sheet(self, file_obj, sheet_name=None):
        """
        Parses a single Max Finance sheet.
        """
        try:
            if sheet_name is not None:
                # Excel file with specific sheet
                file_obj.seek(0)
                df_raw = pd.read_excel(file_obj, sheet_name=sheet_name, header=None)
            else:
                # CSV file
                try:
                    file_obj.seek(0)
                    df_raw = pd.read_csv(file_obj, header=None, names=list(range(30)), encoding='utf-8')
                except Exception:
                    file_obj.seek(0)
                    df_raw = pd.read_csv(file_obj, header=None, names=list(range(30)), encoding='iso-8859-8')

            header_idx = -1
            for idx, row in df_raw.iterrows():
                row_str = " ".join(row.astype(str).values)
                if "שם בית העסק" in row_str and "4 ספרות אחרונות" in row_str:
                    header_idx = idx
                    break
            
            if header_idx == -1: 
                return []
                
            # Read with proper header
            if sheet_name is not None:
                file_obj.seek(0)
                df = pd.read_excel(file_obj, sheet_name=sheet_name, skiprows=header_idx)
            else:
                file_obj.seek(0)
                try:
                    df = pd.read_csv(file_obj, skiprows=header_idx, encoding='utf-8')
                except Exception:
                    file_obj.seek(0)
                    df = pd.read_csv(file_obj, skiprows=header_idx, encoding='iso-8859-8')
                
            transactions = []
            date_col = next((c for c in df.columns if "תאריך עסקה" in str(c)), None)
            desc_col = next((c for c in df.columns if "שם בית העסק" in str(c)), None)
            amount_col = next((c for c in df.columns if "סכום חיוב" in str(c)), None)
            ref_col = next((c for c in df.columns if "שובר" in str(c) or "אסמכתא" in str(c)), None) # Usually "מספר שובר"
            
            if not amount_col:
                amount_col = next((c for c in df.columns if "סכום עסקה" in str(c)), None)
            
            if not (date_col and desc_col and amount_col):
                return []

            for _, row in df.iterrows():
                if pd.isna(row[desc_col]): continue

                raw_amount = self.clean_amount(row.get(amount_col, 0))
                
                # Enhanced refund detection
                notes = str(row.get('הערות', '')).lower()
                desc_lower = str(row[desc_col]).lower()
                
                # Check for refund indicators in notes or description
                is_refund = (
                    "ביטול" in notes or 
                    "זיכוי" in notes or
                    "זיכוי" in desc_lower or
                    "החזר" in notes or
                    "החזר" in desc_lower
                )
                
                if is_refund:
                    final_amount = abs(raw_amount)  # Refunds are positive
                else:
                    final_amount = -1 * abs(raw_amount)  # Expenses are negative

                date_str = self.parse_date(str(row[date_col]))
                
                if date_str:
                    # Detect spender from card pattern
                    spender = self.detect_spender(str(row[desc_col]))
                    
                    transactions.append({
                        'date': date_str,
                        'description': row[desc_col],
                        'amount': final_amount,
                        'category': 'Uncategorized',
                        'currency': 'ILS',
                        'source_file': 'Max_Card',
                        'spender': spender,
                        'ref_id': str(row[ref_col]).strip() if ref_col and pd.notna(row[ref_col]) else None
                    })
                    
            return transactions
            
        except Exception as e:
            print(f"Error parsing Max Finance sheet: {e}")
            return []

    def _parse_isracard(self, file_obj):
        """
        Parses Isracard.
        """
        try:
            file_obj.seek(0)
            df_raw = pd.read_csv(file_obj, header=None, names=list(range(30)), encoding='utf-8')
        except Exception:
            file_obj.seek(0)
            try:
                df_raw = pd.read_csv(file_obj, header=None, names=list(range(30)), encoding='iso-8859-8')
            except Exception:
                file_obj.seek(0)
                df_raw = pd.read_excel(file_obj, header=None)

        # Auto-detect file owner from content
        detected_owner = self.detect_file_owner(df_raw.astype(str).to_string())
        if detected_owner and detected_owner != "Joint":
            self.default_spender = detected_owner

        transactions = []
        col_indices = {}
        current_section = "SEARCH"  # SEARCH -> PENDING -> VALID
        
        for idx, row in df_raw.iterrows():
            row_vals = [str(v).strip() for v in row.values]
            row_str = " ".join(row_vals)
            
            # Detect section changes
            if "עסקאות שטרם נקלטו" in row_str:
                current_section = "PENDING"
                col_indices = {}  # Reset column indices
                continue
            
            if "עסקאות למועד חיוב" in row_str or "עסקאות בחיוב" in row_str:
                current_section = "VALID"
                col_indices = {}  # Reset column indices
                continue
            
            # Detect header row (can appear multiple times)
            if "תאריך רכישה" in row_vals and "שם בית עסק" in row_vals:
                col_indices = {}
                for i, val in enumerate(row_vals):
                    if val and val != 'nan':
                        col_indices[val] = i
                
                # Fallback: if "שם בית עסק" missing, try aliases
                if "שם בית עסק" not in col_indices:
                    for alias in ["שם שיוך", "תיאור", "פרטים"]:
                         if alias in row_vals:
                             col_indices["שם בית עסק"] = row_vals.index(alias)
                continue
            
            # Skip pending transactions
            if current_section == "PENDING":
                continue
            
            # Skip if we haven't found a header yet
            if not col_indices:
                continue
            
            # Try to parse transaction
            date_idx = col_indices.get("תאריך רכישה", 0)
            if date_idx >= len(row):
                continue
            
            date_val = str(row[date_idx]).strip()
            
            # Check if this row has a valid date
            if not re.match(r'\d{2}[./]\d{2}[./]\d{2,4}', date_val):
                continue
            if "תאריך" in date_val:  # Skip if it's a header
                continue
            
            # Get amount (try "סכום חיוב" first, then "סכום עסקה")
            amount_idx = col_indices.get("סכום חיוב", col_indices.get("סכום עסקה", 2))
            amount_val = 0
            if amount_idx < len(row):
                amount_val = self.clean_amount(row[amount_idx])
            
            # If still zero, try fallback column
            if amount_val == 0:
                fallback_idx = col_indices.get("סכום עסקה", 2)
                if fallback_idx < len(row):
                    amount_val = self.clean_amount(row[fallback_idx])
            
            if amount_val == 0:
                continue  # Skip zero amounts
            
            # Handle refunds: if amount is negative in source, it's a refund (credit = positive)
            # If amount is positive in source, it's an expense (debit = negative)
            if amount_val < 0:
                final_amount = abs(amount_val)  # Refund: make positive
            else:
                final_amount = -1 * abs(amount_val)  # Expense: make negative
            
            # Get description
            desc_idx = col_indices.get("שם בית עסק", 1)
            # Improved Fallback: if default index 1 is out of bounds or empty?
            if desc_idx < len(row):
                 desc_val = row[desc_idx]
            else:
                 # Try finding longest text column as last resort? 
                 # Or just "Unknown"
                 desc_val = "Unknown"
            
            # Get Ref ID
            ref_id = None
            # Common names for Ref in Isracard CSV
            # "מס' שובר" is the specific one found in 2026 Excel exports
            ref_idx = col_indices.get("מס' שובר", col_indices.get("מספר שובר", col_indices.get("שובר", col_indices.get("אסמכתא"))))
            if ref_idx and ref_idx < len(row):
                val = str(row[ref_idx]).strip()
                if val and val != 'nan':
                    ref_id = val.split('.')[0]
            
            # Parse date
            date_str = self.parse_date(date_val)
            
            if date_str:
                # Detect spender from card pattern
                spender = self.detect_spender(str(desc_val).strip())
                
                transactions.append({
                    'date': date_str,
                    'description': str(desc_val).strip(),
                    'amount': final_amount,
                    'category': 'Uncategorized',
                    'currency': 'ILS',
                    'source_file': 'Isracard',
                    'spender': spender,
                    'ref_id': ref_id
                })
                    
        df_clean = pd.DataFrame(transactions)
        if not df_clean.empty:
            df_clean['hash_id'] = df_clean.apply(self.generate_hash_id, axis=1)
            # No drop_duplicates here originally, keeping it that way.
        return df_clean

    def _parse_isracard_pdf(self, file_obj):
        """
        Parses Isracard Digital PDF using permissive regex search.
        Finds a Date and an Amount in the line, regardless of order.
        """
        transactions = []
        
        with pdfplumber.open(file_obj) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if not text: continue
                
                lines = text.split('\n')
                for line in lines:
                    line = line.strip()
                    
                    # 1. Find Date
                    date_match = re.search(r'(\d{2}/\d{2}/\d{2,4})', line)
                    if not date_match: 
                        continue
                    date_str = date_match.group(1)
                    
                    # 2. Find Amounts (allow negative, comma)
                    # Look for numbers with 2 decimal places
                    amounts = re.findall(r'(-?\d{1,3}(?:,\d{3})*\.\d{2})', line)
                    if not amounts: 
                        continue
                    
                    # Filter amounts to valid floats
                    valid_amounts = []
                    for a in amounts:
                        try:
                            val = self.clean_amount(a)
                            if abs(val) > 0.01:
                                valid_amounts.append(val)
                        except (ValueError, TypeError):
                            pass

                    if not valid_amounts: continue
                    
                    # Heuristic: The Billing Amount is usually the first number in LTR or last in RTL?
                    amount = valid_amounts[0]
                    
                    # 3. Description is the text removing the date and amount tokens
                    clean_line = line.replace(date_str, '')
                    for a_str in amounts:
                        clean_line = clean_line.replace(a_str, '', 1) 
                        
                    # Remove noise
                    clean_line = clean_line.replace('₪', '').replace("ש'ח", "").replace('ש"ח', "")
                    
                    # Also remove internal value dates if any extra were found
                    clean_line = re.sub(r'\d{2}/\d{2}/\d{2,4}', '', clean_line)
                    
                    # Clean up spaces
                    desc = re.sub(r'\s+', ' ', clean_line).strip()
                    
                    # Final check: remove leading/trailing purely numeric internal codes
                    desc_parts = desc.split()
                    clean_desc_parts = []
                    for p in desc_parts:
                        if re.match(r'^\d+(\.\d+)?$', p): continue
                        clean_desc_parts.append(p)
                    
                    description = " ".join(clean_desc_parts)

                    # --- FIX RTL & FILTER SUMMARY ---
                    # 1. Check for Summary Lines (e.g., 'Total Charge')
                    # 'סה"כ חיוב', 'כ"הס בויח'
                    if 'סה"כ' in description or 'כ"הס' in description or 'בויח' in description or 'חיוב' in description:
                         # Ensure we aren't filtering real transactions that just contain "Charge" in description?
                         # Usually "Total Charge for Date" lines are distinctive.
                         # The description usually becomes just "בויח כ"הס" or similar.
                         # Real transactions rarely have "Total" (Sah-Kal).
                         if 'סה"כ' in description or 'כ"הס' in description:
                             continue

                    # 2. Reverse Description if it looks like RTL Hebrew
                    # Detect Hebrew char
                    if any('א' <= c <= 'ת' for c in description):
                        # Heuristic: If it contains Hebrew, the whole string might be reversed (Chars AND Words).
                        # e.g. "הזה קנילב" -> "בלינק הזה".
                        # Check specific reversed keywords to confirm?
                        # Or just blindly reverse for Isracard PDF which is known to be broken.
                        # User example "A.IGל" -> "לGI.A".
                        # Let's reverse the string.
                        description = description[::-1]
                        
                    # 3. Clean up Reversed Parentheses/Brackets
                    # )text( -> (text)
                    tr_map = {
                        '(': ')', ')': '(',
                        '[': ']', ']': '[',
                        '{': '}', '}': '{',
                        '<': '>', '>': '<'
                    }
                    # Since we reversed the whole string, ')' became '(' relative to text direction?
                    # "abc (123)" reversed -> ")321( cba".
                    # We want "abc (123)".
                    # Using [::-1] gives ")321( cba".
                    # Characters are mirrored.
                    # We might need to swap parens back IF the text is now readable.
                    # But if we reversed chars, ')' became ')' char at start.
                    # Let's leave parens for now, usually minor.

                    # Amount: negative source values are refunds (make positive)
                    if amount < 0:
                        final_amount = abs(amount)
                    else:
                        final_amount = -1 * abs(amount)

                    parsed_date = self.parse_date(date_str)
                    
                    if parsed_date:
                        # Detect spender from card pattern
                        spender = self.detect_spender(description)
                        
                        transactions.append({
                            'date': parsed_date,
                            'description': description,
                            'amount': final_amount,
                            'category': 'Uncategorized',
                            'currency': 'ILS',
                            'source_file': 'Isracard_PDF_Fixed',
                            'spender': spender
                        })

        df = pd.DataFrame(transactions)
        if not df.empty:
            df['hash_id'] = df.apply(self.generate_hash_id, axis=1)
            
        return df

# Helper function that main.py calls
def detect_and_parse(file_obj, filename, default_spender="Joint"):
    parser = TransactionParser(default_spender=default_spender)
    df = parser.parse_file(file_obj, filename)
    if not df.empty:
        return df.to_dict('records')
    return []