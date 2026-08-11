"""Pass 2: linking rows to each other once every row ID is known.

Two different relations, deliberately kept apart. `Depends On` is execution
order and is limited to top-level rows, so prerequisite order never gets
mixed with subtask hierarchy. Containment goes to Notion's native sub-item
relation, which is the only thing that drives real expand/collapse nesting
and can only be created through the Notion UI.
"""

from claude_diary.cli.notion_push.tasks import _get_parent_index, _is_top_level_task
from claude_diary.exporters.notion_hierarchical import detect_subitem_relation


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
        # Report as failures rather than skipping quietly: the rows were pushed
        # but the requested hierarchy was not, and the preserved input JSON lets
        # the user re-run push once Sub-items is enabled in the Notion UI.
        _print_enable_subitems_hint(len(pairs))
        return [
            (
                child_idx,
                tasks[child_idx].get("title") or "(untitled)",
                "sub-item: native Sub-items relation is not enabled in this database",
            )
            for child_idx, _ in pairs
        ]

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
        "[agent-diary diary-notion push] %d task(s) have a parent, but this "
        "database has no native Sub-items relation yet — nesting skipped." % count
    )
    print("  Enable it once in Notion: open the database -> ⋯ menu -> Sub-items,")
    print("  then re-run push or `agent-diary diary-notion ensure` to nest them.")
