
import os
import sys
import pandas as pd
import io

# Mocking the filename provided by user (using the one in tests/raw-test-data)
# Note: The actual filename in the directory might have truncated chars or be slightly different due to encoding.
# We will list the directory to find it.

TEST_DATA_DIR = r"c:\home-proj\tracker\finance-app\tests\raw-test-data"

def find_target_file():
    for f in os.listdir(TEST_DATA_DIR):
        if "One Zero" in f and f.endswith(".xls"):
            return os.path.join(TEST_DATA_DIR, f)
    return None

def test_parser_logic(filepath):
    print(f"Testing file found.")
    
    with open(filepath, 'rb') as f:
        file_content = f.read()
        
    file_obj = io.BytesIO(file_content)
    
    # Simulate parsers.py logic
    print("--- Simulating parsers.py logic ---")
    
    try:
        # Try reading as CSV first
        print("Attempting read_csv...")
        try:
            df_temp = pd.read_csv(file_obj, header=None, names=list(range(30)), encoding='utf-8')
            print("read_csv SUCCESS")
            print("First 5 rows of CSV read:")
            print(df_temp.head().to_string())
        except Exception as e:
            print(f"read_csv FAILED: {e}")
            print("Attempting read_excel...")
            file_obj.seek(0)
            df_temp = pd.read_excel(file_obj, header=None)
            print("read_excel SUCCESS")
            
        content_str = df_temp.to_string()
        print(f"\nContent Search Check:")
        print(f"'תאריך תנועה' found: {'תאריך תנועה' in content_str}")
        print(f"'סכום פעולה' found: {'סכום פעולה' in content_str}")
        
    except Exception as e:
        print(f"Logic FAILED: {e}")

if __name__ == "__main__":
    target = find_target_file()
    if target:
        test_parser_logic(target)
    else:
        print("Target file not found in test dir")
