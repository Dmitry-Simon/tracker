"""Max It Finance (Max Card) statements — Excel with foreign-currency sheets."""
import pandas as pd


class MaxCardMixin:
    def _parse_max_finance(self, file_obj):
        """Iterate every Excel sheet (Max splits ILS / foreign currency / etc.)."""
        all_transactions = []
        try:
            file_obj.seek(0)
            xl_file = pd.ExcelFile(file_obj)

            df_raw_first = pd.read_excel(file_obj, sheet_name=0, header=None)
            detected_owner = self.detect_file_owner(df_raw_first.astype(str).to_string())
            if detected_owner and detected_owner != "Joint":
                self.default_spender = detected_owner

            for sheet_name in xl_file.sheet_names:
                file_obj.seek(0)
                all_transactions.extend(self._parse_max_finance_sheet(file_obj, sheet_name))

        except Exception:
            file_obj.seek(0)
            all_transactions = self._parse_max_finance_sheet(file_obj, sheet_name=None)

        df_clean = pd.DataFrame(all_transactions)
        if not df_clean.empty:
            df_clean['hash_id'] = df_clean.apply(self.generate_hash_id, axis=1)
        return df_clean

    def _parse_max_finance_sheet(self, file_obj, sheet_name=None):
        """Parse a single sheet (Excel) or the whole CSV (sheet_name=None).

        Sign convention: source amount is positive=expense. Flip to tracker
        convention (expense<0, refund>0); refund detection looks at 'הערות' and
        the merchant name for ביטול / זיכוי / החזר.
        """
        try:
            if sheet_name is not None:
                file_obj.seek(0)
                df_raw = pd.read_excel(file_obj, sheet_name=sheet_name, header=None)
            else:
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
            ref_col = next((c for c in df.columns if "שובר" in str(c) or "אסמכתא" in str(c)), None)

            if not amount_col:
                amount_col = next((c for c in df.columns if "סכום עסקה" in str(c)), None)

            if not (date_col and desc_col and amount_col):
                return []

            for _, row in df.iterrows():
                if pd.isna(row[desc_col]):
                    continue

                raw_amount = self.clean_amount(row.get(amount_col, 0))

                notes = str(row.get('הערות', '')).lower()
                desc_lower = str(row[desc_col]).lower()
                is_refund = (
                    "ביטול" in notes or "זיכוי" in notes or "זיכוי" in desc_lower
                    or "החזר" in notes or "החזר" in desc_lower
                )
                final_amount = abs(raw_amount) if is_refund else -1 * abs(raw_amount)

                date_str = self.parse_date(str(row[date_col]))
                if not date_str:
                    continue

                transactions.append({
                    'date': date_str,
                    'description': row[desc_col],
                    'amount': final_amount,
                    'category': 'Uncategorized',
                    'currency': 'ILS',
                    'source_file': 'Max_Card',
                    'spender': self.detect_spender(str(row[desc_col])),
                    'ref_id': str(row[ref_col]).strip() if ref_col and pd.notna(row[ref_col]) else None,
                })

            return transactions

        except Exception as e:
            print(f"Error parsing Max Finance sheet: {e}")
            return []
