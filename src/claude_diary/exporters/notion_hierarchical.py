"""Notion hierarchical exporter — pushes task entries to a year/DB/row hierarchy.

Structure (on Notion):
    [Root page (user-specified)]
     ├─ 2026 (page, auto-created)
     │   └─ Entries (database, auto-created, shared schema)
     │       ├─ row 1
     │       └─ row 2
     ├─ 2027
     └─ ...

Used by `/diary-notion` and `$diary-notion` via `claude-diary diary-notion push`.
Separate from the flat-mode NotionExporter (Stop Hook auto-push).

Error handling policy:
  401/403         → fail fast (auth/permission problem affects all tasks)
  400             → skip this task, continue with the rest
  404             → invalidate cache, auto-recreate parent, retry
  429             → respect Retry-After, inline retry
  5xx / network   → exponential backoff, inline retry (max 3)
"""

import time

from claude_diary.log import get_logger
from claude_diary.lib import notion_cache

logger = get_logger("claude_diary.exporters.notion_hierarchical")


NOTION_API_VERSION = "2022-06-28"
NOTION_API_BASE = "https://api.notion.com/v1"
MAX_RETRIES = 3
RICH_TEXT_LIMIT = 2000
SCHEMA_VERSION = "v7"
DATABASE_TITLE = "Entries"


class NotionAuthError(Exception):
    """401/403 — token invalid or page not shared with integration."""


class NotionNotFound(Exception):
    """404 — parent page/db was deleted out from under us."""


class NotionBadRequest(Exception):
    """400 — malformed properties for this specific row."""


class NotionHierarchicalExporter:
    """Pushes tasks to the year/database/row hierarchy.

    Unlike BaseExporter subclasses, this is invoked directly by the
        `diary-notion push` CLI with a list of tasks, not a single entry_data.
    """

    def __init__(self, config):
        self.api_token = config.get("api_token")
        self.root_page_id = config.get("root_page_id")
        self._session = None
        self._cache = None

    def validate_config(self):
        return bool(self.api_token) and bool(self.root_page_id)

    def _ensure_requests(self):
        try:
            import requests
            return requests
        except ImportError:
            raise RuntimeError(
                "Notion exporter requires 'requests'. Install with: pip install requests"
            )

    def _headers(self):
        return {
            "Authorization": "Bearer %s" % self.api_token,
            "Content-Type": "application/json",
            "Notion-Version": NOTION_API_VERSION,
        }

    def _request(self, method, path, json_body=None):
        """HTTP wrapper with retry + error categorization.

        Returns parsed JSON on 200. Raises typed exceptions for known errors.
        """
        requests = self._ensure_requests()
        url = "%s%s" % (NOTION_API_BASE, path)

        last_error = None
        for attempt in range(MAX_RETRIES):
            try:
                resp = requests.request(
                    method, url,
                    headers=self._headers(),
                    json=json_body,
                    timeout=15,
                )
            except Exception as e:
                last_error = e
                if attempt < MAX_RETRIES - 1:
                    time.sleep(2 ** attempt)
                    continue
                raise RuntimeError("Notion API network error: %s" % e)

            status = resp.status_code
            if status == 200:
                return resp.json()

            if status == 401 or status == 403:
                raise NotionAuthError(
                    "Notion API %d: %s" % (status, _short_error(resp))
                )

            if status == 404:
                raise NotionNotFound(
                    "Notion API 404: %s" % _short_error(resp)
                )

            if status == 400:
                raise NotionBadRequest(
                    "Notion API 400: %s" % _short_error(resp)
                )

            if status == 429:
                retry_after = int(resp.headers.get("Retry-After", "1"))
                time.sleep(min(retry_after, 30))
                last_error = "rate limited"
                continue

            if 500 <= status < 600:
                if attempt < MAX_RETRIES - 1:
                    time.sleep(2 ** attempt)
                    last_error = "5xx (%d)" % status
                    continue
                raise RuntimeError(
                    "Notion API %d after %d retries: %s" %
                    (status, MAX_RETRIES, _short_error(resp))
                )

            raise RuntimeError(
                "Notion API unexpected status %d: %s" %
                (status, _short_error(resp))
            )

        raise RuntimeError("Notion API failed after retries: %s" % last_error)

    def load_cache(self):
        self._cache = notion_cache.load(self.root_page_id)
        return self._cache

    def save_cache(self):
        if self._cache is not None:
            notion_cache.save(self._cache)

    def ensure_year_page(self, year):
        """Get year page ID, creating if missing.

        Cache hit + page still exists → return cached ID.
        Cache hit but 404 → invalidate, recreate.
        Cache miss → search children of root page, create if not found.
        """
        cached = notion_cache.get_year_page(self._cache, year)
        if cached:
            try:
                self._request("GET", "/blocks/%s" % cached)
                return cached
            except NotionNotFound:
                logger.warning("Year page %s not found in Notion, recreating", year)
                notion_cache.invalidate_year(self._cache, year)

        existing = self._find_child_page(self.root_page_id, str(year))
        if existing:
            notion_cache.set_year_page(self._cache, year, existing)
            return existing

        created = self._create_year_page(year)
        notion_cache.set_year_page(self._cache, year, created)
        return created

    def _find_child_page(self, parent_id, title):
        """Scan parent's children for a child_page with matching title."""
        cursor = None
        while True:
            path = "/blocks/%s/children?page_size=100" % parent_id
            if cursor:
                path += "&start_cursor=%s" % cursor
            data = self._request("GET", path)
            for block in data.get("results", []):
                if block.get("type") != "child_page":
                    continue
                block_title = block.get("child_page", {}).get("title", "")
                if block_title == title:
                    return block["id"]
            if not data.get("has_more"):
                return None
            cursor = data.get("next_cursor")

    def _create_year_page(self, year):
        body = {
            "parent": {"page_id": self.root_page_id},
            "properties": {
                "title": [{"text": {"content": str(year)}}],
            },
        }
        resp = self._request("POST", "/pages", body)
        return resp["id"]

    def ensure_database(self, year, force_schema=False):
        """Get Entries database ID for a year, creating if missing.

        Also ensures the current schema extensions are present — needed for
        older DBs created before those columns were part of the design.
        Tracked via cache so we only patch once on the happy path.
        """
        cached = notion_cache.get_database(self._cache, year)
        db_id = None
        if cached:
            try:
                self._request("GET", "/databases/%s" % cached)
                db_id = cached
            except NotionNotFound:
                logger.warning("Database for %s not found, recreating", year)
                notion_cache.set_database(self._cache, year, None)

        if db_id is None:
            year_page_id = self.ensure_year_page(year)
            db_id = self._find_child_database(year_page_id, DATABASE_TITLE)
            if db_id is None:
                db_id = self._create_database(year_page_id)
            notion_cache.set_database(self._cache, year, db_id)

        self._ensure_db_schema_extensions(db_id, force=force_schema)
        return db_id

    def resolve_existing_database(self, year):
        """Return an existing Entries DB ID without creating or patching anything."""
        cached = notion_cache.get_database(self._cache, year)
        if cached:
            try:
                self._request("GET", "/databases/%s" % cached)
                return cached
            except NotionNotFound:
                notion_cache.set_database(self._cache, year, None)

        year_page_id = notion_cache.get_year_page(self._cache, year)
        if year_page_id:
            try:
                self._request("GET", "/blocks/%s" % year_page_id)
            except NotionNotFound:
                notion_cache.invalidate_year(self._cache, year)
                year_page_id = None

        if not year_page_id:
            year_page_id = self._find_child_page(self.root_page_id, str(year))
        if not year_page_id:
            return None

        return self._find_child_database(year_page_id, DATABASE_TITLE)

    def _find_child_database(self, parent_id, title):
        """Scan parent's children for a child_database with matching title."""
        cursor = None
        while True:
            path = "/blocks/%s/children?page_size=100" % parent_id
            if cursor:
                path += "&start_cursor=%s" % cursor
            data = self._request("GET", path)
            for block in data.get("results", []):
                if block.get("type") != "child_database":
                    continue
                block_title = block.get("child_database", {}).get("title", "")
                if block_title == title:
                    return block["id"]
            if not data.get("has_more"):
                return None
            cursor = data.get("next_cursor")

    def _ensure_db_schema_extensions(self, db_id, force=False):
        """Add current schema extensions if not yet recorded in cache.

        Patching the same property twice is harmless (Notion treats existing
        properties as no-ops), but we still gate by a cache flag to skip the
        API call on the happy path.
        """
        schema_v = self._cache.setdefault("schema_v", {})
        current = schema_v.get(db_id)
        if current == SCHEMA_VERSION and not force:
            return
        if current == SCHEMA_VERSION and force:
            self._request("PATCH", "/databases/%s" % db_id, {
                "properties": _current_schema_extensions(db_id)
            })
            schema_v[db_id] = SCHEMA_VERSION
            return
        self._request("PATCH", "/databases/%s" % db_id, {
            "properties": _current_schema_extensions(db_id)
        })
        schema_v[db_id] = SCHEMA_VERSION

    def _create_database(self, parent_page_id):
        """Create the Entries inline database with the base schema.

        Purpose, Status, Task Group, and self-relations are added afterwards
        by `_ensure_db_schema_extensions` — keeping them out
        of this call means new and pre-existing DBs go through the same
        upgrade path.
        """
        body = {
            "parent": {"type": "page_id", "page_id": parent_page_id},
            "is_inline": True,
            "title": [{"text": {"content": DATABASE_TITLE}}],
            "properties": {
                "Name":        {"title": {}},
                "Date":        {"date": {}},
                "Project":     {"select": {}},
                "Branch":      {"select": {}},
                "Categories":  {"multi_select": {}},
                "Files":       {"number": {}},
                "Commits":     {"number": {}},
                "Lines":       {"number": {}},
                "Session ID":  {"rich_text": {}},
                "Task Index":  {"number": {}},
            },
        }
        resp = self._request("POST", "/databases", body)
        return resp["id"]

    def find_existing_row(self, db_id, session_id, task_index):
        """Return row page ID if a row with the same Session ID + Task Index exists."""
        cached = notion_cache.get_row(self._cache, session_id, task_index)
        if cached:
            try:
                self._request("GET", "/pages/%s" % cached)
                return cached
            except NotionNotFound:
                notion_cache.invalidate_row(self._cache, session_id, task_index)

        body = {
            "filter": {
                "and": [
                    {"property": "Session ID", "rich_text": {"equals": session_id}},
                    {"property": "Task Index", "number": {"equals": task_index}},
                ]
            },
            "page_size": 1,
        }
        try:
            resp = self._request("POST", "/databases/%s/query" % db_id, body)
        except NotionNotFound:
            return None
        results = resp.get("results", [])
        if not results:
            return None
        row_id = results[0]["id"]
        notion_cache.set_row(self._cache, session_id, task_index, row_id)
        return row_id

    def archive_rows_for_session(self, db_id, session_id):
        """Archive (soft-delete) all rows whose Session ID matches.

        Used by --force to allow a clean re-push.
        """
        body = {
            "filter": {
                "property": "Session ID",
                "rich_text": {"equals": session_id},
            },
            "page_size": 100,
        }
        archived = 0
        cursor = None
        while True:
            if cursor:
                body["start_cursor"] = cursor
            resp = self._request("POST", "/databases/%s/query" % db_id, body)
            for row in resp.get("results", []):
                self._request("PATCH", "/pages/%s" % row["id"], {"archived": True})
                archived += 1
            if not resp.get("has_more"):
                break
            cursor = resp.get("next_cursor")
        notion_cache.invalidate_rows_for_session(self._cache, session_id)
        return archived

    def create_row(self, db_id, properties, body_blocks):
        """Create a new row (page) in the database with properties + body blocks."""
        body = {
            "parent": {"database_id": db_id},
            "properties": properties,
            "children": body_blocks,
        }
        resp = self._request("POST", "/pages", body)
        return resp["id"]

    def update_row_relation(self, row_id, depends_on_row_ids):
        """PATCH a row to set its `Depends On` relation.

        Used by the 2-pass push flow: rows are created first (so we have
        their IDs), then dependency edges are wired up in a second pass.
        """
        self._request("PATCH", "/pages/%s" % row_id, {
            "properties": {
                "Depends On": {
                    "relation": [{"id": rid} for rid in depends_on_row_ids]
                }
            }
        })

    def update_row_parent(self, row_id, parent_row_id):
        """PATCH a row to set its `Parent Task` containment relation."""
        self._request("PATCH", "/pages/%s" % row_id, {
            "properties": {
                "Parent Task": {
                    "relation": [{"id": parent_row_id}]
                }
            }
        })

    def update_row_subitems(self, row_id, child_row_ids):
        """PATCH a parent row to include native Notion `Sub-items` relations."""
        merged_ids = _unique_ids(
            self.get_row_relation_ids(row_id, "Sub-items") + list(child_row_ids)
        )
        self._request("PATCH", "/pages/%s" % row_id, {
            "properties": {
                "Sub-items": {
                    "relation": [{"id": rid} for rid in merged_ids]
                }
            }
        })

    def get_row_relation_ids(self, row_id, property_name):
        """Return relation target IDs for a page property if present."""
        data = self._request("GET", "/pages/%s" % row_id)
        prop = (data.get("properties") or {}).get(property_name) or {}
        return [
            item.get("id")
            for item in prop.get("relation") or []
            if item.get("id")
        ]


def _short_error(resp):
    """Extract a one-line error description from a Notion error response."""
    try:
        data = resp.json()
        return data.get("message") or data.get("code") or resp.text[:200]
    except Exception:
        return resp.text[:200]


def _self_relation(db_id):
    """Return a self-relation schema object for the current database API version."""
    return {
        "relation": {
            "database_id": db_id,
            "type": "single_property",
            "single_property": {},
        }
    }


def _subitem_parent_relation(db_id):
    """Return the Parent Task side of Notion's native sub-item relation pair."""
    return {
        "relation": {
            "database_id": db_id,
            "type": "dual_property",
            "dual_property": {
                "synced_property_name": "Sub-items",
            },
        }
    }


def _current_schema_extensions(db_id):
    """Return the full current extension schema beyond the base DB columns."""
    return {
        "Purpose": {"select": {}},
        "Status": {"select": {}},
        "Task Group": {"select": {}},
        "Depends On": _self_relation(db_id),
        "Parent Task": _subitem_parent_relation(db_id),
        "Work Period": {"date": {}},
        "Priority": {"select": {}},
        "Next Action": {"rich_text": {}},
        "Blocked": {"checkbox": {}},
        "Block Reason": {"rich_text": {}},
        "Carryover": {"checkbox": {}},
        "Review Status": {"select": {}},
        "Last Reviewed": {"date": {}},
    }


def _unique_ids(values):
    seen = set()
    result = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
