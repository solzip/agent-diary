"""Numbering the sessions that continue a task group.

A task group is the only thing tying several days of the same work together,
and a bare select tag gives no sense of progress. Counting the sessions
already filed under the name turns it into a readable sequence without adding
a database column.
"""

from claude_diary.exporters.notion_hierarchical import NotionBadRequest
from claude_diary.log import get_logger

logger = get_logger("claude_diary.cli.notion_push")


def _resolve_task_group_ordinals(exporter, year, tasks, session_id, db_id=None):
    """Return {task_group: ordinal} — which session of that group this push is.

    A task group is the only thing tying several days of the same work
    together, and a bare select tag gives no sense of progress. Counting the
    distinct sessions already filed under the name turns it into a readable
    sequence without adding a database column. Best-effort: a query failure
    just means no ordinal, never a failed push.

    `db_id` lets a caller supply a database it already knows about. That
    matters for `--dry-run`: `ensure_database` creates the year page and the
    database when they are missing, which a preview must never do.
    """
    groups = []
    for task in tasks:
        group = (task.get("task_group") or "").strip()
        if group and group not in groups:
            groups.append(group)
    if not groups:
        return {}

    if db_id is None:
        try:
            db_id = exporter.ensure_database(year)
        except Exception as e:
            logger.warning("Task group ordinal lookup skipped: %s", e)
            return {}

    ordinals = {}
    for group in groups:
        try:
            prior = set(exporter.get_task_group_session_ids(db_id, group) or [])
        except NotionBadRequest:
            # Notion rejects a select filter naming an option that does not
            # exist yet, which is exactly what a brand-new task group looks
            # like. That is not an error: it means no prior session.
            prior = set()
        except Exception as e:
            logger.warning("Task group ordinal lookup failed for %s: %s", group, e)
            continue
        prior.discard(session_id)
        ordinals[group] = len(prior) + 1
    return ordinals


def _stamp_task_group_ordinals(tasks, ordinals):
    """Append `(N차)` to titles continuing an existing task group.

    The first session of a group is left alone — `(1차)` on every one-off task
    would be noise. Mutates `tasks` before pass 1 so the row title, the push
    report, and the local run artifacts all agree.
    """
    for task in tasks:
        group = (task.get("task_group") or "").strip()
        ordinal = ordinals.get(group)
        if not ordinal or ordinal < 2:
            continue
        title = (task.get("title") or "").strip()
        suffix = " (%d차)" % ordinal
        if title and not title.endswith(suffix):
            task["title"] = title + suffix
