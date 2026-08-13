"""Exporter plugin loader — dynamically loads and runs enabled exporters.

`.export_queue.json` is the fifth state file this tool keeps beside the
diary, and it was the one that never got the treatment the other four had.
The day file, `.session_counts.json`, `.diary_index.json` and
`.session_progress.json` each hold a lock, write atomically, and move an
unreadable file aside rather than replacing it. This one did none of that,
and it is the file that holds work not yet delivered anywhere:

    a truncated queue of 20 -> 1 entry survives   (read fails, `queue = []`,
                                                   one append, whole file
                                                   written back)
    40 concurrent hooks     -> 23 of 40 arrive    (no lock on a
                                                   read-modify-write)
"""

import importlib
import json
import os

from claude_diary.lib.filelock import FileLock
from claude_diary.log import get_logger

logger = get_logger("claude_diary.exporters.loader")

QUEUE_FILENAME = ".export_queue.json"


def load_exporters(config):
    """Load enabled exporters from config.

    Returns list of (name, exporter_instance) tuples.
    """
    exporters_config = config.get("exporters", {})
    loaded = []

    for name, exp_config in exporters_config.items():
        if not exp_config.get("enabled", False):
            continue
        try:
            module = importlib.import_module("claude_diary.exporters.%s" % name)
            class_name = "%sExporter" % name.capitalize()
            exporter_class = getattr(module, class_name, None)
            if exporter_class is None:
                logger.warning("Exporter '%s': class '%s' not found", name, class_name)
                continue
            instance = exporter_class(exp_config)
            if instance.validate_config():
                loaded.append((name, instance))
            else:
                logger.warning("Exporter '%s': invalid config", name)
        except ImportError:
            logger.warning("Exporter '%s': module not found", name)
        except Exception as e:
            logger.warning("Exporter '%s': load error: %s", name, e)

    return loaded


def run_exporters(exporters, entry_data, diary_dir=None):
    """Run all loaded exporters with entry_data.

    Returns dict: {"success": [names], "failed": [names]}
    Failed exports are queued for retry.
    """
    result = {"success": [], "failed": []}

    for name, exporter in exporters:
        try:
            success = exporter.export(entry_data)
            if success:
                result["success"].append(name)
            else:
                result["failed"].append(name)
                _queue_failed(diary_dir, name, entry_data, "export returned False")
        except Exception as e:
            result["failed"].append(name)
            logger.warning("Exporter '%s' failed: %s", name, e)
            _queue_failed(diary_dir, name, entry_data, str(e))

    return result


def queue_path_for(diary_dir):
    return os.path.join(diary_dir, QUEUE_FILENAME)


def _item_key(item):
    """Identity for a queued export, used to merge concurrent additions.

    The timestamp is `datetime.now().isoformat()` — microsecond resolution —
    so the pair is unique in practice, and items written by older versions
    have both fields already.
    """
    return (item.get("timestamp", ""), item.get("exporter", ""))


def _load_queue(queue_path):
    """Read the queue, or move an unreadable one aside and start empty.

    The caller is about to write the whole file back, so returning `[]` for a
    file that merely failed to parse deletes every export still waiting to be
    delivered. Measured: a truncated 20-entry queue came back as 1.
    """
    if not os.path.exists(queue_path):
        return []
    try:
        with open(queue_path, "r", encoding="utf-8") as f:
            queue = json.load(f)
    except Exception as e:
        from claude_diary.writer import preserve_corrupt
        logger.warning(
            "Export retry queue unreadable (%s); starting a new one. "
            "The old file is kept alongside it with a .corrupt suffix.", e,
        )
        preserve_corrupt(queue_path)
        return []

    if not isinstance(queue, list):
        # Parsing is not the only way this file can be wrong, and a dict here
        # is no less somebody's data than a truncated list. The search index
        # draws the line in the same place.
        from claude_diary.writer import preserve_corrupt
        logger.warning(
            "Export retry queue has an unexpected shape; starting a new one. "
            "The old file is kept alongside it with a .corrupt suffix.",
        )
        preserve_corrupt(queue_path)
        return []
    return queue


def _write_queue(queue_path, queue):
    """Write the queue atomically, so a crash cannot truncate it.

    Losing the queue to a half-written file is the failure `_load_queue`
    above has to recover from; not creating it in the first place is better.
    """
    tmp = "%s.tmp%d" % (queue_path, os.getpid())
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(queue, f, indent=2, ensure_ascii=False)
        os.replace(tmp, queue_path)
    except Exception as e:
        logger.warning("Could not write the export retry queue: %s", e)
        try:
            os.unlink(tmp)
        except OSError:
            pass


def retry_queued(config, diary_dir):
    """Retry previously failed exports. Called at the start of each session."""
    queue_path = queue_path_for(diary_dir)
    if not os.path.exists(queue_path):
        return

    with FileLock(queue_path):
        queue = _load_queue(queue_path)

    if not queue:
        return

    exporters = load_exporters(config)
    exporter_map = {name: exp for name, exp in exporters}

    remaining = []
    for item in queue:
        name = item.get("exporter", "")
        retries = item.get("retries", 0)

        if retries >= 3:
            logger.warning("Exporter '%s': max retries reached, dropping", name)
            continue

        if name not in exporter_map:
            remaining.append(item)
            continue

        try:
            success = exporter_map[name].export(item.get("entry_data", {}))
            if not success:
                item["retries"] = retries + 1
                remaining.append(item)
        except Exception:
            item["retries"] = retries + 1
            remaining.append(item)

    # The exporters above ran without the lock held — they make network calls
    # and one slow retry must not stall a hook that only wants to add a line.
    # So the write merges rather than replaces: anything queued meanwhile is
    # not ours to drop.
    handled = {_item_key(item) for item in queue}
    with FileLock(queue_path):
        added = [item for item in _load_queue(queue_path)
                 if _item_key(item) not in handled]
        final = remaining + added
        if final:
            _write_queue(queue_path, final)
        else:
            try:
                os.remove(queue_path)
            except OSError:
                pass


def _queue_failed(diary_dir, name, entry_data, error):
    """Add failed export to retry queue."""
    if not diary_dir:
        return

    queue_path = queue_path_for(diary_dir)

    from datetime import datetime
    item = {
        "timestamp": datetime.now().isoformat(),
        "exporter": name,
        "entry_data": {
            "date": entry_data.get("date", ""),
            "time": entry_data.get("time", ""),
            "project": entry_data.get("project", ""),
            "summary_hints": entry_data.get("summary_hints", [])[:3],
        },
        "error": error,
        "retries": 0,
    }

    # Read and write under one lock. Two hooks ending together is the normal
    # case, not the rare one, and unlocked this dropped 17 of 40.
    with FileLock(queue_path):
        queue = _load_queue(queue_path)
        # Keep queue manageable
        if len(queue) > 50:
            queue = queue[-50:]
        queue.append(item)
        _write_queue(queue_path, queue)
