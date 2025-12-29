import streamlit as st

def load_css():
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');

    /* General Global Reset / Setting */
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }

    /* Streamlit Main Container */
    .block-container {
        padding-top: 2rem;
        padding-bottom: 3rem;
        max-width: 1200px;
    }

    /* --- Metric/Stat Cards --- */
    div[data-testid="metric-container"] {
        background-color: #FFFFFF;
        border: 1px solid #F0F2F6;
        padding: 20px;
        border-radius: 12px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
        transition: all 0.2s ease-in-out;
    }

    div[data-testid="metric-container"]:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(0,0,0,0.08);
        border-color: #E0E3E9;
    }

    div[data-testid="metric-container"] label {
        color: #64748B; /* Slate-500 */
        font-weight: 500;
    }

    div[data-testid="metric-container"] div[data-testid="stMetricValue"] {
        color: #1E293B; /* Slate-800 */
        font-weight: 700;
    }

    /* --- Headers --- */
    h1, h2, h3 {
        font-family: 'Inter', sans-serif;
        font-weight: 700;
        color: #0F172A; /* Slate-900 */
        letter-spacing: -0.02em;
    }



    /* --- Custom Content Card --- */
    .css-card {
        background-color: #FFFFFF;
        padding: 24px;
        border-radius: 16px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.03);
        margin-bottom: 24px;
        border: 1px solid #F1F5F9;
    }

    /* --- Sidebar --- */
    section[data-testid="stSidebar"] {
        background-color: #F8FAFC; /* Slate-50 */
        border-right: 1px solid #E2E8F0;
    }

    div[data-testid="stSidebarNav"] {
        padding-top: 1rem;
    }

    /* --- Buttons --- */
    .stButton button {
        border-radius: 8px;
        font-weight: 600;
        padding-top: 0.5rem;
        padding-bottom: 0.5rem;
        transition: all 0.2s;
    }
    
    .stButton button:active {
        transform: scale(0.98);
    }

    </style>
    """, unsafe_allow_html=True)


import contextlib

@contextlib.contextmanager
def card():
    st.markdown('<div class="css-card">', unsafe_allow_html=True)
    yield
    st.markdown('</div>', unsafe_allow_html=True)

