import streamlit as st
from src.ui import sidebar, dashboard, data_editor, upload, ai_assistant, styles

st.set_page_config(page_title="Finance Tracker", layout="wide", page_icon="💸")

styles.load_css()

st.title("💸 Finance Tracker")

# 1. Sidebar Logic & Navigation
filters = sidebar.render_sidebar()
view = filters["selected_view"]

# 2. Main Content Routing
if view == "Dashboard":
    dashboard.render_dashboard(filters)

elif view == "Data Editor":
    data_editor.render_data_editor(filters)

elif view == "Upload Data":
    upload.render_upload()

elif view == "AI Assistant":
    ai_assistant.render_ai_assistant()
