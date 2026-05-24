"""Headless ingest pipeline.

Consumes statement files dropped in scrape/inbox/ (Isracard .xlsx via chrome-devtools
export, OneZero .xls via app export) and runs the full ingest flow:

  1. Parse each file in scrape/inbox/ (.xlsx, .xls, .csv, .pdf, .json).
  2. Dedupe each candidate against existing DB rows in a +-3-day window:
       - exact hash match: enrich-or-skip
       - ref_id-equality with same amount: hard override -> skipped as dupe
       - confidence >= 0.85: skipped as high-confidence dupe
       - 0.75 <= confidence < 0.85: skipped as uncertain (per user policy)
       - else: insert
  3. Loop AI categorization (5 iterations max) to drain the uncategorized backlog.
  4. Archive processed files to scrape/inbox/processed/. Update state/last_run.json.
  5. Email/Telegram summary (or failure) via src.notify.

Flags:
  --dry-run        do everything except DB writes and notification send
"""
import argparse
import glob
import json
import os
import shutil
import sys
import traceback
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import db, parsers  # noqa: E402
from src.ai import enrich_uncategorized_data  # noqa: E402

INBOX = ROOT / "scrape" / "inbox"
PROCESSED = INBOX / "processed"
STATE = ROOT / "state"
LOGS = ROOT / "logs"
LOCK = STATE / ".running"

UNCERTAIN_LOW = 0.75
UNCERTAIN_HIGH = 0.85
AI_MAX_ITERATIONS = 5


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        h = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not h:
            return False
        ctypes.windll.kernel32.CloseHandle(h)
        return True
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _acquire_lock() -> bool:
    STATE.mkdir(exist_ok=True)
    if LOCK.exists():
        try:
            pid = int(LOCK.read_text().strip() or 0)
        except ValueError:
            pid = 0
        if _pid_alive(pid):
            print(f"Another auto_ingest is running (pid={pid}). Aborting.")
            return False
        # stale lock
    LOCK.write_text(str(os.getpid()))
    return True


def _release_lock():
    try:
        LOCK.unlink(missing_ok=True)
    except Exception:
        pass


def _check_near_dupe(tx: dict):
    """Return highest-confidence match against ±3-day window (or None if no
    candidates). Hard overrides:
      - ref_id equal + amount equal -> 1.0 (cutover safety vs old PDF uploads)
      - exact hash match -> 1.0
    """
    d = date.fromisoformat(tx["date"])
    window = db.get_transactions_by_range(
        (d - timedelta(days=3)).isoformat(),
        (d + timedelta(days=3)).isoformat(),
    )
    if not window:
        return None

    tx_hash = db.generate_hash_id(
        tx["date"], tx["amount"], tx["description"], tx.get("ref_id")
    )
    best = 0.0
    for existing in window:
        ex_ref = existing.get("ref_id")
        if (tx.get("ref_id") and ex_ref and tx["ref_id"] == ex_ref
                and abs(float(tx["amount"]) - float(existing.get("amount", 0))) < 0.01):
            return 1.0
        if existing.get("_id") == tx_hash:
            return 1.0
        score, _reason = db.calculate_duplicate_confidence(tx, existing)
        if score > best:
            best = score
    return best if best > 0 else None


def _ingest_file(path: Path, log: dict, dry_run: bool):
    """Parse one statement file via the same parser used by the Streamlit upload UI."""
    suffix = path.suffix.lower()
    if suffix not in (".xlsx", ".xls", ".csv", ".pdf"):
        log["errors"].append(f"unsupported file type: {path.name}")
        return

    with path.open("rb") as f:
        txs = parsers.detect_and_parse(f, path.name)
    for tx in txs:
        tx.setdefault("uploaded_from", f"auto:{path.name}")
    src = txs[0].get("source_file", path.stem) if txs else path.stem

    log["by_source"].setdefault(src, {"candidates": 0, "added": 0, "updated": 0,
                                      "skipped_dupe": 0, "skipped_uncertain": 0})
    log["by_source"][src]["candidates"] += len(txs)

    for tx in txs:
        if dry_run:
            continue
        try:
            near = _check_near_dupe(tx)
        except Exception as e:
            log["errors"].append(f"dedupe error for {tx.get('description','?')}: {e}")
            continue

        if near is not None and UNCERTAIN_LOW <= near < UNCERTAIN_HIGH:
            log["skipped_uncertain"] += 1
            log["by_source"][src]["skipped_uncertain"] += 1
            log["uncertain_samples"].append({
                "date": tx["date"], "desc": tx["description"][:60],
                "amount": tx["amount"], "confidence": round(near, 2),
            })
            continue
        if near is not None and near >= UNCERTAIN_HIGH:
            log["skipped_dupe"] += 1
            log["by_source"][src]["skipped_dupe"] += 1
            continue

        try:
            outcome = db.add_transaction(tx)
        except Exception as e:
            log["errors"].append(f"insert error for {tx.get('description','?')}: {e}")
            continue
        if outcome == "added":
            log["added"] += 1
            log["by_source"][src]["added"] += 1
        elif outcome == "updated":
            log["updated"] += 1
            log["by_source"][src]["updated"] += 1
        else:
            log["skipped_dupe"] += 1
            log["by_source"][src]["skipped_dupe"] += 1


def _ai_categorize_loop(log: dict):
    total = 0
    for _ in range(AI_MAX_ITERATIONS):
        try:
            count, err = enrich_uncategorized_data()
        except Exception as e:
            log["errors"].append(f"AI categorize error: {e}")
            break
        if err and "No uncategorized" not in (err or ""):
            log["ai_error"] = err
            break
        if not count:
            break
        total += count
    log["ai_categorized"] = total


def _archive_processed_files(json_files):
    PROCESSED.mkdir(exist_ok=True)
    for p in json_files:
        try:
            shutil.move(str(p), str(PROCESSED / p.name))
        except Exception:
            pass  # best-effort; if it fails, dedupe will catch on next run


def _write_run_log(log: dict):
    LOGS.mkdir(exist_ok=True)
    fname = f"ingest_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}.json"
    (LOGS / fname).write_text(json.dumps(log, indent=2, default=str), encoding="utf-8")


def _update_state(log: dict):
    STATE.mkdir(exist_ok=True)
    state_file = STATE / "last_run.json"
    try:
        prior = json.loads(state_file.read_text(encoding="utf-8"))
    except Exception:
        prior = {"schema_version": 1, "bootstrap_done": False}
    now = datetime.now(timezone.utc).isoformat()
    prior["schema_version"] = 1
    prior["last_attempt_utc"] = now
    if not log["errors"]:
        prior["last_success_utc"] = now
        prior["bootstrap_done"] = True
    state_file.write_text(json.dumps(prior, indent=2), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="do everything except DB writes and notification send")
    args = ap.parse_args()

    if not _acquire_lock():
        sys.exit(75)

    log = {
        "start_utc": datetime.now(timezone.utc).isoformat(),
        "dry_run": args.dry_run,
        "added": 0, "updated": 0,
        "skipped_dupe": 0, "skipped_uncertain": 0,
        "ai_categorized": 0,
        "by_source": {},
        "uncertain_samples": [],
        "errors": [],
    }

    try:
        candidate_files = []
        for ext in ("*.json", "*.xlsx", "*.xls", "*.csv", "*.pdf"):
            candidate_files.extend(glob.glob(str(INBOX / ext)))
        candidate_files = [Path(p) for p in sorted(candidate_files)]
        log["files_seen"] = [p.name for p in candidate_files]

        for path in candidate_files:
            try:
                _ingest_file(path, log, args.dry_run)
            except Exception as e:
                log["errors"].append(f"ingest failed for {path.name}: {e}\n{traceback.format_exc()}")

        if not args.dry_run:
            _ai_categorize_loop(log)
            _archive_processed_files(candidate_files)
            _update_state(log)

        # Email summary — best-effort; if SMTP is not configured, log and continue.
        if not args.dry_run:
            try:
                from src.notify import send_summary
                send_summary(log)
            except Exception as e:
                log["errors"].append(f"email send failed: {e}")

    except Exception:
        log["errors"].append(traceback.format_exc())
        if not args.dry_run:
            try:
                from src.notify import send_failure
                send_failure(log)
            except Exception:
                pass
        _write_run_log(log)
        _release_lock()
        raise
    else:
        _write_run_log(log)
        _release_lock()

    print(json.dumps({
        "added": log["added"], "updated": log["updated"],
        "skipped_dupe": log["skipped_dupe"],
        "skipped_uncertain": log["skipped_uncertain"],
        "ai_categorized": log["ai_categorized"],
        "errors": len(log["errors"]),
    }))


if __name__ == "__main__":
    main()
