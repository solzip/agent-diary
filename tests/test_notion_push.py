"""Tests for `claude-diary diary-notion push` CLI."""

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
    _normalize_purpose,
    _normalize_work_period,
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


class TestNormalizePurpose:
    def test_valid_purpose_passes_through(self):
        assert _normalize_purpose("Feature") == "Feature"

    def test_aliases_normalized(self):
        assert _normalize_purpose("documentation") == "Docs"
        assert _normalize_purpose("testing") == "Test"

    def test_missing_or_unknown_returns_general(self):
        assert _normalize_purpose("") == "General"
        assert _normalize_purpose(None) == "General"
        assert _normalize_purpose("unexpected") == "General"


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
        task["purpose"] = "Feature"
        props = _build_properties(task, "2026-05-26", "feat/x", git_info, "sess1", 0)
        assert props["Name"]["title"][0]["text"]["content"] == "DB 결정"
        assert props["Date"]["date"]["start"] == "2026-05-26"
        assert props["Work Period"]["date"]["start"] == "2026-05-26"
        assert props["Project"]["select"]["name"] == "diary"
        assert props["Purpose"]["select"]["name"] == "Feature"
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

    def test_v2_appendix_files_counted(self):
        task = {
            "title": "v2 task",
            "project": "diary",
            "appendix": {
                "files_modified": ["src/a.py", "src/b.py"],
                "files_created": ["tests/test_a.py"],
            },
        }
        props = _build_properties(task, "2026-05-26", "main", {}, "sess1", 0)
        assert props["Files"]["number"] == 3

    def test_v2_next_actions_feed_next_action_property(self):
        task = {
            "title": "v2 task",
            "project": "diary",
            "next_actions": ["Run dry-run preview", "Push to Notion"],
        }
        props = _build_properties(task, "2026-05-26", "main", {}, "sess1", 0)
        assert props["Next Action"]["rich_text"][0]["text"]["content"] == "Run dry-run preview"

    def test_report_schema_version_property_included_when_stamped(self):
        task = dict(self._base_task(), _report_schema_version="v2")
        props = _build_properties(task, "2026-05-26", "main", {}, "sess1", 0)
        assert props["Schema Version"]["select"]["name"] == "v2"

    def test_missing_purpose_defaults_to_general(self):
        task = self._base_task()
        props = _build_properties(task, "2026-05-26", "main", {}, "sess1", 0)
        assert props["Purpose"]["select"]["name"] == "General"

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
        assert "Parent Task" not in props

    def test_work_period_range_included(self):
        task = dict(self._base_task(), work_period={"start": "2026-05-25", "end": "2026-05-26"})
        props = _build_properties(task, "2026-05-26", "main", {}, "sess1", 0)
        assert props["Work Period"]["date"] == {
            "start": "2026-05-25",
            "end": "2026-05-26",
        }

    def test_missing_project_falls_back_to_cwd_folder(self):
        task = dict(self._base_task())
        task.pop("project")
        props = _build_properties(
            task, "2026-05-26", "main", {}, "sess1", 0,
            "C:\\Users\\sol\\work\\actual-project",
        )
        assert props["Project"]["select"]["name"] == "actual-project"

    def test_unknown_project_falls_back_to_cwd_folder(self):
        task = dict(self._base_task(), project="unknown")
        props = _build_properties(
            task, "2026-05-26", "main", {}, "sess1", 0,
            "/home/sol/work/actual-project",
        )
        assert props["Project"]["select"]["name"] == "actual-project"

    def test_v7_operating_properties_included(self):
        task = dict(
            self._base_task(),
            priority="high",
            next_action="다른 세션에서 ensure 검증",
            blocked=True,
            block_reason="Notion API 응답 확인 필요",
            carryover=True,
        )
        props = _build_properties(task, "2026-06-02", "main", {}, "sess1", 0)

        assert props["Priority"]["select"]["name"] == "P1"
        assert props["Next Action"]["rich_text"][0]["text"]["content"] == "다른 세션에서 ensure 검증"
        assert props["Blocked"]["checkbox"] is True
        assert props["Block Reason"]["rich_text"][0]["text"]["content"] == "Notion API 응답 확인 필요"
        assert props["Carryover"]["checkbox"] is True

    def test_review_state_is_system_owned(self):
        # The session that produced the work never gets to call it reviewed.
        task = dict(self._base_task(), review_status="Reviewed", last_reviewed="2026-06-02")
        props = _build_properties(task, "2026-06-02", "main", {}, "sess1", 0)

        assert props["Review Status"]["select"]["name"] == "Needs Review"
        assert "Last Reviewed" not in props


class TestNormalizeWorkPeriod:
    def test_missing_falls_back_to_date(self):
        assert _normalize_work_period(None, "2026-05-26") == {"start": "2026-05-26"}

    def test_single_date_collapses_to_execution_date(self):
        # A lone agent-supplied day is not trusted over the day push actually ran.
        assert _normalize_work_period("2026-05-25", "2026-05-26") == {"start": "2026-05-26"}

    def test_execution_date_is_kept(self):
        assert _normalize_work_period("2026-05-26", "2026-05-26") == {"start": "2026-05-26"}

    def test_future_range_end_is_clamped(self):
        assert _normalize_work_period("2026-05-24..2026-09-01", "2026-05-26") == {
            "start": "2026-05-24",
            "end": "2026-05-26",
        }

    def test_future_start_falls_back(self):
        assert _normalize_work_period("2026-09-01", "2026-05-26") == {"start": "2026-05-26"}

    def test_string_range(self):
        assert _normalize_work_period("2026-05-25..2026-05-26", "2026-05-26") == {
            "start": "2026-05-25",
            "end": "2026-05-26",
        }

    def test_invalid_falls_back(self):
        assert _normalize_work_period("not-a-date", "2026-05-26") == {"start": "2026-05-26"}


class TestTaskGroupOrdinals:
    def test_ordinal_counts_distinct_prior_sessions(self):
        from claude_diary.cli.notion_push import _resolve_task_group_ordinals
        mock_exp = MagicMock()
        mock_exp.ensure_database.return_value = "db"
        mock_exp.get_task_group_session_ids.return_value = {"s1", "s2", "s3"}

        tasks = [{"title": "A", "task_group": "auth-refactor"}]
        ordinals = _resolve_task_group_ordinals(mock_exp, 2026, tasks, "s4")

        assert ordinals == {"auth-refactor": 4}

    def test_repush_of_same_session_does_not_advance_ordinal(self):
        from claude_diary.cli.notion_push import _resolve_task_group_ordinals
        mock_exp = MagicMock()
        mock_exp.ensure_database.return_value = "db"
        mock_exp.get_task_group_session_ids.return_value = {"s1", "s2"}

        tasks = [{"title": "A", "task_group": "auth-refactor"}]
        ordinals = _resolve_task_group_ordinals(mock_exp, 2026, tasks, "s2")

        assert ordinals == {"auth-refactor": 2}

    def test_lookup_failure_is_not_fatal(self):
        from claude_diary.cli.notion_push import _resolve_task_group_ordinals
        mock_exp = MagicMock()
        mock_exp.ensure_database.return_value = "db"
        mock_exp.get_task_group_session_ids.side_effect = RuntimeError("boom")

        tasks = [{"title": "A", "task_group": "auth-refactor"}]
        assert _resolve_task_group_ordinals(mock_exp, 2026, tasks, "s1") == {}

    def test_tasks_without_group_are_skipped(self):
        from claude_diary.cli.notion_push import _resolve_task_group_ordinals
        mock_exp = MagicMock()
        assert _resolve_task_group_ordinals(mock_exp, 2026, [{"title": "A"}], "s1") == {}
        mock_exp.ensure_database.assert_not_called()

    def test_first_session_title_is_left_alone(self):
        from claude_diary.cli.notion_push import _stamp_task_group_ordinals
        tasks = [{"title": "인증 미들웨어", "task_group": "auth-refactor"}]
        _stamp_task_group_ordinals(tasks, {"auth-refactor": 1})
        assert tasks[0]["title"] == "인증 미들웨어"

    def test_continuation_title_gets_ordinal_suffix(self):
        from claude_diary.cli.notion_push import _stamp_task_group_ordinals
        tasks = [
            {"title": "인증 미들웨어", "task_group": "auth-refactor"},
            {"title": "무관한 작업"},
        ]
        _stamp_task_group_ordinals(tasks, {"auth-refactor": 3})
        assert tasks[0]["title"] == "인증 미들웨어 (3차)"
        assert tasks[1]["title"] == "무관한 작업"

    def test_stamping_is_idempotent(self):
        from claude_diary.cli.notion_push import _stamp_task_group_ordinals
        tasks = [{"title": "인증 미들웨어", "task_group": "auth-refactor"}]
        _stamp_task_group_ordinals(tasks, {"auth-refactor": 2})
        _stamp_task_group_ordinals(tasks, {"auth-refactor": 2})
        assert tasks[0]["title"] == "인증 미들웨어 (2차)"

    def test_push_writes_the_ordinal_into_the_row_title(self, tmp_path):
        input_path = tmp_path / "in.json"
        with open(str(input_path), "w", encoding="utf-8") as f:
            json.dump({
                "session_id": "s3",
                "tasks": [{"title": "인증 미들웨어", "task_group": "auth-refactor"}],
            }, f)

        mock_exp = MagicMock()
        mock_exp.ensure_database.return_value = "db_xyz"
        mock_exp.find_existing_row.return_value = None
        mock_exp.create_row.return_value = "row_a"
        mock_exp.get_task_group_session_ids.return_value = {"s1", "s2"}
        mock_exp._cache = {"rows": {}, "years": {}, "databases": {}, "root_page_id": "p"}

        args = MagicMock()
        args.input = str(input_path)
        args.force = False
        args.dry_run = False
        args.preview_file = ""
        args.artifact_dir = ""
        args.no_artifacts = False

        config = {"exporters": {"notion_hierarchical": {"api_token": "t", "root_page_id": "p"}}}
        with patch.dict(os.environ, {}, clear=True), \
             patch("claude_diary.cli.notion_push.load_config", return_value=config), \
             patch("claude_diary.cli.notion_push.NotionHierarchicalExporter", return_value=mock_exp), \
             patch("claude_diary.cli.notion_push.get_head_branch", return_value="main"), \
             pytest.raises(SystemExit):
            cmd_notion_push(args)

        props = mock_exp.create_row.call_args.args[1]
        assert props["Name"]["title"][0]["text"]["content"] == "인증 미들웨어 (3차)"


class TestDependsOnWiring:
    def _make_args(self, input_path, force=False):
        args = MagicMock()
        args.input = input_path
        args.force = force
        args.dry_run = False
        args.preview_file = ""
        args.artifact_dir = ""
        args.no_artifacts = False
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

    def test_wire_depends_on_only_links_top_level_tasks(self):
        """Sub-items use Parent Task, while Depends On is only for main rows."""
        from claude_diary.cli.notion_push import _wire_depends_on
        mock_exp = MagicMock()
        tasks = [
            {"title": "Main A"},
            {"title": "Sub A", "parent_index": 0, "depends_on_indices": [0]},
            {"title": "Main B", "depends_on_indices": [0, 1]},
        ]
        row_ids = {0: "row_a", 1: "row_sub_a", 2: "row_b"}

        _wire_depends_on(mock_exp, tasks, row_ids)

        mock_exp.update_row_relation.assert_called_once_with("row_b", ["row_a"])

    _NATIVE_PROP_MAP = {
        "Parent item": {
            "id": "P", "type": "relation",
            "relation": {"type": "dual_property",
                         "dual_property": {"synced_property_name": "Sub-item"}},
        },
        "Sub-item": {
            "id": "C", "type": "relation",
            "relation": {"type": "dual_property",
                         "dual_property": {"synced_property_name": "Parent item"}},
        },
    }

    def test_wire_parent_tasks_calls_update_for_children(self, tmp_path):
        input_path = tmp_path / "in.json"
        self._write_json(str(input_path), {
            "session_id": "s1",
            "tasks": [
                {"title": "A"},
                {"title": "B", "parent_index": 0},
                {"title": "C", "parent_task_index": 1},
            ],
        })
        config = {
            "exporters": {
                "notion_hierarchical": {"api_token": "t", "root_page_id": "p"}
            }
        }

        mock_exp = MagicMock()
        mock_exp.ensure_database.return_value = "db_xyz"
        mock_exp.get_database_property_map.return_value = self._NATIVE_PROP_MAP
        mock_exp.find_existing_row.return_value = None
        mock_exp.create_row.side_effect = ["row_a", "row_b", "row_c"]
        mock_exp._cache = {"rows": {}, "years": {}, "databases": {}, "root_page_id": "p"}

        with patch.dict(os.environ, {}, clear=True), \
             patch("claude_diary.cli.notion_push.load_config", return_value=config), \
             patch("claude_diary.cli.notion_push.NotionHierarchicalExporter",
                   return_value=mock_exp), \
             patch("claude_diary.cli.notion_push.get_head_branch", return_value="main"), \
             pytest.raises(SystemExit):
            cmd_notion_push(self._make_args(str(input_path)))

        # children are wired into the NATIVE parent relation (single write each)
        calls = mock_exp.update_row_native_parent.call_args_list
        assert len(calls) == 2
        assert calls[0].args == ("row_b", "row_a", "Parent item")
        assert calls[1].args == ("row_c", "row_b", "Parent item")
        mock_exp.update_row_parent.assert_not_called()
        mock_exp.update_row_subitems.assert_not_called()

    def test_wire_parent_tasks_writes_native_parent(self):
        from claude_diary.cli.notion_push import _wire_parent_tasks
        mock_exp = MagicMock()
        mock_exp.ensure_database.return_value = "db"
        mock_exp.get_database_property_map.return_value = self._NATIVE_PROP_MAP
        tasks = [{"title": "A"}, {"title": "B", "parent_index": 0}]
        row_ids = {0: "row_a", 1: "row_b"}
        failures = _wire_parent_tasks(mock_exp, 2026, tasks, row_ids)
        mock_exp.update_row_native_parent.assert_called_once_with(
            "row_b", "row_a", "Parent item"
        )
        assert failures == []

    def test_wire_parent_tasks_reports_failure_when_no_native(self, capsys):
        from claude_diary.cli.notion_push import _wire_parent_tasks
        mock_exp = MagicMock()
        mock_exp.ensure_database.return_value = "db"
        # only the legacy reserved relations exist -> no native relation
        mock_exp.get_database_property_map.return_value = {
            "Parent Task": {"id": "x", "type": "relation",
                            "relation": {"type": "dual_property",
                                         "dual_property": {"synced_property_name": "Sub-items"}}},
            "Sub-items": {"id": "y", "type": "relation",
                          "relation": {"type": "dual_property",
                                       "dual_property": {"synced_property_name": "Parent Task"}}},
        }
        tasks = [{"title": "A"}, {"title": "B", "parent_index": 0}]
        row_ids = {0: "row_a", 1: "row_b"}
        failures = _wire_parent_tasks(mock_exp, 2026, tasks, row_ids)
        mock_exp.update_row_native_parent.assert_not_called()
        # The child row could not be nested — surfaced instead of silently dropped.
        assert [f[0] for f in failures] == [1]
        assert "sub-item" in failures[0][2]
        assert "Sub-items" in capsys.readouterr().out

    def test_wire_parent_tasks_skips_missing_parent(self):
        from claude_diary.cli.notion_push import _wire_parent_tasks
        mock_exp = MagicMock()
        tasks = [
            {"title": "A"},
            {"title": "B", "parent_index": 99},
        ]
        row_ids = {0: "row_a", 1: "row_b"}
        _wire_parent_tasks(mock_exp, 2026, tasks, row_ids)
        mock_exp.update_row_native_parent.assert_not_called()

    def test_wire_parent_tasks_skips_self_parent(self):
        """A task whose parent_index points at itself must not be wired.

        Mirrors the self-reference guard in _wire_depends_on; without it a row
        would be set as its own parent.
        """
        from claude_diary.cli.notion_push import _wire_parent_tasks
        mock_exp = MagicMock()
        tasks = [{"title": "A", "parent_index": 0}]
        row_ids = {0: "row_a"}
        failures = _wire_parent_tasks(mock_exp, 2026, tasks, row_ids)
        mock_exp.update_row_native_parent.assert_not_called()
        assert failures == []


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
    args.dry_run = False
    args.preview_file = ""
    args.artifact_dir = ""
    args.no_artifacts = False
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

    def test_v2_appendix_commit_hashes_drive_git_info_and_properties(self, tmp_path):
        input_path = tmp_path / "in.json"
        _write_json(str(input_path), {
            "session_id": "s1",
            "tasks": [{
                "title": "v2 task",
                "project": "diary",
                "appendix": {
                    "files_modified": ["src/a.py"],
                    "files_created": ["tests/test_a.py"],
                    "commit_hashes": ["abc1234"],
                },
            }],
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
             patch("claude_diary.cli.notion_push.get_branch_for_commit",
                   return_value="feat/v2") as mock_branch, \
             patch("claude_diary.cli.notion_push.get_commit_info",
                   return_value={"hash": "abc1234", "short_hash": "abc1234", "message": "v2"}), \
             patch("claude_diary.cli.notion_push.get_diff_stat_for_commits",
                   return_value={"added": 10, "deleted": 2, "files": 2}), \
             pytest.raises(SystemExit) as exc:
            cmd_notion_push(_make_args(str(input_path)))

        assert exc.value.code == 0
        mock_branch.assert_called_once_with(os.getcwd(), "abc1234")
        props = mock_exp.create_row.call_args.args[1]
        assert props["Branch"]["select"]["name"] == "feat/v2"
        assert props["Files"]["number"] == 2
        assert props["Commits"]["number"] == 1
        assert props["Lines"]["number"] == 12
        assert not input_path.exists()

    def test_push_dry_run_renders_preview_without_credentials_or_cleanup(self, tmp_path, capsys):
        input_path = tmp_path / "in.json"
        _write_json(str(input_path), {
            "session_id": "s1",
            "tasks": [{
                "title": "dry run v2",
                "project": "diary",
                "purpose": "Test",
                "summary": {
                    "intro": "Compact report preview",
                    "outcomes": ["Core renderer ready"],
                    "verification": ["Tests passed"],
                    "remaining": ["Install skill"],
                },
                "work": {
                    "context": "v2 rollout",
                    "scope": "push preview",
                    "approach": "render blocks locally",
                    "state": "Testing",
                },
                "appendix": {
                    "files_modified": ["src/claude_diary/cli/notion_push.py"],
                    "commands_run": ["python -m pytest -q"],
                },
            }],
        })
        args = _make_args(str(input_path))
        args.dry_run = True

        with patch.dict(os.environ, {}, clear=True), \
             patch("claude_diary.cli.notion_push.load_config", return_value={}), \
             patch("claude_diary.cli.notion_push.NotionHierarchicalExporter") as mock_exporter, \
             patch("claude_diary.cli.notion_push.get_head_branch", return_value="feat/v2"):
            cmd_notion_push(args)

        out = capsys.readouterr().out
        assert "[claude-diary diary-notion push --dry-run]" in out
        assert "dry run v2" in out
        assert "[Callout] Compact report preview" in out
        assert "## 결과" in out
        assert "> 명령 / 파일 / 커밋 근거" in out
        mock_exporter.assert_not_called()
        assert input_path.exists()

    def test_v2_validation_rejects_missing_normalized_sections_before_auth(self, tmp_path, capsys):
        input_path = tmp_path / "in.json"
        _write_json(str(input_path), {
            "session_id": "s1",
            "schema_version": 2,
            "tasks": [{"title": "bad v2"}],
        })

        with patch.dict(os.environ, {}, clear=True), \
             patch("claude_diary.cli.notion_push.load_config", return_value={}), \
             patch("claude_diary.cli.notion_push.NotionHierarchicalExporter") as mock_exporter, \
             pytest.raises(SystemExit) as exc:
            cmd_notion_push(_make_args(str(input_path)))

        assert exc.value.code == 1
        err = capsys.readouterr().err
        assert "Invalid input" in err
        assert "tasks[0].summary must be an object" in err
        mock_exporter.assert_not_called()
        assert input_path.exists()

    def test_dry_run_writes_preview_and_artifacts(self, tmp_path, capsys):
        input_path = tmp_path / "in.json"
        preview_path = tmp_path / "preview.md"
        artifact_root = tmp_path / "runs"
        _write_json(str(input_path), {
            "session_id": "s1",
            "schema_version": 2,
            "tasks": [{
                "title": "dry run artifacts",
                "project": "diary",
                "summary": {
                    "intro": "Preview with artifacts",
                    "outcomes": ["Rendered"],
                    "verification": ["Checked"],
                    "remaining": [],
                },
                "work": {
                    "context": "Artifact validation",
                    "scope": "Preview file and manifest",
                    "approach": "Local render",
                    "state": "Testing",
                },
                "appendix": {
                    "files_modified": ["src/claude_diary/cli/notion_push.py"],
                    "commands_run": ["python -m pytest -q"],
                },
            }],
        })
        args = _make_args(str(input_path))
        args.dry_run = True
        args.preview_file = str(preview_path)
        args.artifact_dir = str(artifact_root)

        with patch.dict(os.environ, {}, clear=True), \
             patch("claude_diary.cli.notion_push.load_config", return_value={}), \
             patch("claude_diary.cli.notion_push.get_head_branch", return_value="feat/v2"):
            cmd_notion_push(args)

        out = capsys.readouterr().out
        assert "Preview file:" in out
        assert "preview.md" in out
        assert "manifest.json" in out
        assert preview_path.exists()
        assert "Schema Version: v2" in preview_path.read_text(encoding="utf-8")
        run_dirs = list(artifact_root.iterdir())
        assert len(run_dirs) == 1
        names = {p.name for p in run_dirs[0].iterdir()}
        assert {"input.json", "git-diff.patch", "preview.md", "manifest.json"} <= names
        manifest = json.loads((run_dirs[0] / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["run_id"]
        assert any(a["kind"] == "preview" for a in manifest["artifacts"])
        assert any(a["kind"] == "manifest" for a in manifest["artifacts"]) is False

    def test_missing_project_uses_command_cwd(self, tmp_path, monkeypatch):
        input_path = tmp_path / "in.json"
        _write_json(str(input_path), {
            "session_id": "s1",
            "tasks": [{"title": "task A"}],
        })
        workdir = tmp_path / "real-project"
        workdir.mkdir()
        monkeypatch.chdir(workdir)
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
        props = mock_exp.create_row.call_args.args[1]
        assert props["Project"]["select"]["name"] == "real-project"

    def test_notion_body_uses_korean_labels_even_when_config_lang_en(self, tmp_path):
        input_path = tmp_path / "in.json"
        _write_json(str(input_path), {
            "session_id": "s1",
            "tasks": [{"title": "작업 제목", "summary_hints": ["요약"], "project": "diary"}],
        })
        config = {
            "lang": "en",
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
             patch("claude_diary.cli.notion_push.build_notion_blocks", return_value=[]) as mock_blocks, \
             pytest.raises(SystemExit) as exc:
            cmd_notion_push(_make_args(str(input_path)))

        assert exc.value.code == 0
        mock_blocks.assert_called_once()
        assert mock_blocks.call_args.args[2] == "ko"

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
             pytest.raises(SystemExit) as exc:
            cmd_notion_push(_make_args(str(input_path)))

        assert exc.value.code == 1
        # B was still attempted after A failed
        assert mock_exp.create_row.call_count == 2
        # File preserved because of partial failure
        assert input_path.exists()
