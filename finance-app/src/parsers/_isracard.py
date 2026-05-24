"""Isracard credit-card statements — Excel (preferred) and PDF (legacy)."""
import re

import pandas as pd
import pdfplumber


class IsracardMixin:
    def _parse_isracard(self, file_obj):
        """Parse Isracard Excel/CSV export.

        Layout: a SEARCH zone, then a 'pending' section we skip, then a 'valid'
        section with the real headers (תאריך רכישה, שם בית עסק, סכום חיוב, …).
        Sign convention: source amount is positive=expense, negative=refund.
        We flip to the tracker convention (expense<0, refund>0).
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

        detected_owner = self.detect_file_owner(df_raw.astype(str).to_string())
        if detected_owner and detected_owner != "Joint":
            self.default_spender = detected_owner

        transactions = []
        col_indices = {}
        current_section = "SEARCH"

        for idx, row in df_raw.iterrows():
            row_vals = [str(v).strip() for v in row.values]
            row_str = " ".join(row_vals)

            if "עסקאות שטרם נקלטו" in row_str:
                current_section = "PENDING"
                col_indices = {}
                continue
            if "עסקאות למועד חיוב" in row_str or "עסקאות בחיוב" in row_str:
                current_section = "VALID"
                col_indices = {}
                continue

            if "תאריך רכישה" in row_vals and "שם בית עסק" in row_vals:
                col_indices = {}
                for i, val in enumerate(row_vals):
                    if val and val != 'nan':
                        col_indices[val] = i
                if "שם בית עסק" not in col_indices:
                    for alias in ["שם שיוך", "תיאור", "פרטים"]:
                        if alias in row_vals:
                            col_indices["שם בית עסק"] = row_vals.index(alias)
                continue

            if current_section == "PENDING":
                continue
            if not col_indices:
                continue

            date_idx = col_indices.get("תאריך רכישה", 0)
            if date_idx >= len(row):
                continue
            date_val = str(row[date_idx]).strip()
            if not re.match(r'\d{2}[./]\d{2}[./]\d{2,4}', date_val):
                continue
            if "תאריך" in date_val:
                continue

            amount_idx = col_indices.get("סכום חיוב", col_indices.get("סכום עסקה", 2))
            amount_val = 0
            if amount_idx < len(row):
                amount_val = self.clean_amount(row[amount_idx])
            if amount_val == 0:
                fallback_idx = col_indices.get("סכום עסקה", 2)
                if fallback_idx < len(row):
                    amount_val = self.clean_amount(row[fallback_idx])
            if amount_val == 0:
                continue

            if amount_val < 0:
                final_amount = abs(amount_val)
            else:
                final_amount = -1 * abs(amount_val)

            desc_idx = col_indices.get("שם בית עסק", 1)
            desc_val = row[desc_idx] if desc_idx < len(row) else "Unknown"

            ref_id = None
            ref_idx = col_indices.get("מס' שובר", col_indices.get("מספר שובר", col_indices.get("שובר", col_indices.get("אסמכתא"))))
            if ref_idx and ref_idx < len(row):
                val = str(row[ref_idx]).strip()
                if val and val != 'nan':
                    ref_id = val.split('.')[0]

            date_str = self.parse_date(date_val)
            if date_str:
                transactions.append({
                    'date': date_str,
                    'description': str(desc_val).strip(),
                    'amount': final_amount,
                    'category': 'Uncategorized',
                    'currency': 'ILS',
                    'source_file': 'Isracard',
                    'spender': self.detect_spender(str(desc_val).strip()),
                    'ref_id': ref_id,
                })

        df_clean = pd.DataFrame(transactions)
        if not df_clean.empty:
            df_clean['hash_id'] = df_clean.apply(self.generate_hash_id, axis=1)
        return df_clean

    def _parse_isracard_pdf(self, file_obj):
        """Parse Isracard digital PDFs by regex-scanning each line.

        Isracard PDFs render Hebrew RTL — descriptions usually need a final
        full-string reverse to be readable.
        """
        transactions = []

        with pdfplumber.open(file_obj) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if not text:
                    continue

                for line in text.split('\n'):
                    line = line.strip()

                    date_match = re.search(r'(\d{2}/\d{2}/\d{2,4})', line)
                    if not date_match:
                        continue
                    date_str = date_match.group(1)

                    amounts = re.findall(r'(-?\d{1,3}(?:,\d{3})*\.\d{2})', line)
                    if not amounts:
                        continue

                    valid_amounts = []
                    for a in amounts:
                        try:
                            val = self.clean_amount(a)
                            if abs(val) > 0.01:
                                valid_amounts.append(val)
                        except (ValueError, TypeError):
                            pass
                    if not valid_amounts:
                        continue

                    amount = valid_amounts[0]

                    clean_line = line.replace(date_str, '')
                    for a_str in amounts:
                        clean_line = clean_line.replace(a_str, '', 1)
                    clean_line = clean_line.replace('₪', '').replace("ש'ח", "").replace('ש"ח', "")
                    clean_line = re.sub(r'\d{2}/\d{2}/\d{2,4}', '', clean_line)
                    desc = re.sub(r'\s+', ' ', clean_line).strip()

                    clean_desc_parts = []
                    for p in desc.split():
                        if re.match(r'^\d+(\.\d+)?$', p):
                            continue
                        clean_desc_parts.append(p)
                    description = " ".join(clean_desc_parts)

                    # Skip "Total Charge" summary lines (Hebrew variants)
                    if 'סה"כ' in description or 'כ"הס' in description:
                        continue

                    # Heuristic: if Hebrew chars appear, the entire string is reversed
                    if any('א' <= c <= 'ת' for c in description):
                        description = description[::-1]

                    if amount < 0:
                        final_amount = abs(amount)
                    else:
                        final_amount = -1 * abs(amount)

                    parsed_date = self.parse_date(date_str)
                    if parsed_date:
                        transactions.append({
                            'date': parsed_date,
                            'description': description,
                            'amount': final_amount,
                            'category': 'Uncategorized',
                            'currency': 'ILS',
                            'source_file': 'Isracard_PDF_Fixed',
                            'spender': self.detect_spender(description),
                        })

        df = pd.DataFrame(transactions)
        if not df.empty:
            df['hash_id'] = df.apply(self.generate_hash_id, axis=1)
        return df
