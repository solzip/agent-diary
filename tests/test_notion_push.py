"""Tests for `claude-diary notion push` CLI."""

import json
import os
from unittest.mock import patch, MagicMock

import pytest

from claude_diary.cli.notion_push import (
    cmd_notion_push,
    _resolve_credentials,
    _safe_select,
    _build_properties,
    _gather_git_info,
    _read_json,
)
from claude_diary.exporters.notion_hierarchical import (
    NotionAuthError,
    NotionBadRequest,
)


class TestResolveCredentials:
    def test_env_vars_take_priority(self):
        config = {
            "exporters": {
                "notion_hierarchical": {
                    "api_token": "config_token",
                    "root_page_id": "config_page",
                }
            }
        }
        with patch.dict(os.environ, {
            "CLAUDE_DIARY_NOTION_TOKEN": "env_token",
            "CLAUDE_DIARY_NOTION_ROOT_PAGE_ID": "env_page",
        }):
            token, page = _resolve_credentials(config)
        assert token == "env_token"
        assert page == "env_page"

    def test_config_used_when_no_env(self):
        config = {
            "exporters": {
                "notion_hierarchical": {
                    "api_token": "config_token",
                    "root_page_id": "config_page",
                }
            }
        }
        with patch.dict(os.environ, {}, clear=True):
            token, page = _resolve_credentials(config)
        assert token == "config_token"
        assert page == "config_page"

    def test_missing_returns_none(self):
        with patch.dict(os.environ, {}, clear=True):
            token, page = _resolve_credentials({"exporters": {}})
        assert token is None
        assert page is None


class TestSafeSelect:
    def test_replaces_comma(self):
        assert _safe_select("foo, bar") == "foo- bar"

    def test_truncates_to_100(self):
        assert len(_safe_select("x" * 200)) == 100

    def test_empty_returns_unknown(self):
        assert _safe_select("") == "unknown"
        assert _safe_select(None) == "unknown"


class TestBuildProperties:
    def _base_task(self):
        return {
            "title": "DB 결정",
            "project": "diary",
            "categories": ["design"],
            "files_modified": ["a.py"],
            "files_created": ["b.py"],
        }

    def test_all_columns_present(self):
        task = self._base_task()
        git_info = {
            "branch": "feat/x",
            "commits": [{"hash": "abc", "short_hash": "abc", "message": "m"}],
            "diff_stat": {"added": 10, "deleted": 5, "files": 2},
        }
        props = _build_properties(task, "2026-05-26", "feat/x", git_info, "sess1", 0)
        assert props["Name"]["title"][0]["text"]["content"] == "DB 결정"
        assert props["Date"]["date"]["start"] == "2026-05-26"
        assert props["Project"]["select"]["name"] == "diary"
        assert props["Branch"]["select"]["name"] == "feat/x"
        assert props["Categories"]["multi_select"][0]["name"] == "design"
        assert props["Files"]["number"] == 2
        assert props["Commits"]["number"] == 1
        assert props["Lines"]["number"] == 15
        assert props["Session ID"]["rich_text"][0]["text"]["content"] == "sess1"
        assert props["Task Index"]["number"] == 0

    def test_branch_omitted_when_empty(self):
        task = self._base_task()
        props = _build_properties(task, "2026-05-26", "", {}, "sess1", 0)
        assert "Branch" not in props

    def test_empty_categories_filtered(self):
        task = self._base_task()
        task["categories"] = ["", "design", None, "  "]
        props = _build_properties(task, "2026-05-26", "main", {}, "sess1", 0)
        cats = props["Categories"]["multi_select"]
        # empty/None filtered, whitespace kept after _safe_select but not stripped here
        names = [c["name"] for c in cats]
        assert "design" in names

    def test_no_commits_zeros(self):
        task = self._base_task()
        props = _build_properties(task, "2026-05-26", "main", {}, "sess1", 0)
        assert props["Commits"]["number"] == 0
        assert props["Lines"]["number"] == 0

    def test_valid_status_included(self):
        task = dict(self._base_task(), status="Implementation")
        props = _build_properties(task, "2026-05-26", "main", {}, "sess1", 0)
        assert props["Status"]["select"]["name"] == "Implementation"

    def test_invalid_status_omitted(self):
        task = dict(self._base_task(), status="MadeUpValue")
        props = _build_properties(task, "2026-05-26", "main", {}, "sess1", 0)
        assert "Status" not in props

    def test_task_group_included(self):
        task = dict(self._base_task(), task_group="diary-notion-impl")
        props = _build_properties(task, "2026-05-26", "main", {}, "sess1", 0)
        assert props["Task Group"]["select"]["name"] == "diary-notion-impl"

    def test_empty_task_group_omitted(self):
        task = dict(self._base_task(), task_group="")
        props = _build_properties(task, "2026-05-26", "main", {}, "sess1", 0)
        assert "Task Group" not in props

    def test_depends_on_not_in_properties(self):
        """Depends On relation is wired up in pass 2, not in _build_properties."""
        task = dict(self._base_task(), depends_on_indices=[0, 1])
        props = _build_properties(task, "2026-05-26", "main", {}, "sess1", 0)
        assert "Depends On" not in props


class TestDependsOnWiring:
    def _make_args(self, input_path, force=False):
        args = MagicMock()
        args.input = input_path
        args.force = force
        return args

    def _write_json(self, path, data):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)

    def test_wire_depends_on_calls_update_for_each_task_with_deps(self, tmp_path):
        input_path = tmp_path / "in.json"
        self._write_json(str(input_path), {
            "session_id": "s1",
            "tasks": [
                {"title": "A", "depends_on_indices": []},
                {"title": "B", "depends_on_indices": [0]},          # depends on A
                {"title": "C", "depends_on_indices": [0, 1]},       # depends on A and B
            ],
        })
        config = {
            "exporters": {
                "notion_hierarchical": {"api_token": "t", "root_page_id": "p"}
            }
        }

        mock_exp = MagicMock()
        mock_exp.ensure_database.return_value = "db_xyz"
        mock_exp.find_existing_row.return_value = None
        # Three create_row calls → three row IDs
        mock_exp.create_row.side_effect = ["row_a", "row_b", "row_c"]
        mock_exp._cache = {"rows": {}, "years": {}, "databases": {}, "root_page_id": "p"}

        with patch.dict(os.environ, {}, clear=True), \
             patch("claude_diary.cli.notion_push.load_config", return_value=config), \
             patch("claude_diary.cli.notion_push.NotionHierarchicalExporter",
                   return_value=mock_exp), \
             patch("claude_diary.cli.notion_push.get_head_branch", return_value="main"), \
             pytest.raises(SystemExit):
            cmd_notion_push(self._make_args(str(input_path)))

        # update_row_relation called for B (deps=[A]) and C (deps=[A, B]),
        # not for A (no deps).
        rel_calls = mock_exp.update_row_relation.call_args_list
        assert len(rel_calls) == 2
        # B → [A]
        assert rel_calls[0].args == ("row_b", ["row_a"])
        # C → [A, B]
        assert rel_calls[1].args == ("row_c", ["row_a", "row_b"])

    def test_wire_depends_on_skips_missing_targets(self, tmp_path):
        """If a referenced task index has no row_id (failed), the missing target is dropped."""
        from claude_diary.cli.notion_push import _wire_depends_on
        mock_exp = MagicMock()
        tasks = [
            {"title": "A"},
            {"title": "B", "depends_on_indices": [0, 99]},  # 99 doesn't exist
        ]
        row_ids = {0: "row_a", 1: "row_b"}
        _wire_depends_on(mock_exp, tasks, row_ids)
        # Only the valid target (0 → row_a) is passed
        mock_exp.update_row_relation.assert_called_once_with("row_b", ["row_a"])

    def test_wire_depends_on_skips_when_self_failed(self):
        """If this task itself failed in pass 1, no relation update attempted."""
        from claude_diary.cli.notion_push import _wire_depends_on
        mock_exp = MagicMock()
        tasks = [
            {"title": "A"},
            {"title": "B", "depends_on_indices": [0]},
        ]
        # Task 1 (B) has no row_id (failed in pass 1)
        row_ids = {0: "row_a"}
        _wire_depends_on(mock_exp, tasks, row_ids)
        mock_exp.update_row_relation.assert_not_called()


class TestGatherGitInfo:
    def test_with_commit_hashes(self):
        with patch("claude_diary.cli.notion_push.get_branch_for_commit",
                   return_value="feat/x"), \
             patch("claude_diary.cli.notion_push.get_commit_info",
                   side_effect=[{"hash": "a", "short_hash": "a", "message": "m"}]), \
             patch("claude_diary.cli.notion_push.get_diff_stat_for_commits",
                   return_value={"added": 5, "deleted": 2, "files": 1}):
            info = _gather_git_info("/repo", ["abc1234"])
        assert info["branch"] == "feat/x"
        assert len(info["commits"]) == 1
        assert info["diff_stat"]["added"] == 5

    def test_no_commits_uses_head(self):
        with patch("claude_diary.cli.notion_push.get_head_branch",
                   return_value="main"):
            info = _gather_git_info("/repo", [])
        assert info["branch"] == "main"
        assert info["commits"] == []
        assert info["diff_stat"] == {"added": 0, "deleted": 0, "files": 0}


class TestReadJson:
    def test_missing_file_returns_none(self, tmp_path):
        assert _read_json(str(tmp_path / "nonexistent.json")) is None

    def test_invalid_json_returns_none(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("{{{ not json", encoding="utf-8")
        assert _read_json(str(p)) is None

    def test_valid_json_parsed(self, tmp_path):
        p = tmp_path / "good.json"
        p.write_text('{"session_id":"s1","tasks":[]}', encoding="utf-8")
        data = _read_json(str(p))
        assert data["session_id"] == "s1"


# ── End-to-end cmd_notion_push tests ──────────────────────────────────────

def _make_args(input_path, force=False):
    args = MagicMock()
    args.input = input_path
    args.force = force
    return args


def _write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


class TestCmdNotionPush:
    def test_missing_credentials_exits(self, tmp_path):
        input_path = tmp_path / "in.json"
        _write_json(str(input_path), {"session_id": "s1", "tasks": [{"title": "t"}]})

        with patch.dict(os.environ, {}, clear=True), \
             patch("claude_diary.cli.notion_push.load_config", return_value={}), \
             pytest.raises(SystemExit) as exc:
            cmd_notion_push(_make_args(str(input_path)))
        assert exc.value.code == 1

    def test_missing_input_file_exits(self):
        config = {
            "exporters": {
                "notion_hierarchical": {"api_token": "t", "root_page_id": "p"}
            }
        }
        with patch.dict(os.environ, {}, clear=True), \
             patch("claude_diary.cli.notion_push.load_config", return_value=config), \
             pytest.raises(SystemExit) as exc:
            cmd_notion_push(_make_args("/nonexistent/file.json"))
        assert exc.value.code == 1

    def test_empty_tasks_cleans_up(self, tmp_path):
        input_path = tmp_path / "in.json"
        _write_json(str(input_path), {"session_id": "s1", "tasks": []})
        config = {
            "exporters": {
                "notion_hierarchical": {"api_token": "t", "root_page_id": "p"}
            }
        }
        with patch.dict(os.environ, {}, clear=True), \
             patch("claude_diary.cli.notion_push.load_config", return_value=config):
            cmd_notion_push(_make_args(str(input_path)))
        # File deleted after empty-tasks no-op
        assert not input_path.exists()

    def test_successful_push_cleans_up(self, tmp_path):
        input_path = tmp_path / "in.json"
        _write_json(str(input_path), {
            "session_id": "s1",
            "tasks": [{"title": "task A", "project": "diary"}],
        })
        config = {
            "exporters": {
                "notion_hierarchical": {"api_token": "t", "root_page_id": "p"}
            }
        }

        mock_exp = MagicMock()
        mock_exp.ensure_database.return_value = "db_xyz"
        mock_exp.find_existing_row.return_value = None
        mock_exp.create_row.return_value = "row_abc"
        mock_exp._cache = {"rows": {}, "years": {}, "databases": {}, "root_page_id": "p"}

        with patch.dict(os.environ, {}, clear=True), \
             patch("claude_diary.cli.notion_push.load_config", return_value=config), \
             patch("claude_diary.cli.notion_push.NotionHierarchicalExporter",
                   return_value=mock_exp), \
             patch("claude_diary.cli.notion_push.get_head_branch", return_value="main"), \
             pytest.raises(SystemExit) as exc:
            cmd_notion_push(_make_args(str(input_path)))

        assert exc.value.code == 0
        mock_exp.create_row.assert_called_once()
        assert not input_path.exists()

    def test_skip_existing_row(self, tmp_path):
        input_path = tmp_path / "in.json"
        _write_json(str(input_path), {
            "session_id": "s1",
            "tasks": [{"title": "task A", "project": "diary"}],
        })
        config = {
            "exporters": {
                "notion_hierarchical": {"api_token": "t", "root_page_id": "p"}
            }
        }

        mock_exp = MagicMock()
        mock_exp.ensure_database.return_value = "db_xyz"
        mock_exp.find_existing_row.return_value = "existing_row_id"  # exists!
        mock_exp._cache = {"rows": {}, "years": {}, "databases": {}, "root_page_id": "p"}

        with patch.dict(os.environ, {}, clear=True), \
             patch("claude_diary.cli.notion_push.load_config", return_value=config), \
             patch("claude_diary.cli.notion_push.NotionHierarchicalExporter",
                   return_value=mock_exp), \
             pytest.raises(SystemExit):
            cmd_notion_push(_make_args(str(input_path)))

        # No new row created
        mock_exp.create_row.assert_not_called()

    def test_force_archives_then_pushes(self, tmp_path):
        input_path = tmp_path / "in.json"
        _write_json(str(input_path), {
            "session_id": "s1",
            "tasks": [{"title": "task A", "project": "diary"}],
        })
        config = {
            "exporters": {
                "notion_hierarchical": {"api_token": "t", "root_page_id": "p"}
            }
        }

        mock_exp = MagicMock()
        mock_exp.ensure_database.return_value = "db_xyz"
        mock_exp.archive_rows_for_session.return_value = 2
        mock_exp.find_existing_row.return_value = None
        mock_exp.create_row.return_value = "row_new"
        mock_exp._cache = {"rows": {}, "years": {}, "databases": {}, "root_page_id": "p"}

        with patch.dict(os.environ, {}, clear=True), \
             patch("claude_diary.cli.notion_push.load_config", return_value=config), \
             patch("claude_diary.cli.notion_push.NotionHierarchicalExporter",
                   return_value=mock_exp), \
             patch("claude_diary.cli.notion_push.get_head_branch", return_value="main"), \
             pytest.raises(SystemExit):
            cmd_notion_push(_make_args(str(input_path), force=True))

        mock_exp.archive_rows_for_session.assert_called_once()
        mock_exp.create_row.assert_called_once()

    def test_auth_error_aborts_remaining_tasks(self, tmp_path):
        input_path = tmp_path / "in.json"
        _write_json(str(input_path), {
            "session_id": "s1",
            "tasks": [
                {"title": "A"}, {"title": "B"}, {"title": "C"},
            ],
        })
        config = {
            "exporters": {
                "notion_hierarchical": {"api_token": "t", "root_page_id": "p"}
            }
        }

        mock_exp = MagicMock()
        # First task triggers auth error
        mock_exp.ensure_database.side_effect = NotionAuthError("unauthorized")
        mock_exp._cache = {"rows": {}, "years": {}, "databases": {}, "root_page_id": "p"}

        with patch.dict(os.environ, {}, clear=True), \
             patch("claude_diary.cli.notion_push.load_config", return_value=config), \
             patch("claude_diary.cli.notion_push.NotionHierarchicalExporter",
                   return_value=mock_exp), \
             pytest.raises(SystemExit) as exc:
            cmd_notion_push(_make_args(str(input_path)))

        # Exits 1 due to auth error
        assert exc.value.code == 1
        # JSON file preserved for retry
        assert input_path.exists()

    def test_bad_request_skips_one_task(self, tmp_path):
        input_path = tmp_path / "in.json"
        _write_json(str(input_path), {
            "session_id": "s1",
            "tasks": [{"title": "A"}, {"title": "B"}],
        })
        config = {
            "exporters": {
                "notion_hierarchical": {"api_token": "t", "root_page_id": "p"}
            }
        }

        mock_exp = MagicMock()
        mock_exp.ensure_database.return_value = "db"
        mock_exp.find_existing_row.return_value = None
        mock_exp.create_row.side_effect = [
            NotionBadRequest("malformed"),  # A fails
            "row_b_id",                      # B succeeds
        ]
        mock_exp._cache = {"rows": {}, "years": {}, "databases": {}, "root_page_id": "p"}

        with patch.dict(os.environ, {}, clear=True), \
             patch("claude_diary.cli.notion_push.load_config", return_value=config), \
             patch("claude_diary.cli.notion_push.NotionHierarchicalExporter",
                   return_value=mock_exp), \
             patch("claude_diary.cli.notion_push.get_head_branch", return_value="main"), \
             pytest.raises(SystemExit):
            cmd_notion_push(_make_args(str(input_path)))

        # B was still attempted after A failed
        assert mock_exp.create_row.call_count == 2
        # File preserved because of partial failure
        assert input_path.exists()
