"""How far into each transcript the diary has already recorded.

The Stop Hook fires once per assistant turn, not once per session, and it used
to re-read the transcript from line 1 every time. Measured across one real
diary: 5,904 of 6,971 entries (85%) were copies of an earlier entry in the same
session, one session having 395 copies of the same five prompts.

Transcripts are append-only — verified by hashing a live one's first 100, 500,
1,000 and 2,000 lines, letting a turn pass, and hashing again while the file
grew by 22 lines — so a line count is enough to resume from.

Kept in its own file rather than in the search index or the audit log. The
index is a derived artifact that `reindex` rebuilds from the Markdown, and a
rebuild must not be able to lose the position; the audit log is append-only
with no line count in it, so a position would have to be inferred by scanning
3.4MB on every turn. `backfill` already refuses to read session ids out of
derived artifacts for the same reason.
"""

import json
import os
from datetime import datetime, timedelta, timezone

from claude_diary.lib.filelock import FileLock
from claude_diary.log import get_logger

logger = get_logger("claude_diary.lib.progress")

PROGRESS_FILE = ".session_progress.json"


def get_progress_path(diary_dir):
    return os.path.join(diary_dir, PROGRESS_FILE)


def read_position(diary_dir, session_id, transcript_path):
    """Lines of this transcript already recorded, or None if unknown.

    None and 0 mean different things. 0 is "start from the beginning"; None is
    "there is no record of this session", which the caller answers differently
    depending on whether the diary already holds entries for it.
    """
    if not session_id:
        return None
    entry = _load(get_progress_path(diary_dir)).get(session_id)
    if not isinstance(entry, dict):
        return None

    stored_path = entry.get("transcript") or ""
    if stored_path and transcript_path and not _same_path(stored_path, transcript_path):
        # A different file under the same session id. Nothing about the old
        # count applies to it.
        return 0

    lines = entry.get("lines")
    if not isinstance(lines, int) or lines < 0:
        return None

    # A file shorter than the position was replaced or truncated; resuming
    # inside it would skip content that is now at a different offset.
    actual = _count_lines(transcript_path)
    if actual is not None and actual < lines:
        logger.warning(
            "Transcript for %s is shorter than recorded (%d < %d); "
            "recording it from the start.", session_id, actual, lines,
        )
        return 0

    return lines


def record_position(diary_dir, session_id, transcript_path, lines):
    """Store how far this session has been recorded. Best effort.

    Never raises: the diary entry is already written by the time this runs, and
    failing here should cost a repeated turn rather than the command.
    """
    if not session_id or not isinstance(lines, int) or lines < 0:
        return
    path = get_progress_path(diary_dir)
    try:
        with FileLock(path):
            data = _load(path)
            data[session_id] = {
                "lines": lines,
                "transcript": transcript_path or "",
                "updated": _now(),
            }
            _prune(data)
            _save(path, data)
    except Exception as e:
        logger.warning("Could not record read position: %s", e)


def _prune(data):
    """Drop sessions whose transcript is gone.

    Old transcripts stop being present — 65% of the sessions in one diary no
    longer have one — and without this the file only ever grows.
    """
    for session_id in list(data):
        entry = data.get(session_id)
        if not isinstance(entry, dict):
            del data[session_id]
            continue
        path = entry.get("transcript")
        if path and not os.path.exists(path):
            del data[session_id]


def _same_path(a, b):
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def _count_lines(path):
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return sum(1 for _ in f)
    except OSError:
        return None


def _now():
    return datetime.now(timezone(timedelta(hours=0))).isoformat()


def _load(path):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        # Same treatment as the other state files: keep the bytes rather than
        # overwrite them, because losing every position silently re-records
        # every live session from the beginning.
        from claude_diary.writer import preserve_corrupt
        logger.warning("%s was unreadable; starting a new one.", path)
        preserve_corrupt(path)
        return {}
    return data if isinstance(data, dict) else {}


def _save(path, data):
    tmp = "%s.tmp%d" % (path, os.getpid())
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
