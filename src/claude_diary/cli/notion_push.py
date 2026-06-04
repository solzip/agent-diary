"""`claude-diary diary-notion push` — push tasks JSON to the Notion hierarchical DB.

Driven by the `/diary-notion` slash command or `$diary-notion` Codex skill:
  1. The agent writes `.diary-notion-<id>.json` in cwd
  2. This CLI reads it, resolves git info, and pushes each task as a DB row
  3. On success the temp file is deleted; on partial failure it is preserved
     so the user can re-push with `--force`

Idempotency: each row carries hidden Session ID + Task Index columns. Re-runs
skip already-pushed rows. `--force` first archives prior rows for the session,
then re-pushes everything.
"""

import json
import os
import sys
from datetime import datetime, timezone, timedelta

from claude_diary.config import load_config
from claude_diary.log import get_logger, configure_from_config
from claude_diary.formatter import build_notion_blocks
from claude_diary.lib import notion_cache
from claude_diary.lib.git_info import (
    get_branch_for_commit,
    get_head_branch,
    get_commit_info,
    get_diff_stat_for_commits,
)
from claude_diary.exporters.notion_hierarchical import (
    NotionHierarchicalExporter,
    NotionAuthError,
    NotionBadRequest,
    NotionNotFound,
    detect_subitem_relation,
)

logger = get_logger("claude_diary.cli.notion_push")


def cmd_notion_push(args):
    """Read tasks JSON and push each task as a row to the Notion DB."""
    config = load_config()
    configure_from_config(config)

    token, root_page_id = _resolve_credentials(config)
    if not token or not root_page_id:
        _print_setup_hint()
        sys.exit(1)

    input_path = args.input
    data = _read_json(input_path)
    if data is None:
        sys.exit(1)

    session_id = data.get("session_id") or _fallback_session_id()
    tasks = data.get("tasks") or []
    if not tasks:
        print("[claude-diary diary-notion push] No tasks to push.")
        _cleanup(input_path)
        return

    cwd = os.getcwd()
    # Hierarchical Notion diary pages are developer work records for this
    # workflow: titles and narrative body sections are Korean by policy. Raw
    # artifacts such as file paths, commands, branches, commits, and enum
    # values remain unchanged.
    lang = "ko"
    tz_offset = config.get("timezone_offset", 9)
    local_tz = timezone(timedelta(hours=tz_offset))
    today = datetime.now(local_tz)
    year = today.year
    date_str = today.strftime("%Y-%m-%d")

    exporter = NotionHierarchicalExporter({
        "api_token": token,
        "root_page_id": root_page_id,
    })
    exporter.load_cache()

    if args.force:
        try:
            db_id = exporter.ensure_database(year)
            archived = exporter.archive_rows_for_session(db_id, session_id)
            print("[claude-diary diary-notion push] --force: archived %d existing row(s)" % archived)
        except NotionAuthError as e:
            print("[claude-diary diary-notion push] Auth error: %s" % e, file=sys.stderr)
            print("  Check: claude-diary config or run `claude-diary diary-notion init`", file=sys.stderr)
            sys.exit(1)

    results = {"pushed": [], "skipped": [], "failed": []}
    row_ids = {}  # task_index → Notion row_id (used by 2nd pass for relations)
    auth_failed = False

    # Pass 1: create rows (or detect existing). Depends On left blank for now.
    for idx, task in enumerate(tasks):
        title = task.get("title") or "(untitled)"
        if auth_failed:
            results["failed"].append((idx, title, "skipped after earlier auth error"))
            continue
        try:
            outcome, row_id = _push_task(
                exporter, year, date_str, session_id, idx, task, cwd, lang
            )
            if row_id:
                row_ids[idx] = row_id
            if outcome == "pushed":
                results["pushed"].append((idx, title))
            else:
                results["skipped"].append((idx, title, "already exists"))
        except NotionAuthError as e:
            auth_failed = True
            results["failed"].append((idx, title, "auth: %s" % e))
        except NotionBadRequest as e:
            results["failed"].append((idx, title, "bad request: %s" % e))
        except Exception as e:
            results["failed"].append((idx, title, str(e)))

    # Pass 2: wire up relation fields now that all row_ids are known.
    relation_failures = _wire_depends_on(exporter, tasks, row_ids)
    relation_failures += _wire_parent_tasks(exporter, year, tasks, row_ids)
    for idx, title, reason in relation_failures:
        results["failed"].append((idx, title, "relation: %s" % reason))

    exporter.save_cache()

    _print_report(results, input_path)

    if not results["failed"]:
        _cleanup(input_path)

    sys.exit(1 if auth_failed else 0)


def _wire_depends_on(exporter, tasks, row_ids):
    """Pass 2: set main-task Depends On relations from gathered row_ids.

    Returns a list of (idx, title, reason) for tasks whose relation update
    failed. Tasks without depends_on are silently skipped.

    Containment is represented by `Parent Task`/Notion sub-items. `Depends On`
    is deliberately limited to top-level rows so subtask hierarchy does not
    get mixed with prerequisite order.
    """
    failures = []
    for idx, task in enumerate(tasks):
        deps = task.get("depends_on_indices") or []
        if not deps:
            continue
        if not _is_top_level_task(task):
            continue
        my_row = row_ids.get(idx)
        if not my_row:
            continue  # task itself failed in pass 1
        target_rows = [
            row_ids[d]
            for d in deps
            if d != idx
            and d in row_ids
            and 0 <= d < len(tasks)
            and _is_top_level_task(tasks[d])
        ]
        if not target_rows:
            continue
        try:
            exporter.update_row_relation(my_row, target_rows)
        except Exception as e:
            failures.append((idx, task.get("title") or "(untitled)", "depends_on: %s" % e))
    return failures


def _wire_parent_tasks(exporter, year, tasks, row_ids):
    """Pass 2: wire task containment into Notion's NATIVE sub-item relation.

    `parent_index` is a single zero-based task index in the same push, separate
    from `depends_on_indices` (containment vs execution order).

    Only Notion's native sub-item relation drives the expand/collapse nesting,
    and it can only be created via the Notion UI. We detect it and write each
    child's parent link into its parent side (one write per child; Notion syncs
    the child-listing side). If the database has no native sub-item relation yet,
    containment is skipped with a one-time hint — rows are still recorded.
    """
    pairs = []  # (child_idx, parent_idx), self-reference guarded
    for idx, task in enumerate(tasks):
        parent_idx = _get_parent_index(task)
        if parent_idx is None or parent_idx == idx:
            continue
        if idx in row_ids and parent_idx in row_ids:
            pairs.append((idx, parent_idx))
    if not pairs:
        return []

    try:
        db_id = exporter.ensure_database(year)
        native = detect_subitem_relation(exporter.get_database_property_map(db_id))
    except Exception as e:
        return [
            (idx, tasks[idx].get("title") or "(untitled)", "subitem detect: %s" % e)
            for idx, _ in pairs
        ]

    if not native:
        _print_enable_subitems_hint(len(pairs))
        return []

    parent_prop = native["parent_name"]
    failures = []
    for child_idx, parent_idx in pairs:
        try:
            exporter.update_row_native_parent(
                row_ids[child_idx], row_ids[parent_idx], parent_prop
            )
        except Exception as e:
            failures.append((
                child_idx,
                tasks[child_idx].get("title") or "(untitled)",
                "sub-item: %s" % e,
            ))
    return failures


def _print_enable_subitems_hint(count):
    """Tell the user how to turn on native sub-items (a one-time UI action)."""
    print(
        "[claude-diary diary-notion push] %d task(s) have a parent, but this "
        "database has no native Sub-items relation yet — nesting skipped." % count
    )
    print("  Enable it once in Notion: open the database -> ⋯ menu -> Sub-items,")
    print("  then re-run push or `working-diary diary-notion ensure` to nest them.")


def _get_parent_index(task):
    """Return the optional parent task index, accepting the old/new field name."""
    if "parent_index" in task:
        value = task.get("parent_index")
    else:
        value = task.get("parent_task_index")
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _is_top_level_task(task):
    """Return True when a task is a main row, not a sub-item row."""
    return _get_parent_index(task) is None


def _resolve_credentials(config):
    """Resolve token and root_page_id from env vars first, then config."""
    notion_cfg = (config.get("exporters") or {}).get("notion_hierarchical") or {}
    token = (
        os.environ.get("CLAUDE_DIARY_NOTION_TOKEN")
        or notion_cfg.get("api_token")
    )
    root_page_id = (
        os.environ.get("CLAUDE_DIARY_NOTION_ROOT_PAGE_ID")
        or notion_cfg.get("root_page_id")
    )
    return token, root_page_id


def _read_json(path):
    if not path or not os.path.exists(path):
        print("[claude-diary diary-notion push] Input file not found: %s" % path, file=sys.stderr)
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print("[claude-diary diary-notion push] Failed to read JSON: %s" % e, file=sys.stderr)
        return None


def _fallback_session_id():
    import time
    return "manual-%d" % int(time.time())


def _push_task(exporter, year, date_str, session_id, task_index, task, cwd, lang):
    """Push one task to Notion. Returns (outcome, row_id).

    outcome ∈ {"pushed", "skipped"}.  row_id is the Notion page ID for
    this task — either the newly created one or the existing match.
    """
    db_id = exporter.ensure_database(year)

    existing = exporter.find_existing_row(db_id, session_id, task_index)
    if existing:
        return "skipped", existing

    git_info = _gather_git_info(cwd, task.get("commit_hashes") or [])
    branch = git_info.get("branch") or ""

    properties = _build_properties(
        task, date_str, branch, git_info, session_id, task_index, cwd
    )
    body_blocks = build_notion_blocks(task, git_info, lang)

    row_id = exporter.create_row(db_id, properties, body_blocks)
    notion_cache.set_row(exporter._cache, session_id, task_index, row_id)
    return "pushed", row_id


def _gather_git_info(cwd, commit_hashes):
    """Resolve branch + commits + diff_stat for a task."""
    info = {"branch": "", "commits": [], "diff_stat": {"added": 0, "deleted": 0, "files": 0}}
    if commit_hashes:
        info["branch"] = get_branch_for_commit(cwd, commit_hashes[0])
        for h in commit_hashes:
            c = get_commit_info(cwd, h)
            if c:
                info["commits"].append(c)
        info["diff_stat"] = get_diff_stat_for_commits(cwd, commit_hashes)
    else:
        info["branch"] = get_head_branch(cwd)
    return info


VALID_STATUSES = {"Discussion", "Design", "Implementation", "Testing", "Deployed"}
VALID_PRIORITIES = {"P0", "P1", "P2", "P3"}
VALID_REVIEW_STATUSES = {"Needs Review", "Reviewed", "Deferred"}

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


def _build_properties(task, date_str, branch, git_info, session_id, task_index, cwd=None):
    """Build Notion DB row properties from task data.

    Note: relation properties are NOT set here — `Depends On` and
    `Parent Task` are wired up in pass 2 once all row IDs are known.
    """
    title = task.get("title") or "(untitled)"
    project = _resolve_project_name(task.get("project"), cwd)
    categories = [c for c in (task.get("categories") or []) if c]
    stat = git_info.get("diff_stat") or {}
    commits = git_info.get("commits") or []
    files_count = (
        len(task.get("files_modified") or []) +
        len(task.get("files_created") or [])
    )
    lines = (stat.get("added", 0) or 0) + (stat.get("deleted", 0) or 0)

    props = {
        "Name": {"title": [{"text": {"content": title[:2000]}}]},
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
        "Session ID": {"rich_text": [{"text": {"content": session_id[:2000]}}]},
        "Task Index": {"number": task_index},
    }
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

    next_action = _clean_rich_text(task.get("next_action"))
    if next_action:
        props["Next Action"] = {"rich_text": [{"text": {"content": next_action}}]}

    if isinstance(task.get("blocked"), bool):
        props["Blocked"] = {"checkbox": task.get("blocked")}

    block_reason = _clean_rich_text(task.get("block_reason"))
    if block_reason:
        props["Block Reason"] = {"rich_text": [{"text": {"content": block_reason}}]}

    if isinstance(task.get("carryover"), bool):
        props["Carryover"] = {"checkbox": task.get("carryover")}

    review_status = _normalize_review_status(task.get("review_status"))
    if review_status:
        props["Review Status"] = {"select": {"name": review_status}}

    last_reviewed = _clean_date(task.get("last_reviewed"))
    if last_reviewed:
        props["Last Reviewed"] = {"date": {"start": last_reviewed}}

    return props


def _resolve_project_name(value, cwd=None):
    """Use the task project unless it is missing/placeholder, then fall back to cwd."""
    raw = str(value or "").strip()
    if raw and raw.lower() not in {"unknown", "<cwd folder name>", "cwd folder name"}:
        return raw
    return _project_name_from_cwd(cwd)


def _project_name_from_cwd(cwd):
    """Extract a stable project name from the command working directory."""
    if not cwd:
        return "unknown"
    normalized = str(cwd).replace("\\", "/").rstrip("/")
    name = normalized.rsplit("/", 1)[-1].strip()
    if not name or name in {".", ".."}:
        return "unknown"
    return name


def _normalize_work_period(value, fallback_date):
    """Return a Notion date object for the actual work period."""
    if isinstance(value, dict):
        start = _clean_date(value.get("start") or value.get("date"))
        end = _clean_date(value.get("end"))
        if start:
            result = {"start": start}
            if end and end != start:
                result["end"] = end
            return result
    elif isinstance(value, str):
        raw = value.strip()
        if raw:
            if ".." in raw:
                start, end = raw.split("..", 1)
                result = {"start": _clean_date(start) or fallback_date}
                end = _clean_date(end)
                if end and end != result["start"]:
                    result["end"] = end
                return result
            clean = _clean_date(raw)
            if clean:
                return {"start": clean}
    return {"start": fallback_date}


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


def _normalize_review_status(value):
    raw = str(value or "").strip()
    normalized = {
        "needs_review": "Needs Review",
        "needs review": "Needs Review",
        "reviewed": "Reviewed",
        "deferred": "Deferred",
    }.get(raw.lower(), raw)
    return normalized if normalized in VALID_REVIEW_STATUSES else ""


def _clean_rich_text(value):
    raw = str(value or "").strip()
    return raw[:2000] if raw else ""


def _print_report(results, input_path):
    pushed = len(results["pushed"])
    skipped = len(results["skipped"])
    failed = len(results["failed"])
    print("[claude-diary diary-notion push] Pushed %d, skipped %d, failed %d" %
          (pushed, skipped, failed))
    for _, title in results["pushed"]:
        print("  + %s" % title)
    for _, title, reason in results["skipped"]:
        print("  - %s (%s)" % (title, reason))
    for _, title, reason in results["failed"]:
        print("  ! %s -- %s" % (title, reason))
    if failed > 0:
        print()
        print("Failed tasks preserved in: %s" % input_path)
        print("Retry: claude-diary diary-notion push --input %s --force" % input_path)


def _cleanup(input_path):
    if not input_path:
        return
    try:
        os.remove(input_path)
    except OSError:
        pass


def _print_setup_hint():
    print("[claude-diary diary-notion push] Notion hierarchical exporter not configured.",
          file=sys.stderr)
    print("  Run: claude-diary diary-notion init", file=sys.stderr)
    print("  Or set CLAUDE_DIARY_NOTION_TOKEN and CLAUDE_DIARY_NOTION_ROOT_PAGE_ID",
          file=sys.stderr)
