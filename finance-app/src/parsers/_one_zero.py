"""One Zero bank statements — PDF (table extraction) and Excel/.xls."""
import re

import pandas as pd
import pdfplumber


class OneZeroMixin:
    def _parse_one_zero_pdf(self, file_obj):
        """Parse a One Zero PDF using pdfplumber table extraction.

        Header is usually one of (RTL): תאריך, תאריך ערך, תיאור, אסמכתא, חובה, זכות, יתרה.
        We map columns by header text first, and fall back to per-row heuristics
        if header detection fails.
        """
        transactions = []

        with pdfplumber.open(file_obj) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables()

                for table in tables:
                    headers = None
                    col_map = {}

                    for row_idx, row in enumerate(table):
                        row_clean = [str(c).replace('\n', ' ').strip() for c in row if c]
                        row_str = " ".join(row_clean)

                        if 'תאריך' in row_str and ('חובה' in row_str or 'זכות' in row_str or 'יתרה' in row_str):
                            headers = row
                            break

                    if headers:
                        for idx, cell in enumerate(headers):
                            if not cell:
                                continue
                            val = str(cell).replace('\n', ' ').strip()
                            if 'תאריך' in val and 'ערך' not in val: col_map['date'] = idx
                            elif 'תיאור' in val or 'פעולה' in val: col_map['desc'] = idx
                            elif 'חובה' in val: col_map['debit'] = idx
                            elif 'זכות' in val: col_map['credit'] = idx
                            elif 'יתרה' in val: col_map['balance'] = idx
                            elif 'אסמכתא' in val: col_map['ref'] = idx

                    row_idx = row_idx if headers else -1
                    start_row = row_idx + 1

                    for i in range(start_row, len(table)):
                        row = table[i]
                        if not any(row):
                            continue

                        date_val = None
                        desc_val = ""
                        amount_val = 0.0

                        if 'date' in col_map:
                            date_val = row[col_map['date']]
                        else:
                            for idx, cell in enumerate(row):
                                if cell and re.match(r'\d{2}[/.]\d{2}[/.]\d{4}', str(cell).strip()):
                                    date_val = cell
                                    col_map['date'] = idx
                                    break

                        if not date_val:
                            continue

                        debit = 0.0
                        credit = 0.0
                        if 'debit' in col_map and 'credit' in col_map:
                            debit = self.clean_amount(row[col_map['debit']])
                            credit = self.clean_amount(row[col_map['credit']])
                            if debit != 0:
                                amount_val = -1 * abs(debit)
                            elif credit != 0:
                                amount_val = abs(credit)

                        if amount_val == 0.0 and abs(debit) < 0.001 and abs(credit) < 0.001:
                            continue

                        if 'desc' in col_map:
                            desc_val = row[col_map['desc']]
                        else:
                            parts = []
                            for idx, cell in enumerate(row):
                                if idx in col_map.values():
                                    continue
                                if not cell:
                                    continue
                                s = str(cell).strip()
                                if re.match(r'^-?[\d,.]+$', s):
                                    continue
                                parts.append(s)
                            desc_val = " ".join(parts)

                        if desc_val:
                            desc_val = str(desc_val).replace('\n', ' ')
                            for noise in ['ש"ח', 'ש”ח', '00.0', 'NIS', '/']:
                                desc_val = desc_val.replace(noise, ' ')
                            desc_val = re.sub(r'\b\d{5,}\b', '', desc_val)
                            desc_val = " ".join(desc_val.split())

                        if not desc_val or len(desc_val) < 2:
                            desc_val = "OneZero Transaction"

                        category = 'Uncategorized'
                        desc_lower = desc_val.lower()
                        if 'משכורת' in desc_val or 'ממופ"ת' in desc_val or 'salary' in desc_lower:
                            category = 'Salary'
                        elif 'ביטוח לאומי' in desc_val:
                            category = 'Benefits'
                        elif amount_val > 0 and ('העברה' in desc_val or 'bit' in desc_lower or 'paybox' in desc_lower):
                            category = 'Income'
                        elif amount_val < 0:
                            keywords = ['isracard', 'ישראכרט', 'max', 'מקס', 'cal', 'כאל', 'visa', 'ויזה', 'amex', '0164', '1973']
                            if any(k in desc_lower for k in keywords):
                                category = 'Credit Card Payoff'

                        ref_val = None
                        if 'ref' in col_map:
                            ref_str = str(row[col_map['ref']]).strip()
                            if ref_str and ref_str != 'nan':
                                ref_val = ref_str

                        parsed_date = self.parse_date(date_val)
                        if parsed_date:
                            transactions.append({
                                'date': parsed_date,
                                'description': desc_val,
                                'amount': amount_val,
                                'category': category,
                                'currency': 'ILS',
                                'source_file': 'OneZero_Table',
                                'spender': self.detect_spender(desc_val),
                                'ref_id': ref_val,
                            })

        df = pd.DataFrame(transactions)
        if not df.empty:
            df['hash_id'] = df.apply(self.generate_hash_id, axis=1)
        return df

    def _parse_one_zero_excel(self, file_obj):
        """Parse a One Zero Excel export (.xlsx / .xls).

        Key distinction vs. the PDF parser: One Zero Excel **already signs the
        amount** (debits negative, credits positive). Do NOT flip signs based on
        the חיוב/זיכוי column.
        """
        transactions = []

        try:
            file_obj.seek(0)
            df = pd.read_excel(file_obj)

            detected_owner = self.detect_file_owner(df.astype(str).to_string())
            if detected_owner and detected_owner != "Joint":
                self.default_spender = detected_owner

            date_col = desc_col = amount_col = debit_credit_col = ref_col = bank_category_col = None

            for col in df.columns:
                col_str = str(col).strip()
                if 'תאריך' in col_str:
                    if 'תנועה' in col_str and not date_col:
                        date_col = col
                    elif not date_col and 'ערך' not in col_str:
                        date_col = col
                if 'תיאור' in col_str:
                    desc_col = col
                if 'סכום' in col_str:
                    if 'פעולה' in col_str:
                        amount_col = col
                    elif not amount_col:
                        amount_col = col
                if 'חיוב' in col_str or 'זיכוי' in col_str:
                    debit_credit_col = col
                if 'אסמכתא' in col_str:
                    ref_col = col
                if 'סוג פעולה' in col_str or 'סוג' in col_str and 'פעולה' in col_str:
                    bank_category_col = col

            if not (date_col and desc_col and amount_col):
                print("One Zero Excel: Missing required columns")
                print(f"  date_col: {date_col}")
                print(f"  desc_col: {desc_col}")
                print(f"  amount_col: {amount_col}")
                return pd.DataFrame()

            for _, row in df.iterrows():
                if pd.isna(row[desc_col]):
                    continue

                date_val = row[date_col]
                parsed_date = None
                if pd.notna(date_val):
                    if isinstance(date_val, pd.Timestamp):
                        parsed_date = date_val.strftime('%Y-%m-%d')
                    elif isinstance(date_val, (int, float)):
                        try:
                            dt = pd.to_datetime(date_val, unit='D', origin='1899-12-30')
                            parsed_date = dt.strftime('%Y-%m-%d')
                        except (ValueError, TypeError):
                            pass
                    else:
                        parsed_date = self.parse_date(str(date_val))
                if not parsed_date:
                    continue

                amount_val = self.clean_amount(row[amount_col])

                desc_val = str(row[desc_col]).strip()
                desc_reversed = desc_val[::-1]
                for noise in ['ש"ח', 'ש"ח', 'NIS', '/']:
                    desc_val = desc_val.replace(noise, ' ')
                    desc_reversed = desc_reversed.replace(noise[::-1], ' ').replace(noise, ' ')
                desc_val = re.sub(r'\b\d{5,}\b', '', desc_val)
                desc_val = " ".join(desc_val.split())
                if not desc_val or len(desc_val) < 2:
                    desc_val = "OneZero Transaction"

                # OneZero Excel often has visually-reversed Hebrew (תרוכשמ vs משכורת).
                # We categorize against both directions, but keep the raw text for display
                # so English merchant names (Amazon, Google, …) stay readable.
                search_text = (desc_val + " " + desc_reversed).lower()

                category = 'Uncategorized'
                if 'משכורת' in search_text or 'salary' in search_text or 'ממופ"ת' in search_text or 'מופ"ת' in search_text or 'מופת' in search_text:
                    category = 'Salary'
                elif 'ביטוח לאומי' in search_text or 'בטוח לאומי' in search_text or 'ב"ל' in search_text or 'מילואים' in search_text or 'מענק' in search_text:
                    category = 'Benefits'
                elif 'משהבט' in search_text or 'קופ"ג' in search_text or 'פנסיה' in search_text:
                    category = 'Income'
                elif 'ריבית' in search_text:
                    category = 'Interest'
                elif amount_val > 0:
                    if 'כרטיס' in search_text or 'ישראכרט' in search_text or '0164' in search_text or '4610' in search_text:
                        category = 'Refund'
                    elif 'הפועלים' in search_text or 'מזרחי' in search_text or 'לחשבון' in search_text or 'withdrawal' in search_text:
                        category = 'Transfer'
                    elif 'העברה' in search_text or 'bit' in search_text or 'paybox' in search_text:
                        category = 'Income'
                    elif 'משיכה מחיסכון' in search_text or 'פירעון' in search_text:
                        category = 'Income'
                    else:
                        category = 'Income'
                elif amount_val < 0:
                    keywords = ['isracard', 'ישראכרט', 'max', 'מקס', 'cal', 'כאל', 'visa', 'ויזה', 'amex', '0164', '1973']
                    if any(k in search_text for k in keywords):
                        category = 'Credit Card Payoff'

                ref_val = None
                if ref_col and pd.notna(row[ref_col]):
                    ref_val = str(row[ref_col]).strip().split('.')[0]

                bank_cat_val = None
                if bank_category_col and pd.notna(row[bank_category_col]):
                    bank_cat_val = str(row[bank_category_col]).strip()

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
                    'spender': self.detect_spender(desc_val),
                    'ref_id': ref_val,
                    'bank_category': bank_cat_val,
                    'transaction_type': tx_type_val,
                })

        except Exception as e:
            print(f"Error parsing One Zero Excel: {e}")
            return pd.DataFrame()

        df_result = pd.DataFrame(transactions)
        if not df_result.empty:
            df_result['hash_id'] = df_result.apply(self.generate_hash_id, axis=1)
        return df_result
