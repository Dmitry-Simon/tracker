# Centralized constants for the Finance Tracker application.
# All category definitions and model configs live here to ensure consistency.

import streamlit as st

# --- User Profile (loaded from secrets, with empty defaults) ---
def _get_user_profile():
    """Load user profile from st.secrets[user_profile] if available."""
    try:
        profile = st.secrets.get("user_profile", {})
        return {
            'card_patterns': dict(profile.get("card_patterns", {})),
            'spender_names': list(profile.get("spender_names", ["Joint"])),
            'context': str(profile.get("context", "")),
        }
    except Exception:
        return {'card_patterns': {}, 'spender_names': ["Joint"], 'context': ""}

def get_card_patterns() -> dict:
    """Returns card_number -> spender_name mapping from secrets."""
    return _get_user_profile()['card_patterns']

def get_spender_names() -> list:
    """Returns list of spender names from secrets."""
    return _get_user_profile()['spender_names']

def get_ai_context() -> str:
    """Returns personal context string for AI prompts from secrets."""
    return _get_user_profile()['context']

INCOME_CATEGORIES = ['Salary', 'Income', 'Benefits', 'Interest']
SAVINGS_CATEGORIES = ['Savings']
IGNORE_CATS_EXPENSE = ['Credit Card Payoff', 'Transfer', 'Savings']
IGNORE_CATS_METRIC = ['Credit Card Payoff', 'Transfer']

ALL_CATEGORIES = [
    'Food', 'Groceries', 'Transport', 'Shopping', 'Bills',
    'Salary', 'Income', 'Benefits', 'Interest',
    'Health', 'Entertainment', 'Transfer', 'Rent/Mortgage',
    'Savings', 'Credit Card Payoff', 'Restaurants', 'Refund',
    'Uncategorized', 'Other'
]

def get_spender_options() -> list:
    """Returns spender options for UI dropdowns."""
    names = get_spender_names()
    if 'Joint' not in names:
        names = ['Joint'] + names
    return names

AI_MODELS = [
    'gemini-3-flash-preview',
    'gemini-2.0-flash-exp',
    'gemini-1.5-flash'
]

AI_CATEGORY_LIST = [
    'Food', 'Groceries', 'Transport', 'Shopping', 'Bills',
    'Salary', 'Income', 'Health', 'Entertainment',
    'Transfer', 'Rent/Mortgage', 'Savings'
]
