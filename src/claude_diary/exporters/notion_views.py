"""Notion Views API client and core view ensure logic."""

import time
from dataclasses import dataclass, field
from urllib.parse import unquote, urlencode

from claude_diary.exporters.notion_hierarchical import (
    NOTION_API_BASE,
    MAX_RETRIES,
    NotionAuthError,
    NotionBadRequest,
    NotionNotFound,
    detect_subitem_relation,
    short_error,
)


NOTION_VIEWS_API_VERSION = "2026-03-11"
# One view per question the vision (§1) says this database exists to answer —
# what did I do today, what is blocked, what is next — plus the structure and
# continuity views that give those answers their shape. Order matches
# _build_core_view_specs, which is the tab order in Notion.
CORE_VIEW_NAMES = ("작업 계층", "오늘 작업", "Blocked")
OPERATION_VIEW_NAMES = ("전날 미완료", "작업 그룹별")
ENSURED_VIEW_NAMES = CORE_VIEW_NAMES + OPERATION_VIEW_NAMES

# Views earlier versions created that this spec no longer manages: pure
# group-by duplicates of one another. `ensure` reports them so they can be
# deleted by hand — deleting a Notion view could discard a layout the user
# customised, so it is never done automatically.
RETIRED_VIEW_NAMES = ("상태별", "목적별", "프로젝트별", "오늘 우선순위", "리뷰 필요")

REQUIRED_PROPERTIES = (
    "Name",
    "Date",
    "Work Period",
    "Project",
    "Purpose",
    "Status",
    "Task Group",
    "Parent Task",
    "Sub-items",
    "Depends On",
    "Priority",
    "Next Action",
    "Blocked",
    "Block Reason",
    "Carryover",
    "Review Status",
    "Last Reviewed",
    "Session ID",
    "Task Index",
)

HIDDEN_PROPERTIES = ("Session ID", "Task Index")
SCHEMA_EXTENSION_PROPERTIES = (
    "Purpose",
    "Status",
    "Task Group",
    "Depends On",
    "Parent Task",
    "Sub-items",
    "Work Period",
    "Priority",
    "Next Action",
    "Blocked",
    "Block Reason",
    "Carryover",
    "Review Status",
    "Last Reviewed",
)


@dataclass
class ViewConflict:
    name: str
    reason: str


@dataclass
class ViewFailure:
    name: str
    reason: str


@dataclass
class EnsureViewsResult:
    created: list = field(default_factory=list)
    updated: list = field(default_factory=list)
    verified: list = field(default_factory=list)
    planned: list = field(default_factory=list)
    updates_planned: list = field(default_factory=list)
    conflicts: list = field(default_factory=list)
    failed: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    repaired: list = field(default_factory=list)

    def ok(self):
        return not self.conflicts and not self.failed


class NotionViewsClient:
    """Small wrapper around Notion's 2025+ Views/Data source APIs."""

    def __init__(self, config):
        self.api_token = config.get("api_token")

    def validate_config(self):
        return bool(self.api_token)

    def _ensure_requests(self):
        try:
            import requests
            return requests
        except ImportError:
            raise RuntimeError(
                "Notion views client requires 'requests'. Install with: pip install requests"
            ) from None

    def _headers(self):
        return {
            "Authorization": "Bearer %s" % self.api_token,
            "Content-Type": "application/json",
            "Notion-Version": NOTION_VIEWS_API_VERSION,
        }

    def _request(self, method, path, json_body=None):
        requests = self._ensure_requests()
        url = "%s%s" % (NOTION_API_BASE, path)

        last_error = None
        for attempt in range(MAX_RETRIES):
            try:
                resp = requests.request(
                    method,
                    url,
                    headers=self._headers(),
                    json=json_body,
                    timeout=15,
                )
            except Exception as e:
                last_error = e
                if attempt < MAX_RETRIES - 1:
                    time.sleep(2 ** attempt)
                    continue
                raise RuntimeError("Notion Views API network error: %s" % e) from e

            status = resp.status_code
            if status in (200, 201):
                return resp.json()

            if status == 401 or status == 403:
                raise NotionAuthError(
                    "Notion Views API %d: %s" % (status, short_error(resp))
                )
            if status == 404:
                raise NotionNotFound(
                    "Notion Views API 404: %s" % short_error(resp)
                )
            if status == 400:
                raise NotionBadRequest(
                    "Notion Views API 400: %s" % short_error(resp)
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
                    "Notion Views API %d after %d retries: %s" %
                    (status, MAX_RETRIES, short_error(resp))
                )

            raise RuntimeError(
                "Notion Views API unexpected status %d: %s" %
                (status, short_error(resp))
            )

        raise RuntimeError("Notion Views API failed after retries: %s" % last_error)

    def retrieve_database(self, database_id):
        return self._request("GET", "/databases/%s" % database_id)

    def get_primary_data_source_id(self, database_id):
        database = self.retrieve_database(database_id)
        data_sources = database.get("data_sources") or []
        if not data_sources:
            raise RuntimeError("Database has no data_sources in 2025-09-03 API response")
        return data_sources[0]["id"]

    def retrieve_data_source(self, data_source_id):
        return self._request("GET", "/data_sources/%s" % data_source_id)

    def get_property_map(self, data_source_id):
        data_source = self.retrieve_data_source(data_source_id)
        properties = data_source.get("properties") or {}
        prop_map = {}
        for name, prop in properties.items():
            prop_map[name] = {
                "id": unquote(prop.get("id") or name),
                "type": prop.get("type") or _infer_property_type(prop),
                "relation": prop.get("relation"),
            }
        return prop_map

    def list_views(self, database_id):
        views = []
        cursor = None
        while True:
            params = {"database_id": database_id, "page_size": 100}
            if cursor:
                params["start_cursor"] = cursor
            data = self._request("GET", "/views?%s" % urlencode(params))
            for ref in data.get("results", []):
                view_id = ref.get("id")
                if view_id:
                    views.append(self.retrieve_view(view_id))
            if not data.get("has_more"):
                return views
            cursor = data.get("next_cursor")

    def retrieve_view(self, view_id):
        return self._request("GET", "/views/%s" % view_id)

    def create_view(self, payload):
        return self._request("POST", "/views", payload)

    def update_view(self, view_id, payload):
        return self._request("PATCH", "/views/%s" % view_id, payload)

    def update_data_source(self, data_source_id, payload):
        return self._request("PATCH", "/data_sources/%s" % data_source_id, payload)

    def query_data_source_rows(self, data_source_id):
        """Return all rows (pages) of a data source, following pagination."""
        rows = []
        cursor = None
        while True:
            body = {"page_size": 100}
            if cursor:
                body["start_cursor"] = cursor
            data = self._request(
                "POST", "/data_sources/%s/query" % data_source_id, body
            )
            rows.extend(data.get("results", []))
            if not data.get("has_more"):
                return rows
            cursor = data.get("next_cursor")

    def update_page_relation(self, page_id, property_name, target_ids):
        """PATCH a single page's relation property to the given target IDs."""
        return self._request("PATCH", "/pages/%s" % page_id, {
            "properties": {
                property_name: {"relation": [{"id": tid} for tid in target_ids]}
            }
        })


class CoreViewsEnsurer:
    """Create or verify the permanent core and operating views."""

    def __init__(self, client):
        self.client = client

    def ensure(self, database_id, today, dry_run=False):
        result = EnsureViewsResult()
        data_source_id = self.client.get_primary_data_source_id(database_id)
        prop_map = self.client.get_property_map(data_source_id)

        if _needs_subitems_schema(prop_map):
            if dry_run:
                result.updates_planned.append("작업 계층")
                result.warnings.append(
                    "schema v8 would convert Parent Task to a dual-property "
                    "Sub-items relation"
                )
                return result
            self.client.update_data_source(
                data_source_id,
                _subitems_schema_payload(data_source_id),
            )
            prop_map = self.client.get_property_map(data_source_id)

        missing = [name for name in REQUIRED_PROPERTIES if name not in prop_map]
        if missing:
            if dry_run and set(missing).issubset(set(SCHEMA_EXTENSION_PROPERTIES)):
                result.planned.extend(ENSURED_VIEW_NAMES)
                result.warnings.append(
                    "schema %s would add missing properties: %s" %
                    ("v7", ", ".join(missing))
                )
                return result
            result.failed.append(ViewFailure(
                "schema",
                "missing required properties: %s" % ", ".join(missing),
            ))
            return result

        specs = _build_core_view_specs(database_id, data_source_id, prop_map, today)
        existing_by_name = {
            view.get("name"): view
            for view in self.client.list_views(database_id)
            if view.get("name")
        }

        retired = [name for name in RETIRED_VIEW_NAMES if name in existing_by_name]
        if retired:
            result.warnings.append(
                "no longer managed — delete by hand in Notion if unused: %s" %
                ", ".join(retired)
            )

        for spec in specs:
            existing = existing_by_name.get(spec["name"])
            if existing:
                reasons = _verify_view(existing, spec, prop_map, today)
                if reasons:
                    if dry_run:
                        result.updates_planned.append(spec["name"])
                        result.warnings.append(
                            "%s would update required settings: %s" %
                            (spec["name"], "; ".join(reasons))
                        )
                    else:
                        self._update_view(existing, spec, result, reasons)
                else:
                    result.verified.append(spec["name"])
                continue

            if dry_run:
                result.planned.append(spec["name"])
                continue

            self._create_view(spec, result)

        self._migrate_subitems_to_native(data_source_id, prop_map, result, dry_run)
        return result

    def _migrate_subitems_to_native(self, data_source_id, prop_map, result, dry_run):
        """Copy legacy `Parent Task` links into Notion's native sub-item relation.

        Only the native relation drives nesting, so rows pushed via the legacy
        `Parent Task` relation must be migrated. If the database has no native
        sub-item relation yet, we warn (the user must enable Sub-items in the UI
        once). Best-effort: row-query / PATCH failures degrade to warnings and
        never fail the ensure run.
        """
        native = detect_subitem_relation(prop_map)
        if not native:
            result.warnings.append(
                "native Sub-items not enabled: open the database -> ⋯ -> Sub-items "
                "to turn on nesting, then rerun ensure"
            )
            return

        try:
            rows = self.client.query_data_source_rows(data_source_id)
        except Exception as e:
            result.warnings.append("sub-item migration skipped: %s" % e)
            return

        migrations = _compute_native_migration(rows, native["parent_name"])
        if not migrations:
            return

        by_id = {row["id"]: row for row in rows if row.get("id")}
        parent_prop = native["parent_name"]
        if dry_run:
            for child_id, _merged, added in migrations:
                result.repaired.append(
                    "%s (+%d planned)" % (_row_title(by_id.get(child_id, {})), added)
                )
            return

        for child_id, merged, added in migrations:
            title = _row_title(by_id.get(child_id, {}))
            try:
                self.client.update_page_relation(child_id, parent_prop, merged)
                result.repaired.append("%s (+%d)" % (title, added))
            except Exception as e:
                result.warnings.append("sub-item migration failed for %s: %s" % (title, e))

    def _create_view(self, spec, result):
        payload = _payload_for_spec(spec)
        try:
            self.client.create_view(payload)
            result.created.append(spec["name"])
            return
        except NotionBadRequest as e:
            if spec.get("subtasks"):
                fallback = _payload_for_spec(spec, include_subtasks=False)
                try:
                    self.client.create_view(fallback)
                    result.created.append(spec["name"])
                    result.warnings.append(
                        "%s subtasks not enabled: base table fallback created" %
                        spec["name"]
                    )
                    return
                except Exception as fallback_error:
                    result.failed.append(ViewFailure(spec["name"], str(fallback_error)))
                    return
            if spec.get("relative_today"):
                fallback_spec = dict(spec)
                fallback_spec["filter"] = _fixed_relative_today_filter(
                    spec["today"],
                    spec.get("filter"),
                )
                fallback_spec["relative_today"] = False
                fallback = _payload_for_spec(fallback_spec)
                try:
                    self.client.create_view(fallback)
                    result.created.append(spec["name"])
                    result.warnings.append(
                        "%s relative today filter failed: fixed date fallback created" %
                        spec["name"]
                    )
                    return
                except Exception as fallback_error:
                    result.failed.append(ViewFailure(spec["name"], str(fallback_error)))
                    return
            result.failed.append(ViewFailure(spec["name"], str(e)))
        except Exception as e:
            result.failed.append(ViewFailure(spec["name"], str(e)))

    def _update_view(self, existing, spec, result, reasons):
        view_id = existing.get("id")
        if not view_id:
            result.conflicts.append(ViewConflict(
                spec["name"],
                "missing view id for update: %s" % "; ".join(reasons),
            ))
            return

        payload = _update_payload_for_spec(spec)
        try:
            self.client.update_view(view_id, payload)
            result.updated.append(spec["name"])
            return
        except NotionBadRequest as e:
            if spec.get("subtasks"):
                fallback = _update_payload_for_spec(spec, include_subtasks=False)
                try:
                    self.client.update_view(view_id, fallback)
                    result.updated.append(spec["name"])
                    result.warnings.append(
                        "%s subtasks not enabled: base table fallback updated" %
                        spec["name"]
                    )
                    return
                except Exception as fallback_error:
                    result.failed.append(ViewFailure(spec["name"], str(fallback_error)))
                    return
            if spec.get("relative_today"):
                fallback_spec = dict(spec)
                fallback_spec["filter"] = _fixed_relative_today_filter(
                    spec["today"],
                    spec.get("filter"),
                )
                fallback_spec["relative_today"] = False
                fallback = _update_payload_for_spec(fallback_spec)
                try:
                    self.client.update_view(view_id, fallback)
                    result.updated.append(spec["name"])
                    result.warnings.append(
                        "%s relative today filter failed: fixed date fallback updated" %
                        spec["name"]
                    )
                    return
                except Exception as fallback_error:
                    result.failed.append(ViewFailure(spec["name"], str(fallback_error)))
                    return
            result.failed.append(ViewFailure(spec["name"], str(e)))
        except Exception as e:
            result.failed.append(ViewFailure(spec["name"], str(e)))


def _build_core_view_specs(database_id, data_source_id, prop_map, today):
    # Only Notion's native sub-item relation (UI-created) drives nesting. When it
    # is present, point the hierarchy view's subtasks at its child side; when it
    # is absent the view degrades to a plain table (ensure() warns separately).
    native = detect_subitem_relation(prop_map)
    hierarchy_subtasks = None
    if native and native.get("child_id"):
        hierarchy_subtasks = {
            "property_id": native["child_id"],
            "display_mode": "show",
            "filter_scope": "parents_and_subitems",
            "toggle_column_id": _prop_id(prop_map, "Name"),
        }
    # Hide the legacy Parent Task column only once a native relation supersedes it.
    hierarchy_hidden = ["Depends On", "Sub-items"]
    if native:
        hierarchy_hidden.append("Parent Task")
    # Each view carries at most five columns. Anything a row needs beyond that
    # lives in the page body, and the read-only signals that used to justify
    # their own views (blocked, needs-review, today's priorities) are what
    # `working-diary diary-notion ops` reports.
    return [
        _view_spec(
            "작업 계층",
            database_id,
            data_source_id,
            prop_map,
            visible=["Name", "Status", "Project", "Task Group", "Date"],
            hidden=hierarchy_hidden,
            sorts=[_date_desc_sort()],
            subtasks=hierarchy_subtasks,
        ),
        _view_spec(
            "오늘 작업",
            database_id,
            data_source_id,
            prop_map,
            visible=["Name", "Status", "Priority", "Next Action", "Project"],
            filter_body=_relative_today_filter(),
            sorts=[_priority_asc_sort(), _date_desc_sort()],
            relative_today=True,
            today=today,
        ),
        _view_spec(
            "Blocked",
            database_id,
            data_source_id,
            prop_map,
            visible=["Name", "Priority", "Block Reason", "Next Action", "Project"],
            filter_body=_blocked_filter(),
            sorts=[_priority_asc_sort(), _date_desc_sort()],
        ),
        _view_spec(
            "전날 미완료",
            database_id,
            data_source_id,
            prop_map,
            visible=["Name", "Status", "Priority", "Next Action", "Date"],
            filter_body=_unfinished_before_today_filter(),
            sorts=[_priority_asc_sort(), _date_desc_sort()],
            relative_today=True,
            today=today,
        ),
        _view_spec(
            "작업 그룹별",
            database_id,
            data_source_id,
            prop_map,
            visible=["Name", "Status", "Project", "Date"],
            group_by=_group_by(prop_map, "Task Group"),
            sorts=[_date_desc_sort()],
        ),
    ]


def _view_spec(
    name,
    database_id,
    data_source_id,
    prop_map,
    visible,
    hidden=None,
    filter_body=None,
    sorts=None,
    group_by=None,
    subtasks=None,
    relative_today=False,
    today=None,
):
    return {
        "name": name,
        "database_id": database_id,
        "data_source_id": data_source_id,
        "visible": visible,
        "hidden": hidden or [],
        "properties": _property_config(prop_map, visible, hidden or []),
        "filter": filter_body,
        "sorts": sorts or [],
        "group_by": group_by,
        "subtasks": subtasks,
        "relative_today": relative_today,
        "today": today,
    }


def _payload_for_spec(spec, include_subtasks=True):
    configuration = {
        "type": "table",
        "properties": spec["properties"],
        "wrap_cells": False,
        "frozen_column_index": 1,
        "show_vertical_lines": True,
    }
    if spec.get("group_by"):
        configuration["group_by"] = spec["group_by"]
    if include_subtasks and spec.get("subtasks"):
        configuration["subtasks"] = spec["subtasks"]

    payload = {
        "database_id": spec["database_id"],
        "data_source_id": spec["data_source_id"],
        "name": spec["name"],
        "type": "table",
        "configuration": configuration,
    }
    if spec.get("filter"):
        payload["filter"] = spec["filter"]
    if spec.get("sorts"):
        payload["sorts"] = spec["sorts"]
    return payload


def _update_payload_for_spec(spec, include_subtasks=True):
    payload = _payload_for_spec(spec, include_subtasks=include_subtasks)
    result = {
        "name": payload["name"],
        "configuration": payload["configuration"],
    }
    if payload.get("filter"):
        result["filter"] = payload["filter"]
    if payload.get("sorts"):
        result["sorts"] = payload["sorts"]
    return result


def _property_config(prop_map, visible, hidden=None):
    """Order the view's columns: `visible` first, then everything else hidden.

    Notion leaves any property omitted from this list at whatever visibility it
    already had, so listing only a hand-picked subset let the table widen every
    time the schema gained a column. Enumerating the entire property map pins
    each view to exactly its `visible` columns, now and after future schema
    additions.
    """
    visible_set = set(visible)
    ordered = [
        {"property_id": _prop_id(prop_map, name), "visible": True}
        for name in visible
    ]
    placed = set(visible_set)
    for name in list(hidden or []) + list(HIDDEN_PROPERTIES) + list(prop_map):
        if name in placed or name not in prop_map:
            continue
        placed.add(name)
        ordered.append({"property_id": _prop_id(prop_map, name), "visible": False})
    return ordered


def _prop_id(prop_map, name):
    return prop_map[name]["id"]


def _prop_type(prop_map, name):
    return prop_map[name]["type"]


def _group_by(prop_map, name):
    body = {
        "type": _prop_type(prop_map, name),
        "property_id": _prop_id(prop_map, name),
        "sort": {"type": "manual"},
        "hide_empty_groups": False,
    }
    if body["type"] == "status":
        body["group_by"] = "group"
    if body["type"] == "date":
        body["group_by"] = "day"
    return body


def _date_desc_sort():
    return {"property": "Date", "direction": "descending"}


def _relative_today_filter():
    return {"property": "Date", "date": {"equals": "today"}}


def _fixed_today_filter(today):
    return {"property": "Date", "date": {"equals": today}}


def _fixed_relative_today_filter(today, filter_body=None):
    if not filter_body:
        return _fixed_today_filter(today)
    return _replace_relative_today(filter_body, today)


def _unfinished_before_today_filter():
    return {
        "and": [
            {"property": "Date", "date": {"before": "today"}},
            {"property": "Status", "select": {"does_not_equal": "Deployed"}},
        ]
    }


def _blocked_filter():
    return {"property": "Blocked", "checkbox": {"equals": True}}


def _priority_asc_sort():
    return {"property": "Priority", "direction": "ascending"}


def _verify_view(view, spec, prop_map, today):
    reasons = []
    if view.get("type") != "table":
        reasons.append("view type is not table")

    visible_ids, visible_names, explicitly_visible_ids = _visible_properties(view, prop_map)
    for name in spec["visible"]:
        if name == "Name":
            continue
        if _prop_id(prop_map, name) not in visible_ids and name not in visible_names:
            reasons.append("missing visible property: %s" % name)

    # Every column outside the spec must be hidden. Checking the whole property
    # map (not just a curated list) is what lets `ensure` narrow a table that
    # was already wide before this spec existed.
    spec_visible = set(spec["visible"])
    for name in prop_map:
        if name in spec_visible:
            continue
        prop_id = _prop_id(prop_map, name)
        if prop_id in explicitly_visible_ids or name in visible_names:
            label = "hidden property is visible" if name in HIDDEN_PROPERTIES else "property should be hidden"
            reasons.append("%s: %s" % (label, name))

    if spec["name"] == "오늘 작업":
        if not _has_today_filter(view.get("filter"), prop_map, today):
            reasons.append("missing Date=today filter")
        if not _has_date_desc_sort(view.get("sorts"), prop_map):
            reasons.append("missing Date descending sort")

    if spec["name"] == "Blocked":
        if not _has_checkbox_filter(view.get("filter"), "Blocked", True, prop_map):
            reasons.append("missing Blocked=true filter")

    if spec["name"] == "전날 미완료":
        if not _has_date_before_today_filter(view.get("filter"), prop_map, today):
            reasons.append("missing Date before today filter")
        if not _has_select_filter(view.get("filter"), "Status", "does_not_equal", "Deployed", prop_map):
            reasons.append("missing Status!=Deployed filter")

    if spec.get("group_by"):
        if not _has_group_by(view, spec["group_by"]):
            reasons.append("missing %s group_by" % _group_name(spec["name"]))

    if spec.get("subtasks"):
        if not _has_subtasks(view, spec["subtasks"]):
            reasons.append("missing required subtasks configuration")

    return reasons


def _visible_properties(view, prop_map):
    config = view.get("configuration") or {}
    visible_ids = set()
    visible_names = set()
    explicitly_visible_ids = set()
    for entry in config.get("properties") or []:
        prop = entry.get("property_id")
        if not prop:
            continue
        is_visible = entry.get("visible") is not False
        if is_visible:
            visible_ids.add(prop)
            visible_names.add(entry.get("property_name") or prop)
            explicitly_visible_ids.add(prop)
    return visible_ids, visible_names, explicitly_visible_ids


def _has_today_filter(filter_body, prop_map, today):
    date_names = {"Date", _prop_id(prop_map, "Date")}
    for node in _walk(filter_body):
        if not isinstance(node, dict):
            continue
        if (node.get("property") or node.get("property_id")) not in date_names:
            continue
        date_filter = node.get("date") or {}
        equals = date_filter.get("equals")
        if equals == "today" or equals == today:
            return True
    return False


def _has_date_before_today_filter(filter_body, prop_map, today):
    date_names = {"Date", _prop_id(prop_map, "Date")}
    for node in _walk(filter_body):
        if not isinstance(node, dict):
            continue
        if (node.get("property") or node.get("property_id")) not in date_names:
            continue
        date_filter = node.get("date") or {}
        before = date_filter.get("before")
        if before == "today" or before == today:
            return True
    return False


def _has_date_desc_sort(sorts, prop_map):
    date_keys = {"Date", _prop_id(prop_map, "Date")}
    for sort in sorts or []:
        prop = sort.get("property") or sort.get("property_id")
        if prop in date_keys and sort.get("direction") == "descending":
            return True
    return False


def _has_filter_property(filter_body, name, prop_map):
    keys = {name, _prop_id(prop_map, name)}
    for node in _walk(filter_body):
        if isinstance(node, dict) and (node.get("property") or node.get("property_id")) in keys:
            return True
    return False


def _has_checkbox_filter(filter_body, name, expected, prop_map):
    keys = {name, _prop_id(prop_map, name)}
    for node in _walk(filter_body):
        if not isinstance(node, dict):
            continue
        if (node.get("property") or node.get("property_id")) not in keys:
            continue
        checkbox = node.get("checkbox") or {}
        if checkbox.get("equals") is expected:
            return True
    return False


def _has_select_filter(filter_body, name, op, expected, prop_map):
    keys = {name, _prop_id(prop_map, name)}
    for node in _walk(filter_body):
        if not isinstance(node, dict):
            continue
        if (node.get("property") or node.get("property_id")) not in keys:
            continue
        select_filter = node.get("select") or {}
        if select_filter.get(op) == expected:
            return True
    return False


def _has_group_by(view, required):
    config = view.get("configuration") or {}
    group_by = config.get("group_by") or {}
    return (
        group_by.get("property_id") == required.get("property_id")
        and group_by.get("type") == required.get("type")
    )


def _has_subtasks(view, required):
    config = view.get("configuration") or {}
    subtasks = config.get("subtasks") or {}
    return (
        subtasks.get("property_id") == required.get("property_id")
        and subtasks.get("display_mode") == required.get("display_mode")
        and subtasks.get("filter_scope") == required.get("filter_scope")
        and subtasks.get("toggle_column_id") == required.get("toggle_column_id")
    )


def _group_name(view_name):
    if view_name == "작업 그룹별":
        return "Task Group"
    return "required"


def _relation_ids(row, property_name):
    prop = (row.get("properties") or {}).get(property_name) or {}
    return [item.get("id") for item in (prop.get("relation") or []) if item.get("id")]


def _row_title(row):
    arr = ((row.get("properties") or {}).get("Name") or {}).get("title") or []
    return "".join(part.get("plain_text", "") for part in arr)


def _compute_native_migration(rows, native_parent_name):
    """Compute legacy→native parent migrations.

    Each child's legacy `Parent Task` link must be mirrored into the native
    sub-item parent property (`native_parent_name`) so Notion renders nesting.
    Returns [(child_id, merged_parent_ids, added_count)] for rows whose native
    parent relation is missing one or more legacy links. Rows already migrated
    (or pushed straight to the native relation) yield nothing — idempotent.
    """
    by_id = {row["id"]: row for row in rows if row.get("id")}
    migrations = []
    for row in rows:
        rid = row.get("id")
        legacy = [p for p in _relation_ids(row, "Parent Task") if p != rid and p in by_id]
        if not legacy:
            continue
        current = _relation_ids(row, native_parent_name)
        current_set = set(current)
        added = [pid for pid in dict.fromkeys(legacy) if pid not in current_set]
        if added:
            migrations.append((rid, current + added, len(added)))
    return migrations


def _needs_subitems_schema(prop_map):
    parent = prop_map.get("Parent Task")
    if not parent:
        return False
    subitems = prop_map.get("Sub-items")
    relation = parent.get("relation") or {}
    dual = relation.get("dual_property") or {}
    return not subitems or dual.get("synced_property_name") != "Sub-items"


def _subitems_schema_payload(data_source_id):
    return {
        "properties": {
            "Parent Task": {
                "relation": {
                    "data_source_id": data_source_id,
                    "dual_property": {
                        "synced_property_name": "Sub-items",
                    },
                }
            }
        }
    }


def _replace_relative_today(value, today):
    if isinstance(value, dict):
        result = {}
        for key, child in value.items():
            if key == "date" and isinstance(child, dict):
                date_filter = dict(child)
                for op in ("equals", "before", "after", "on_or_before", "on_or_after"):
                    if date_filter.get(op) == "today":
                        date_filter[op] = today
                result[key] = date_filter
                continue
            result[key] = _replace_relative_today(child, today)
        return result
    if isinstance(value, list):
        return [_replace_relative_today(child, today) for child in value]
    return value


def _walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            for item in _walk(child):
                yield item
    elif isinstance(value, list):
        for child in value:
            for item in _walk(child):
                yield item


def _infer_property_type(prop):
    for key in (
        "title", "rich_text", "number", "select", "multi_select", "date",
        "relation", "status", "checkbox",
    ):
        if key in prop:
            return key
    return "unknown"


