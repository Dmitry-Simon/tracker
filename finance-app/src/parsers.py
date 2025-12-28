import re
import pandas as pd
import pdfplumber
from datetime import datetime
from typing import List, Dict, Any, Optional

def parse_date(date_str: str) -> Optional[str]:
    """Parses date string DD/MM/YYYY or DD-MM-YYYY or DD.MM.YYYY or DD.MM.YY to YYYY-MM-DD."""
    if not date_str:
        return None
    
    # Clean string
    date_str = str(date_str).strip()
    
    # Try formats
    formats = ["%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d.%m.%y"]
    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None

def clean_amount(amount_str: Any) -> float:
    """Cleans amount string (removes currency symbols, commas) and converts to float."""
    if isinstance(amount_str, (int, float)):
        return float(amount_str)
    
    s = str(amount_str).strip()
    # Remove currency chars if present (simple check)
    s = re.sub(r"[^\d\.\-]", "", s)
    if not s:
        return 0.0
    return float(s)

# --- Type A: One Zero Bank (PDF) ---
def parse_one_zero(file_obj) -> List[Dict[str, Any]]:
    transactions = []
    # Regex as defined in requirements:
    # r'"([\d,]+\.?\d*)"\s*,\s*"([\d,]+\.?\d*)"\s*,\s*"([\d,]+\.?\d*)"\s*,\s*"(.*?)"\s*,\s*"(\d{2}/\d{2}/\d{4})"\s*,\s*"(\d{2}/\d{2}/\d{4})"'
    # Note: pdfplumber extracts text, regex matches lines.
    
    pattern = re.compile(r'"([\d,]+\.?\d*)"\s*,\s*"([\d,]+\.?\d*)"\s*,\s*"([\d,]+\.?\d*)"\s*,\s*"(.*?)"\s*,\s*"(\d{2}/\d{2}/\d{4})"\s*,\s*"(\d{2}/\d{2}/\d{4})"')
    
    with pdfplumber.open(file_obj) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue
            
            for line in text.split('\n'):
                match = pattern.search(line)
                if match:
                    # Group 1: Original Amount (maybe?) - Not specified in mapping logic, but present in regex
                    # Group 2: Credit
                    # Group 3: Debit
                    # Group 4: Description
                    # Group 5: Date 1 (Operation Date?)
                    # Group 6: Date 2 (Value Date?)
                    
                    credit_str = match.group(2).replace(',', '')
                    debit_str = match.group(3).replace(',', '')
                    desc = match.group(4).strip()
                    date_str = match.group(6) # Using Group 6 as requested (or implied by date format check) - Wait, requirements said "Group 6 = Date"
                    
                    credit = float(credit_str) if credit_str else 0.0
                    debit = float(debit_str) if debit_str else 0.0
                    
                    # Logic: Group 2 (Credit) - Group 3 (Debit) = Amount
                    amount = credit - debit
                    
                    parsed_date = parse_date(date_str)
                    
                    if parsed_date:
                        transactions.append({
                            "date": parsed_date,
                            "description": desc,
                            "amount": amount,
                            "source": "One Zero"
                        })
    return transactions

# --- Type B: Max It Finance (CSV/XLSX) ---
def parse_max(file_obj, filename: str) -> List[Dict[str, Any]]:
    transactions = []
    
    # Load DF. Handle CSV vs XLSX
    if filename.lower().endswith('.csv'):
        # Try reading with default header first
        # Max usually has garbage rows.
        # We'll read the whole file as a list of lists or naive DF then find header.
        try:
            # Use 'names' to handle ragged CSVs (fewer cols in first row than later)
            df_raw = pd.read_csv(file_obj, header=None, names=list(range(30)), encoding='utf-8')
        except:
             # Try utf-16 or iso-8859-8 for Hebrew
            file_obj.seek(0)
            df_raw = pd.read_csv(file_obj, header=None, names=list(range(30)), encoding='iso-8859-8')
    else:
        df_raw = pd.read_excel(file_obj, header=None)
        
    # Find header row
    header_idx = -1
    for idx, row in df_raw.iterrows():
        # Check for key columns
        row_str = " ".join([str(x) for x in row.values])
        if "שם בית העסק" in row_str and "4 ספרות אחרונות" in row_str:
            header_idx = idx
            break
            
    if header_idx == -1:
        print("Max Parser: Header not found.")
        return []
    
    # Reload with correct header
    file_obj.seek(0)
    if filename.lower().endswith('.csv'):
        # encoding might match previous attempt
        # simple retry with skiprows
        try:
            df = pd.read_csv(file_obj, skiprows=header_idx, encoding='utf-8')
        except:
            file_obj.seek(0)
            df = pd.read_csv(file_obj, skiprows=header_idx, encoding='iso-8859-8')
    else:
        df = pd.read_excel(file_obj, skiprows=header_idx)
        
    # Necessary columns: תאריך עסקה, שם בית העסק, סכום חיוב
    # Note: 'סכום חיוב' might be 'סכום חיוב בש"ח' or similar?
    # Req says: "Always use סכום חיוב (Billing Amount)"
    
    # Normalize columns strip whitespace
    df.columns = [str(c).strip() for c in df.columns]
    
    # Identify specific column names if slightly different
    date_col = next((c for c in df.columns if "תאריך עסקה" in c), None)
    desc_col = next((c for c in df.columns if "שם בית העסק" in c), None)
    amount_col = next((c for c in df.columns if "סכום חיוב" in c), None) # Prefer shorter match?
    # Max sometimes has 'סכום העסקה' and 'סכום החיוב', prefer 'סכום חיוב' per specs
    
    if not (date_col and desc_col and amount_col):
        print(f"Max Parser: Missing columns. Found: {df.columns}")
        return []

    for _, row in df.iterrows():
        try:
            d_str = row[date_col]
            if pd.isna(d_str): continue
            
            parsed_date = parse_date(d_str)
            if not parsed_date: continue
            
            desc = str(row[desc_col]).strip()
            
            amt_val = clean_amount(row[amount_col])
            # Req: Multiply Amount by -1 (Expense = Negative)
            # Max usually shows positive numbers for expenses.
            final_amount = amt_val * -1
            
            transactions.append({
                "date": parsed_date,
                "description": desc,
                "amount": final_amount,
                "source": "Max"
            })
        except Exception as e:
            print(f"Error parsing row: {e}")
            continue

    return transactions

# --- Type C: Isracard / Mastercard (CSV/XLSX) ---
def parse_isracard(file_obj, filename: str) -> List[Dict[str, Any]]:
    transactions = []
    
    # Load logic similar to Max
    if filename.lower().endswith('.csv'):
        try:
            df_raw = pd.read_csv(file_obj, header=None, names=list(range(30)), encoding='utf-8')
        except:
            file_obj.seek(0)
            df_raw = pd.read_csv(file_obj, header=None, names=list(range(30)), encoding='iso-8859-8')
    else:
        df_raw = pd.read_excel(file_obj, header=None)

    # State Machine approach as data is multi-section
    # We iterate rows manually.
    
    # Keyword Strings
    SECTION_PENDING = "עסקאות שטרם נקלטו"
    SECTION_CLEARED = "עסקאות למועד חיוב" # Also "עסקאות שנקלטו" sometimes
    SECTION_OFFCYCLE = "עסקאות בחיוב מחוץ למועד"
    
    COL_DATE = "תאריך רכישה"
    COL_DESC = "שם בית עסק"
    COL_AMOUNT_BILLING = "סכום חיוב"
    COL_AMOUNT_DEAL = "סכום עסקה"
    
    # We need to find the header row first to know column indices.
    # Note: Isracard might have headers repeated for each section, or one global header.
    # Usually Isracard exports from website have one header row, then sections.
    # Strategy: Find header row first.
    
    header_indices = {} # map col name to index
    
    # Scan for header
    header_row_idx = -1
    for idx, row in df_raw.iterrows():
        row_vals = [str(x).strip() for x in row.values]
        if COL_DATE in row_vals and COL_DESC in row_vals:
            header_row_idx = idx
            # map headers
            for col_idx, val in enumerate(row_vals):
                header_indices[val] = col_idx
            break
            
    if header_row_idx == -1:
        print("Isracard Parser: Header not found.")
        return []
    
    # Helper to clean and get val
    def get_val(row_vals, col_name):
        idx = header_indices.get(col_name)
        if idx is not None and idx < len(row_vals):
            return row_vals[idx]
        return None

    # Iterate from header + 1
    current_section = None # 'VALID' or 'IGNORE'
    
    # Heuristic: If we haven't seen a section header yet, what is the default?
    # Usually "Transactions for billing date..." comes first.
    # Let's assume Valid unless we hit Pending.
    current_section = "VALID" 
    
    for idx in range(header_row_idx + 1, len(df_raw)):
        row = df_raw.iloc[idx]
        row_vals = [str(x).strip() for x in row.values if not pd.isna(x)]
        full_row_str = " ".join([str(x) for x in row.values])
        
        # Check Section Headers
        if SECTION_PENDING in full_row_str:
            current_section = "IGNORE"
            continue
        if SECTION_CLEARED in full_row_str or SECTION_OFFCYCLE in full_row_str:
            current_section = "VALID"
            continue
            
        if current_section == "IGNORE":
            continue
            
        # Parse Row
        # Get raw values using mapped indices
        raw_row_vals = list(row.values) # Don't strip yet, keep original types if needed
        
        date_val = get_val(raw_row_vals, COL_DATE)
        desc_val = get_val(raw_row_vals, COL_DESC)
        
        if not date_val or pd.isna(date_val) or str(date_val).strip() == "":
            continue # Skip empty rows or summary rows
            
        # Isracard sometimes puts summary lines that look like data?
        # Check if date is parseable
        parsed_date = parse_date(date_val)
        if not parsed_date:
            continue
            
        billing_sum = get_val(raw_row_vals, COL_AMOUNT_BILLING)
        deal_sum = get_val(raw_row_vals, COL_AMOUNT_DEAL)
        
        # Priority: Billing Sum -> Deal Sum
        amount_to_use = billing_sum if (billing_sum is not None and str(billing_sum).strip() != "") else deal_sum
        
        final_amount = clean_amount(amount_to_use)
        
        # Req: Multiply by -1
        final_amount = final_amount * -1
        
        transactions.append({
            "date": parsed_date,
            "description": str(desc_val).strip(),
            "amount": final_amount,
            "source": "Isracard"
        })
        
    return transactions

def detect_and_parse(file_obj, filename: str) -> List[Dict[str, Any]]:
    filename = filename.lower()
    
    if filename.endswith('.pdf'):
        return parse_one_zero(file_obj)
        
    # Check CSV/XLSX content for detection
    # We need to peek at the file.
    # Since we might need to read it differently (pd.read_csv vs pd.read_excel), 
    # and we don't want to rely solely on filename for Max vs Isracard separation if they are both CSVs.
    
    # However, parse_max and parse_isracard logic includes detection loops?
    # No, the REQUIREMENTS say:
    # Type B Detection: Header row contains שם בית העסק and 4 ספרות אחרונות.
    # Type C Detection: Header row contains תאריך רכישה and שם בית עסק.
    
    # We should read enough to detect.
    
    is_csv = filename.endswith('.csv')
    
    # Read first chunk
    try:
        if is_csv:
            file_obj.seek(0)
            # Try utf-8 first
            try:
                sample_df = pd.read_csv(file_obj, header=None, names=list(range(30)), nrows=20, encoding='utf-8')
            except:
                file_obj.seek(0)
                sample_df = pd.read_csv(file_obj, header=None, names=list(range(30)), nrows=20, encoding='iso-8859-8')
        else:
            file_obj.seek(0)
            sample_df = pd.read_excel(file_obj, header=None, nrows=20)
    except Exception as e:
        print(f"Error reading file for detection: {e}")
        return []
        
    file_content_str = sample_df.to_string()
    
    if "שם בית העסק" in file_content_str and "4 ספרות אחרונות" in file_content_str:
        file_obj.seek(0)
        return parse_max(file_obj, filename)
        
    if "תאריך רכישה" in file_content_str and "שם בית עסק" in file_content_str:
        file_obj.seek(0)
        return parse_isracard(file_obj, filename)
        
    print("Unknown file format based on headers.")
    return []
