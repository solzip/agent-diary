"""Exporter plugin loader — dynamically loads and runs enabled exporters."""

import importlib
import json
import os
import sys

from claude_diary.log import get_logger

logger = get_logger("claude_diary.exporters.loader")


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


def retry_queued(config, diary_dir):
    """Retry previously failed exports. Called at the start of each session."""
    queue_path = os.path.join(diary_dir, ".export_queue.json")
    if not os.path.exists(queue_path):
        return

    try:
        with open(queue_path, "r", encoding="utf-8") as f:
            queue = json.load(f)
    except Exception:
        return

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

    # Update queue
    if remaining:
        with open(queue_path, "w", encoding="utf-8") as f:
            json.dump(remaining, f, indent=2, ensure_ascii=False)
    else:
        try:
            os.remove(queue_path)
        except OSError:
            pass


def _queue_failed(diary_dir, name, entry_data, error):
    """Add failed export to retry queue."""
    if not diary_dir:
        return

    queue_path = os.path.join(diary_dir, ".export_queue.json")
    queue = []
    if os.path.exists(queue_path):
        try:
            with open(queue_path, "r", encoding="utf-8") as f:
                queue = json.load(f)
        except Exception:
            queue = []

    # Keep queue manageable
    if len(queue) > 50:
        queue = queue[-50:]

    from datetime import datetime
    queue.append({
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
    })

    try:
        with open(queue_path, "w", encoding="utf-8") as f:
            json.dump(queue, f, indent=2, ensure_ascii=False)
    except Exception:
        pass
