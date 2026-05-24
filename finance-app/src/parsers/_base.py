"""Shared helpers used by every per-bank parser."""
import re
from datetime import datetime

import pandas as pd

from src import db
from src.constants import get_card_patterns


class BaseParserMixin:
    def __init__(self, default_spender="Joint"):
        self.default_spender = default_spender
        self.card_patterns = get_card_patterns()

    def detect_spender(self, description):
        if not description:
            return self.default_spender
        desc_str = str(description)
        for card_num, spender in self.card_patterns.items():
            if card_num in desc_str:
                return spender
        return self.default_spender

    def detect_file_owner(self, content_str):
        """Scan the whole file to pick the dominant spender (or None if mixed)."""
        if not content_str:
            return None
        counts = {}
        for card, spender in self.card_patterns.items():
            counts[spender] = counts.get(spender, 0) + content_str.count(card)
        found = {k: v for k, v in counts.items() if v > 0}
        if not found:
            return None
        if len(found) == 1:
            return list(found.keys())[0]
        return "Joint"

    def generate_hash_id(self, row):
        return db.generate_hash_id(
            row['date'], row['amount'], row['description'], row.get('ref_id'),
        )

    def parse_date(self, date_str):
        """Try the formats Israeli banks actually emit."""
        if not isinstance(date_str, str):
            return date_str
        date_str = str(date_str).strip()
        for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d.%m.%y", "%d/%m/%y", "%Y-%m-%d"):
            try:
                return datetime.strptime(date_str, fmt).strftime('%Y-%m-%d')
            except ValueError:
                continue
        return None

    def clean_amount(self, val_str):
        """Strip Hebrew currency noise (₪, ש""ח, etc.) and return a float."""
        if pd.isna(val_str) or val_str is None:
            return 0.0
        s = str(val_str).strip()
        if s.startswith('ס') or 'ס ש' in s:
            if not any(char.isdigit() for char in s):
                return 0.0
        s = s.replace('ש""ח', '').replace('ש"ח', '').replace('₪', '').replace('ח"ש', '')
        s = s.replace(',', '').replace('"', '').replace("'", "")
        s = re.sub(r'[^\d\.\-]', '', s)
        if not s:
            return 0.0
        try:
            return float(s)
        except (ValueError, TypeError):
            return 0.0
