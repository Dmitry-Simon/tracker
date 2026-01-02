import streamlit as st

def load_css():
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Outfit:wght@400;600;700&display=swap');

    /* Global Typography & Design Tokens */
    :root {
        --font-main: 'Inter', sans-serif;
        --font-header: 'Outfit', sans-serif;
        --card-bg-light: rgba(255, 255, 255, 0.7);
        --card-bg-dark: rgba(25, 25, 25, 0.7);
        --glass-border: rgba(128, 128, 128, 0.1);
        --glass-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
    }

    html, body, [class*="css"], label, p, span {
        font-family: var(--font-main);
        font-size: 0.9rem; /* Compact font size */
    }

    /* Streamlit Main Container Optimization */
    .block-container {
        padding-top: 1rem;
        padding-bottom: 2rem;
        max-width: 1200px;
    }

    /* --- Premium Glassmorphism Card --- */
    .app-glass-frame {
        background-color: var(--card-bg-light) !important;
        backdrop-filter: blur(12px) !important;
        -webkit-backdrop-filter: blur(12px) !important;
        padding: 20px !important;
        border-radius: 16px !important;
        border: 1px solid var(--glass-border) !important;
        margin-bottom: 24px !important;
        box-shadow: 0 4px 24px rgba(0, 0, 0, 0.04) !important;
    }
    
    [data-theme="dark"] .app-glass-frame {
        background-color: var(--card-bg-dark) !important;
    }

    /* --- Universal Glassmorphism Card --- */
    .css-card {
        background: var(--card-bg-light);
        backdrop-filter: blur(8px);
        -webkit-backdrop-filter: blur(8px);
        padding: 24px;
        border-radius: 16px;
        box-shadow: var(--glass-shadow);
        margin-bottom: 24px;
        border: 1px solid var(--glass-border);
        transition: transform 0.2s ease, box-shadow 0.2s ease;
    }
    
    [data-theme="dark"] .css-card {
        background: var(--card-bg-dark);
    }

    /* --- Metric Containers Refined --- */
    div[data-testid="metric-container"] {
        background: var(--card-bg-light);
        backdrop-filter: blur(4px);
        padding: 1.25rem;
        border-radius: 16px;
        border: 1px solid var(--glass-border);
        box-shadow: 0 2px 8px rgba(0,0,0,0.03);
        min-width: 180px; /* Prevent cramping */
    }
    
    [data-theme="dark"] div[data-testid="metric-container"] {
        background: var(--card-bg-dark);
    }

    div[data-testid="metric-container"] label {
        font-family: var(--font-header);
        color: var(--text-color);
        opacity: 0.65;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        font-size: 0.8rem;
    }

    div[data-testid="metric-container"] div[data-testid="stMetricValue"] {
        font-family: var(--font-header);
        color: var(--text-color);
        font-weight: 700;
        font-size: 1.5rem; /* Reduced from 1.8rem */
    }

    /* --- Modern Headers --- */
    h1, h2, h3 {
        font-family: var(--font-header);
        font-weight: 700;
        letter-spacing: -0.01em;
        margin-bottom: 0.5rem !important;
    }
    
    h1 { font-size: 1.6rem !important; }
    h2 { font-size: 1.2rem !important; }
    h3 { font-size: 0.95rem !important; }

    /* --- Sidebar Visual Differentiation --- */
    [data-testid="stSidebar"] {
        border-right: 1px solid var(--glass-border);
    }
    
    [data-testid="stSidebar"] .stPills [data-testid="stBaseButton-secondaryPill"] {
        font-weight: 500;
    }

    /* --- Transaction Table & RTL Helpers --- */
    .rtl-text {
        direction: rtl;
        text-align: right;
        font-family: var(--font-main);
    }

    /* Target the data editor cells with Hebrew content */
    [data-testid="stDataFrame"] {
        border-radius: 12px;
        overflow: hidden;
        border: 1px solid var(--glass-border);
    }

    /* --- Buttons with Micro-animations --- */
    .stButton button {
        border-radius: 10px;
        font-weight: 600;
        border: 1px solid var(--glass-border);
        transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
        text-transform: none;
        letter-spacing: 0.01em;
    }
    
    .stButton button:hover {
        transform: translateY(-1px);
        box-shadow: 0 4px 12px rgba(0,0,0,0.1);
        border-color: #FF4B4B;
    }

    /* --- Search Input Styling --- */
    [data-testid="stTextInput"] input {
        border-radius: 12px;
        border: 1px solid var(--glass-border);
        padding: 0.6rem 1rem;
    }

    /* --- Force Red Accents on Primary Elements (Premium Outlined) --- */
    [data-testid="stBaseButton-pillsActive"] {
        background-color: rgba(255, 75, 75, 0.08) !important;
        color: #FF4B4B !important;
        border: 1px solid #FF4B4B !important;
        font-weight: 600 !important;
    }
    
    [data-testid="stBaseButton-pills"] {
        border-radius: 20px !important;
        border: 1px solid rgba(128, 128, 128, 0.2) !important;
        background-color: transparent !important;
        transition: all 0.2s ease !important;
    }

    [data-testid="stBaseButton-pills"]:hover {
        border-color: #FF4B4B !important;
        color: #FF4B4B !important;
        background-color: rgba(255, 75, 75, 0.04) !important;
    }
    
    /* Support legacy/secondary pills just in case */
    [data-testid="stBaseButton-secondaryPill"][aria-pressed="true"] {
        background-color: rgba(255, 75, 75, 0.08) !important;
        color: #FF4B4B !important;
        border: 1px solid #FF4B4B !important;
    }

    /* Primary buttons (Save, etc) */
    .stButton button {
        border-radius: 12px !important;
        font-weight: 600 !important;
        border: 1px solid rgba(128, 128, 128, 0.2) !important;
    }

    /* Danger Zone Aesthetic */
    .danger-zone {
        background-color: rgba(255, 75, 75, 0.02) !important;
        border: 1px solid rgba(255, 75, 75, 0.1) !important;
    }

    /* --- Premium Divider --- */
    hr.premium-hr {
        border: 0 !important;
        height: 1px !important;
        background: linear-gradient(90deg, transparent, rgba(128, 128, 128, 0.3), transparent) !important;
        margin: 3rem 0 !important;
        clear: both !important;
    }

    /* Clean up standard Streamlit dividers */
    hr {
        background-color: rgba(128, 128, 128, 0.1) !important;
        height: 1px !important;
    }

    /* --- AI Summary Specific Styles --- */
    .ai-insight-card {
        background: linear-gradient(135deg, rgba(99, 102, 241, 0.05) 0%, rgba(168, 85, 247, 0.05) 100%);
        border-left: 3px solid #6366F1;
        padding: 16px;
        border-radius: 12px;
        margin: 12px 0;
        transition: transform 0.2s ease;
    }
    
    .ai-insight-card:hover {
        transform: translateX(4px);
    }
    
    .anomaly-highlight {
        background: rgba(255, 75, 75, 0.05);
        border: 1px solid rgba(255, 75, 75, 0.2);
        border-radius: 8px;
        padding: 8px;
    }
    
    .recommendation-box {
        background: rgba(34, 197, 94, 0.05);
        border-left: 3px solid #22C55E;
        padding: 12px;
        border-radius: 8px;
        margin: 8px 0;
    }
    
    /* AI Summary header gradient */
    .ai-summary-header {
        background: linear-gradient(90deg, #6366F1 0%, #EC4899 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
    }

    </style>
    """, unsafe_allow_html=True)



import contextlib

@contextlib.contextmanager
def card(class_name=""):
    st.markdown(f'<div class="premium-glass-card {class_name}">', unsafe_allow_html=True)
    yield
    st.markdown('</div>', unsafe_allow_html=True)

def divider():
    """Renders a premium, subtle horizontal line."""
    st.markdown('<hr class="premium-hr">', unsafe_allow_html=True)
