"""Diary file writer — appends entries to daily markdown files."""

import json
import os
from pathlib import Path

from claude_diary.formatter import format_daily_header
from claude_diary.lib.filelock import FileLock


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

        with open(diary_path, "a", encoding="utf-8") as f:
            f.write(entry_text)


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
            try:
                with open(count_file, "r", encoding="utf-8") as f:
                    counts = json.load(f)
            except (json.JSONDecodeError, IOError, ValueError):
                counts = {}

        counts[date_str] = counts.get(date_str, 0) + 1

        # Write to a sibling and replace, so a crash mid-write cannot leave a
        # truncated file where the counts used to be.
        tmp = "%s.tmp%d" % (count_file, os.getpid())
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(counts, f, indent=2)
        os.replace(tmp, count_file)

        return counts[date_str]
