"""Tests for Notion Views API client and core view automation."""

from unittest.mock import MagicMock, patch

import pytest

from claude_diary.exporters.notion_hierarchical import NotionBadRequest
from claude_diary.exporters.notion_views import (
    CORE_VIEW_NAMES,
    NOTION_VIEWS_API_VERSION,
    CoreViewsEnsurer,
    NotionViewsClient,
    _build_core_view_specs,
    _payload_for_spec,
)


def _make_response(status, json_body=None, headers=None):
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = json_body or {}
    resp.headers = headers or {}
    resp.text = "<error body>"
    return resp


def _patch_requests(mock_requests):
    return patch.dict("sys.modules", {"requests": mock_requests})


def _prop_map():
    return {
        "Name": {"id": "title", "type": "title"},
        "Date": {"id": "date_id", "type": "date"},
        "Work Period": {"id": "work_period_id", "type": "date"},
        "Project": {"id": "project_id", "type": "select"},
        "Purpose": {"id": "purpose_id", "type": "select"},
        "Status": {"id": "status_id", "type": "select"},
        "Task Group": {"id": "task_group_id", "type": "select"},
        "Parent Task": {"id": "parent_id", "type": "relation"},
        "Depends On": {"id": "depends_id", "type": "relation"},
        "Session ID": {"id": "session_id", "type": "rich_text"},
        "Task Index": {"id": "task_index_id", "type": "number"},
        "Files": {"id": "files_id", "type": "number"},
        "Commits": {"id": "commits_id", "type": "number"},
        "Lines": {"id": "lines_id", "type": "number"},
        "Categories": {"id": "categories_id", "type": "multi_select"},
        "Branch": {"id": "branch_id", "type": "select"},
    }


def _matching_views(database_id="db1", data_source_id="ds1", today="2026-06-02"):
    specs = _build_core_view_specs(database_id, data_source_id, _prop_map(), today)
    views = []
    for spec in specs:
        payload = _payload_for_spec(spec)
        views.append({
            "id": "%s_id" % spec["name"],
            "name": spec["name"],
            "type": payload["type"],
            "filter": payload.get("filter"),
            "sorts": payload.get("sorts"),
            "configuration": payload["configuration"],
        })
    return views


class FakeViewsClient:
    def __init__(self, views=None, prop_map=None):
        self.views = views if views is not None else []
        self.prop_map = prop_map if prop_map is not None else _prop_map()
        self.created_payloads = []

    def get_primary_data_source_id(self, database_id):
        return "ds1"

    def get_property_map(self, data_source_id):
        return self.prop_map

    def list_views(self, database_id):
        return self.views

    def create_view(self, payload):
        self.created_payloads.append(payload)
        return {"id": "created_%d" % len(self.created_payloads)}


class TestNotionViewsClient:
    def test_uses_views_api_version_header(self):
        mock_req = MagicMock()
        mock_req.request.return_value = _make_response(200, {"id": "view1"})
        with _patch_requests(mock_req):
            client = NotionViewsClient({"api_token": "secret_xxx"})
            client.retrieve_view("view1")

        headers = mock_req.request.call_args.kwargs["headers"]
        assert headers["Notion-Version"] == NOTION_VIEWS_API_VERSION

    def test_get_primary_data_source_id_from_database(self):
        client = NotionViewsClient({"api_token": "secret_xxx"})
        with patch.object(client, "retrieve_database", return_value={
            "data_sources": [{"id": "ds1", "name": "Entries"}],
        }):
            assert client.get_primary_data_source_id("db1") == "ds1"

    def test_property_map_uses_data_source_property_ids(self):
        client = NotionViewsClient({"api_token": "secret_xxx"})
        with patch.object(client, "retrieve_data_source", return_value={
            "properties": {
                "Name": {"id": "title", "type": "title"},
                "Status": {"id": "abc", "type": "select"},
                "Date": {"id": "yo%7DQ", "type": "date"},
            }
        }):
            prop_map = client.get_property_map("ds1")
        assert prop_map["Name"] == {"id": "title", "type": "title"}
        assert prop_map["Status"] == {"id": "abc", "type": "select"}
        assert prop_map["Date"] == {"id": "yo}Q", "type": "date"}


class TestCoreViewsEnsurer:
    def test_creates_all_missing_core_views(self):
        client = FakeViewsClient()
        result = CoreViewsEnsurer(client).ensure("db1", "2026-06-02")

        assert result.created == list(CORE_VIEW_NAMES)
        assert result.ok()
        assert len(client.created_payloads) == 5

        by_name = {payload["name"]: payload for payload in client.created_payloads}
        hierarchy = by_name["작업 계층"]
        hierarchy_config = hierarchy["configuration"]
        assert hierarchy_config["subtasks"]["property_id"] == "parent_id"
        assert _visible(hierarchy, "parent_id") is True
        assert _visible(hierarchy, "work_period_id") is True
        assert _visible(hierarchy, "session_id") is False

        today = by_name["오늘 작업"]
        assert today["filter"] == {"property": "Date", "date": {"equals": "today"}}
        assert today["sorts"] == [{"property": "Date", "direction": "descending"}]

        assert by_name["상태별"]["configuration"]["group_by"]["property_id"] == "status_id"
        assert by_name["목적별"]["configuration"]["group_by"]["property_id"] == "purpose_id"
        assert by_name["프로젝트별"]["configuration"]["group_by"]["property_id"] == "project_id"

    def test_verifies_existing_matching_views(self):
        client = FakeViewsClient(views=_matching_views())
        result = CoreViewsEnsurer(client).ensure("db1", "2026-06-02")

        assert result.verified == list(CORE_VIEW_NAMES)
        assert result.ok()
        assert client.created_payloads == []

    def test_dry_run_plans_missing_views_without_create(self):
        client = FakeViewsClient()
        result = CoreViewsEnsurer(client).ensure("db1", "2026-06-02", dry_run=True)

        assert result.planned == list(CORE_VIEW_NAMES)
        assert result.ok()
        assert client.created_payloads == []

    def test_existing_view_with_required_mismatch_is_conflict(self):
        views = _matching_views()
        for view in views:
            if view["name"] == "오늘 작업":
                view["filter"] = None

        client = FakeViewsClient(views=views)
        result = CoreViewsEnsurer(client).ensure("db1", "2026-06-02")

        assert not result.ok()
        assert len(result.conflicts) == 1
        assert result.conflicts[0].name == "오늘 작업"
        assert "Date=today" in result.conflicts[0].reason

    def test_missing_required_property_fails_before_create(self):
        prop_map = dict(_prop_map())
        prop_map.pop("Work Period")
        client = FakeViewsClient(prop_map=prop_map)

        result = CoreViewsEnsurer(client).ensure("db1", "2026-06-02")

        assert not result.ok()
        assert result.failed[0].name == "schema"
        assert "Work Period" in result.failed[0].reason
        assert client.created_payloads == []

    def test_dry_run_plans_schema_extension_when_work_period_missing(self):
        prop_map = dict(_prop_map())
        prop_map.pop("Work Period")
        client = FakeViewsClient(prop_map=prop_map)

        result = CoreViewsEnsurer(client).ensure("db1", "2026-06-02", dry_run=True)

        assert result.ok()
        assert result.planned == list(CORE_VIEW_NAMES)
        assert any("Work Period" in w for w in result.warnings)
        assert client.created_payloads == []

    def test_today_relative_filter_falls_back_to_fixed_date(self):
        views = [v for v in _matching_views() if v["name"] != "오늘 작업"]
        client = FailingCreateClient(
            views=views,
            fail_when=lambda payload: (
                payload["name"] == "오늘 작업"
                and payload.get("filter", {}).get("date", {}).get("equals") == "today"
            ),
        )

        result = CoreViewsEnsurer(client).ensure("db1", "2026-06-02")

        assert result.ok()
        assert result.created == ["오늘 작업"]
        assert client.created_payloads[-1]["filter"] == {
            "property": "Date",
            "date": {"equals": "2026-06-02"},
        }
        assert any("relative today filter failed" in w for w in result.warnings)

    def test_subtasks_failure_falls_back_to_base_table(self):
        views = [v for v in _matching_views() if v["name"] != "작업 계층"]
        client = FailingCreateClient(
            views=views,
            fail_when=lambda payload: (
                payload["name"] == "작업 계층"
                and "subtasks" in payload.get("configuration", {})
            ),
        )

        result = CoreViewsEnsurer(client).ensure("db1", "2026-06-02")

        assert result.ok()
        assert result.created == ["작업 계층"]
        assert "subtasks" not in client.created_payloads[-1]["configuration"]
        assert any("subtasks not enabled" in w for w in result.warnings)


class FailingCreateClient(FakeViewsClient):
    def __init__(self, views, fail_when):
        super().__init__(views=views)
        self.fail_when = fail_when

    def create_view(self, payload):
        self.created_payloads.append(payload)
        if self.fail_when(payload):
            raise NotionBadRequest("rejected")
        return {"id": "created_%d" % len(self.created_payloads)}


def _visible(payload, property_id):
    for entry in payload["configuration"]["properties"]:
        if entry["property_id"] == property_id:
            return entry["visible"]
    return None
