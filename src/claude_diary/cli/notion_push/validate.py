"""Rejecting bad push input before anything reaches Notion.

A push is not atomic — each task is a separate API call — so a malformed task
halfway down the list would leave the database half written. Everything is
checked up front and the whole run refuses rather than partially applying.
"""

import sys

from claude_diary.cli.notion_push.properties import (
    VALID_PRIORITIES,
    VALID_STATUSES,
    _clean_schema_version,
    _normalize_priority,
)
from claude_diary.cli.notion_push.tasks import _get_parent_index


def _report_schema_version(data, tasks):
    raw = data.get("schema_version")
    if raw is not None:
        return _clean_schema_version(raw)
    for task in tasks:
        if isinstance(task, dict) and (
            isinstance(task.get("summary"), dict)
            or isinstance(task.get("work"), dict)
            or isinstance(task.get("appendix"), dict)
        ):
            return "v2"
    return "legacy"


def _stamp_report_schema_version(tasks, version):
    for task in tasks:
        if isinstance(task, dict):
            task["_report_schema_version"] = version


def _validate_push_data(data):
    errors = []
    if not isinstance(data, dict):
        return ["input root must be a JSON object"]
    tasks = data.get("tasks")
    if tasks is None:
        return ["tasks is required"]
    if not isinstance(tasks, list):
        return ["tasks must be an array"]

    schema_version = data.get("schema_version")
    if schema_version is not None and _clean_schema_version(schema_version) != "v2":
        errors.append("schema_version must be 2 for normalized report input")

    strict_v2 = _clean_schema_version(schema_version) == "v2"
    for idx, task in enumerate(tasks):
        prefix = "tasks[%d]" % idx
        if not isinstance(task, dict):
            errors.append("%s must be an object" % prefix)
            continue
        if not str(task.get("title") or "").strip():
            errors.append("%s.title is required" % prefix)
        if strict_v2:
            for key in ("summary", "work", "appendix"):
                if not isinstance(task.get(key), dict):
                    errors.append("%s.%s must be an object for schema_version 2" % (prefix, key))
        status = task.get("status")
        if status and str(status).strip() not in VALID_STATUSES:
            errors.append("%s.status must be one of: %s" % (prefix, ", ".join(sorted(VALID_STATUSES))))
        priority = task.get("priority")
        if priority and not _normalize_priority(priority):
            errors.append("%s.priority must be one of: %s" % (prefix, ", ".join(sorted(VALID_PRIORITIES))))
        parent_idx = _get_parent_index(task)
        if parent_idx is not None and parent_idx >= len(tasks):
            errors.append("%s.parent_index points outside tasks" % prefix)
        deps = task.get("depends_on_indices") or []
        if not isinstance(deps, list):
            errors.append("%s.depends_on_indices must be an array" % prefix)
        else:
            for dep in deps:
                if not isinstance(dep, int) or dep < 0 or dep >= len(tasks):
                    errors.append("%s.depends_on_indices contains invalid index %r" % (prefix, dep))
        appendix = task.get("appendix") if isinstance(task.get("appendix"), dict) else {}
        artifacts = appendix.get("artifacts") or task.get("artifacts") or []
        if isinstance(artifacts, dict):
            artifacts = [artifacts]
        if artifacts and not isinstance(artifacts, list):
            errors.append("%s.appendix.artifacts must be an array" % prefix)
        elif isinstance(artifacts, list):
            for art_idx, artifact in enumerate(artifacts):
                if isinstance(artifact, dict) and not str(artifact.get("path") or "").strip():
                    errors.append("%s.appendix.artifacts[%d].path is required" % (prefix, art_idx))
    return errors


def _print_validation_errors(errors, input_path):
    print("[claude-diary diary-notion push] Invalid input: %s" % input_path, file=sys.stderr)
    for error in errors[:20]:
        print("  - %s" % error, file=sys.stderr)
