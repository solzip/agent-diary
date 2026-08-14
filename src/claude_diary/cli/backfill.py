"""`agent-diary backfill` — import sessions that happened before you installed.

Until now the first thing a new user saw was nothing. `init` registers the
Stop Hook, and then you wait for a session to end before the tool can show
you what it does.

Claude Code has been keeping transcripts on disk the whole time, under
`~/.claude/projects/<encoded-cwd>/<session-id>.jsonl`. This reads them and
files each one under the day it was actually worked, so a fresh install has
history in it immediately.

Two properties matter here:

- **Repeatable.** A session already present in the diary is skipped, so
  running it twice does not double anything. The check reads the diary files
  themselves rather than the audit log or the index, because those are
  derived and the diary is the thing being protected from duplicates.
- **Ordered.** Sessions are imported oldest first, so entries land in the
  same order they would have if the hook had written them at the time.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, NamedTuple, Optional, Set

from claude_diary.config import CLAUDE_TRANSCRIPT_ROOT, load_config, resolve_diary_dir
from claude_diary.core import process_session
from claude_diary.log import configure_from_config, get_logger

logger = get_logger("claude_diary.cli.backfill")

DEFAULT_TRANSCRIPT_ROOT = CLAUDE_TRANSCRIPT_ROOT

# The writer emits the full session id on its own line inside a <details>
# block. That line is what makes an import repeatable.
_SESSION_ID_LINE = re.compile(r"^<code>([0-9A-Za-z][0-9A-Za-z._-]{7,})</code>\s*$", re.M)

# Records that carry no work, only session bookkeeping. Reading a 300MB
# transcript tree to find a cwd and a timestamp is worth short-circuiting.
_DISCOVERY_SCAN_LIMIT = 200


class Candidate(NamedTuple):
    """A transcript that could become a diary entry."""

    path: str
    session_id: str
    cwd: str
    started_at: datetime


def cmd_backfill(args) -> None:
    config = load_config()
    configure_from_config(config)

    diary_dir = resolve_diary_dir(config)
    tz_offset = config.get("timezone_offset", 9)
    local_tz = timezone(timedelta(hours=tz_offset))

    root = os.path.expanduser(getattr(args, "transcripts", None) or DEFAULT_TRANSCRIPT_ROOT)
    if not os.path.isdir(root):
        print("[agent-diary backfill] No transcripts found at: %s" % root)
        print("  Claude Code writes them there. Pass --transcripts to point elsewhere.")
        return

    since = _parse_since(getattr(args, "since", None))
    if getattr(args, "since", None) and since is None:
        print("[agent-diary backfill] --since must be YYYY-MM-DD", flush=True)
        raise SystemExit(2)

    recorded = _recorded_session_ids(diary_dir)
    candidates, subagents = _discover(root)

    total = len(candidates)
    pending = [c for c in candidates if c.session_id not in recorded]
    already = total - len(pending)

    if since is not None:
        before = len(pending)
        pending = [c for c in pending if c.started_at.astimezone(local_tz).date() >= since]
        skipped_by_date = before - len(pending)
    else:
        skipped_by_date = 0

    pending.sort(key=lambda c: c.started_at)

    limit = getattr(args, "limit", None)
    truncated = 0
    if limit and limit > 0 and len(pending) > limit:
        truncated = len(pending) - limit
        pending = pending[:limit]

    print("[agent-diary backfill] %d session transcript(s) under %s" % (total, root))
    if subagents:
        print("  subagent transcripts : %d  (not sessions, skipped)" % subagents)
    print("  already in the diary : %d" % already)
    if skipped_by_date:
        print("  before --since       : %d" % skipped_by_date)
    if truncated:
        print("  beyond --limit       : %d" % truncated)
    print("  to import            : %d" % len(pending))

    if not pending:
        return

    if getattr(args, "dry_run", False):
        print("\n--dry-run, nothing written:")
        for c in pending:
            print("  %s  %-28s %s" % (
                c.started_at.astimezone(local_tz).strftime("%Y-%m-%d %H:%M"),
                _project_of(c.cwd),
                c.session_id[:8],
            ))
        return

    written = 0
    empty = 0
    failed = 0
    for c in pending:
        try:
            if process_session(c.session_id, c.path, c.cwd, when=c.started_at):
                written += 1
            else:
                empty += 1
        except Exception as e:
            failed += 1
            logger.warning("Backfill failed for %s: %s", c.session_id, e)

    print("\n  imported : %d" % written)
    if empty:
        print("  no content: %d" % empty)
    if failed:
        print("  failed    : %d  (see log)" % failed)
    print("  diary     : %s" % diary_dir)

    if failed:
        raise SystemExit(1)


def _recorded_session_ids(diary_dir: str) -> Set[str]:
    """Session ids already present in the diary.

    Reads the Markdown rather than the search index or the audit log: those
    are derived, and a stale one would let a duplicate through.
    """
    found: Set[str] = set()
    if not os.path.isdir(diary_dir):
        return found
    for path in Path(diary_dir).glob("*.md"):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        found.update(_SESSION_ID_LINE.findall(text))
    return found


def _discover(root: str) -> tuple:
    """Find importable transcripts. Returns (candidates, subagent_count).

    Subagents get their own transcript file, and on this machine they were
    115 of 194 — importing them would fill the diary with fragments of
    sessions rather than sessions.
    """
    out: List[Candidate] = []
    subagents = 0
    for path in Path(root).rglob("*.jsonl"):
        if _is_subagent_name(path.stem):
            subagents += 1
            continue
        meta = _read_head(str(path))
        if meta is None:
            continue
        cwd, started_at, is_subagent = meta
        if is_subagent:
            subagents += 1
            continue
        out.append(Candidate(
            path=str(path),
            session_id=path.stem,
            cwd=cwd,
            started_at=started_at,
        ))
    return out, subagents


def _is_subagent_name(stem: str) -> bool:
    return stem.startswith("agent-")


def _read_head(path: str) -> Optional[tuple]:
    """Pull the cwd, the first timestamp, and whether this is a subagent.

    Returns (cwd, started_at, is_subagent), or None when the transcript
    carries no cwd or no timestamp — it could then be filed against neither a
    project nor a date, and guessing at either is worse than skipping.

    Both subagent signals were checked against a real tree of 194
    transcripts: the `agent-` filename prefix and an `agentId` field select
    exactly the same 115 files, and `agentId` is always on the first record.
    The field is the semantic check; the filename is a cheap pre-filter that
    avoids opening the file at all.
    """
    cwd = None
    started_at = None
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f):
                if i >= _DISCOVERY_SCAN_LIMIT:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
                if not isinstance(rec, dict):
                    continue
                if rec.get("agentId"):
                    return "", None, True
                if cwd is None and rec.get("cwd"):
                    cwd = rec["cwd"]
                if started_at is None and rec.get("timestamp"):
                    started_at = _parse_timestamp(rec["timestamp"])
                if cwd and started_at:
                    return cwd, started_at, False
    except OSError:
        return None
    return None


def _parse_timestamp(raw: str) -> Optional[datetime]:
    """Parse an ISO-8601 timestamp, tolerating the trailing Z.

    `datetime.fromisoformat` only learned to read `Z` in 3.11, and this
    project supports 3.8.
    """
    if not raw:
        return None
    text = str(raw).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _parse_since(raw: Optional[str]):
    if not raw:
        return None
    try:
        return datetime.strptime(str(raw).strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def _project_of(cwd: str) -> str:
    name = str(cwd or "").replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
    return name or "unknown"


__all__ = ["cmd_backfill"]
