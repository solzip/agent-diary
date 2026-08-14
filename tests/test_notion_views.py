"""Tests for Notion Views API client and core view automation."""

from unittest.mock import MagicMock, patch


from claude_diary.exporters.notion_hierarchical import NotionBadRequest
from claude_diary.exporters.notion_views import (
    NOTION_VIEWS_API_VERSION,
    CoreViewsEnsurer,
    NotionViewsClient,
    _build_core_view_specs,
    _compute_native_migration,
    _payload_for_spec,
    _update_payload_for_spec,
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
        "Parent Task": {
            "id": "parent_id",
            "type": "relation",
            "relation": {
                "dual_property": {
                    "synced_property_name": "Sub-items",
                    "synced_property_id": "subitems_id",
                }
            },
        },
        "Sub-items": {
            "id": "subitems_id",
            "type": "relation",
            "relation": {
                "dual_property": {
                    "synced_property_name": "Parent Task",
                    "synced_property_id": "parent_id",
                }
            },
        },
        # Notion's native sub-item relation (UI-created, locale-named). This is
        # the pair that actually drives nesting and that detection must find.
        "Parent item": {
            "id": "parent_item_id",
            "type": "relation",
            "relation": {
                "type": "dual_property",
                "dual_property": {
                    "synced_property_name": "Sub-item",
                    "synced_property_id": "sub_item_id",
                },
            },
        },
        "Sub-item": {
            "id": "sub_item_id",
            "type": "relation",
            "relation": {
                "type": "dual_property",
                "dual_property": {
                    "synced_property_name": "Parent item",
                    "synced_property_id": "parent_item_id",
                },
            },
        },
        "Depends On": {"id": "depends_id", "type": "relation"},
        "Priority": {"id": "priority_id", "type": "select"},
        "Next Action": {"id": "next_action_id", "type": "rich_text"},
        "Blocked": {"id": "blocked_id", "type": "checkbox"},
        "Block Reason": {"id": "block_reason_id", "type": "rich_text"},
        "Carryover": {"id": "carryover_id", "type": "checkbox"},
        "Review Status": {"id": "review_status_id", "type": "select"},
        "Last Reviewed": {"id": "last_reviewed_id", "type": "date"},
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
    def __init__(self, views=None, prop_map=None, rows=None):
        self.views = views if views is not None else []
        self.prop_map = prop_map if prop_map is not None else _prop_map()
        self.rows = rows if rows is not None else []
        self.created_payloads = []
        self.updated_payloads = []
        self.updated_data_sources = []
        self.relation_updates = []

    def get_primary_data_source_id(self, database_id):
        return "ds1"

    def query_data_source_rows(self, data_source_id):
        return self.rows

    def update_page_relation(self, page_id, property_name, target_ids):
        self.relation_updates.append((page_id, property_name, list(target_ids)))
        return {"id": page_id}

    def get_property_map(self, data_source_id):
        return self.prop_map

    def list_views(self, database_id):
        return self.views

    def create_view(self, payload):
        self.created_payloads.append(payload)
        return {"id": "created_%d" % len(self.created_payloads)}

    def update_view(self, view_id, payload):
        self.updated_payloads.append((view_id, payload))
        return {"id": view_id}

    def update_data_source(self, data_source_id, payload):
        self.updated_data_sources.append((data_source_id, payload))
        self.prop_map["Parent Task"] = {
            "id": "parent_id",
            "type": "relation",
            "relation": {
                "dual_property": {
                    "synced_property_name": "Sub-items",
                    "synced_property_id": "subitems_id",
                }
            },
        }
        self.prop_map["Sub-items"] = {
            "id": "subitems_id",
            "type": "relation",
            "relation": {
                "dual_property": {
                    "synced_property_name": "Parent Task",
                    "synced_property_id": "parent_id",
                }
            },
        }
        return {"id": data_source_id}


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
        assert prop_map["Name"] == {"id": "title", "type": "title", "relation": None}
        assert prop_map["Status"] == {"id": "abc", "type": "select", "relation": None}
        assert prop_map["Date"] == {"id": "yo}Q", "type": "date", "relation": None}


class TestCoreViewsEnsurer:
    def test_creates_all_missing_core_views(self):
        client = FakeViewsClient()
        result = CoreViewsEnsurer(client).ensure("db1", "2026-06-02")

        from claude_diary.exporters.notion_views import ENSURED_VIEW_NAMES
        assert result.created == list(ENSURED_VIEW_NAMES)
        assert result.ok()
        assert len(client.created_payloads) == 5

        by_name = {payload["name"]: payload for payload in client.created_payloads}
        hierarchy = by_name["작업 계층"]
        hierarchy_config = hierarchy["configuration"]
        # subtasks must point at the NATIVE child relation, not the legacy one
        assert hierarchy_config["subtasks"]["property_id"] == "sub_item_id"
        assert _visible(hierarchy, "parent_id") is False       # legacy Parent Task hidden
        assert _visible(hierarchy, "subitems_id") is False     # legacy Sub-items hidden
        assert _visible(hierarchy, "depends_id") is False
        assert _visible(hierarchy, "session_id") is False
        # Off-spec columns are hidden even though the spec never names them.
        assert _visible(hierarchy, "work_period_id") is False
        assert _visible(hierarchy, "review_status_id") is False
        assert _visible(hierarchy, "carryover_id") is False

        today = by_name["오늘 작업"]
        assert today["filter"] == {"property": "Date", "date": {"equals": "today"}}
        assert today["sorts"] == [
            {"property": "Priority", "direction": "ascending"},
            {"property": "Date", "direction": "descending"},
            {"property": "Task Index", "direction": "ascending"},
        ]

        assert by_name["Blocked"]["filter"] == {
            "property": "Blocked",
            "checkbox": {"equals": True},
        }
        assert by_name["작업 그룹별"]["configuration"]["group_by"]["property_id"] == "task_group_id"
        assert by_name["전날 미완료"]["filter"]["and"][0] == {
            "property": "Date",
            "date": {"before": "today"},
        }

    def test_every_view_is_capped_at_five_columns(self):
        specs = _build_core_view_specs("db1", "ds1", _prop_map(), "2026-06-02")
        for spec in specs:
            assert len(spec["visible"]) <= 5, spec["name"]

    def test_every_view_tie_breaks_on_work_order(self):
        # All rows from one push share a Date, so without this the order within
        # a day is arbitrary.
        specs = _build_core_view_specs("db1", "ds1", _prop_map(), "2026-06-02")
        for spec in specs:
            assert spec["sorts"][-1] == {
                "property": "Task Index", "direction": "ascending",
            }, spec["name"]

    def test_existing_view_without_the_tie_break_is_repaired(self):
        views = _matching_views()
        for view in views:
            view["sorts"] = [s for s in view["sorts"] if s["property"] != "Task Index"]

        from claude_diary.exporters.notion_views import ENSURED_VIEW_NAMES
        client = FakeViewsClient(views=views)
        result = CoreViewsEnsurer(client).ensure("db1", "2026-06-02")

        assert result.ok()
        assert sorted(result.updated) == sorted(ENSURED_VIEW_NAMES)

    def test_retired_views_are_reported_not_deleted(self):
        stale = _matching_views() + [{"id": "old", "name": "리뷰 필요", "type": "table"}]
        client = FakeViewsClient(views=stale)
        result = CoreViewsEnsurer(client).ensure("db1", "2026-06-02")

        assert client.created_payloads == []
        assert any("리뷰 필요" in w for w in result.warnings)

    def test_verifies_existing_matching_views(self):
        client = FakeViewsClient(views=_matching_views())
        result = CoreViewsEnsurer(client).ensure("db1", "2026-06-02")

        from claude_diary.exporters.notion_views import ENSURED_VIEW_NAMES
        assert result.verified == list(ENSURED_VIEW_NAMES)
        assert result.ok()
        assert client.created_payloads == []

    def test_dry_run_plans_missing_views_without_create(self):
        client = FakeViewsClient()
        result = CoreViewsEnsurer(client).ensure("db1", "2026-06-02", dry_run=True)

        from claude_diary.exporters.notion_views import ENSURED_VIEW_NAMES
        assert result.planned == list(ENSURED_VIEW_NAMES)
        assert result.ok()
        assert client.created_payloads == []

    def test_converts_parent_task_to_dual_subitems_schema(self):
        prop_map = dict(_prop_map())
        prop_map.pop("Sub-items")
        prop_map["Parent Task"] = {
            "id": "parent_id",
            "type": "relation",
            "relation": {"single_property": {}},
        }
        client = FakeViewsClient(prop_map=prop_map)

        result = CoreViewsEnsurer(client).ensure("db1", "2026-06-02")

        assert result.ok()
        assert client.updated_data_sources == [
            (
                "ds1",
                {
                    "properties": {
                        "Parent Task": {
                            "relation": {
                                "data_source_id": "ds1",
                                "dual_property": {
                                    "synced_property_name": "Sub-items",
                                },
                            }
                        }
                    }
                },
            )
        ]
        from claude_diary.exporters.notion_views import ENSURED_VIEW_NAMES
        assert result.created == list(ENSURED_VIEW_NAMES)

    def test_dry_run_plans_subitems_schema_conversion(self):
        prop_map = dict(_prop_map())
        prop_map.pop("Sub-items")
        prop_map["Parent Task"] = {
            "id": "parent_id",
            "type": "relation",
            "relation": {"single_property": {}},
        }
        client = FakeViewsClient(prop_map=prop_map)

        result = CoreViewsEnsurer(client).ensure("db1", "2026-06-02", dry_run=True)

        assert result.ok()
        assert result.updates_planned == ["작업 계층"]
        assert client.updated_data_sources == []
        assert any("Sub-items" in warning for warning in result.warnings)

    def test_existing_view_with_required_mismatch_is_updated(self):
        views = _matching_views()
        for view in views:
            if view["name"] == "오늘 작업":
                view["filter"] = None

        client = FakeViewsClient(views=views)
        result = CoreViewsEnsurer(client).ensure("db1", "2026-06-02")

        assert result.ok()
        assert result.updated == ["오늘 작업"]
        assert len(client.updated_payloads) == 1
        view_id, payload = client.updated_payloads[0]
        assert view_id == "오늘 작업_id"
        assert payload["filter"] == {"property": "Date", "date": {"equals": "today"}}
        assert payload["sorts"] == [
            {"property": "Priority", "direction": "ascending"},
            {"property": "Date", "direction": "descending"},
            {"property": "Task Index", "direction": "ascending"},
        ]

    def test_dry_run_plans_required_mismatch_update(self):
        views = _matching_views()
        for view in views:
            if view["name"] == "작업 계층":
                for entry in view["configuration"]["properties"]:
                    if entry["property_id"] == "depends_id":
                        entry["visible"] = True

        client = FakeViewsClient(views=views)
        result = CoreViewsEnsurer(client).ensure("db1", "2026-06-02", dry_run=True)

        assert result.ok()
        assert result.updates_planned == ["작업 계층"]
        assert client.updated_payloads == []
        assert any("Depends On" in warning for warning in result.warnings)

    def test_existing_hierarchy_view_with_parent_task_subtasks_is_updated(self):
        views = _matching_views()
        for view in views:
            if view["name"] == "작업 계층":
                view["configuration"]["subtasks"]["property_id"] = "parent_id"

        client = FakeViewsClient(views=views)
        result = CoreViewsEnsurer(client).ensure("db1", "2026-06-02")

        assert result.ok()
        assert result.updated == ["작업 계층"]
        view_id, payload = client.updated_payloads[0]
        assert view_id == "작업 계층_id"
        # corrected to the NATIVE child relation, not the legacy Sub-items
        assert payload["configuration"]["subtasks"]["property_id"] == "sub_item_id"

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
        from claude_diary.exporters.notion_views import ENSURED_VIEW_NAMES
        assert result.planned == list(ENSURED_VIEW_NAMES)
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

    def test_carryover_relative_filter_fallback_keeps_status_filter(self):
        views = [v for v in _matching_views() if v["name"] != "전날 미완료"]
        client = FailingCreateClient(
            views=views,
            fail_when=lambda payload: (
                payload["name"] == "전날 미완료"
                and payload.get("filter", {}).get("and", [{}])[0].get("date", {}).get("before") == "today"
            ),
        )

        result = CoreViewsEnsurer(client).ensure("db1", "2026-06-02")

        assert result.ok()
        assert result.created == ["전날 미완료"]
        assert client.created_payloads[-1]["filter"] == {
            "and": [
                {"property": "Date", "date": {"before": "2026-06-02"}},
                {"property": "Status", "select": {"does_not_equal": "Deployed"}},
            ]
        }
        assert any("relative today filter failed" in w for w in result.warnings)

    def test_update_payload_omits_empty_filter_and_sorts(self):
        from claude_diary.exporters.notion_views import _view_spec
        spec = _view_spec("컬럼만", "db1", "ds1", _prop_map(), visible=["Name", "Status"])
        payload = _update_payload_for_spec(spec)

        assert payload["name"] == "컬럼만"
        assert "configuration" in payload
        assert "filter" not in payload
        assert "sorts" not in payload

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


def _row(rid, title="t", parent_task=None, native_parent=None):
    props = {"Name": {"title": [{"plain_text": title}]}}
    if parent_task is not None:
        props["Parent Task"] = {"relation": [{"id": parent_task}]}
    if native_parent is not None:
        props["Parent item"] = {"relation": [{"id": native_parent}]}
    return {"id": rid, "properties": props}


class TestComputeNativeMigration:
    def test_legacy_parent_migrated_to_native(self):
        rows = [
            _row("p", "parent"),
            _row("c1", "child1", parent_task="p"),
            _row("c2", "child2", parent_task="p"),
        ]
        m = _compute_native_migration(rows, "Parent item")
        assert len(m) == 2
        by_child = {cid: (merged, added) for cid, merged, added in m}
        assert by_child["c1"] == (["p"], 1)
        assert by_child["c2"] == (["p"], 1)

    def test_already_native_needs_no_migration(self):
        rows = [
            _row("p", "parent"),
            _row("c1", "child1", parent_task="p", native_parent="p"),
        ]
        assert _compute_native_migration(rows, "Parent item") == []

    def test_row_pushed_straight_to_native_is_skipped(self):
        rows = [_row("p", "parent"), _row("c1", "child1", native_parent="p")]
        assert _compute_native_migration(rows, "Parent item") == []

    def test_self_reference_ignored(self):
        rows = [_row("p", "parent", parent_task="p")]
        assert _compute_native_migration(rows, "Parent item") == []

    def test_dangling_parent_ignored(self):
        rows = [_row("c1", "child1", parent_task="ghost")]
        assert _compute_native_migration(rows, "Parent item") == []


class TestEnsureMigratesSubitems:
    def _seed(self):
        return [
            _row("p", "parent"),
            _row("c1", "child1", parent_task="p"),
            _row("c2", "child2", parent_task="p"),
        ]

    def test_ensure_migrates_legacy_to_native(self):
        client = FakeViewsClient(views=_matching_views(), rows=self._seed())
        result = CoreViewsEnsurer(client).ensure("db1", "2026-06-02")
        assert result.ok()
        assert len(client.relation_updates) == 2
        for _page_id, prop, ids in client.relation_updates:
            assert prop == "Parent item"  # native parent side
            assert ids == ["p"]
        assert {pid for pid, _, _ in client.relation_updates} == {"c1", "c2"}

    def test_dry_run_reports_but_does_not_patch(self):
        client = FakeViewsClient(views=_matching_views(), rows=self._seed())
        result = CoreViewsEnsurer(client).ensure("db1", "2026-06-02", dry_run=True)
        assert client.relation_updates == []
        assert any("planned" in entry for entry in result.repaired)

    def test_no_rows_no_migration(self):
        client = FakeViewsClient(views=_matching_views(), rows=[])
        result = CoreViewsEnsurer(client).ensure("db1", "2026-06-02")
        assert result.repaired == []
        assert client.relation_updates == []

    def test_native_missing_warns_and_skips(self):
        pm = _prop_map()
        del pm["Parent item"]
        del pm["Sub-item"]
        client = FakeViewsClient(prop_map=pm, rows=self._seed())
        result = CoreViewsEnsurer(client).ensure("db1", "2026-06-02")
        assert client.relation_updates == []
        assert any("native Sub-items not enabled" in w for w in result.warnings)

    def test_query_failure_degrades_to_warning(self):
        client = FakeViewsClient(views=_matching_views())
        client.query_data_source_rows = MagicMock(side_effect=RuntimeError("boom"))
        result = CoreViewsEnsurer(client).ensure("db1", "2026-06-02")
        assert result.ok()  # migration failure must not fail the ensure run
        assert any("sub-item migration skipped" in w for w in result.warnings)


class TestTheLegacyRelationPairIsGone:
    """`Parent Task`/`Sub-items` were a custom dual-property pair that nothing
    filled. `update_row_parent` had no callers, and `_wire_parent_tasks` reports
    a failure asking the user to enable Notion's native sub-items rather than
    writing to this pair — so on a database without native sub-items the columns
    existed and stayed empty either way.

    Measured before removal: 13 legacy links in the live database, all 13 also
    present in the native pair, so nothing was carried only here.

    Pinned because removing the two names from both lists broke no test at all —
    the lists had never been asserted on.
    """

    LEGACY = ("Parent Task", "Sub-items")

    def test_ensure_does_not_recreate_them(self):
        from claude_diary.exporters.notion_views import (
            REQUIRED_PROPERTIES, SCHEMA_EXTENSION_PROPERTIES,
        )
        for name in self.LEGACY:
            assert name not in REQUIRED_PROPERTIES, (
                "%s is back in REQUIRED_PROPERTIES; `ensure` will recreate the "
                "column on every database" % name)
            assert name not in SCHEMA_EXTENSION_PROPERTIES, name

    def test_a_new_database_is_not_given_them(self):
        from claude_diary.exporters.notion_hierarchical import _current_schema_extensions
        props = _current_schema_extensions("db-1")
        for name in self.LEGACY:
            assert name not in props

    def test_reading_old_links_still_works(self):
        """Databases in the wild still have the columns and the links in them.
        The migration that folds them into the native pair has to keep reading."""
        import claude_diary.exporters.notion_views as nv
        rows = [
            {"id": "child", "properties": {
                "Parent Task": {"type": "relation", "relation": [{"id": "parent"}]},
                "상위 항목": {"type": "relation", "relation": []},
            }},
            {"id": "parent", "properties": {}},
        ]
        migrations = nv._compute_native_migration(rows, "상위 항목")
        assert migrations == [("child", ["parent"], 1)]
