"""Notion ID cache — avoids re-querying year pages, databases, and rows.

Cache layout (`<config_dir>/notion-cache.json`):
    {
      "root_page_id": "abc-123",
      "years":     { "2026": "page_id_xxx" },
      "databases": { "2026": "db_id_xxx" },
      "rows":      { "<session_id>:<task_index>": "row_page_id" }
    }

If config's root_page_id changes, the whole cache is invalidated on load
(user switched root page → all child IDs are stale).
"""

import json
import os
from pathlib import Path

from claude_diary.config import get_config_dir


CACHE_FILENAME = "notion-cache.json"


def _cache_path():
    return os.path.join(get_config_dir(), CACHE_FILENAME)


def load(root_page_id):
    """Load cache from disk.

    If the on-disk root_page_id doesn't match the current config's root_page_id,
    the cache is treated as stale and an empty cache is returned.
    """
    path = _cache_path()
    if not os.path.exists(path):
        return _empty(root_page_id)

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError):
        return _empty(root_page_id)

    if data.get("root_page_id") != root_page_id:
        return _empty(root_page_id)

    return {
        "root_page_id": root_page_id,
        "years": data.get("years") or {},
        "databases": data.get("databases") or {},
        "rows": data.get("rows") or {},
    }


def save(cache):
    """Persist cache to disk."""
    path = _cache_path()
    Path(os.path.dirname(path)).mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)


def _empty(root_page_id):
    return {
        "root_page_id": root_page_id,
        "years": {},
        "databases": {},
        "rows": {},
    }


def get_year_page(cache, year):
    return cache["years"].get(str(year))


def set_year_page(cache, year, page_id):
    cache["years"][str(year)] = page_id


def get_database(cache, year):
    return cache["databases"].get(str(year))


def set_database(cache, year, db_id):
    cache["databases"][str(year)] = db_id


def _row_key(session_id, task_index):
    return "%s:%d" % (session_id, task_index)


def get_row(cache, session_id, task_index):
    return cache["rows"].get(_row_key(session_id, task_index))


def set_row(cache, session_id, task_index, row_id):
    cache["rows"][_row_key(session_id, task_index)] = row_id


def invalidate_year(cache, year):
    """Remove a year page and its dependent database + rows.

    Used when Notion API returns 404 — page was deleted by user.
    """
    year_key = str(year)
    cache["years"].pop(year_key, None)
    cache["databases"].pop(year_key, None)
    # Rows aren't tagged with year, but row IDs against a missing DB are
    # useless. Clear them all — conservative but safe (just means next push
    # has to re-query).
    cache["rows"] = {}


def invalidate_row(cache, session_id, task_index):
    cache["rows"].pop(_row_key(session_id, task_index), None)


def invalidate_rows_for_session(cache, session_id):
    """Remove all row entries for a session (used by --force)."""
    prefix = "%s:" % session_id
    cache["rows"] = {
        k: v for k, v in cache["rows"].items() if not k.startswith(prefix)
    }
