"""Statistics engine for diary data analysis."""

import os
import re
from collections import Counter

from claude_diary.lib.conventional import commit_type


def parse_daily_file(filepath):
    """Parse a daily diary .md file and extract statistics.
    Matches both Korean and English labels.
    """
    stats = {
        "sessions": 0,
        "projects": set(),
        "files_created": [],
        "files_modified": [],
        "tasks": [],
        "issues": [],
        "categories": [],
        "raw_entries": [],
        "commit_types": [],
        "commits": 0,
        "sessions_with_commits": 0,
    }

    if not os.path.exists(filepath):
        return stats

    try:
        # `errors="replace"`, because a diary file can end mid-character —
        # a hook killed partway through an append, a disk that filled — and
        # strict decoding turned that into an empty result for the whole day.
        # Measured: a file with four visible entries reported zero sessions,
        # and `reindex` skipped the day on the strength of that zero. The
        # replacement character costs one glyph; the alternative cost a day.
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except Exception:
        return stats

    stats["sessions"] = content.count("### ⏰")

    project_matches = re.findall(r'📁 `([^`]+)`', content)
    stats["projects"] = set(project_matches)

    # Per-project session counts
    project_counter = Counter(project_matches)
    stats["project_sessions"] = dict(project_counter)

    # Files created (KO/EN)
    created_matches = re.findall(
        r'(?:생성된 파일|Files Created).*?\n((?:\s+- `[^`]+`\n?)+)', content
    )
    for block in created_matches:
        stats["files_created"].extend(re.findall(r'`([^`]+)`', block))

    # Files modified (KO/EN)
    modified_matches = re.findall(
        r'(?:수정된 파일|Files Modified).*?\n((?:\s+- `[^`]+`\n?)+)', content
    )
    for block in modified_matches:
        stats["files_modified"].extend(re.findall(r'`([^`]+)`', block))

    # Work summary (KO/EN)
    summary_matches = re.findall(
        r'(?:작업 요약|Work Summary).*?\n((?:\s+- .+\n?)+)', content
    )
    for block in summary_matches:
        stats["tasks"].extend(re.findall(r'- (.+)', block))

    # Issues (KO/EN)
    issue_matches = re.findall(
        r'(?:발생한 이슈|Issues Encountered).*?\n((?:\s+- .+\n?)+)', content
    )
    for block in issue_matches:
        stats["issues"].extend(re.findall(r'- (.+)', block))

    # Categories (KO/EN)
    cat_matches = re.findall(r'(?:카테고리|Categories).*?`([^`]+)`', content)
    stats["categories"].extend(cat_matches)

    # Task requests (KO/EN)
    request_matches = re.findall(
        r'(?:작업 요청|Task Requests).*?\n((?:\s+\d+\. .+\n?)+)', content
    )
    for block in request_matches:
        stats["raw_entries"].extend(re.findall(r'\d+\. (.+)', block))

    _collect_commit_types(content, stats)

    return stats


# `  - 커밋: `hash` subject` / `  - Commit: `hash` subject`
_COMMIT_LINE = re.compile(r"(?:커밋|Commit):\s*`[^`]+`\s*(.+)")


def _collect_commit_types(content, stats):
    """Count commits by their Conventional Commit type.

    A separate axis from `categories`, and a better-founded one: a category is
    guessed from words that appeared in the conversation, while a commit type
    is what the author declared they were doing. Measured over 6,906 entries
    the two disagree on a third of the entries that have both, and the
    disagreement is lopsided — the keyword rules count `test` about four times
    as often as `test:` commits exist, because saying "tests pass" during a
    bug fix is enough to classify the session as testing.

    They are not merged for the same reason they are worth comparing. Fewer
    than half the entries have a commit at all, so replacing one with the
    other would trade a wrong number for a missing one.
    """
    sessions = content.split("### ⏰")[1:]
    for session in sessions:
        subjects = _COMMIT_LINE.findall(session)
        if subjects:
            stats["sessions_with_commits"] += 1
        for subject in subjects:
            stats["commits"] += 1
            kind = commit_type(subject)
            if kind:
                stats["commit_types"].append(kind)
