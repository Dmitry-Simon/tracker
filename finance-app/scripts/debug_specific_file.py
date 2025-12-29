
import os
import sys
import pandas as pd
import warnings

# Suppress OpenPyXL warnings
warnings.simplefilter("ignore")

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src import parsers

TEST_DATA_DIR = r"c:\home-proj\tracker\finance-app\tests\raw-test-data"

def find_target_file():
    for f in os.listdir(TEST_DATA_DIR):
        if "One Zero" in f and f.endswith(".xls"):
            return f
    return None

def test_file(filename):
    print(f"Testing target file...")
    filepath = os.path.join(TEST_DATA_DIR, filename)
    
    with open(filepath, 'rb') as f:
        # Create Parser
        parser = parsers.TransactionParser()
        # Parse
        try:
            txs = parser.parse_file(f, filename)
            print(f"Transactions found: {len(txs)}")
            if len(txs) > 0:
                print("First transaction:")
                print(txs[0])
            else:
                print("Returning empty list.")
                
                # If empty, let's debug WHY by manually checking signatures
                f.seek(0)
                try:
                    df = pd.read_excel(f, header=None)
                    s = df.to_string()
                    print(f"Has 'תאריך תנועה': {'תאריך תנועה' in s}")
                    print(f"Has 'סכום פעולה': {'סכום פעולה' in s}")
                    print(f"Full string snippet: {s[:200]}...")
                except Exception as e:
                    print(f"Manual read_excel failed: {e}")

        except Exception as e:
            print(f"Parser crashed: {e}")

if __name__ == "__main__":
    target = find_target_file()
    if target:
        test_file(target)
    else:
        print("Target file not found")
