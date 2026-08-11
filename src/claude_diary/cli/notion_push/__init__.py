"""`agent-diary diary-notion push` — push tasks JSON to the Notion hierarchical DB.

Driven by the `/diary-notion` slash command or `$diary-notion` Codex skill:
  1. The agent writes `.diary-notion-<id>.json` in cwd
  2. This CLI reads it, resolves git info, and pushes each task as a DB row
  3. On success the temp file is deleted; on partial failure it is preserved
     so the user can re-push with `--force`

Idempotency: each row carries hidden Session ID + Task Index columns. Re-runs
skip already-pushed rows. `--force` first archives prior rows for the session,
then re-pushes everything.

The command and the two functions that reach outside it — `_gather_git_info`
and `_push_task` — live here rather than in a submodule so that patching
`claude_diary.cli.notion_push.<name>` still reaches the name the running code
resolves. Everything with no such coupling is split out:

    tasks       reading fields off a task dict
    properties  task dict -> Notion row properties
    validate    rejecting bad input before anything is written
    relations   pass 2, linking rows once every row ID is known
    ordinals    numbering sessions that continue a task group
    preview     Notion block payload -> readable text
    artifacts   the local record of what a run submitted
"""

import json
import os
import sys
from copy import deepcopy
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
)

from claude_diary.cli.notion_push.artifacts import (
    _artifact_ref,
    _finalize_artifact_manifest,
    _git_diff,
    _prepare_run_artifacts,
    _relpath,
    _run_id,
    _set_run_artifacts,
    _sha256_file,
    _write_artifact_preview,
    _write_text_file,
)
from claude_diary.cli.notion_push.ordinals import (
    _resolve_task_group_ordinals,
    _stamp_task_group_ordinals,
)
from claude_diary.cli.notion_push.preview import (
    _block_text,
    _blocks_to_preview_lines,
    _rich_text_plain,
    _table_preview_lines,
)
from claude_diary.cli.notion_push.properties import (
    DEFAULT_REVIEW_STATUS,
    PURPOSE_ALIASES,
    VALID_PRIORITIES,
    VALID_PURPOSES,
    VALID_STATUSES,
    _build_properties,
    _clean_date,
    _clean_rich_text,
    _clean_schema_version,
    _normalize_priority,
    _normalize_purpose,
    _normalize_work_period,
    _project_name_from_cwd,
    _resolve_project_name,
    _safe_select,
)
from claude_diary.cli.notion_push.relations import (
    _print_enable_subitems_hint,
    _wire_depends_on,
    _wire_parent_tasks,
)
from claude_diary.cli.notion_push.tasks import (
    _get_parent_index,
    _is_top_level_task,
    _task_appendix,
    _task_commit_hashes,
    _task_files_count,
    _task_next_action,
    _task_texts,
)
from claude_diary.cli.notion_push.validate import (
    _print_validation_errors,
    _report_schema_version,
    _stamp_report_schema_version,
    _validate_push_data,
)

logger = get_logger("claude_diary.cli.notion_push")


def cmd_notion_push(args):
    """Read tasks JSON and push each task as a row to the Notion DB."""
    config = load_config()
    configure_from_config(config)
    dry_run = getattr(args, "dry_run", False) is True

    input_path = args.input
    data = _read_json(input_path)
    if data is None:
        sys.exit(1)

    session_id = data.get("session_id") or _fallback_session_id()
    tasks = data.get("tasks") or []
    validation_errors = _validate_push_data(data)
    if validation_errors:
        _print_validation_errors(validation_errors, input_path)
        sys.exit(1)
    if not tasks:
        print("[agent-diary diary-notion push] No tasks to push.")
        if not dry_run:
            _cleanup(input_path)
        return
    tasks = deepcopy(tasks)
    report_schema_version = _report_schema_version(data, tasks)
    _stamp_report_schema_version(tasks, report_schema_version)

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

    artifact_dir = _arg_str(args, "artifact_dir")
    if getattr(args, "no_artifacts", False) is True:
        artifact_dir = ""
    preview_file = _arg_str(args, "preview_file")
    if dry_run:
        run_artifacts = _prepare_run_artifacts(
            input_path, data, tasks, session_id, date_str, cwd, artifact_dir
        )
        if run_artifacts:
            _complete_run_artifacts_before_render(
                run_artifacts, tasks, session_id, date_str, cwd, lang
            )
        preview = _build_dry_run_preview(tasks, session_id, date_str, cwd, lang)
        if preview_file:
            _write_text_file(preview_file, preview)
            print("[agent-diary diary-notion push --dry-run] Preview file: %s" % preview_file)
        print(preview)
        return

    token, root_page_id = _resolve_credentials(config)
    if not token or not root_page_id:
        _print_setup_hint()
        sys.exit(1)

    run_artifacts = _prepare_run_artifacts(
        input_path, data, tasks, session_id, date_str, cwd, artifact_dir
    )
    if run_artifacts:
        _complete_run_artifacts_before_render(
            run_artifacts, tasks, session_id, date_str, cwd, lang
        )

    exporter = NotionHierarchicalExporter({
        "api_token": token,
        "root_page_id": root_page_id,
    })
    exporter.load_cache()

    if args.force:
        try:
            db_id = exporter.ensure_database(year)
            archived = exporter.archive_rows_for_session(db_id, session_id)
            print("[agent-diary diary-notion push] --force: archived %d existing row(s)" % archived)
        except NotionAuthError as e:
            print("[agent-diary diary-notion push] Auth error: %s" % e, file=sys.stderr)
            print("  Check: agent-diary config or run `agent-diary diary-notion init`", file=sys.stderr)
            sys.exit(1)

    # Resolve after --force archiving so re-pushed rows are not counted twice.
    _stamp_task_group_ordinals(
        tasks, _resolve_task_group_ordinals(exporter, year, tasks, session_id)
    )

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
    if run_artifacts:
        _finalize_artifact_manifest(run_artifacts, tasks, results)
        print("[agent-diary diary-notion push] Artifacts: %s" % run_artifacts["run_dir"])

    if not results["failed"]:
        _cleanup(input_path)

    sys.exit(1 if results["failed"] else 0)


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
        print("[agent-diary diary-notion push] Input file not found: %s" % path, file=sys.stderr)
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print("[agent-diary diary-notion push] Failed to read JSON: %s" % e, file=sys.stderr)
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

    git_info = _gather_git_info(cwd, _task_commit_hashes(task))
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


def _build_dry_run_preview(tasks, session_id, date_str, cwd, lang):
    lines = [
        "[agent-diary diary-notion push --dry-run]",
        "Session ID: %s" % session_id,
        "Tasks: %d" % len(tasks),
    ]
    for idx, task in enumerate(tasks):
        title = task.get("title") or "(untitled)"
        git_info = _gather_git_info(cwd, _task_commit_hashes(task))
        branch = git_info.get("branch") or ""
        props = _build_properties(task, date_str, branch, git_info, session_id, idx, cwd)
        blocks = build_notion_blocks(task, git_info, lang)
        lines.append("")
        lines.append("[%d] %s" % (idx, title))
        lines.append("  Project: %s" % props["Project"]["select"]["name"])
        lines.append("  Purpose: %s" % props["Purpose"]["select"]["name"])
        if "Schema Version" in props:
            lines.append("  Schema Version: %s" % props["Schema Version"]["select"]["name"])
        lines.append("  Files: %d" % props["Files"]["number"])
        lines.append("  Commits: %d" % props["Commits"]["number"])
        lines.append("  Lines: %d" % props["Lines"]["number"])
        if branch:
            lines.append("  Branch: %s" % branch)
        for line in _blocks_to_preview_lines(blocks):
            lines.append("  %s" % line)
    return "\n".join(lines)


def _complete_run_artifacts_before_render(run_artifacts, tasks, session_id, date_str, cwd, lang):
    preview_tasks = deepcopy(tasks)
    _set_run_artifacts(preview_tasks, run_artifacts)
    preview = _build_dry_run_preview(preview_tasks, session_id, date_str, cwd, lang)
    _write_artifact_preview(run_artifacts, preview)
    _finalize_artifact_manifest(run_artifacts, tasks)
    _set_run_artifacts(tasks, run_artifacts)


def _arg_str(args, name):
    value = getattr(args, name, None)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return ""


def _print_report(results, input_path):
    pushed = len(results["pushed"])
    skipped = len(results["skipped"])
    failed = len(results["failed"])
    print("[agent-diary diary-notion push] Pushed %d, skipped %d, failed %d" %
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
        print("Retry: agent-diary diary-notion push --input %s --force" % input_path)


def _cleanup(input_path):
    if not input_path:
        return
    try:
        os.remove(input_path)
    except OSError:
        pass


def _print_setup_hint():
    print("[agent-diary diary-notion push] Notion hierarchical exporter not configured.",
          file=sys.stderr)
    print("  Run: agent-diary diary-notion init", file=sys.stderr)
    print("  Or set CLAUDE_DIARY_NOTION_TOKEN and CLAUDE_DIARY_NOTION_ROOT_PAGE_ID",
          file=sys.stderr)
