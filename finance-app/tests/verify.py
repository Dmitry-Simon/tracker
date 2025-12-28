import unittest
import sys
import os
import io
from unittest.mock import MagicMock, patch

# MOCK Dependencies BEFORE import
sys.modules['pdfplumber'] = MagicMock()
sys.modules['firebase_admin'] = MagicMock()
sys.modules['firebase_admin.credentials'] = MagicMock()
sys.modules['firebase_admin.firestore'] = MagicMock()
sys.modules['google.generativeai'] = MagicMock()
sys.modules['streamlit'] = MagicMock()
sys.modules['openpyxl'] = MagicMock() # Often used by pandas for excel

# Ensure streamlit secrets dict exists in mock
sys.modules['streamlit'].secrets = {}

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Try importing dependencies cleanly
try:
    import pandas as pd
except ImportError:
    print("Warning: pandas is missing. Mocks might fail if code relies on real pandas.")

from src import parsers, db

class TestParsers(unittest.TestCase):
    
    def test_parse_date(self):
        self.assertEqual(parsers.parse_date("01/01/2025"), "2025-01-01")
        self.assertEqual(parsers.parse_date("31-12-2024"), "2024-12-31")
        self.assertIsNone(parsers.parse_date("Invalid"))

    def test_clean_amount(self):
        self.assertEqual(parsers.clean_amount("1,200.50"), 1200.50)
        self.assertEqual(parsers.clean_amount("100"), 100.0)
        self.assertEqual(parsers.clean_amount("-50.00"), -50.0)

    def test_one_zero_parser(self):
        import pdfplumber
        
        # Mock PDF content
        mock_page = MagicMock()
        text_content_income = '"300.50", "300.50", "0.00", "SALARY", "01/01/2025", "01/01/2025"'
        text_content_expense = '"50.00", "0.00", "50.00", "NETFLIX", "01/01/2025", "01/01/2025"'
        
        mock_page.extract_text.return_value = text_content_income + "\n" + text_content_expense
        
        mock_pdf = MagicMock()
        mock_pdf.pages = [mock_page]
        pdfplumber.open.return_value.__enter__.return_value = mock_pdf
        
        file_obj = io.BytesIO(b"dummy pdf")
        txs = parsers.parse_one_zero(file_obj)
        
        self.assertEqual(len(txs), 2)
        # Income
        self.assertEqual(txs[0]['amount'], 300.50)
        self.assertEqual(txs[0]['description'], "SALARY")
        # Expense
        self.assertEqual(txs[1]['amount'], -50.00)
        self.assertEqual(txs[1]['description'], "NETFLIX")

    def test_max_parser(self):
        csv_data = """
trash,row
תאריך עסקה,שם בית העסק,סכום חיוב,4 ספרות אחרונות
10-01-2025,AMAZON,100.00,1234
11-01-2025,EBAY,25.50,1234
        """.strip()
        
        file_obj = io.BytesIO(csv_data.encode('utf-8'))
        
        # Re-import parsers or rely on pandas usage inside
        # Pandas is real, IO is real.
        
        txs = parsers.parse_max(file_obj, "test.csv")
        
        self.assertEqual(len(txs), 2)
        # Test Case B1: Expense = Negative
        self.assertEqual(txs[0]['amount'], -100.00)
        self.assertEqual(txs[0]['description'], "AMAZON")
        self.assertEqual(txs[0]['date'], "2025-01-10")

    def test_isracard_parser(self):
        csv_data = """
header,info
תאריך רכישה,שם בית עסק,סכום חיוב,סכום עסקה,more
05/01/2025,CAFE JOE,15.00,15.00,
עסקאות שטרם נקלטו
06/01/2025,PENDING,100.00,100.00,
עסקאות למועד חיוב
07/01/2025,CLEARED,50.00,50.00,
        """.strip()
        
        file_obj = io.BytesIO(csv_data.encode('utf-8'))
        
        txs = parsers.parse_isracard(file_obj, "test.csv")
        
        descriptions = [t['description'] for t in txs]
        self.assertIn("CAFE JOE", descriptions)
        self.assertIn("CLEARED", descriptions)
        self.assertNotIn("PENDING", descriptions)
        
        cafe = next(t for t in txs if t['description'] == "CAFE JOE")
        self.assertEqual(cafe['amount'], -15.00)

class TestDB(unittest.TestCase):
    def test_dedup_hash(self):
        d = "2025-01-01"
        amt = -100.00
        desc = "  Supermarket   TLV  "
        
        norm_desc = "supermarket tlv"
        raw = f"2025-01-01_100.00_{norm_desc}"
        import hashlib
        expected_hash = hashlib.sha256(raw.encode('utf-8')).hexdigest()
        
        generated_hash = db.generate_hash_id(d, amt, desc)
        self.assertEqual(generated_hash, expected_hash)
        
    def test_dedup_hash_stability(self):
        h1 = db.generate_hash_id("2025-01-01", -50, "Test")
        h2 = db.generate_hash_id("2025-01-01", -50, "test")
        self.assertEqual(h1, h2)

if __name__ == '__main__':
    unittest.main()
