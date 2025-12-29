import google.generativeai as genai
import streamlit as st
import json
import time
from src import db

# Configure API Key (Global try, but we also check in function)
if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
elif "gemini" in st.secrets and "api_key" in st.secrets["gemini"]:
    genai.configure(api_key=st.secrets["gemini"]["api_key"])

def categorize_transactions(transactions: list) -> tuple[list, str]:
    """
    Uses Gemini to categorize a list of transactions.
    
    Args:
        transactions: List of dicts, must contain 'description', 'amount', '_id'.
    
    Returns:
        (results_list, error_message)
        results_list is list of dicts with keys: '_id', 'category', 'description' (normalized).
    """
    if not transactions:
        return [], None

    # Model Selection Strategy
    # User requested "Gemini 3 Flash".
    # We try: 3.0 Flash -> 2.0 Flash -> 1.5 Flash
    models_to_try = [
        'gemini-3-flash-preview',
        'gemini-2.0-flash-exp',
        'gemini-1.5-flash'
    ]
    
    # Start with primary
    current_model_name = models_to_try[0]
    model = genai.GenerativeModel(current_model_name)

    # Prepare batch
    BATCH_SIZE = 25
    results = []
    
    for i in range(0, len(transactions), BATCH_SIZE):
        batch = transactions[i:i+BATCH_SIZE]
        
        # Lightweight JSON payload
        payload = [
            {"id": t['_id'], "desc": t['description'], "amount": t['amount']} 
            for t in batch
        ]
        
        prompt = f"""
        You are a financial assistant.
        1. Categorize these transactions into: [Food, Transport, Shopping, Bills, Salary, Health, Entertainment, Transfer, Rent/Mortgage].
        2. Clean the merchant name (e.g. "MCDONALDS 889 TLV" -> "McDonald's").
        
        CRITICAL RULES:
        - DO NOT TRANSLATE the description. Keep it in the original language (e.g. Hebrew).
        - If the description is "רמי לוי", keep it "רמי לוי". Do NOT change it to "Rami Levy".
        - Only remove transaction IDs, dates, or city names that clutter the merchant name.
        
        Return STRICT JSON array of objects: {{"id": "...", "category": "...", "clean_desc": "..."}}.
        NO Markdown. NO Backticks.
        
        Input:
        {json.dumps(payload)}
        """
        
        try:
            response = model.generate_content(prompt)
            clean_text = response.text.replace("```json", "").replace("```", "").strip()
            
            parsed = json.loads(clean_text)
            
            # Map back to internal format
            for item in parsed:
                results.append({
                    '_id': item['id'],
                    'category': item.get('category', 'Uncategorized'),
                    'description': item.get('clean_desc', item.get('desc', '')) 
                })
                
        except Exception as e:
            err_str = str(e)
            
            # Logic: If 404/Not Found, try fallbacks for this specific batch
            # Logic: If 404/Not Found, try fallbacks for this specific batch
            if "404" in err_str or "not found" in err_str.lower():
                # Safe fallback logging
                try:
                    st.toast(f"Model {current_model_name} failed. Trying fallbacks...", icon="⚠️")
                except:
                    pass
                
                success_fallback = False
                for fallback_name in models_to_try:
                    if fallback_name == current_model_name: continue # Skip failed one
                    
                    try:
                        # st.write(f"Trying fallback model: {fallback_name}")
                        fb_model = genai.GenerativeModel(fallback_name)
                        response = fb_model.generate_content(prompt)
                        clean_text = response.text.replace("```json", "").replace("```", "").strip()
                        parsed = json.loads(clean_text)
                        
                        for item in parsed:
                            results.append({
                                '_id': item['id'],
                                'category': item.get('category', 'Uncategorized'),
                                'description': item.get('clean_desc', item.get('desc', '')) 
                            })
                            
                        # If success, update the main model for next batches to avoid retrying
                        model = fb_model
                        current_model_name = fallback_name
                        success_fallback = True
                        break # Exit fallback loop
                        
                    except Exception as e2:
                        continue
                
                if success_fallback:
                    time.sleep(1) # Rate limit safety
                    continue # Continue to next batch
            
            # If fallbacks failed or it was another error
            error_msg = f"AI Error batch {i}: {str(e)[:100]}" # Truncate to avoid huge errors
            return [], error_msg
            
        # Rate limit safety
        time.sleep(1)
        
    return results, None

def enrich_uncategorized_data():
    """
    Orchestrator: Fetches uncategorized, AI processes, updates DB.
    Returns: (count, error_message)
    """
    # 1. Get API Key
    api_key = None
    if "GEMINI_API_KEY" in st.secrets:
        api_key = st.secrets["GEMINI_API_KEY"]
    elif "gemini" in st.secrets and "api_key" in st.secrets["gemini"]:
        api_key = st.secrets["gemini"]["api_key"]
        
    if not api_key:
        return 0, "Missing GEMINI_API_KEY or [gemini] api_key in secrets.toml"

    # Re-configure to be safe
    genai.configure(api_key=api_key)

    # 2. Fetch Data
    raw_txs = db.get_uncategorized_transactions(limit=50)
    
    if not raw_txs:
        return 0, "No uncategorized transactions found."
        
    # 3. Call AI
    updated_data, error = categorize_transactions(raw_txs)
    
    if error:
        return 0, error
        
    # 4. Save Updates
    if updated_data:
        saved_count = db.update_transaction_batch(updated_data)
        return saved_count, None
    
    return 0, "No data updated."
