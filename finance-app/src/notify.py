"""Notification transport(s) for the auto-ingest pipeline.

Supports two channels — both optional, both checked independently:

  Telegram (preferred for personal use)
    TELEGRAM_BOT_TOKEN    — token from @BotFather
    TELEGRAM_CHAT_ID      — your chat id (from getUpdates)

  SMTP (Gmail app password)
    SMTP_USER, SMTP_APP_PASSWORD, SMTP_HOST, SMTP_PORT,
    SUMMARY_RECIPIENTS, NOTIFY_FROM_NAME

The pipeline calls send_summary / send_failure once; this module fans the
message out to whichever channels are configured. If none are configured,
the calls log and return False; the orchestrator treats notifications as
best-effort.
"""
import json
import os
import smtplib
import ssl
import urllib.parse
import urllib.request
from email.message import EmailMessage


def _smtp_configured() -> bool:
    return bool(os.environ.get("SMTP_USER")
                and os.environ.get("SMTP_APP_PASSWORD")
                and os.environ.get("SUMMARY_RECIPIENTS"))


def _telegram_configured() -> bool:
    return bool(os.environ.get("TELEGRAM_BOT_TOKEN")
                and os.environ.get("TELEGRAM_CHAT_ID"))


def _send_smtp(subject: str, body: str) -> bool:
    user = os.environ["SMTP_USER"]
    pw = os.environ["SMTP_APP_PASSWORD"]
    host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    port = int(os.environ.get("SMTP_PORT", "465"))
    from_name = os.environ.get("NOTIFY_FROM_NAME", "Finance Tracker Bot")
    recipients = [x.strip() for x in os.environ["SUMMARY_RECIPIENTS"].split(",") if x.strip()]

    msg = EmailMessage()
    msg["From"] = f"{from_name} <{user}>"
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject
    msg.set_content(body)

    context = ssl.create_default_context()
    if port == 465:
        with smtplib.SMTP_SSL(host, port, context=context) as s:
            s.login(user, pw)
            s.send_message(msg)
    else:
        with smtplib.SMTP(host, port) as s:
            s.starttls(context=context)
            s.login(user, pw)
            s.send_message(msg)
    return True


def _send_telegram(subject: str, body: str) -> bool:
    """Telegram messages have a 4096-char limit. We send subject + body in one
    message, truncate if too long, and use HTML mode for a tiny bit of structure.
    Returns True on Telegram API success."""
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]

    text = f"<b>{_html_escape(subject)}</b>\n\n<pre>{_html_escape(body)}</pre>"
    if len(text) > 4000:
        text = text[:3990] + "\n…</pre>"

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            payload = json.loads(r.read().decode("utf-8"))
            if not payload.get("ok"):
                print(f"[notify] Telegram API responded not-ok: {payload}")
                return False
            return True
    except Exception as e:
        print(f"[notify] Telegram send failed: {e}")
        return False


def _html_escape(s: str) -> str:
    return (str(s)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;"))


def _send(subject: str, body: str) -> bool:
    """Fan out to every configured channel. Returns True if at least one delivered."""
    sent_any = False
    if _telegram_configured():
        try:
            if _send_telegram(subject, body):
                sent_any = True
        except Exception as e:
            print(f"[notify] Telegram send failed: {e}")
    if _smtp_configured():
        try:
            if _send_smtp(subject, body):
                sent_any = True
        except Exception as e:
            print(f"[notify] SMTP send failed: {e}")
    if not sent_any:
        print("[notify] No notification channel configured (need TELEGRAM_BOT_TOKEN+TELEGRAM_CHAT_ID "
              "and/or SMTP_USER+SMTP_APP_PASSWORD+SUMMARY_RECIPIENTS).")
    return sent_any


def _format_uncertain_samples(samples):
    if not samples:
        return ""
    lines = ["", "Uncertain auto-skips (review in Streamlit if any look wrong):"]
    for s in samples[:15]:
        lines.append(f"  - {s.get('date','')}  {s.get('desc','')[:50]:<50}  "
                     f"{s.get('amount',0):>10.2f}  conf={s.get('confidence','?')}")
    if len(samples) > 15:
        lines.append(f"  ... and {len(samples) - 15} more")
    return "\n".join(lines)


def _by_source_summary(by_source: dict) -> str:
    if not by_source:
        return "  (none)"
    lines = []
    for src, stats in by_source.items():
        lines.append(
            f"  {src:<14} candidates={stats.get('candidates',0):<4} "
            f"added={stats.get('added',0):<4} updated={stats.get('updated',0):<4} "
            f"dupe={stats.get('skipped_dupe',0):<4} uncertain={stats.get('skipped_uncertain',0)}"
        )
    return "\n".join(lines)


def send_summary(log: dict) -> bool:
    body = (
        f"Auto-ingest summary — started {log.get('start_utc','?')} UTC\n"
        f"Mode: {'DRY-RUN' if log.get('dry_run') else 'LIVE'}\n\n"
        f"  Added:               {log.get('added',0)}\n"
        f"  Updated (enriched):  {log.get('updated',0)}\n"
        f"  Skipped (dupe):      {log.get('skipped_dupe',0)}\n"
        f"  Skipped (uncertain): {log.get('skipped_uncertain',0)}\n"
        f"  AI categorized:      {log.get('ai_categorized',0)}\n\n"
        f"By source:\n{_by_source_summary(log.get('by_source', {}))}\n"
        f"{_format_uncertain_samples(log.get('uncertain_samples', []))}\n\n"
        f"Errors: {len(log.get('errors', []))}\n"
    )
    if log.get("errors"):
        body += "\nFirst errors (truncated):\n" + "\n".join(
            str(e)[:300] for e in log["errors"][:3]
        )
    subject = f"[Tracker] Daily ingest — {log.get('added',0)} new"
    if log.get("errors"):
        subject = f"[Tracker] Ingest with errors — {log.get('added',0)} new, {len(log['errors'])} err"
    if log.get("scrape_exit") == 42:
        subject = "[Tracker] OneZero OTP needed — Isracard ran"
    return _send(subject, body)


def send_failure(log: dict) -> bool:
    body = (
        f"Auto-ingest FAILED at {log.get('start_utc','?')}.\n\n"
        f"Errors:\n" + "\n\n".join(str(e)[:1500] for e in log.get("errors", []))[:5000] + "\n\n"
        f"Partial counts: added={log.get('added',0)} skipped={log.get('skipped_dupe',0)}\n"
        f"Last log payload:\n{json.dumps({k: v for k, v in log.items() if k != 'errors'}, indent=2, default=str)[:3000]}"
    )
    return _send("[Tracker] FAILED — auto-ingest", body)
