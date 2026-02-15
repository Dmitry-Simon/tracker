# Finance Tracker

A personal finance management tool built with **Streamlit**, **Firebase Firestore**, and **Google Gemini AI**. Upload bank statements, track spending, detect duplicates, and get AI-powered insights into your finances.

## Features

- **Dashboard** — Interactive charts and KPI metrics for income, expenses, savings, and budget tracking.
- **AI Assistant** — Chat with your financial data using Google Gemini (e.g. "How much did I spend on groceries last month?").
- **AI Summary** — Automated monthly financial reports with historical comparison.
- **Statement Upload** — Import bank/credit card statements in PDF and Excel formats with two-phase duplicate detection.
- **Data Editor** — Edit, categorize, and manage transactions manually.
- **Duplicate Detection** — Confidence-scored duplicate identification across bank and credit card sources.
- **Dark/Light Mode** — Theme toggle with custom styling.
- **Mock Mode** — Run locally without cloud credentials using a local JSON file.

## Tech Stack

- **Frontend**: [Streamlit](https://streamlit.io/)
- **Database**: [Google Firebase Firestore](https://firebase.google.com/docs/firestore)
- **AI**: [Google Gemini](https://ai.google.dev/) (flash models)
- **Data Processing**: Pandas, OpenPyXL, PDFPlumber, Plotly

## Prerequisites

- Python 3.9 or higher
- A Google Cloud project with Firestore enabled (for cloud mode)
- A Google AI Studio API key (for AI features)

---

## Setup

### 1. Clone the Repository

```bash
git clone https://github.com/your-username/finance-tracker.git
cd finance-tracker/finance-app
```

### 2. Create a Virtual Environment

#### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
```

#### Windows (Command Prompt)

```cmd
python -m venv .venv
.venv\Scripts\activate.bat
```

#### Windows (PowerShell)

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

> If you get an execution policy error on PowerShell, run:
> `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

**Dependencies**: streamlit, firebase-admin, google-generativeai, pandas, pdfplumber, openpyxl, xlrd, plotly, python-dotenv.

---

## Firebase Setup

### 1. Create a Firebase Project

1. Go to the [Firebase Console](https://console.firebase.google.com/).
2. Click **Add project** and follow the wizard.
3. Once created, navigate to **Build > Firestore Database**.
4. Click **Create database**, select a location, and start in **production mode**.

### 2. Generate a Service Account Key

1. In the Firebase Console, go to **Project Settings** (gear icon) > **Service accounts**.
2. Click **Generate new private key**. This downloads a JSON file.
3. Keep this file secure — it contains credentials for your database.

### 3. Configure Secrets

Create the file `.streamlit/secrets.toml` inside the `finance-app` directory:

```toml
[gemini]
api_key = "YOUR_GEMINI_API_KEY"

[gcp_service_account]
type = "service_account"
project_id = "your-project-id"
private_key_id = "your-private-key-id"
private_key = "-----BEGIN PRIVATE KEY-----\nYOUR_KEY_HERE\n-----END PRIVATE KEY-----\n"
client_email = "firebase-adminsdk-xxxxx@your-project-id.iam.gserviceaccount.com"
client_id = "123456789"
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "https://www.googleapis.com/robot/v1/metadata/x509/firebase-adminsdk-xxxxx%40your-project-id.iam.gserviceaccount.com"
universe_domain = "googleapis.com"
```

Copy the values from the downloaded service account JSON into the `[gcp_service_account]` section. Get your Gemini API key from [Google AI Studio](https://aistudio.google.com/apikey).

> **Mock Mode**: If no secrets file is found, the app falls back to mock mode using a local `mock_db.json` file. This is useful for development and testing without Firebase.

### 4. Firestore Collections

The app automatically creates three Firestore collections:

| Collection       | Purpose                              |
|------------------|--------------------------------------|
| `transactions`   | All uploaded financial transactions  |
| `settings`       | App settings (e.g. monthly budget)   |
| `ai_summaries`   | Cached AI-generated monthly reports  |

No manual collection setup is needed — they are created on first use.

---

## Running the App

### macOS / Linux

```bash
source .venv/bin/activate
streamlit run main.py
```

### Windows (Command Prompt)

```cmd
.venv\Scripts\activate.bat
streamlit run main.py
```

### Windows (PowerShell)

```powershell
.venv\Scripts\Activate.ps1
streamlit run main.py
```

The app opens at **http://localhost:8501**.

---

## Deploying to Streamlit Community Cloud

[Streamlit Community Cloud](https://streamlit.io/cloud) lets you host your app for free.

### 1. Push to GitHub

Make sure your code is in a GitHub repository. Do **not** commit `.streamlit/secrets.toml` (it should be in `.gitignore`).

### 2. Deploy

1. Go to [share.streamlit.io](https://share.streamlit.io/) and sign in with GitHub.
2. Click **New app**.
3. Select your repository, branch, and set the main file path to `finance-app/main.py`.
4. Click **Deploy**.

### 3. Add Secrets

1. Once the app is deployed, go to **App settings > Secrets**.
2. Paste the full contents of your local `.streamlit/secrets.toml` into the secrets editor.
3. Save. The app will restart with your credentials.

### Custom Domain and Settings

In the app dashboard on Streamlit Cloud you can also configure:
- Custom subdomain URL
- Python version
- Access controls (public or private)

---

## Project Structure

```
finance-app/
├── main.py                  # App entry point
├── requirements.txt         # Python dependencies
├── mock_db.json             # Local mock database (dev/testing)
├── .streamlit/
│   ├── config.toml          # Streamlit theme and server config
│   └── secrets.toml         # Credentials (not committed)
├── src/
│   ├── db.py                # Firestore integration and data models
│   ├── ai.py                # Gemini AI integration
│   ├── auth.py              # Optional password authentication
│   ├── parsers.py           # Bank statement parsing (PDF/Excel)
│   ├── utils.py             # Metric calculations and helpers
│   ├── ai_summary_cache.py  # AI summary caching
│   └── ui/
│       ├── sidebar.py       # Navigation and period filters
│       ├── dashboard.py     # Dashboard view with charts
│       ├── data_editor.py   # Transaction editing
│       ├── upload.py        # File upload with duplicate detection
│       ├── ai_assistant.py  # AI chat interface
│       ├── ai_summary.py    # AI financial reports
│       ├── styles.py        # Custom CSS
│       └── theme_manager.py # Dark/light mode toggle
├── scripts/                 # Maintenance and data migration scripts
└── tests/                   # Test suite
```

## Troubleshooting

| Issue | Solution |
|---|---|
| `ModuleNotFoundError` | Make sure the virtual environment is activated and dependencies are installed. |
| App starts in Mock Mode | Check that `.streamlit/secrets.toml` exists and contains valid Firebase credentials. |
| AI features not working | Verify your Gemini API key in `secrets.toml` under `[gemini] api_key`. |
| PowerShell won't activate venv | Run `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`. |
| Port 8501 already in use | Stop the other Streamlit process or run with `streamlit run main.py --server.port 8502`. |
