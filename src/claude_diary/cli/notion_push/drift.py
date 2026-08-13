"""What the project looks like after the push, printed where it will be seen.

`diary-notion ops` already computes every number here. Measured across one
real diary, it had been run a handful of times while `diary-notion push` ran
2,286 — so the detection existed and the signal never reached anybody. This is
the same shape as the failures found earlier in this tool: not a missing
check, a check nobody opens.

So the summary rides along with the command that already runs. It is scoped to
the project just pushed, both because that is the useful comparison and
because it keeps the extra work to a single filtered query.

Nothing here may interrupt a push. The rows are already written by the time it
runs; a report that raises would turn a completed push into a failed command.
"""

from claude_diary.cli.notion_ops import build_ops_report
from claude_diary.cli.notion_push.properties import _resolve_project_name
from claude_diary.log import get_logger

logger = get_logger("claude_diary.cli.notion_push.drift")

PREFIX = "[agent-diary diary-notion push]"


def print_pushed_projects_drift(exporter, db_id, tasks, pushed, cwd, today):
    """Summarise every project this push wrote to. Never raises.

    Normally one — a session has one working directory — but a task may name
    its own project, so the set is taken from what was actually written rather
    than assumed.
    """
    projects = []
    for idx, _title in pushed:
        if not (0 <= idx < len(tasks)):
            continue
        name = _resolve_project_name(tasks[idx].get("project"), cwd)
        if name and name not in projects:
            projects.append(name)

    for project in projects:
        print_project_drift(exporter, db_id, project, today)


def print_project_drift(exporter, db_id, project, today, parent_property_name="Parent Task"):
    """Print open-work signals for one project. Never raises."""
    try:
        rows = exporter.query_database_rows(
            db_id,
            row_filter={"property": "Project", "select": {"equals": project}},
        )
    except Exception as e:
        logger.debug("Drift summary skipped: %s", e)
        return None

    try:
        report = build_ops_report(rows, today, 7, parent_property_name)
    except Exception as e:
        logger.debug("Drift summary skipped: %s", e)
        return None

    stats = (report.get("projects") or {}).get(project)
    counts = report.get("counts") or {}
    if not stats:
        return None

    _render(project, stats, counts)
    return report


def _render(project, stats, counts):
    active = stats.get("active", 0)
    total = stats.get("total", 0)
    done = stats.get("done", 0)
    ratio = stats.get("done_ratio") or 0.0

    print()
    print("%s Open work in %s:" % (PREFIX, project))
    print("  %-22s %d of %d rows" % ("still open", active, total))

    # Only the signals that are actually present. A list of zeroes reads as
    # noise and trains the reader to skip the block, which is the failure this
    # summary exists to avoid.
    for key, label in (
        ("stale", "untouched 7+ days"),
        ("needs_review", "awaiting review"),
        ("missing_next_action", "no next action"),
        ("blocked", "blocked"),
    ):
        value = counts.get(key, 0)
        if value:
            print("  %-22s %d" % (label, value))

    print("  %-22s %d closed (%.0f%%)" % ("done", done, 100.0 * ratio))

    hint = _hint(active, ratio, counts)
    if hint:
        print("  %s" % hint)


def _hint(active, ratio, counts):
    """One line, and only when the numbers warrant it.

    The thresholds are deliberately low-traffic: this prints after every push,
    so a hint that shows most of the time is a hint nobody reads.
    """
    if active >= 20 and ratio < 0.1:
        return "-> %d open and %.0f%% closed. `agent-diary diary-notion ops` lists them." % (
            active, 100.0 * ratio,
        )
    if counts.get("blocked"):
        return "-> %d blocked. `agent-diary diary-notion ops` shows the reasons." % (
            counts["blocked"],
        )
    if counts.get("needs_review", 0) >= 10:
        return "-> %d awaiting review. `agent-diary diary-notion review` lists them." % (
            counts["needs_review"],
        )
    return ""
