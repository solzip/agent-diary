"""`claude-diary notion-push` — push tasks JSON to the Notion hierarchical DB.

Driven by the `/diary-notion` slash command:
  1. Claude writes `.diary-notion-<id>.json` in cwd
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
        print("[claude-diary notion-push] No tasks to push.")
        _cleanup(input_path)
        return

    cwd = os.getcwd()
    lang = config.get("lang", "ko")
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
            print("[claude-diary notion-push] --force: archived %d existing row(s)" % archived)
        except NotionAuthError as e:
            print("[claude-diary notion-push] Auth error: %s" % e, file=sys.stderr)
            print("  Check: claude-diary config or run `claude-diary notion init`", file=sys.stderr)
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

    # Pass 2: wire up Depends On relations now that all row_ids are known.
    relation_failures = _wire_depends_on(exporter, tasks, row_ids)
    for idx, title, reason in relation_failures:
        results["failed"].append((idx, title, "depends_on: %s" % reason))

    exporter.save_cache()

    _print_report(results, input_path)

    if not results["failed"]:
        _cleanup(input_path)

    sys.exit(1 if auth_failed else 0)


def _wire_depends_on(exporter, tasks, row_ids):
    """Pass 2: set Depends On relations using the row_ids gathered in pass 1.

    Returns a list of (idx, title, reason) for tasks whose relation update
    failed. Tasks without depends_on are silently skipped.
    """
    failures = []
    for idx, task in enumerate(tasks):
        deps = task.get("depends_on_indices") or []
        if not deps:
            continue
        my_row = row_ids.get(idx)
        if not my_row:
            continue  # task itself failed in pass 1
        target_rows = [row_ids[d] for d in deps if d in row_ids]
        if not target_rows:
            continue
        try:
            exporter.update_row_relation(my_row, target_rows)
        except Exception as e:
            failures.append((idx, task.get("title") or "(untitled)", str(e)))
    return failures


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
        print("[claude-diary notion-push] Input file not found: %s" % path, file=sys.stderr)
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print("[claude-diary notion-push] Failed to read JSON: %s" % e, file=sys.stderr)
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
        task, date_str, branch, git_info, session_id, task_index
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


def _build_properties(task, date_str, branch, git_info, session_id, task_index):
    """Build Notion DB row properties from task data.

    Note: `Depends On` relation is NOT set here — it's wired up in pass 2
    via update_row_relation() once all row IDs are known.
    """
    title = task.get("title") or "(untitled)"
    project = (task.get("project") or "unknown").strip() or "unknown"
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
        "Project": {"select": {"name": _safe_select(project)}},
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

    return props


def _safe_select(name):
    """Notion select names cannot contain commas. Replace with '-'."""
    return (name or "").replace(",", "-")[:100] or "unknown"


def _print_report(results, input_path):
    pushed = len(results["pushed"])
    skipped = len(results["skipped"])
    failed = len(results["failed"])
    print("[claude-diary notion-push] Pushed %d, skipped %d, failed %d" %
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
        print("Retry: claude-diary notion-push --input %s --force" % input_path)


def _cleanup(input_path):
    if not input_path:
        return
    try:
        os.remove(input_path)
    except OSError:
        pass


def _print_setup_hint():
    print("[claude-diary notion-push] Notion hierarchical exporter not configured.",
          file=sys.stderr)
    print("  Run: claude-diary notion init", file=sys.stderr)
    print("  Or set CLAUDE_DIARY_NOTION_TOKEN and CLAUDE_DIARY_NOTION_ROOT_PAGE_ID",
          file=sys.stderr)
