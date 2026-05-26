"""Tests for NotionHierarchicalExporter — HTTP layer + page/DB/row CRUD."""

from unittest.mock import patch, MagicMock, call

import pytest

from claude_diary.exporters.notion_hierarchical import (
    NotionHierarchicalExporter,
    NotionAuthError,
    NotionNotFound,
    NotionBadRequest,
)


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
        mock_req.request.return_value = _make_response(200, {"id": "db_xyz"})
        with _patch_requests(mock_req):
            db_id = exp.ensure_database(2026)

        assert db_id == "db_xyz"
        # Inspect the database-create POST body
        create_body = mock_req.request.call_args.kwargs["json"]
        assert create_body["parent"]["page_id"] == "year_page"
        assert create_body["is_inline"] is True
        props = create_body["properties"]
        for col in ["Name", "Date", "Project", "Branch", "Categories",
                    "Files", "Commits", "Lines", "Session ID", "Task Index"]:
            assert col in props


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
