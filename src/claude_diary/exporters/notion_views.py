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
)


NOTION_VIEWS_API_VERSION = "2025-09-03"
CORE_VIEW_NAMES = ("작업 계층", "오늘 작업", "상태별", "목적별", "프로젝트별")

REQUIRED_PROPERTIES = (
    "Name",
    "Date",
    "Work Period",
    "Project",
    "Purpose",
    "Status",
    "Task Group",
    "Parent Task",
    "Depends On",
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
    "Work Period",
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
    verified: list = field(default_factory=list)
    planned: list = field(default_factory=list)
    conflicts: list = field(default_factory=list)
    failed: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

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
            )

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
                raise RuntimeError("Notion Views API network error: %s" % e)

            status = resp.status_code
            if status in (200, 201):
                return resp.json()

            if status == 401 or status == 403:
                raise NotionAuthError(
                    "Notion Views API %d: %s" % (status, _short_error(resp))
                )
            if status == 404:
                raise NotionNotFound(
                    "Notion Views API 404: %s" % _short_error(resp)
                )
            if status == 400:
                raise NotionBadRequest(
                    "Notion Views API 400: %s" % _short_error(resp)
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
                    (status, MAX_RETRIES, _short_error(resp))
                )

            raise RuntimeError(
                "Notion Views API unexpected status %d: %s" %
                (status, _short_error(resp))
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


class CoreViewsEnsurer:
    """Create or verify the 5 permanent core views for the working diary DB."""

    def __init__(self, client):
        self.client = client

    def ensure(self, database_id, today, dry_run=False):
        result = EnsureViewsResult()
        data_source_id = self.client.get_primary_data_source_id(database_id)
        prop_map = self.client.get_property_map(data_source_id)
        missing = [name for name in REQUIRED_PROPERTIES if name not in prop_map]
        if missing:
            if dry_run and set(missing).issubset(set(SCHEMA_EXTENSION_PROPERTIES)):
                result.planned.extend(CORE_VIEW_NAMES)
                result.warnings.append(
                    "schema %s would add missing properties: %s" %
                    ("v5", ", ".join(missing))
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

        for spec in specs:
            existing = existing_by_name.get(spec["name"])
            if existing:
                reasons = _verify_view(existing, spec, prop_map, today)
                if reasons:
                    result.conflicts.append(ViewConflict(spec["name"], "; ".join(reasons)))
                else:
                    result.verified.append(spec["name"])
                continue

            if dry_run:
                result.planned.append(spec["name"])
                continue

            self._create_view(spec, result)

        return result

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
                fallback_spec["filter"] = _fixed_today_filter(spec["today"])
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


def _build_core_view_specs(database_id, data_source_id, prop_map, today):
    return [
        _view_spec(
            "작업 계층",
            database_id,
            data_source_id,
            prop_map,
            visible=[
                "Name", "Status", "Project", "Purpose", "Task Group",
                "Parent Task", "Depends On", "Work Period", "Date",
            ],
            sorts=[_date_desc_sort()],
            subtasks={
                "property_id": _prop_id(prop_map, "Parent Task"),
                "display_mode": "show",
                "filter_scope": "parents_and_subitems",
                "toggle_column_id": _prop_id(prop_map, "Name"),
            },
        ),
        _view_spec(
            "오늘 작업",
            database_id,
            data_source_id,
            prop_map,
            visible=[
                "Name", "Status", "Project", "Purpose", "Task Group",
                "Work Period", "Parent Task", "Depends On",
            ],
            filter_body=_relative_today_filter(),
            sorts=[_date_desc_sort()],
            relative_today=True,
            today=today,
        ),
        _view_spec(
            "상태별",
            database_id,
            data_source_id,
            prop_map,
            visible=["Name", "Project", "Purpose", "Task Group", "Parent Task", "Work Period", "Date"],
            group_by=_group_by(prop_map, "Status"),
        ),
        _view_spec(
            "목적별",
            database_id,
            data_source_id,
            prop_map,
            visible=["Name", "Status", "Project", "Task Group", "Work Period", "Date"],
            group_by=_group_by(prop_map, "Purpose"),
        ),
        _view_spec(
            "프로젝트별",
            database_id,
            data_source_id,
            prop_map,
            visible=["Name", "Status", "Purpose", "Task Group", "Parent Task", "Work Period", "Date"],
            group_by=_group_by(prop_map, "Project"),
        ),
    ]


def _view_spec(
    name,
    database_id,
    data_source_id,
    prop_map,
    visible,
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
        "properties": _property_config(prop_map, visible),
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


def _property_config(prop_map, visible):
    visible_set = set(visible)
    ordered = []
    for name in visible:
        ordered.append({"property_id": _prop_id(prop_map, name), "visible": True})
    for name in HIDDEN_PROPERTIES:
        ordered.append({"property_id": _prop_id(prop_map, name), "visible": False})
    for name in ("Files", "Commits", "Lines", "Categories", "Branch"):
        if name in prop_map and name not in visible_set:
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

    for name in HIDDEN_PROPERTIES:
        prop_id = _prop_id(prop_map, name)
        if prop_id in explicitly_visible_ids or name in visible_names:
            reasons.append("hidden property is visible: %s" % name)

    if spec["name"] == "오늘 작업":
        if not _has_today_filter(view.get("filter"), prop_map, today):
            reasons.append("missing Date=today filter")
        if not _has_date_desc_sort(view.get("sorts"), prop_map):
            reasons.append("missing Date descending sort")

    if spec.get("group_by"):
        if not _has_group_by(view, spec["group_by"]):
            reasons.append("missing %s group_by" % _group_name(spec["name"]))

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
            visible_names.add(prop)
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


def _has_date_desc_sort(sorts, prop_map):
    date_keys = {"Date", _prop_id(prop_map, "Date")}
    for sort in sorts or []:
        prop = sort.get("property") or sort.get("property_id")
        if prop in date_keys and sort.get("direction") == "descending":
            return True
    return False


def _has_group_by(view, required):
    config = view.get("configuration") or {}
    group_by = config.get("group_by") or {}
    return (
        group_by.get("property_id") == required.get("property_id")
        and group_by.get("type") == required.get("type")
    )


def _group_name(view_name):
    if view_name == "상태별":
        return "Status"
    if view_name == "목적별":
        return "Purpose"
    if view_name == "프로젝트별":
        return "Project"
    return "required"


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


def _short_error(resp):
    try:
        data = resp.json()
        return data.get("message") or data.get("code") or resp.text[:200]
    except Exception:
        return resp.text[:200]
