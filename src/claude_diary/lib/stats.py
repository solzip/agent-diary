"""Statistics engine for diary data analysis."""

import os
import re
from collections import Counter
from datetime import datetime, timezone, timedelta


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
    }

    if not os.path.exists(filepath):
        return stats

    try:
        with open(filepath, "r", encoding="utf-8") as f:
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

    return stats
