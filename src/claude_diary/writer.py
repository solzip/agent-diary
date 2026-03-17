"""Diary file writer — appends entries to daily markdown files."""

import json
import os
from pathlib import Path

from claude_diary.formatter import format_daily_header


def ensure_diary_dir(diary_dir):
    """Create diary directory and subdirectories."""
    Path(diary_dir).mkdir(parents=True, exist_ok=True)
    Path(diary_dir, "weekly").mkdir(parents=True, exist_ok=True)


def append_entry(diary_dir, date_str, entry_text, lang="ko"):
    """Append a formatted diary entry to the daily file."""
    ensure_diary_dir(diary_dir)
    diary_path = os.path.join(diary_dir, "%s.md" % date_str)

    if not os.path.exists(diary_path):
        with open(diary_path, "w", encoding="utf-8") as f:
            f.write(format_daily_header(date_str, lang))

    with open(diary_path, "a", encoding="utf-8") as f:
        f.write(entry_text)


def update_session_count(diary_dir, date_str):
    """Track daily session count in a separate JSON file."""
    count_file = os.path.join(diary_dir, ".session_counts.json")
    counts = {}
    if os.path.exists(count_file):
        try:
            with open(count_file, "r") as f:
                counts = json.load(f)
        except Exception:
            counts = {}

    counts[date_str] = counts.get(date_str, 0) + 1

    with open(count_file, "w") as f:
        json.dump(counts, f, indent=2)

    return counts[date_str]
