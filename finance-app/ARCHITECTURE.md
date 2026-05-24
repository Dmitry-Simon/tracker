# Architecture

This document explains *how* the code is organized and *how data flows through
it*. For setup and run instructions, see [README.md](README.md).

## One-paragraph overview

The tracker has two completely separate execution paths sharing one Firestore
database:

1. **Streamlit app (`main.py`)** — the interactive UI. Manual statement
   uploads, dashboards, AI chat, the data editor.
2. **Auto-ingest pipeline (`scripts/auto_ingest.py`)** — a headless script.
   Reads statement files dropped in `scrape/inbox/`, dedupes them against
   Firestore, inserts new rows, runs AI categorization, and sends a
   Telegram/email summary. Triggered by Windows Task Scheduler.

Both paths use the **same parsers** (`src/parsers/`) and the **same dedup +
write logic** (`src/db.py`). That's intentional — a duplicate uploaded via the
UI and one auto-ingested produce identical hashes.

## Flow 1 — Streamlit upload

```
User drops .xlsx into upload UI
        │
        ▼
src/ui/upload.py
        │ calls
        ▼
src/parsers/__init__.py::detect_and_parse(file_obj, filename)
        │ dispatches by signature (תאריך תנועה → One Zero, תאריך רכישה → Isracard, …)
        ▼
src/parsers/{_one_zero,_isracard,_max_card}.py
        │ returns list[dict] transactions
        ▼
two-phase duplicate review UI  (src/ui/upload.py)
        │ user confirms which to keep
        ▼
src/db.py::add_transaction()  →  Firestore `transactions` collection
        │
        ▼
optional: AI categorize via src/ai.py
```

## Flow 2 — Auto-ingest (headless)

```
Windows Task Scheduler @ 07:00
        │
        ▼
scripts/run_auto_ingest.bat       (activates .venv, runs python)
        │
        ▼
scripts/auto_ingest.py
        │
        │ 1. acquire lockfile state/.running
        │ 2. for each file in scrape/inbox/:
        │       parsers.detect_and_parse  →  list[dict]
        │       for each tx: _check_near_dupe  →  add_transaction
        │ 3. AI categorize loop (5 iter max)  →  src/ai.py
        │ 4. archive consumed files to scrape/inbox/processed/
        │ 5. write logs/ingest_<ts>.json
        │ 6. send_summary  →  src/notify.py  →  SMTP + Telegram
        ▼
state/last_run.json updated
```

## How statements get into `scrape/inbox/` today

Both refresh paths are **manual but low-friction**. There is no live scraper.

### Isracard

The Node-based scraper was abandoned — Cloudflare blocks the login API
permanently. Workflow:

1. Open Chrome to <https://digital.isracard.co.il>, log in.
2. Browse to `web.isracard.co.il/transactions`.
3. Call the `ExportExcel` API for each billing cycle (Chrome DevTools console
   or programmatically). Decoded base64 = the same `.xlsx` Isracard's UI
   produces when you click "download excel".
4. Drop the `.xlsx` files in `scrape/inbox/`.
5. Run `python scripts/auto_ingest.py`.

The API shape:

```
POST https://web.isracard.co.il/ocp/transactions/DigitalV3.Transactions/ExportExcel
Content-Type: application/json
{"card4Number": "0164",
 "billingMonth": "01/06/2026",
 "isNextBillingDate": true,           # false for closed cycles
 "shouldCallMonthlyBilling": false,   # true for closed cycles
 "cardStatus": 0, "companyCode": 11, "isPartner": false,
 "serviceType": 35, "getCardListCompanyCode": 99}
```

Sessions expire fast (minutes idle, <24h hard cap). For unattended automation
the eventual path is **Playwright Python with a persistent `storage_state.json`**
that handles login interactively the first time and reuses cookies after.

### One Zero

App-only bank; no web UI to scrape. Workflow:

1. Open the One Zero mobile app.
2. Export Excel for the period you want.
3. Drop the `.xls` into `scrape/inbox/`.
4. Run `python scripts/auto_ingest.py`.

## Module map

```
finance-app/
├── main.py                            Streamlit entry point — wires up the UI tabs.
├── requirements.txt
├── .streamlit/
│   ├── config.toml                    Streamlit theme + server settings.
│   └── secrets.toml                   Firebase creds + Gemini key (gitignored).
├── .env.example                       Headless secrets template (real .env gitignored).
├── ARCHITECTURE.md                    This file.
├── README.md                          Setup + run guide.
├── scripts/
│   ├── auto_ingest.py                 Headless pipeline (see Flow 2).
│   ├── run_auto_ingest.bat            Windows wrapper: activate venv, run python.
│   └── install_task.ps1               One-time Task Scheduler registration.
├── scrape/
│   └── inbox/                         Drop statement files here (gitignored).
│       └── processed/                 Auto-ingest archives consumed files here.
├── state/                             Run state — last_run.json, .running lockfile.
├── logs/                              Per-run ingest_<ts>.json.
└── src/
    ├── config.py                      Unified secrets loader (Streamlit OR env).
    ├── constants.py                   CATEGORIES, SPENDER_NAMES, AI_MODELS list.
    ├── db.py                          Firestore + dedup + hash IDs + MOCK_MODE.
    ├── ai.py                          Gemini integration (categorization + chat).
    ├── auth.py                        Optional Streamlit password gate.
    ├── notify.py                      SMTP + Telegram summary fanout.
    ├── utils.py                       Metric helpers (income/expense math).
    ├── ai_summary_cache.py            Monthly-report cache in Firestore.
    ├── parsers/                       Per-bank statement parsers (see below).
    │   ├── __init__.py                TransactionParser + detect_and_parse + router.
    │   ├── _base.py                   Shared utilities (clean_amount, parse_date, …).
    │   ├── _one_zero.py               One Zero PDF + Excel.
    │   ├── _isracard.py               Isracard Excel + PDF.
    │   └── _max_card.py               Max It Finance Excel (multi-sheet).
    └── ui/
        ├── sidebar.py                 Navigation, period filters, theme toggle.
        ├── dashboard.py               KPIs and Plotly charts.
        ├── upload.py                  File upload + duplicate review.
        ├── data_editor.py             Inline editing of transactions.
        ├── ai_assistant.py            Chat with your transactions.
        ├── ai_summary.py              Monthly AI-generated reports.
        ├── styles.py                  Custom CSS injection.
        └── theme_manager.py           Dark/light mode toggle.
```

## Data model

### Firestore collections

| Collection      | Purpose                                       |
|-----------------|-----------------------------------------------|
| `transactions`  | Every parsed transaction. Doc ID = hash_id.   |
| `settings`      | App-level settings (monthly budget, etc).     |
| `ai_summaries`  | Cached monthly AI-generated reports.          |

### Transaction document shape

```python
{
    "_id":              str,        # = hash_id (also the Firestore doc ID)
    "date":             "YYYY-MM-DD",
    "description":      str,
    "amount":           float,      # negative = expense, positive = income/refund
    "currency":         "ILS",
    "category":         str,        # CATEGORIES from constants.py, or "Uncategorized"
    "spender":          str,        # one of SPENDER_NAMES
    "source_file":      str,        # "OneZero_Excel" / "Isracard" / "Max_Card" / ...
    "uploaded_from":    str,        # original filename or "auto:<name>"
    "ref_id":           str | None, # bank's own reference ID when available
    "bank_category":    str | None, # only set by OneZero Excel (סוג פעולה)
    "transaction_type": str | None, # only set by OneZero Excel (חיוב/זיכוי)
    "hash_id":          str,        # SHA256(date|amount|description|ref_id)
    "created_at":       Timestamp,
}
```

Hash IDs are produced by `db.generate_hash_id(date, amount, description,
ref_id)`. Two transactions are considered the same iff their hashes match —
this is what lets the upload UI and the auto-ingest pipeline both write
without producing dupes.

### Dedup confidence (near-duplicates)

Inside a ±3-day window, every candidate is scored against existing rows
(`db.calculate_duplicate_confidence`). Outcomes in the auto-ingest pipeline:

- `1.0` (ref_id-equal + amount-equal **or** exact hash match) → skipped, dupe.
- `>= 0.85` → skipped, high-confidence dupe.
- `0.75 ≤ x < 0.85` → skipped, "uncertain" (per user policy; visible in the
  manual review UI later).
- else → inserted.

## Configuration

Two parallel secret sources, both supported simultaneously:

1. `.streamlit/secrets.toml` — used by Streamlit. Has `[gcp_service_account]`,
   `[gemini] api_key`, `[user_profile]` (card patterns, spender names).

2. `finance-app/.env` — used by the headless pipeline. Has
   `GCP_SERVICE_ACCOUNT_JSON`, `GEMINI_API_KEY`, `CARD_PATTERNS_JSON`,
   `SPENDER_NAMES_JSON`, `SMTP_USER`, `SMTP_APP_PASSWORD`,
   `SUMMARY_RECIPIENTS`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.

`src/config.py` unifies access: it checks `st.secrets` first (Streamlit
runtime), then falls back to env vars / `.env` (headless). All other code
imports from `config.py`, not from `st.secrets` directly.

If neither source has Firebase creds, `db.py` flips to `MOCK_MODE` and reads
/writes a local `mock_db.json` instead.

## Adding a new bank

1. Add `src/parsers/_<bank>.py` with a `<Bank>Mixin` class that defines
   `_parse_<bank>_excel(self, file_obj)` (and/or `_pdf`). Use `self.clean_amount`,
   `self.parse_date`, `self.detect_spender` from `BaseParserMixin`.
2. Add the mixin to `TransactionParser`'s bases in `src/parsers/__init__.py`.
3. Add a signature check to `parse_file` (a Hebrew header substring is usually
   the cleanest discriminator).
4. Pick a `source_file` string — add it to the right list in
   `db.is_bank_cc_overlap` (`bank_sources` or `cc_sources`) if cross-source
   overlap matters for your dedup.
