"""Tests for NotionHierarchicalExporter — HTTP layer + page/DB/row CRUD."""

from unittest.mock import patch, MagicMock

import pytest

from claude_diary.exporters.notion_hierarchical import (
    NotionHierarchicalExporter,
    NotionAuthError,
    NotionNotFound,
    NotionBadRequest,
    SCHEMA_VERSION,
    detect_subitem_relation,
)


def _dual(synced, prop_id="id"):
    return {
        "id": prop_id,
        "type": "relation",
        "relation": {
            "type": "dual_property",
            "dual_property": {"synced_property_name": synced},
        },
    }


class TestDetectSubitemRelation:
    def test_finds_korean_native_pair(self):
        props = {
            "Parent Task": _dual("Sub-items", "Tush"),
            "Sub-items": _dual("Parent Task", "subs"),
            "Depends On": {"id": "d", "type": "relation",
                           "relation": {"type": "single_property"}},
            "상위 항목": _dual("하위 항목", "pid"),
            "하위 항목": _dual("상위 항목", "cid"),
        }
        native = detect_subitem_relation(props)
        assert native["parent_name"] == "상위 항목"
        assert native["parent_id"] == "pid"
        assert native["child_name"] == "하위 항목"
        assert native["child_id"] == "cid"

    def test_finds_english_native_pair(self):
        props = {
            "Parent item": _dual("Sub-item", "P"),
            "Sub-item": _dual("Parent item", "C"),
        }
        native = detect_subitem_relation(props)
        assert native["parent_name"] == "Parent item"
        assert native["child_name"] == "Sub-item"

    def test_none_when_only_reserved_relations(self):
        props = {
            "Parent Task": _dual("Sub-items", "Tush"),
            "Sub-items": _dual("Parent Task", "subs"),
        }
        assert detect_subitem_relation(props) is None

    def test_none_when_no_relations(self):
        assert detect_subitem_relation({"Name": {"id": "title", "type": "title"}}) is None
        assert detect_subitem_relation({}) is None

    def test_ignores_single_property_relations(self):
        props = {
            "Depends On": {"id": "d", "type": "relation",
                           "relation": {"type": "single_property"}},
        }
        assert detect_subitem_relation(props) is None


def _make_response(status, json_body=None, headers=None):
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = json_body or {}
    resp.headers = headers or {}
    resp.text = "<error body>"
    return resp


def _patch_requests(mock_requests):
    """Helper: install a mock requests module."""
    return patch.dict("sys.modules", {"requests": mock_requests})


def _make_exporter():
    return NotionHierarchicalExporter({
        "api_token": "secret_xxx",
        "root_page_id": "root_abc",
    })


CURRENT_EXTENSION_COLUMNS = [
    "Purpose",
    "Status",
    "Task Group",
    "Depends On",
    "Parent Task",
    "Work Period",
    "Priority",
    "Next Action",
    "Blocked",
    "Block Reason",
    "Carryover",
    "Review Status",
    "Last Reviewed",
    "Schema Version",
]


def _assert_current_extension_schema(patch_body, db_id):
    props = patch_body["properties"]
    for col in CURRENT_EXTENSION_COLUMNS:
        assert col in props

    relation = props["Depends On"]["relation"]
    assert relation["database_id"] == db_id
    assert relation["type"] == "single_property"

    parent_relation = props["Parent Task"]["relation"]
    assert parent_relation["database_id"] == db_id
    assert parent_relation["type"] == "dual_property"
    assert parent_relation["dual_property"]["synced_property_name"] == "Sub-items"

    assert props["Priority"] == {"select": {}}
    assert props["Next Action"] == {"rich_text": {}}
    assert props["Blocked"] == {"checkbox": {}}
    assert props["Block Reason"] == {"rich_text": {}}
    assert props["Carryover"] == {"checkbox": {}}
    assert props["Review Status"] == {"select": {}}
    assert props["Last Reviewed"] == {"date": {}}
    assert props["Schema Version"] == {"select": {}}


class TestValidateConfig:
    def test_both_present(self):
        assert _make_exporter().validate_config() is True

    def test_missing_token(self):
        exp = NotionHierarchicalExporter({"root_page_id": "root_abc"})
        assert exp.validate_config() is False

    def test_missing_root_page(self):
        exp = NotionHierarchicalExporter({"api_token": "secret_xxx"})
        assert exp.validate_config() is False


class TestRequestErrorMapping:
    def test_200_returns_json(self):
        mock_req = MagicMock()
        mock_req.request.return_value = _make_response(200, {"id": "page_xyz"})
        with _patch_requests(mock_req):
            exp = _make_exporter()
            data = exp._request("GET", "/pages/page_xyz")
        assert data["id"] == "page_xyz"

    def test_401_raises_auth_error(self):
        mock_req = MagicMock()
        mock_req.request.return_value = _make_response(401, {"message": "unauthorized"})
        with _patch_requests(mock_req):
            exp = _make_exporter()
            with pytest.raises(NotionAuthError):
                exp._request("GET", "/pages/x")

    def test_403_raises_auth_error(self):
        mock_req = MagicMock()
        mock_req.request.return_value = _make_response(403, {"message": "forbidden"})
        with _patch_requests(mock_req):
            with pytest.raises(NotionAuthError):
                _make_exporter()._request("GET", "/pages/x")

    def test_404_raises_not_found(self):
        mock_req = MagicMock()
        mock_req.request.return_value = _make_response(404, {"message": "not found"})
        with _patch_requests(mock_req):
            with pytest.raises(NotionNotFound):
                _make_exporter()._request("GET", "/pages/x")

    def test_400_raises_bad_request(self):
        mock_req = MagicMock()
        mock_req.request.return_value = _make_response(400, {"message": "bad"})
        with _patch_requests(mock_req):
            with pytest.raises(NotionBadRequest):
                _make_exporter()._request("POST", "/pages", {"x": 1})

    def test_429_then_200_retries(self):
        mock_req = MagicMock()
        mock_req.request.side_effect = [
            _make_response(429, headers={"Retry-After": "0"}),
            _make_response(200, {"ok": True}),
        ]
        with _patch_requests(mock_req), \
             patch("claude_diary.exporters.notion_hierarchical.time.sleep"):
            data = _make_exporter()._request("GET", "/pages/x")
        assert data["ok"] is True
        assert mock_req.request.call_count == 2

    def test_5xx_then_200_retries(self):
        mock_req = MagicMock()
        mock_req.request.side_effect = [
            _make_response(500),
            _make_response(200, {"ok": True}),
        ]
        with _patch_requests(mock_req), \
             patch("claude_diary.exporters.notion_hierarchical.time.sleep"):
            data = _make_exporter()._request("GET", "/pages/x")
        assert data["ok"] is True
        assert mock_req.request.call_count == 2

    def test_5xx_exhausted_raises_runtime(self):
        mock_req = MagicMock()
        mock_req.request.return_value = _make_response(503)
        with _patch_requests(mock_req), \
             patch("claude_diary.exporters.notion_hierarchical.time.sleep"):
            with pytest.raises(RuntimeError):
                _make_exporter()._request("GET", "/pages/x")
        # MAX_RETRIES attempts
        assert mock_req.request.call_count == 3

    def test_network_error_retries(self):
        mock_req = MagicMock()
        mock_req.request.side_effect = [
            Exception("connection reset"),
            _make_response(200, {"ok": True}),
        ]
        with _patch_requests(mock_req), \
             patch("claude_diary.exporters.notion_hierarchical.time.sleep"):
            data = _make_exporter()._request("GET", "/pages/x")
        assert data["ok"] is True


class TestEnsureYearPage:
    def test_cache_hit_and_still_exists(self, tmp_path):
        exp = _make_exporter()
        with patch("claude_diary.lib.notion_cache.get_config_dir", return_value=str(tmp_path)):
            exp.load_cache()
        # Pre-populate cache
        exp._cache["years"]["2026"] = "cached_page"

        mock_req = MagicMock()
        mock_req.request.return_value = _make_response(200, {"id": "cached_page"})
        with _patch_requests(mock_req):
            page_id = exp.ensure_year_page(2026)
        assert page_id == "cached_page"
        # Only the existence-check call, no creation
        assert mock_req.request.call_count == 1

    def test_cache_hit_but_404_triggers_recreate(self, tmp_path):
        exp = _make_exporter()
        with patch("claude_diary.lib.notion_cache.get_config_dir", return_value=str(tmp_path)):
            exp.load_cache()
        exp._cache["years"]["2026"] = "stale_page"

        mock_req = MagicMock()
        mock_req.request.side_effect = [
            _make_response(404),                              # existence check fails
            _make_response(200, {"results": [], "has_more": False}),  # search finds nothing
            _make_response(200, {"id": "new_page"}),          # create
        ]
        with _patch_requests(mock_req):
            page_id = exp.ensure_year_page(2026)

        assert page_id == "new_page"
        assert exp._cache["years"]["2026"] == "new_page"

    def test_cache_miss_finds_existing(self, tmp_path):
        exp = _make_exporter()
        with patch("claude_diary.lib.notion_cache.get_config_dir", return_value=str(tmp_path)):
            exp.load_cache()

        mock_req = MagicMock()
        mock_req.request.return_value = _make_response(200, {
            "results": [
                {"id": "found_page", "type": "child_page",
                 "child_page": {"title": "2026"}},
            ],
            "has_more": False,
        })
        with _patch_requests(mock_req):
            page_id = exp.ensure_year_page(2026)

        assert page_id == "found_page"
        assert exp._cache["years"]["2026"] == "found_page"

    def test_cache_miss_not_found_creates(self, tmp_path):
        exp = _make_exporter()
        with patch("claude_diary.lib.notion_cache.get_config_dir", return_value=str(tmp_path)):
            exp.load_cache()

        mock_req = MagicMock()
        mock_req.request.side_effect = [
            _make_response(200, {"results": [], "has_more": False}),
            _make_response(200, {"id": "created_page"}),
        ]
        with _patch_requests(mock_req):
            page_id = exp.ensure_year_page(2026)

        assert page_id == "created_page"
        # Verify create call used title "2026"
        create_call = mock_req.request.call_args_list[1]
        body = create_call.kwargs["json"]
        assert body["parent"]["page_id"] == "root_abc"
        assert body["properties"]["title"][0]["text"]["content"] == "2026"


class TestEnsureDatabase:
    def test_creates_database_with_full_schema(self, tmp_path):
        exp = _make_exporter()
        with patch("claude_diary.lib.notion_cache.get_config_dir", return_value=str(tmp_path)):
            exp.load_cache()
        exp._cache["years"]["2026"] = "year_page"  # year already cached

        mock_req = MagicMock()
        # Four calls:
        #   1. GET /blocks/year_page (existence check from ensure_year_page cache hit)
        #   2. GET /blocks/year_page/children (find an existing Entries DB)
        #   3. POST /databases (create base schema)
        #   4. PATCH /databases/{id} (Purpose + Status + Task Group + relation extensions)
        mock_req.request.side_effect = [
            _make_response(200, {"id": "year_page"}),
            _make_response(200, {"results": [], "has_more": False}),
            _make_response(200, {"id": "db_xyz"}),
            _make_response(200, {"id": "db_xyz"}),
        ]
        with _patch_requests(mock_req):
            db_id = exp.ensure_database(2026)

        assert db_id == "db_xyz"
        # Third call: create POST (base schema only)
        create_call = mock_req.request.call_args_list[2]
        assert create_call.args[0] == "POST"
        create_body = create_call.kwargs["json"]
        assert create_body["parent"]["page_id"] == "year_page"
        assert create_body["is_inline"] is True
        props = create_body["properties"]
        for col in ["Name", "Date", "Project", "Branch",
                    "Categories", "Files", "Commits", "Lines",
                    "Session ID", "Task Index"]:
            assert col in props
        # Purpose/Status/Task Group/relation columns NOT in create body — added by schema extension PATCH
        assert "Purpose" not in props
        assert "Status" not in props
        assert "Task Group" not in props
        assert "Depends On" not in props
        assert "Parent Task" not in props

        # Fourth call: PATCH to add the full current extension schema
        patch_call = mock_req.request.call_args_list[3]
        assert patch_call.args[0] == "PATCH"
        assert patch_call.args[1].endswith("/databases/db_xyz")
        patch_body = patch_call.kwargs["json"]
        _assert_current_extension_schema(patch_body, "db_xyz")
        # Cache flag recorded so future calls skip the PATCH
        assert exp._cache["schema_v"]["db_xyz"] == SCHEMA_VERSION

    def test_existing_database_gets_schema_extension(self, tmp_path):
        """Cache-hit database (older schema) gets current schema columns via PATCH."""
        exp = _make_exporter()
        with patch("claude_diary.lib.notion_cache.get_config_dir", return_value=str(tmp_path)):
            exp.load_cache()
        # Pre-existing DB in cache (no schema_v flag — simulates upgrade path)
        exp._cache["databases"]["2026"] = "old_db"

        mock_req = MagicMock()
        mock_req.request.side_effect = [
            _make_response(200, {"id": "old_db"}),   # GET /databases/old_db (exists)
            _make_response(200, {"id": "old_db"}),   # PATCH schema extension
        ]
        with _patch_requests(mock_req):
            db_id = exp.ensure_database(2026)

        assert db_id == "old_db"
        # Second call: PATCH for schema extension on the existing DB
        patch_call = mock_req.request.call_args_list[1]
        assert patch_call.args[0] == "PATCH"
        _assert_current_extension_schema(patch_call.kwargs["json"], "old_db")
        assert exp._cache["schema_v"]["old_db"] == SCHEMA_VERSION

    def test_cache_miss_reuses_existing_entries_database(self, tmp_path):
        """If cache is empty but Entries already exists, do not create a duplicate DB."""
        exp = _make_exporter()
        with patch("claude_diary.lib.notion_cache.get_config_dir", return_value=str(tmp_path)):
            exp.load_cache()
        exp._cache["years"]["2026"] = "year_page"

        mock_req = MagicMock()
        mock_req.request.side_effect = [
            _make_response(200, {"id": "year_page"}),
            _make_response(200, {
                "results": [
                    {
                        "id": "existing_db",
                        "type": "child_database",
                        "child_database": {"title": "Entries"},
                    },
                ],
                "has_more": False,
            }),
            _make_response(200, {"id": "existing_db"}),
        ]
        with _patch_requests(mock_req):
            db_id = exp.ensure_database(2026)

        assert db_id == "existing_db"
        assert exp._cache["databases"]["2026"] == "existing_db"
        methods = [call_args.args[0] for call_args in mock_req.request.call_args_list]
        assert "POST" not in methods
        assert exp._cache["schema_v"]["existing_db"] == SCHEMA_VERSION

    def test_schema_extension_skipped_when_already_flagged(self, tmp_path):
        """Once schema_v records the DB at the current version, no further PATCH is sent."""
        exp = _make_exporter()
        with patch("claude_diary.lib.notion_cache.get_config_dir", return_value=str(tmp_path)):
            exp.load_cache()
        exp._cache["databases"]["2026"] = "db_known"
        exp._cache["schema_v"]["db_known"] = SCHEMA_VERSION

        mock_req = MagicMock()
        mock_req.request.return_value = _make_response(200, {"id": "db_known"})
        with _patch_requests(mock_req):
            db_id = exp.ensure_database(2026)

        assert db_id == "db_known"
        # Only the existence check — no PATCH
        assert mock_req.request.call_count == 1
        assert mock_req.request.call_args.args[0] == "GET"

    def test_force_schema_patches_even_when_already_flagged(self, tmp_path):
        """Explicit ensure can force a schema patch even when cache says current."""
        exp = _make_exporter()
        with patch("claude_diary.lib.notion_cache.get_config_dir", return_value=str(tmp_path)):
            exp.load_cache()
        exp._cache["databases"]["2026"] = "db_known"
        exp._cache["schema_v"]["db_known"] = SCHEMA_VERSION

        mock_req = MagicMock()
        mock_req.request.side_effect = [
            _make_response(200, {"id": "db_known"}),
            _make_response(200, {"id": "db_known"}),
        ]
        with _patch_requests(mock_req):
            db_id = exp.ensure_database(2026, force_schema=True)

        assert db_id == "db_known"
        assert mock_req.request.call_args_list[1].args[0] == "PATCH"
        patch_body = mock_req.request.call_args_list[1].kwargs["json"]
        _assert_current_extension_schema(patch_body, "db_known")

    def test_v3_database_gets_current_schema_upgrade(self, tmp_path):
        """A DB already marked v3 still gets the current schema patch."""
        exp = _make_exporter()
        with patch("claude_diary.lib.notion_cache.get_config_dir", return_value=str(tmp_path)):
            exp.load_cache()
        exp._cache["databases"]["2026"] = "db_v3"
        exp._cache["schema_v"]["db_v3"] = "v3"

        mock_req = MagicMock()
        mock_req.request.side_effect = [
            _make_response(200, {"id": "db_v3"}),
            _make_response(200, {"id": "db_v3"}),
        ]
        with _patch_requests(mock_req):
            db_id = exp.ensure_database(2026)

        assert db_id == "db_v3"
        patch_body = mock_req.request.call_args_list[1].kwargs["json"]
        _assert_current_extension_schema(patch_body, "db_v3")
        assert exp._cache["schema_v"]["db_v3"] == SCHEMA_VERSION

    def test_v2_database_gets_current_schema_upgrade(self, tmp_path):
        """A DB already marked v2 still gets the current schema patch."""
        exp = _make_exporter()
        with patch("claude_diary.lib.notion_cache.get_config_dir", return_value=str(tmp_path)):
            exp.load_cache()
        exp._cache["databases"]["2026"] = "db_v2"
        exp._cache["schema_v"]["db_v2"] = "v2"

        mock_req = MagicMock()
        mock_req.request.side_effect = [
            _make_response(200, {"id": "db_v2"}),
            _make_response(200, {"id": "db_v2"}),
        ]
        with _patch_requests(mock_req):
            db_id = exp.ensure_database(2026)

        assert db_id == "db_v2"
        patch_body = mock_req.request.call_args_list[1].kwargs["json"]
        _assert_current_extension_schema(patch_body, "db_v2")
        assert exp._cache["schema_v"]["db_v2"] == SCHEMA_VERSION

    def test_v4_database_gets_current_schema_upgrade(self, tmp_path):
        """A DB already marked v4 still gets the current v7 schema patch."""
        exp = _make_exporter()
        with patch("claude_diary.lib.notion_cache.get_config_dir", return_value=str(tmp_path)):
            exp.load_cache()
        exp._cache["databases"]["2026"] = "db_v4"
        exp._cache["schema_v"]["db_v4"] = "v4"

        mock_req = MagicMock()
        mock_req.request.side_effect = [
            _make_response(200, {"id": "db_v4"}),
            _make_response(200, {"id": "db_v4"}),
        ]
        with _patch_requests(mock_req):
            db_id = exp.ensure_database(2026)

        assert db_id == "db_v4"
        patch_body = mock_req.request.call_args_list[1].kwargs["json"]
        _assert_current_extension_schema(patch_body, "db_v4")
        assert exp._cache["schema_v"]["db_v4"] == SCHEMA_VERSION


class TestFindExistingRow:
    def test_returns_none_when_no_match(self, tmp_path):
        exp = _make_exporter()
        with patch("claude_diary.lib.notion_cache.get_config_dir", return_value=str(tmp_path)):
            exp.load_cache()

        mock_req = MagicMock()
        mock_req.request.return_value = _make_response(200, {"results": []})
        with _patch_requests(mock_req):
            row = exp.find_existing_row("db_xyz", "sess1", 0)
        assert row is None

    def test_finds_and_caches_existing_row(self, tmp_path):
        exp = _make_exporter()
        with patch("claude_diary.lib.notion_cache.get_config_dir", return_value=str(tmp_path)):
            exp.load_cache()

        mock_req = MagicMock()
        mock_req.request.return_value = _make_response(200, {
            "results": [{"id": "row_abc"}]
        })
        with _patch_requests(mock_req):
            row = exp.find_existing_row("db_xyz", "sess1", 0)
        assert row == "row_abc"
        assert exp._cache["rows"]["sess1:0"] == "row_abc"

    def test_cache_hit_skips_query(self, tmp_path):
        exp = _make_exporter()
        with patch("claude_diary.lib.notion_cache.get_config_dir", return_value=str(tmp_path)):
            exp.load_cache()
        exp._cache["rows"]["sess1:0"] = "cached_row"

        mock_req = MagicMock()
        mock_req.request.return_value = _make_response(200, {"id": "cached_row"})
        with _patch_requests(mock_req):
            row = exp.find_existing_row("db_xyz", "sess1", 0)
        # Only existence check (GET /pages/cached_row), no query
        assert row == "cached_row"
        assert mock_req.request.call_count == 1
        assert mock_req.request.call_args.args[0] == "GET"


class TestArchiveRowsForSession:
    def test_archives_all_matching_rows(self, tmp_path):
        exp = _make_exporter()
        with patch("claude_diary.lib.notion_cache.get_config_dir", return_value=str(tmp_path)):
            exp.load_cache()

        mock_req = MagicMock()
        mock_req.request.side_effect = [
            _make_response(200, {
                "results": [{"id": "row_a"}, {"id": "row_b"}],
                "has_more": False,
            }),
            _make_response(200, {"id": "row_a", "archived": True}),
            _make_response(200, {"id": "row_b", "archived": True}),
        ]
        with _patch_requests(mock_req):
            archived = exp.archive_rows_for_session("db_xyz", "sess1")
        assert archived == 2
        # Verify the PATCH calls used archived=True
        patch_calls = [c for c in mock_req.request.call_args_list
                       if c.args[0] == "PATCH"]
        assert len(patch_calls) == 2
        for c in patch_calls:
            assert c.kwargs["json"] == {"archived": True}


class TestQueryDatabaseRows:
    def test_paginates_all_rows(self):
        exp = _make_exporter()
        mock_req = MagicMock()
        mock_req.request.side_effect = [
            _make_response(200, {
                "results": [{"id": "row_a"}],
                "has_more": True,
                "next_cursor": "cursor-1",
            }),
            _make_response(200, {
                "results": [{"id": "row_b"}],
                "has_more": False,
            }),
        ]

        with _patch_requests(mock_req):
            rows = exp.query_database_rows("db_xyz")

        assert rows == [{"id": "row_a"}, {"id": "row_b"}]
        first = mock_req.request.call_args_list[0]
        second = mock_req.request.call_args_list[1]
        assert first.args[0] == "POST"
        assert first.args[1].endswith("/databases/db_xyz/query")
        assert first.kwargs["json"] == {"page_size": 100}
        assert second.kwargs["json"] == {
            "page_size": 100,
            "start_cursor": "cursor-1",
        }


class TestCreateRow:
    def test_posts_to_pages_endpoint(self, tmp_path):
        exp = _make_exporter()
        mock_req = MagicMock()
        mock_req.request.return_value = _make_response(200, {"id": "new_row"})

        properties = {"Name": {"title": [{"text": {"content": "task"}}]}}
        body_blocks = [{"object": "block", "type": "paragraph",
                        "paragraph": {"rich_text": [{"text": {"content": "x"}}]}}]

        with _patch_requests(mock_req):
            row_id = exp.create_row("db_xyz", properties, body_blocks)

        assert row_id == "new_row"
        call_args = mock_req.request.call_args
        assert call_args.args[0] == "POST"
        # URL ends with /pages
        assert call_args.args[1].endswith("/pages")
        body = call_args.kwargs["json"]
        assert body["parent"]["database_id"] == "db_xyz"
        assert body["properties"] == properties
        assert body["children"] == body_blocks


class TestUpdateRelations:
    def test_update_row_relation_sets_depends_on(self):
        exp = _make_exporter()
        mock_req = MagicMock()
        mock_req.request.return_value = _make_response(200, {"id": "row_b"})

        with _patch_requests(mock_req):
            exp.update_row_relation("row_b", ["row_a", "row_c"])

        body = mock_req.request.call_args.kwargs["json"]
        assert body["properties"]["Depends On"]["relation"] == [
            {"id": "row_a"},
            {"id": "row_c"},
        ]

    def test_update_row_parent_sets_parent_task(self):
        exp = _make_exporter()
        mock_req = MagicMock()
        mock_req.request.return_value = _make_response(200, {"id": "row_child"})

        with _patch_requests(mock_req):
            exp.update_row_parent("row_child", "row_parent")

        body = mock_req.request.call_args.kwargs["json"]
        assert body["properties"]["Parent Task"]["relation"] == [
            {"id": "row_parent"},
        ]

    def test_update_row_subitems_sets_subitems(self):
        exp = _make_exporter()
        mock_req = MagicMock()
        mock_req.request.return_value = _make_response(200, {"id": "row_parent"})

        with _patch_requests(mock_req):
            exp.update_row_subitems("row_parent", ["row_child_1", "row_child_2"])

        body = mock_req.request.call_args.kwargs["json"]
        assert body["properties"]["Sub-items"]["relation"] == [
            {"id": "row_child_1"},
            {"id": "row_child_2"},
        ]

    def test_update_row_subitems_preserves_existing_subitems(self):
        exp = _make_exporter()
        mock_req = MagicMock()
        mock_req.request.side_effect = [
            _make_response(200, {
                "id": "row_parent",
                "properties": {
                    "Sub-items": {
                        "relation": [
                            {"id": "row_existing"},
                            {"id": "row_child_1"},
                        ]
                    }
                },
            }),
            _make_response(200, {"id": "row_parent"}),
        ]

        with _patch_requests(mock_req):
            exp.update_row_subitems("row_parent", ["row_child_1", "row_child_2"])

        body = mock_req.request.call_args_list[1].kwargs["json"]
        assert body["properties"]["Sub-items"]["relation"] == [
            {"id": "row_existing"},
            {"id": "row_child_1"},
            {"id": "row_child_2"},
        ]


class TestRequestsMissing:
    def test_friendly_error_when_requests_not_installed(self):
        exp = _make_exporter()
        import builtins
        original_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "requests":
                raise ImportError("No module named 'requests'")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fake_import):
            with pytest.raises(RuntimeError, match="requests"):
                exp._request("GET", "/anything")
