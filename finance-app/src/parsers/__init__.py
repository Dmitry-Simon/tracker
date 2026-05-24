"""Parsers package — file-type detection + per-bank parsing.

Public API:
    TransactionParser(default_spender="Joint") — class, used by tests
    detect_and_parse(file_obj, filename, default_spender="Joint") -> list[dict]
        the main entry point used by Streamlit upload and the auto-ingest pipeline

Each per-bank module defines a Mixin class. TransactionParser inherits from all
of them so individual `_parse_*` methods stay where they belong (one file per
bank) while still sharing `clean_amount`, `parse_date`, etc. from _base.
"""
import pandas as pd
import pdfplumber

from ._base import BaseParserMixin
from ._isracard import IsracardMixin
from ._max_card import MaxCardMixin
from ._one_zero import OneZeroMixin


class TransactionParser(BaseParserMixin, OneZeroMixin, IsracardMixin, MaxCardMixin):
    def parse_file(self, file_obj, filename):
        """Detect file type by extension + content signatures and dispatch."""
        filename_lower = filename.lower()

        try:
            if filename_lower.endswith('.pdf'):
                try:
                    with pdfplumber.open(file_obj) as pdf:
                        if not pdf.pages:
                            return pd.DataFrame()
                        first_page_text = pdf.pages[0].extract_text() or ""

                        if "isracard" in first_page_text.lower() or "ישראכרט" in first_page_text:
                            file_obj.seek(0)
                            df_result = self._parse_isracard_pdf(file_obj)
                        else:
                            file_obj.seek(0)
                            df_result = self._parse_one_zero_pdf(file_obj)

                        if not df_result.empty:
                            df_result['uploaded_from'] = filename
                        return df_result
                except Exception as e:
                    print(f"Error detecting PDF type for {filename}: {e}")
                    return pd.DataFrame()

            try:
                try:
                    df_temp = pd.read_csv(file_obj, header=None, names=list(range(30)), encoding='utf-8')
                except Exception:
                    file_obj.seek(0)
                    df_temp = pd.read_excel(file_obj, header=None)

                content_str = df_temp.to_string()

                # Order matters: One Zero has a more specific signature than Isracard,
                # so check it first.
                if "תאריך תנועה" in content_str and "סכום פעולה" in content_str:
                    file_obj.seek(0)
                    df_result = self._parse_one_zero_excel(file_obj)
                elif "שם בית העסק" in content_str and "4 ספרות אחרונות" in content_str:
                    file_obj.seek(0)
                    df_result = self._parse_max_finance(file_obj)
                elif "תאריך רכישה" in content_str or "שם בית עסק" in content_str:
                    file_obj.seek(0)
                    df_result = self._parse_isracard(file_obj)
                else:
                    print(f"Unknown CSV format for {filename}")
                    return pd.DataFrame()

                if not df_result.empty:
                    df_result['uploaded_from'] = filename
                return df_result

            except Exception as e:
                print(f"Error reading {filename}: {e}")
                return pd.DataFrame()

        except Exception as e:
            print(f"Critical error parsing {filename}: {e}")
            return pd.DataFrame()


def detect_and_parse(file_obj, filename, default_spender="Joint"):
    """Main entry point — returns parsed transactions as a list of dicts."""
    parser = TransactionParser(default_spender=default_spender)
    df = parser.parse_file(file_obj, filename)
    if not df.empty:
        return df.to_dict('records')
    return []
