"""Turning a task dict into Notion DB row properties.

Every value that reaches Notion as a `select` passes through a normalizer
here, because Notion creates a new option for any unrecognised string and a
typo would silently widen the option list forever.

Relation properties are deliberately absent: `Depends On` and the sub-item
parent link need all row IDs, so they are wired in pass 2 (see `relations`).
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from claude_diary.lib.notion_api import RICH_TEXT_LIMIT
from claude_diary.lib.statuses import VALID as VALID_STATUSES
from claude_diary.types import GitInfo

from datetime import datetime

from claude_diary.cli.notion_push.tasks import _task_files_count, _task_next_action

VALID_PRIORITIES = {"P0", "P1", "P2", "P3"}
# Every pushed row starts unreviewed; `diary-notion review --apply` is the only
# thing that advances it.
DEFAULT_REVIEW_STATUS = "Needs Review"

VALID_PURPOSES = {
    "Feature",
    "Bugfix",
    "Refactor",
    "Docs",
    "Test",
    "Infra",
    "Planning",
    "Research",
    "Review",
    "Release",
    "Support",
    "Maintenance",
    "General",
}

PURPOSE_ALIASES = {
    "bug": "Bugfix",
    "bugfix": "Bugfix",
    "doc": "Docs",
    "docs": "Docs",
    "documentation": "Docs",
    "feature": "Feature",
    "infra": "Infra",
    "infrastructure": "Infra",
    "maintenance": "Maintenance",
    "planning": "Planning",
    "refactor": "Refactor",
    "release": "Release",
    "research": "Research",
    "review": "Review",
    "support": "Support",
    "test": "Test",
    "testing": "Test",
}


def _build_properties(task: Dict[str, Any], date_str: str, branch: str,
                      git_info: GitInfo, session_id: str, task_index: int,
                      cwd: Optional[str] = None) -> Dict[str, Any]:
    """Build Notion DB row properties from task data.

    Note: relation properties are NOT set here — `Depends On` and
    `Parent Task` are wired up in pass 2 once all row IDs are known.
    """
    title = task.get("title") or "(untitled)"
    project = _resolve_project_name(task.get("project"), cwd)
    categories = [c for c in (task.get("categories") or []) if c]
    stat = git_info.get("diff_stat") or {}
    commits = git_info.get("commits") or []
    files_count = _task_files_count(task)
    lines = (stat.get("added", 0) or 0) + (stat.get("deleted", 0) or 0)

    props = {
        "Name": {"title": [{"text": {"content": title[:RICH_TEXT_LIMIT]}}]},
        "Date": {"date": {"start": date_str}},
        "Work Period": {"date": _normalize_work_period(task.get("work_period"), date_str)},
        "Project": {"select": {"name": _safe_select(project)}},
        "Purpose": {"select": {"name": _normalize_purpose(task.get("purpose"))}},
        "Categories": {
            "multi_select": [{"name": _safe_select(c)} for c in categories[:10]]
        },
        "Files": {"number": files_count},
        "Commits": {"number": len(commits)},
        "Lines": {"number": lines},
        "Session ID": {"rich_text": [{"text": {"content": session_id[:RICH_TEXT_LIMIT]}}]},
        "Task Index": {"number": task_index},
    }
    report_schema = _clean_schema_version(task.get("_report_schema_version"))
    if report_schema:
        props["Schema Version"] = {"select": {"name": report_schema}}
    if branch:
        props["Branch"] = {"select": {"name": _safe_select(branch)}}

    status = (task.get("status") or "").strip()
    if status in VALID_STATUSES:
        props["Status"] = {"select": {"name": status}}

    task_group = (task.get("task_group") or "").strip()
    if task_group:
        props["Task Group"] = {"select": {"name": _safe_select(task_group)}}

    priority = _normalize_priority(task.get("priority"))
    if priority:
        props["Priority"] = {"select": {"name": priority}}

    next_action = _clean_rich_text(_task_next_action(task))
    if next_action:
        props["Next Action"] = {"rich_text": [{"text": {"content": next_action}}]}

    if isinstance(task.get("blocked"), bool):
        props["Blocked"] = {"checkbox": task.get("blocked")}

    block_reason = _clean_rich_text(task.get("block_reason"))
    if block_reason:
        props["Block Reason"] = {"rich_text": [{"text": {"content": block_reason}}]}

    if isinstance(task.get("carryover"), bool):
        props["Carryover"] = {"checkbox": task.get("carryover")}

    # Review state is owned by the human, not by the session that produced the
    # work: every new row files as unreviewed and only
    # `diary-notion review --apply` can advance it. `Last Reviewed` is left
    # unset for the same reason — at push time nobody has reviewed anything.
    props["Review Status"] = {"select": {"name": DEFAULT_REVIEW_STATUS}}

    return props


def _resolve_project_name(value, cwd=None):
    """Use the task project unless it is missing/placeholder, then fall back to cwd."""
    raw = str(value or "").strip()
    if raw and raw.lower() not in {"unknown", "<cwd folder name>", "cwd folder name"}:
        return raw
    return _project_name_from_cwd(cwd)


def _project_name_from_cwd(cwd):
    """Extract a stable project name from the command working directory.

    The repository root, not the folder the command happened to run in — the
    same rule the diary uses, so a session filed under `project-a`
    locally does not arrive in Notion as `dev`.
    """
    if not cwd:
        return "unknown"
    from claude_diary.lib.git_info import get_repo_root
    normalized = str(get_repo_root(cwd) or cwd).replace("\\", "/").rstrip("/")
    name = normalized.rsplit("/", 1)[-1].strip()
    if not name or name in {".", ".."}:
        return "unknown"
    return name


def _normalize_work_period(value, fallback_date):
    """Return a Notion date object for the actual work period.

    The row is recorded on the day `push` runs, so `fallback_date` (the
    execution date) anchors the period: a single day always collapses to it and
    a range never ends in the future. Agents author `work_period` from session
    context, so without this anchor a stale session date — or the date copied
    out of the contract's example JSON — lands in Notion and drifts away from
    the `Date` column.
    """
    start = ""
    end = ""
    if isinstance(value, dict):
        start = _clean_date(value.get("start") or value.get("date"))
        end = _clean_date(value.get("end"))
    elif isinstance(value, str):
        raw = value.strip()
        if ".." in raw:
            head, tail = raw.split("..", 1)
            start = _clean_date(head)
            end = _clean_date(tail)
        else:
            start = _clean_date(raw)

    # ISO dates compare correctly as strings; "" (invalid/absent) never wins.
    if start > fallback_date:
        start = ""
    if end > fallback_date:
        end = fallback_date

    if not start or not end or end <= start:
        return {"start": fallback_date}
    return {"start": start, "end": end}


def _clean_date(value):
    """Accept YYYY-MM-DD strings and ignore unsupported date values."""
    if not value:
        return ""
    raw = str(value).strip()
    if len(raw) >= 10:
        raw = raw[:10]
    try:
        datetime.strptime(raw, "%Y-%m-%d")
    except ValueError:
        return ""
    return raw


def _safe_select(name):
    """Notion select names cannot contain commas. Replace with '-'."""
    return (name or "").replace(",", "-")[:100] or "unknown"


def _normalize_purpose(value):
    """Normalize task purpose to a stable Notion select value."""
    if not value:
        return "General"
    raw = str(value).strip()
    if raw in VALID_PURPOSES:
        return raw
    return PURPOSE_ALIASES.get(raw.lower(), "General")


def _normalize_priority(value):
    raw = str(value or "").strip().upper()
    aliases = {
        "CRITICAL": "P0",
        "HIGH": "P1",
        "MEDIUM": "P2",
        "LOW": "P3",
    }
    raw = aliases.get(raw, raw)
    return raw if raw in VALID_PRIORITIES else ""


def _clean_rich_text(value):
    raw = str(value or "").strip()
    return raw[:RICH_TEXT_LIMIT] if raw else ""


def _clean_schema_version(value):
    raw = str(value or "").strip()
    if not raw:
        return ""
    if raw.lower().startswith("v"):
        return raw[:100]
    return ("v%s" % raw)[:100]
