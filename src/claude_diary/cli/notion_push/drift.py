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
from claude_diary.lib.nonfatal import non_fatal

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
    """Print open-work signals for one project. Never raises.

    One guard around the whole thing rather than one per call: `_render` was
    outside the old pair and only stayed non-fatal because the caller had a
    handler too, which is the arrangement that let a bug in this file go a day
    without a word.
    """
    with non_fatal("drift summary", PREFIX):
        rows = exporter.query_database_rows(
            db_id,
            row_filter={"property": "Project", "select": {"equals": project}},
        )
        report = build_ops_report(rows, today, 7, parent_property_name)

        stats = (report.get("projects") or {}).get(project)
        if not stats:
            return None

        _render(project, stats, report.get("counts") or {},
                report.get("task_groups") or {})
        return report
    return None


UNGROUPED = "(no task group)"


def _grouping(task_groups):
    """How much of this project is filed under a task group, and which ones.

    `Task Group` is what makes work from different days findable together, and
    measured on one real database only 38% of rows carried one. A row filed
    without a group cannot be linked to its own continuation later, so the
    count belongs next to the other drift signals rather than in a report
    nobody opens.
    """
    ungrouped = (task_groups.get(UNGROUPED) or {}).get("total", 0)
    named = [
        (name, stats)
        for name, stats in task_groups.items()
        if name != UNGROUPED
    ]
    # Most recently worked first: those are the ones a continuation is likely
    # to belong to, which is the reason for printing them at all.
    named.sort(key=lambda pair: pair[1].get("last_worked_on") or "", reverse=True)
    return ungrouped, [name for name, _ in named]


def _render(project, stats, counts, task_groups):
    active = stats.get("active", 0)
    total = stats.get("total", 0)
    done = stats.get("done", 0)
    ratio = stats.get("done_ratio") or 0.0
    ungrouped, group_names = _grouping(task_groups)

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

    if ungrouped:
        print("  %-22s %d of %d rows" % ("no task group", ungrouped, total))

    print("  %-22s %d closed (%.0f%%)" % ("done", done, 100.0 * ratio))

    if ungrouped and group_names:
        # The vocabulary already in use here, most recent first. A continuation
        # filed under a new name is not a continuation, and this is the list
        # the next push should be choosing from.
        shown = ", ".join(group_names[:5])
        more = len(group_names) - 5
        print("  %-22s %s%s" % (
            "groups in use", shown, " (+%d)" % more if more > 0 else "",
        ))

    hint = _hint(active, ratio, counts, ungrouped, total)
    if hint:
        print("  %s" % hint)


def _hint(active, ratio, counts, ungrouped=0, total=0):
    """One line, and only when the numbers warrant it.

    The thresholds are deliberately low-traffic: this prints after every push,
    so a hint that shows most of the time is a hint nobody reads.
    """
    if total and ungrouped * 2 > total:
        return "-> %d of %d rows have no task group; work from separate days cannot be linked." % (
            ungrouped, total,
        )
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
