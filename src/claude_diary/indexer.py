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
    """Rebuild entire index from all .md files. (Placeholder for CLI command)"""
    # This will be implemented in Sprint 2 (CLI)
    pass


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
