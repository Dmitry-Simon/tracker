import google.generativeai as genai
import streamlit as st
import json
import typing_extensions as typing

# Initialize Gemini
if "gemini" in st.secrets:
    genai.configure(api_key=st.secrets["gemini"]["api_key"])

class CategoryResult(typing.TypedDict):
    category: str
    sub_category: str

def categorize_transaction(description: str, amount: float) -> dict:
    """
    Categorizes a single transaction using Gemini 1.5 Flash (cheaper/faster).
    Returns dict: {category, sub_category}
    """
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    prompt = f"""
    You are a financial assistant. Categorize the following transaction into a broad 'Category' and a specific 'Sub-Category'.
    Common Categories: Food, Transport, Utilities, Shopping, Salary, Transfer, Entertainment, Health, Financial (Fees/Loan), Housing.
    
    Transaction Description: "{description}"
    Amount: {amount} (Negative = Expense, Positive = Income)
    
    Respond in JSON format: {{ "category": "...", "sub_category": "..." }}
    """
    
    try:
        response = model.generate_content(
            prompt,
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json",
                response_schema=CategoryResult
            )
        )
        return json.loads(response.text)
    except Exception as e:
        print(f"AI Error: {e}")
        return {"category": "Uncategorized", "sub_category": "Other"}

def batch_categorize(transactions: list) -> list:
    """
    Categorizes a list of transactions.
    Note: For production, we might want to batch these into a single prompt to save calls,
    but for now we iterate (or could implement batching). 
    Let's do a simple iteration for the MVP.
    """
    results = []
    for tx in transactions:
        cat = categorize_transaction(tx['description'], tx['amount'])
        tx.update(cat)
        results.append(tx)
    return results
