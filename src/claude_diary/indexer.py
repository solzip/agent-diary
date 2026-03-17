"""Search index manager — incremental index for fast CLI search."""

import json
import os


def update_index(diary_dir, entry_data):
    """Add entry metadata to the search index (incremental).

    Args:
        diary_dir: Path to diary directory
        entry_data: Processed entry data dict
    """
    index_path = os.path.join(diary_dir, ".diary_index.json")
    index = _load_index(index_path)

    # Extract keywords from prompts (simple word tokenization)
    keywords = set()
    for prompt in entry_data.get("user_prompts", []):
        words = prompt.lower().split()
        for w in words:
            w = w.strip(".,!?:;\"'()[]{}").strip()
            if len(w) > 2:
                keywords.add(w)

    all_files = entry_data.get("files_created", []) + entry_data.get("files_modified", [])

    git_commits = []
    git_info = entry_data.get("git_info")
    if git_info:
        git_commits = [c["hash"] for c in git_info.get("commits", [])]

    code_stats = entry_data.get("code_stats") or {}

    index_entry = {
        "date": entry_data.get("date", ""),
        "time": entry_data.get("time", ""),
        "project": entry_data.get("project", ""),
        "categories": entry_data.get("categories", []),
        "files": all_files[:20],
        "keywords": sorted(keywords)[:30],
        "git_commits": git_commits[:10],
        "lines_added": code_stats.get("added", 0),
        "lines_deleted": code_stats.get("deleted", 0),
        "session_id": entry_data.get("session_id", ""),
    }

    index["entries"].append(index_entry)
    index["last_indexed"] = "%sT%s" % (entry_data.get("date", ""), entry_data.get("time", ""))

    _save_index(index_path, index)


def load_index(diary_dir):
    """Load the search index."""
    index_path = os.path.join(diary_dir, ".diary_index.json")
    return _load_index(index_path)


def reindex_all(diary_dir):
    """Rebuild entire index from all .md files."""
    import re
    from pathlib import Path
    from claude_diary.lib.stats import parse_daily_file

    index = {"entries": [], "last_indexed": ""}
    count = 0

    for f in sorted(Path(diary_dir).glob("*.md")):
        date_str = f.stem
        stats = parse_daily_file(str(f))
        if stats["sessions"] == 0:
            continue

        try:
            content = f.read_text(encoding="utf-8")
        except Exception:
            continue

        sessions = content.split("### ⏰")
        for session in sessions[1:]:
            time_match = re.match(r'\s*(\d{2}:\d{2}:\d{2})', session)
            time_str = time_match.group(1) if time_match else ""

            proj_match = re.search(r'📁 `([^`]+)`', session)
            project = proj_match.group(1) if proj_match else ""

            cats = re.findall(r'(?:카테고리|Categories).*?`([^`]+)`', session)
            files = re.findall(r'  - `([^`]+)`', session)

            keywords = set()
            prompt_section = re.search(
                r'(?:작업 요청|Task Requests).*?\n((?:\s+\d+\. .+\n?)+)', session
            )
            if prompt_section:
                for word in prompt_section.group(1).lower().split():
                    w = word.strip(".,!?:;\"'()[]{}").strip()
                    if len(w) > 2:
                        keywords.add(w)

            index["entries"].append({
                "date": date_str,
                "time": time_str,
                "project": project,
                "categories": cats,
                "files": files[:20],
                "keywords": sorted(keywords)[:30],
                "git_commits": [],
                "lines_added": 0,
                "lines_deleted": 0,
                "session_id": "",
            })
            count += 1

    from datetime import datetime
    index["last_indexed"] = datetime.now().isoformat()

    index_path = os.path.join(diary_dir, ".diary_index.json")
    _save_index(index_path, index)

    return count


def _load_index(index_path):
    """Load index from file or return empty."""
    if os.path.exists(index_path):
        try:
            with open(index_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"entries": [], "last_indexed": ""}


def _save_index(index_path, index):
    """Save index to file."""
    try:
        with open(index_path, "w", encoding="utf-8") as f:
            json.dump(index, f, indent=2, ensure_ascii=False)
    except Exception:
        pass  # Index failure should never block diary writing
