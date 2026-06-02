"""Tests for `claude-diary diary-notion ensure` CLI."""

from argparse import Namespace
from unittest.mock import ANY, MagicMock, patch

import pytest

from claude_diary.cli.notion_ensure import cmd_notion_ensure
from claude_diary.exporters.notion_hierarchical import SCHEMA_VERSION
from claude_diary.exporters.notion_views import EnsureViewsResult, ViewConflict


def _config():
    return {
        "timezone_offset": 9,
        "exporters": {
            "notion_hierarchical": {
                "api_token": "token",
                "root_page_id": "root_page",
            }
        },
    }


def _args(year=2026, dry_run=False):
    return Namespace(year=year, dry_run=dry_run)


class TestCmdNotionEnsure:
    def test_missing_credentials_exits(self):
        with patch("claude_diary.cli.notion_ensure.load_config", return_value={}), \
             patch.dict("os.environ", {}, clear=True), \
             pytest.raises(SystemExit) as exc:
            cmd_notion_ensure(_args())

        assert exc.value.code == 1

    def test_non_dry_run_ensures_schema_and_views(self, capsys):
        exporter = MagicMock()
        exporter.ensure_database.return_value = "db1"
        result = EnsureViewsResult(created=["작업 계층"], verified=["오늘 작업"])
        ensurer = MagicMock()
        ensurer.ensure.return_value = result

        with patch("claude_diary.cli.notion_ensure.load_config", return_value=_config()), \
             patch.dict("os.environ", {}, clear=True), \
             patch("claude_diary.cli.notion_ensure.NotionHierarchicalExporter", return_value=exporter), \
             patch("claude_diary.cli.notion_ensure.NotionViewsClient") as client_cls, \
             patch("claude_diary.cli.notion_ensure.CoreViewsEnsurer", return_value=ensurer):
            cmd_notion_ensure(_args(year=2026))

        exporter.load_cache.assert_called_once()
        exporter.ensure_database.assert_called_once_with(2026, force_schema=True)
        exporter.save_cache.assert_called_once()
        client_cls.assert_called_once_with({"api_token": "token"})
        ensurer.ensure.assert_called_once_with("db1", ANY, dry_run=False)
        captured = capsys.readouterr()
        assert "Schema: %s ensured" % SCHEMA_VERSION in captured.out
        assert "+ 작업 계층" in captured.out
        assert "= 오늘 작업 (verified)" in captured.out

    def test_prints_updated_and_update_planned(self, capsys):
        exporter = MagicMock()
        exporter.ensure_database.return_value = "db1"
        result = EnsureViewsResult(
            updated=["작업 계층"],
            updates_planned=["오늘 작업"],
        )
        ensurer = MagicMock()
        ensurer.ensure.return_value = result

        with patch("claude_diary.cli.notion_ensure.load_config", return_value=_config()), \
             patch.dict("os.environ", {}, clear=True), \
             patch("claude_diary.cli.notion_ensure.NotionHierarchicalExporter", return_value=exporter), \
             patch("claude_diary.cli.notion_ensure.CoreViewsEnsurer", return_value=ensurer):
            cmd_notion_ensure(_args(year=2026))

        captured = capsys.readouterr()
        assert "~ 작업 계층 (updated)" in captured.out
        assert "~ 오늘 작업 (update planned)" in captured.out

    def test_dry_run_missing_database_prints_plan_without_writes(self, capsys):
        exporter = MagicMock()
        exporter.resolve_existing_database.return_value = None

        with patch("claude_diary.cli.notion_ensure.load_config", return_value=_config()), \
             patch.dict("os.environ", {}, clear=True), \
             patch("claude_diary.cli.notion_ensure.NotionHierarchicalExporter", return_value=exporter), \
             patch("claude_diary.cli.notion_ensure.CoreViewsEnsurer") as ensurer_cls:
            cmd_notion_ensure(_args(year=2027, dry_run=True))

        exporter.load_cache.assert_called_once()
        exporter.resolve_existing_database.assert_called_once_with(2027)
        exporter.ensure_database.assert_not_called()
        exporter.save_cache.assert_not_called()
        ensurer_cls.assert_not_called()
        captured = capsys.readouterr()
        assert "Database: missing" in captured.out
        assert "+ create 5 core views" in captured.out
        assert "+ create 5 operating views" in captured.out

    def test_conflict_exits_1(self):
        exporter = MagicMock()
        exporter.ensure_database.return_value = "db1"
        result = EnsureViewsResult(conflicts=[
            ViewConflict("오늘 작업", "missing Date=today filter"),
        ])
        ensurer = MagicMock()
        ensurer.ensure.return_value = result

        with patch("claude_diary.cli.notion_ensure.load_config", return_value=_config()), \
             patch.dict("os.environ", {}, clear=True), \
             patch("claude_diary.cli.notion_ensure.NotionHierarchicalExporter", return_value=exporter), \
             patch("claude_diary.cli.notion_ensure.CoreViewsEnsurer", return_value=ensurer), \
             pytest.raises(SystemExit) as exc:
            cmd_notion_ensure(_args(year=2026))

        assert exc.value.code == 1
