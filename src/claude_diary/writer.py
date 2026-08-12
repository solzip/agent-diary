"""Diary file writer — appends entries to daily markdown files."""

import json
import os
from pathlib import Path

from claude_diary.formatter import format_daily_header
from claude_diary.lib.filelock import FileLock
from claude_diary.log import get_logger

logger = get_logger("claude_diary.writer")


def ensure_diary_dir(diary_dir):
    """Create diary directory and subdirectories."""
    Path(diary_dir).mkdir(parents=True, exist_ok=True)
    Path(diary_dir, "weekly").mkdir(parents=True, exist_ok=True)


def append_entry(diary_dir, date_str, entry_text, lang="ko"):
    """Append a formatted diary entry to the daily file.

    Locked, because the Stop Hook runs once per session ending and two
    sessions can finish at the same moment. Unlocked, this had two races: the
    exists-then-create on the header let both processes write one, and an
    append this size is not atomic, so entries went missing outright. Twelve
    concurrent writers produced nine entries.
    """
    ensure_diary_dir(diary_dir)
    diary_path = os.path.join(diary_dir, "%s.md" % date_str)

    with FileLock(diary_path):
        if not os.path.exists(diary_path):
            with open(diary_path, "w", encoding="utf-8") as f:
                f.write(format_daily_header(date_str, lang))

        # Roll the file back to its previous length if the append fails
        # partway. A disk that fills mid-write stops at a byte boundary, not a
        # character one, and half a Korean character makes the whole file
        # undecodable — measured, `parse_daily_file` then reported zero
        # sessions for a day whose entries were still plainly there. Losing
        # the one entry we were writing is the acceptable outcome; losing the
        # day is not.
        size_before = os.path.getsize(diary_path)
        try:
            with open(diary_path, "a", encoding="utf-8") as f:
                f.write(entry_text)
        except Exception:
            _truncate_to(diary_path, size_before)
            raise


def update_session_count(diary_dir, date_str):
    """Track daily session count in a separate JSON file.

    A read-modify-write, so it needs the same lock: unlocked, concurrent
    sessions each read the same number and each write it back plus one, and
    the count drifts far below reality. Twelve concurrent writers left it
    reading four.
    """
    count_file = os.path.join(diary_dir, ".session_counts.json")

    with FileLock(count_file):
        counts = {}
        if os.path.exists(count_file):
            readable = True
            try:
                with open(count_file, "r", encoding="utf-8") as f:
                    counts = json.load(f)
            except (json.JSONDecodeError, IOError, ValueError, UnicodeDecodeError):
                readable = False
            if not isinstance(counts, dict):
                counts, readable = {}, False
            if not readable:
                # About to write the whole file back from an empty dict, which
                # would drop every day already counted. Keep the old bytes.
                preserve_corrupt(count_file)
                counts = {}

        counts[date_str] = counts.get(date_str, 0) + 1

        # Write to a sibling and replace, so a crash mid-write cannot leave a
        # truncated file where the counts used to be.
        tmp = "%s.tmp%d" % (count_file, os.getpid())
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(counts, f, indent=2)
            os.replace(tmp, count_file)
        except Exception:
            # The sibling is named after the pid, so a failed write leaves a
            # differently-named file behind every time and they accumulate.
            _remove_quietly(tmp)
            raise

        return counts[date_str]


def _truncate_to(path, size):
    """Cut a file back to a known-good length, best effort."""
    try:
        with open(path, "r+b") as f:
            f.truncate(size)
    except OSError as e:
        logger.warning("Could not roll back %s to %d bytes: %s", path, size, e)


def _remove_quietly(path):
    try:
        os.unlink(path)
    except OSError:
        pass


def preserve_corrupt(path):
    """Move an unreadable state file aside instead of overwriting it.

    These files are read with `except: {}` and then written back whole, so a
    corrupt one is silently replaced by whatever the current session knows —
    measured, a truncated `.session_counts.json` took three months of counts
    down to a single day. Keeping the bytes means the loss is recoverable, or
    at least visible.
    """
    if not os.path.exists(path):
        return None
    kept = "%s.corrupt" % path
    try:
        os.replace(path, kept)
        logger.warning("%s was unreadable; kept the old bytes at %s", path, kept)
        return kept
    except OSError as e:
        logger.warning("%s was unreadable and could not be preserved: %s", path, e)
        return None
