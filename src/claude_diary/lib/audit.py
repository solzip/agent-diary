"""Audit log system — records every Hook execution for transparency and verification."""

import hashlib
import json
import os
import sys
from datetime import datetime, timezone, timedelta


def get_audit_path(diary_dir):
    """Return path to audit log file."""
    return os.path.join(diary_dir, ".audit.jsonl")


def log_entry(diary_dir, session_id, transcript_path, files_written,
              secrets_masked=0, exporters_called=None, exporters_failed=None,
              tz_offset=9):
    """Append an audit log entry.

    Args:
        diary_dir: Path to diary directory
        session_id: Claude session ID
        transcript_path: Path to transcript that was read
        files_written: List of files that were written
        secrets_masked: Number of secrets masked
        exporters_called: List of exporter names called
        exporters_failed: List of exporter names that failed
        tz_offset: Timezone offset for timestamp
    """
    local_tz = timezone(timedelta(hours=tz_offset))
    now = datetime.now(local_tz)

    entry = {
        "timestamp": now.isoformat(),
        "session_id": session_id,
        "action": "diary_entry_created",
        "files_read": [transcript_path] if transcript_path else [],
        "files_written": files_written or [],
        "secrets_masked": secrets_masked,
        "exporters_called": exporters_called or [],
        "exporters_failed": exporters_failed or [],
        "checksum": _compute_source_checksum(),
    }

    audit_path = get_audit_path(diary_dir)
    try:
        with open(audit_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        sys.stderr.write("[diary] Audit log write failed: %s\n" % str(e))


def read_audit_log(diary_dir, days=None, limit=10):
    """Read audit log entries.

    Args:
        diary_dir: Path to diary directory
        days: Filter to last N days (None = no filter)
        limit: Max entries to return

    Returns:
        List of audit entry dicts (newest first)
    """
    audit_path = get_audit_path(diary_dir)
    if not os.path.exists(audit_path):
        return []

    entries = []
    try:
        with open(audit_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    except Exception:
        return []

    # Filter by days (date string comparison, timezone-safe)
    if days is not None:
        cutoff_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        entries = [e for e in entries if e.get("timestamp", "")[:10] >= cutoff_date]

    # Return newest first, limited
    entries.reverse()
    return entries[:limit]


def verify_checksum(diary_dir):
    """Verify source code integrity by comparing checksums.

    Returns:
        (is_valid, current_checksum, last_logged_checksum)
    """
    current = _compute_source_checksum()

    # Get last logged checksum
    entries = read_audit_log(diary_dir, limit=1)
    if not entries:
        return (True, current, None)

    last_checksum = entries[0].get("checksum", "")
    is_valid = (current == last_checksum) if last_checksum else True

    return (is_valid, current, last_checksum)


def _compute_source_checksum():
    """Compute SHA-256 hash of core source files for tamper detection."""
    hasher = hashlib.sha256()

    # Hash all .py source files for comprehensive tamper detection
    src_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    for root, dirs, files in os.walk(src_dir):
        for fname in sorted(files):
            if fname.endswith(".py"):
                full_path = os.path.join(root, fname)
                try:
                    with open(full_path, "rb") as f:
                        hasher.update(f.read())
                except Exception:
                    pass

    return "sha256:" + hasher.hexdigest()
