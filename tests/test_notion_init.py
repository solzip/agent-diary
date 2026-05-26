"""Tests for `claude-diary notion init` interactive setup."""

import json
from unittest.mock import patch, MagicMock

import pytest

from claude_diary.cli.notion_init import (
    cmd_notion_init,
    parse_page_id,
    _verify_access,
    _save_credentials,
)
from claude_diary.exporters.notion_hierarchical import (
    NotionAuthError,
    NotionNotFound,
)


class TestParsePageId:
    def test_plain_undashed_32_hex(self):
        s = "1234567890abcdef1234567890abcdef"
        assert parse_page_id(s) == s

    def test_dashed_uuid_form(self):
        assert parse_page_id("12345678-90ab-cdef-1234-567890abcdef") == \
               "1234567890abcdef1234567890abcdef"

    def test_notion_url_with_dashed_id(self):
        url = "https://www.notion.so/Working-Diary-12345678-90ab-cdef-1234-567890abcdef"
        assert parse_page_id(url) == "1234567890abcdef1234567890abcdef"

    def test_notion_url_with_undashed_id_at_end(self):
        url = "https://notion.so/workspace/1234567890abcdef1234567890abcdef?v=foo"
        assert parse_page_id(url) == "1234567890abcdef1234567890abcdef"

    def test_invalid_returns_none(self):
        assert parse_page_id("not a uuid") is None
        assert parse_page_id("") is None
        assert parse_page_id(None) is None

    def test_too_short_returns_none(self):
        assert parse_page_id("abc123") is None


class TestVerifyAccess:
    def test_both_checks_succeed(self):
        mock_req = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {}
        mock_resp.headers = {}
        mock_req.request.return_value = mock_resp

        with patch.dict("sys.modules", {"requests": mock_req}):
            ok, err = _verify_access("token_xxx", "page_id_yyy")
        assert ok is True
        assert err == ""

    def test_invalid_token_returns_friendly_error(self):
        mock_req = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.json.return_value = {"message": "unauthorized"}
        mock_resp.headers = {}
        mock_req.request.return_value = mock_resp

        with patch.dict("sys.modules", {"requests": mock_req}):
            ok, err = _verify_access("bad_token", "page_id")
        assert ok is False
        assert "Token invalid" in err

    def test_page_not_found_returns_share_hint(self):
        mock_req = MagicMock()
        # First call (users/me) succeeds, second (blocks/{id}) returns 404
        resp_ok = MagicMock(status_code=200, headers={})
        resp_ok.json.return_value = {}
        resp_404 = MagicMock(status_code=404, headers={})
        resp_404.json.return_value = {"message": "not found"}
        mock_req.request.side_effect = [resp_ok, resp_404]

        with patch.dict("sys.modules", {"requests": mock_req}):
            ok, err = _verify_access("token", "missing_page")
        assert ok is False
        assert "Connections" in err  # mentions the share path


class TestSaveCredentials:
    def test_merges_into_existing_config(self, tmp_path):
        with patch("claude_diary.cli.notion_init.load_config",
                   return_value={"lang": "ko", "exporters": {"slack": {"webhook_url": "x"}}}), \
             patch("claude_diary.cli.notion_init.save_config") as mock_save:
            _save_credentials("token_abc", "page_xyz")

        saved = mock_save.call_args[0][0]
        assert saved["lang"] == "ko"
        assert saved["exporters"]["slack"]["webhook_url"] == "x"
        assert saved["exporters"]["notion_hierarchical"]["api_token"] == "token_abc"
        assert saved["exporters"]["notion_hierarchical"]["root_page_id"] == "page_xyz"

    def test_creates_keys_when_missing(self, tmp_path):
        with patch("claude_diary.cli.notion_init.load_config", return_value={}), \
             patch("claude_diary.cli.notion_init.save_config") as mock_save:
            _save_credentials("t", "p")
        saved = mock_save.call_args[0][0]
        assert saved["exporters"]["notion_hierarchical"]["api_token"] == "t"


# ── End-to-end cmd_notion_init ────────────────────────────────────────────

class TestCmdNotionInit:
    def _make_args(self):
        return MagicMock()

    def test_happy_path(self, tmp_path, capsys):
        page_id = "1234567890abcdef1234567890abcdef"

        with patch("claude_diary.cli.notion_init.getpass.getpass", return_value="secret_xxx"), \
             patch("builtins.input", return_value=page_id), \
             patch("claude_diary.cli.notion_init._verify_access", return_value=(True, "")), \
             patch("claude_diary.cli.notion_init._save_credentials") as mock_save:
            cmd_notion_init(self._make_args())

        mock_save.assert_called_once_with("secret_xxx", page_id)

    def test_aborts_on_empty_token(self, capsys):
        with patch("claude_diary.cli.notion_init.getpass.getpass", return_value=""), \
             pytest.raises(SystemExit) as exc:
            cmd_notion_init(self._make_args())
        assert exc.value.code == 1

    def test_aborts_on_empty_page(self):
        with patch("claude_diary.cli.notion_init.getpass.getpass", return_value="secret_x"), \
             patch("builtins.input", return_value=""), \
             pytest.raises(SystemExit) as exc:
            cmd_notion_init(self._make_args())
        assert exc.value.code == 1

    def test_aborts_on_unparseable_page(self):
        with patch("claude_diary.cli.notion_init.getpass.getpass", return_value="secret_x"), \
             patch("builtins.input", return_value="not a real notion url"), \
             pytest.raises(SystemExit) as exc:
            cmd_notion_init(self._make_args())
        assert exc.value.code == 1

    def test_aborts_on_verify_failure(self):
        page_id = "1234567890abcdef1234567890abcdef"
        with patch("claude_diary.cli.notion_init.getpass.getpass", return_value="bad"), \
             patch("builtins.input", return_value=page_id), \
             patch("claude_diary.cli.notion_init._verify_access",
                   return_value=(False, "✗ Token invalid")), \
             pytest.raises(SystemExit) as exc:
            cmd_notion_init(self._make_args())
        assert exc.value.code == 1

    def test_keyboard_interrupt_during_token_aborts(self):
        with patch("claude_diary.cli.notion_init.getpass.getpass",
                   side_effect=KeyboardInterrupt), \
             pytest.raises(SystemExit) as exc:
            cmd_notion_init(self._make_args())
        assert exc.value.code == 1
