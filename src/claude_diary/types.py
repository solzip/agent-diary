"""Core data types for claude-diary."""

# Using plain dicts with documented keys for Python 3.7 compatibility.
# TypedDict is available from 3.8+, so we document the structure here.

# EntryData: dict
# {
#   "session_id": str,
#   "date": str,              # "2026-03-17"
#   "time": str,              # "15:30:00"
#   "project": str,           # "ai-chatbot"
#   "cwd": str,               # "/path/to/project"
#
#   "user_prompts": list[str],
#   "files_created": list[str],
#   "files_modified": list[str],
#   "commands_run": list[str],
#   "summary_hints": list[str],
#   "errors_encountered": list[str],
#
#   "categories": list[str],           # ["feature", "config"]
#   "git_info": dict | None,           # {"branch", "commits", "diff_stat"}
#   "code_stats": dict | None,         # {"added", "deleted", "files"}
#   "secrets_masked": int,
# }

# GitInfo: dict
# {
#   "branch": str,
#   "commits": list[{"hash": str, "message": str}],
#   "diff_stat": {"added": int, "deleted": int, "files": int},
# }

# Config: dict
# {
#   "lang": str,
#   "timezone_offset": int,
#   "diary_dir": str,
#   "enrichment": {"git_info": bool, "auto_category": bool, "code_stats": bool, "session_time": bool},
#   "exporters": { "notion": {...}, "slack": {...}, ... },
#   "custom_categories": dict,
# }


def make_empty_entry_data():
    """Create an empty EntryData dict with all expected keys."""
    return {
        "session_id": "unknown",
        "date": "",
        "time": "",
        "project": "unknown",
        "cwd": "",
        "user_prompts": [],
        "files_created": [],
        "files_modified": [],
        "commands_run": [],
        "summary_hints": [],
        "errors_encountered": [],
        "categories": [],
        "git_info": None,
        "code_stats": None,
        "secrets_masked": 0,
    }
