"""Adapt israeli-bank-scrapers JSON output to the tracker's internal transaction schema.

The scraper returns a per-source document like:
    {"source": "oneZero" | "isracard",
     "scrapedAt": "<iso>",
     "accounts": [
         {"accountNumber": "...",
          "txns": [{type, identifier, date, processedDate,
                    originalAmount, originalCurrency,
                    chargedAmount, chargedCurrency,
                    description, memo, status, installments}]}]}

This module converts that to the dict shape consumed by db.add_transaction.
"""
from src.constants import get_card_patterns


def adapt(scraper_doc: dict) -> list[dict]:
    """Map a single scraper-JSON document to a list of internal transaction dicts."""
    source = scraper_doc.get("source", "")
    scraped_at = scraper_doc.get("scrapedAt", "")
    out = []
    for account in scraper_doc.get("accounts", []):
        acct_no = str(account.get("accountNumber", ""))
        for tx in account.get("txns", []):
            amt_charged = tx.get("chargedAmount")
            amt_orig = tx.get("originalAmount")
            amount_raw = (amt_charged if amt_charged is not None
                          else (amt_orig if amt_orig is not None else 0.0))
            amount = float(amount_raw)

            desc = (tx.get("description") or "").strip()
            ref_id_raw = tx.get("identifier")
            ref_id = str(ref_id_raw) if ref_id_raw is not None else None

            tx_date = (tx.get("date") or "")[:10]

            out.append({
                "date": tx_date,
                "description": desc,
                "amount": amount,  # signed: -=debit, +=credit
                "currency": tx.get("chargedCurrency") or tx.get("originalCurrency") or "ILS",
                "ref_id": ref_id,
                "source_file": "OneZero_Scraper" if source == "oneZero" else "Isracard_Scraper",
                "uploaded_from": f"auto:{source}:{scraped_at}",
                "spender": _detect_spender(desc, acct_no),
                "category": "Uncategorized",
                "bank_category": tx.get("type") or "",
                "transaction_type": "חיוב" if amount < 0 else "זיכוי",
            })
    return out


def _detect_spender(description: str, account_number: str) -> str:
    """Match card-pattern keys against description OR account_number.
    Scraper descriptions are clean (no card suffix), so the account number is
    often the only place the card identifier appears."""
    patterns = get_card_patterns()
    haystack = f"{description} {account_number}"
    for substr, name in patterns.items():
        if substr and substr in haystack:
            return name
    return "Joint"
