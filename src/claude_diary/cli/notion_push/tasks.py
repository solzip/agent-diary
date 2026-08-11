"""Reading fields off a task dict.

Tasks arrive from an agent, so every field is optional and may hold the wrong
type. Both the v2 `appendix` shape and the older flat shape are accepted, and
the readers here are the only place that difference is handled.
"""

from claude_diary.formatter import dedupe_texts


def _task_appendix(task):
    value = task.get("appendix")
    return value if isinstance(value, dict) else {}


def _task_texts(*values):
    items = []
    for value in values:
        if value is None:
            continue
        if isinstance(value, str):
            candidates = [value]
        elif isinstance(value, (list, tuple, set)):
            candidates = value
        else:
            candidates = [value]
        for item in candidates:
            text = str(item or "").replace("\n", " ").strip()
            if text:
                items.append(text)
    return dedupe_texts(items)


def _task_commit_hashes(task):
    appendix = _task_appendix(task)
    return _task_texts(appendix.get("commit_hashes"), task.get("commit_hashes"))


def _task_files_count(task):
    appendix = _task_appendix(task)
    modified = _task_texts(appendix.get("files_modified"), task.get("files_modified"))
    created = _task_texts(appendix.get("files_created"), task.get("files_created"))
    return len(modified) + len(created)


def _task_next_action(task):
    flat = task.get("next_action")
    if flat:
        return flat
    actions = _task_texts(task.get("next_actions"), task.get("next_steps"))
    return actions[0] if actions else ""


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
