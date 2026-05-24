"""Headless auto-ingest pipeline.

Flow:
  1. Spawn Node scraper (scrape/scrape.js) which writes JSON files to scrape/inbox/.
  2. Adapt scraper-JSON -> internal schema.
  3. Dedupe each candidate against existing DB rows in a +-3-day window:
       - exact hash match: enrich-or-skip
       - ref_id-equality with same amount: hard override -> skipped as dupe
       - confidence >= 0.85: skipped as high-confidence dupe
       - 0.75 <= confidence < 0.85: skipped as uncertain (per user policy)
       - else: insert
  4. Loop AI categorization (5 iterations max) to drain the uncategorized backlog.
  5. Archive processed JSON files. Update state/last_run.json.
  6. Email summary (or failure) via src.notify.

Flags:
  --dry-run        do everything except DB writes and email send
  --skip-scrape    consume existing files in scrape/inbox/ without spawning Node
"""
import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
import traceback
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import adapters, db  # noqa: E402
from src.ai import enrich_uncategorized_data  # noqa: E402

INBOX = ROOT / "scrape" / "inbox"
PROCESSED = INBOX / "processed"
STATE = ROOT / "state"
LOGS = ROOT / "logs"
SCRAPE_DIR = ROOT / "scrape"
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


def _run_scrape(log: dict) -> int:
    if not SCRAPE_DIR.exists():
        log["errors"].append("scrape/ directory missing — skipping scrape step")
        return 0
    INBOX.mkdir(parents=True, exist_ok=True)
    try:
        r = subprocess.run(
            ["node", "scrape.js", str(INBOX), str(STATE)],
            cwd=str(SCRAPE_DIR),
            capture_output=True, text=True, timeout=600,
        )
    except FileNotFoundError:
        log["errors"].append("node not found on PATH — install Node.js or use --skip-scrape")
        return 1
    except subprocess.TimeoutExpired:
        log["errors"].append("scraper timed out after 600s")
        return 1

    log["scrape_exit"] = r.returncode
    log["scrape_stdout_tail"] = (r.stdout or "")[-2000:]
    log["scrape_stderr_tail"] = (r.stderr or "")[-2000:]
    return r.returncode


def _ingest_file(path: Path, log: dict, dry_run: bool):
    """Process one file. Supports two formats:
      - *.json: scraper output (see adapters.adapt)
      - *.xlsx / *.xls / *.csv / *.pdf: bank statement, parsed by parsers.detect_and_parse
    """
    suffix = path.suffix.lower()
    if suffix == ".json":
        doc = json.loads(path.read_text(encoding="utf-8"))
        src = doc.get("source", path.stem)
        txs = adapters.adapt(doc)
    elif suffix in (".xlsx", ".xls", ".csv", ".pdf"):
        # Use the existing tracker parser (same path the Streamlit upload UI uses).
        from src import parsers
        with path.open("rb") as f:
            txs = parsers.detect_and_parse(f, path.name)
        # Tag everything with `uploaded_from` so we can trace it back to this run
        for tx in txs:
            tx.setdefault("uploaded_from", f"auto:{path.name}")
        # Group by source_file value (e.g. "Isracard", "OneZero_Excel")
        src = txs[0].get("source_file", path.stem) if txs else path.stem
    else:
        log["errors"].append(f"unsupported file type: {path.name}")
        return

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
                    help="do everything except DB writes and email send")
    ap.add_argument("--skip-scrape", action="store_true",
                    help="consume existing files in scrape/inbox/ without spawning Node")
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
        if not args.skip_scrape:
            rc = _run_scrape(log)
            if rc == 1:
                # config / fatal — abort before touching DB
                raise RuntimeError(
                    f"scraper fatal exit (rc=1). stderr: {log.get('scrape_stderr_tail','')}"
                )
            # rc 0 = ok; 42 = OneZero OTP needed (partial success); 43/44 = per-source failures
            if rc in (42, 43, 44):
                log["errors"].append(f"scraper exit {rc} — partial success; continuing with whatever JSON landed")

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
