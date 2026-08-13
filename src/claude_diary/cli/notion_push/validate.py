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


# Input predating the normalized v2 report shape files under this value.
#
# It reads like a typo, and it began as one: this function returned "legacy"
# and `_clean_schema_version` prefixed a "v" to anything not already starting
# with one. The string is kept because it is load-bearing — it is a live
# select option carrying the majority of rows in existing databases, and
# emitting a different string would strand them under the old option while
# new rows accumulate under the new one. Renaming it is a database migration,
# not an edit here. It is now written out explicitly so no one has to trace
# the prefixing to understand where it comes from.
LEGACY_SCHEMA_VERSION = "vlegacy"


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
    return LEGACY_SCHEMA_VERSION


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


def collect_push_warnings(tasks):
    """Problems worth saying out loud that must not stop the push.

    A missing `task_group` is the case this exists for. It is a real defect —
    a row filed without one cannot be joined to its own continuation later,
    and 62% of rows on one real database have none — but rejecting the push
    over it would discard the record entirely, which is a worse outcome than
    an unlinked row and the failure mode this project keeps having to fix.
    """
    warnings = []
    ungrouped = [
        idx for idx, task in enumerate(tasks)
        if isinstance(task, dict) and not str(task.get("task_group") or "").strip()
    ]
    if ungrouped:
        warnings.append(
            "%d of %d task(s) have no task_group: %s. "
            "Work filed without one cannot be linked to its continuation later."
            % (
                len(ungrouped), len(tasks),
                ", ".join("tasks[%d]" % i for i in ungrouped[:5])
                + (" ..." if len(ungrouped) > 5 else ""),
            )
        )
    return warnings


def print_push_warnings(warnings):
    for warning in warnings:
        print("[agent-diary diary-notion push] warning: %s" % warning)


def _print_validation_errors(errors, input_path):
    print("[agent-diary diary-notion push] Invalid input: %s" % input_path, file=sys.stderr)
    for error in errors[:20]:
        print("  - %s" % error, file=sys.stderr)
