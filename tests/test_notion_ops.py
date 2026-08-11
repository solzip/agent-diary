"""Tests for `agent-diary diary-notion ops` CLI."""

from argparse import Namespace
from unittest.mock import MagicMock, patch

import pytest

from claude_diary.cli.notion_ops import build_ops_report, cmd_notion_ops


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


def _args(year=2026, stale_days=7, json_output=False):
    return Namespace(year=year, stale_days=stale_days, json_output=json_output)


def _row(
    title,
    row_id=None,
    status="Implementation",
    project="working-diary",
    task_group="phase-3",
    blocked=False,
    review_status="Needs Review",
    next_action="",
    block_reason="",
    work_period="2026-06-01",
    parent_ids=None,
    priority="P2",
):
    if row_id is None:
        row_id = "row-%s" % title
    return {
        "id": row_id,
        "url": "https://notion.so/%s" % title,
        "properties": {
            "Name": {"title": [{"plain_text": title}]},
            "Status": {"select": {"name": status}},
            "Project": {"select": {"name": project}},
            "Task Group": {"select": {"name": task_group}},
            "Priority": {"select": {"name": priority}},
            "Blocked": {"checkbox": blocked},
            "Review Status": {"select": {"name": review_status}},
            "Next Action": {"rich_text": [{"plain_text": next_action}]},
            "Block Reason": {"rich_text": [{"plain_text": block_reason}]},
            "Work Period": {"date": {"start": work_period}},
            "Parent Task": {"relation": [{"id": pid} for pid in (parent_ids or [])]},
        },
    }


class TestBuildOpsReport:
    def test_counts_operations_signals(self):
        rows = [
            _row("blocked", blocked=True, block_reason="권한 필요"),
            _row("missing-next", next_action="", review_status="Deferred"),
            _row("review", next_action="검토 요청"),
            _row("done", status="Deployed", review_status="Reviewed", work_period="2026-06-05"),
        ]

        report = build_ops_report(rows, "2026-06-10", stale_days=7)

        assert report["counts"]["total"] == 4
        assert report["counts"]["active"] == 3
        assert report["counts"]["blocked"] == 1
        assert report["counts"]["needs_review"] == 2
        assert report["counts"]["missing_next_action"] == 2
        assert report["counts"]["stale"] == 3
        assert report["counts"]["verification_candidates"] == 2
        assert report["counts"]["today_plan_candidates"] == 1
        assert report["counts"]["parent_status_suggestions"] == 0
        assert report["today_plan_candidates"][0]["title"] == "review"
        assert report["verification_candidates"][0]["reason"]
        assert report["task_groups"]["phase-3"]["done"] == 1
        assert report["task_groups"]["phase-3"]["active"] == 3
        assert report["task_groups"]["phase-3"]["work_days"] == 2
        assert report["task_groups"]["phase-3"]["done_ratio"] == 0.25
        assert report["task_groups"]["phase-3"]["first_worked_on"] == "2026-06-01"
        assert report["task_groups"]["phase-3"]["last_worked_on"] == "2026-06-05"
        assert report["projects"]["working-diary"]["total"] == 4

    def test_archived_rows_are_ignored(self):
        row = _row("archived")
        row["archived"] = True

        report = build_ops_report([row], "2026-06-10")

        assert report["counts"]["total"] == 0

    def test_parent_status_suggestion_when_children_done(self):
        rows = [
            _row("parent", row_id="parent-row", status="Testing"),
            _row("child-a", status="Deployed", parent_ids=["parent-row"]),
            _row("child-b", status="Deployed", parent_ids=["parent-row"]),
        ]

        report = build_ops_report(rows, "2026-06-10")

        assert report["counts"]["parent_status_suggestions"] == 1
        suggestion = report["parent_status_suggestions"][0]
        assert suggestion["title"] == "parent"
        assert suggestion["suggested_status"] == "Deployed"
        assert suggestion["child_count"] == 2
        progress = report["parent_progress"][0]
        assert progress["title"] == "parent"
        assert progress["children"] == 2
        assert progress["done"] == 2
        assert progress["done_ratio"] == 1.0

    def test_parent_progress_counts_active_and_blocked_children(self):
        rows = [
            _row("parent", row_id="parent-row", status="Implementation"),
            _row("child-a", status="Deployed", parent_ids=["parent-row"]),
            _row("child-b", status="Testing", parent_ids=["parent-row"], blocked=True),
        ]

        report = build_ops_report(rows, "2026-06-10")

        progress = report["parent_progress"][0]
        assert progress["children"] == 2
        assert progress["done"] == 1
        assert progress["active"] == 1
        assert progress["blocked"] == 1
        assert progress["done_ratio"] == 0.5

    def test_parent_status_suggests_testing_when_child_reaches_testing(self):
        rows = [
            _row("parent", row_id="parent-row", status="Implementation"),
            _row("child", status="Testing", parent_ids=["parent-row"]),
        ]

        report = build_ops_report(rows, "2026-06-10")

        suggestion = report["parent_status_suggestions"][0]
        assert suggestion["suggested_status"] == "Testing"
        assert suggestion["reason"] == "at least one child task is in Testing"

    def test_parent_status_suggests_implementation_from_design(self):
        rows = [
            _row("parent", row_id="parent-row", status="Design"),
            _row("child", status="Implementation", parent_ids=["parent-row"]),
        ]

        report = build_ops_report(rows, "2026-06-10")

        suggestion = report["parent_status_suggestions"][0]
        assert suggestion["suggested_status"] == "Implementation"
        assert suggestion["reason"] == "at least one child task is in Implementation"

    def test_parent_status_reports_blocked_child_without_overwriting_status(self):
        rows = [
            _row("parent", row_id="parent-row", status="Testing"),
            _row("child", status="Implementation", blocked=True, parent_ids=["parent-row"]),
        ]

        report = build_ops_report(rows, "2026-06-10")

        suggestion = report["parent_status_suggestions"][0]
        assert suggestion["suggested_status"] == "Testing"
        assert suggestion["reason"] == "at least one child task is blocked"

    def test_today_plan_candidates_sorted_by_priority_then_age(self):
        rows = [
            _row("p2-old", next_action="계속", priority="P2", work_period="2026-06-01"),
            _row("p1-new", next_action="먼저", priority="P1", work_period="2026-06-09"),
            _row("blocked", next_action="대기", priority="P0", blocked=True),
            _row("no-action", next_action="", priority="P0"),
        ]

        report = build_ops_report(rows, "2026-06-10")

        assert report["counts"]["today_plan_candidates"] == 2
        assert [item["title"] for item in report["today_plan_candidates"]] == [
            "p1-new",
            "p2-old",
        ]

    def test_verification_candidates_include_reasons_and_sort_testing_first(self):
        rows = [
            _row("implementation", status="Implementation", review_status="Deferred", priority="P0"),
            _row("testing", status="Testing", next_action="", review_status="Needs Review", priority="P3"),
            _row("reviewed", status="Testing", next_action="배포", review_status="Reviewed"),
            _row("blocked", status="Testing", blocked=True, review_status="Needs Review"),
        ]

        report = build_ops_report(rows, "2026-06-10")

        assert report["counts"]["verification_candidates"] == 2
        assert [item["title"] for item in report["verification_candidates"]] == [
            "testing",
            "implementation",
        ]
        assert "testing_without_next_action" in report["verification_candidates"][0]["reason"]
        assert "implementation_review_deferred" in report["verification_candidates"][1]["reason"]


class TestCmdNotionOps:
    def test_missing_credentials_exits(self):
        with patch("claude_diary.cli.notion_ops.load_config", return_value={}), \
             patch.dict("os.environ", {}, clear=True), \
             pytest.raises(SystemExit) as exc:
            cmd_notion_ops(_args())

        assert exc.value.code == 1

    def test_missing_database_exits_without_creating(self, capsys):
        exporter = MagicMock()
        exporter.resolve_existing_database.return_value = None

        with patch("claude_diary.cli.notion_ops.load_config", return_value=_config()), \
             patch.dict("os.environ", {}, clear=True), \
             patch("claude_diary.cli.notion_ops.NotionHierarchicalExporter", return_value=exporter), \
             pytest.raises(SystemExit) as exc:
            cmd_notion_ops(_args(year=2027))

        assert exc.value.code == 1
        exporter.resolve_existing_database.assert_called_once_with(2027)
        exporter.ensure_database.assert_not_called()
        exporter.query_database_rows.assert_not_called()
        captured = capsys.readouterr()
        assert "Database: missing" in captured.out

    def test_prints_operations_report(self, capsys):
        exporter = MagicMock()
        exporter.resolve_existing_database.return_value = "db1"
        exporter.query_database_rows.return_value = [
            _row("blocked", blocked=True, block_reason="토큰 확인"),
            _row("done", status="Deployed", review_status="Reviewed", work_period="2026-06-05"),
        ]
        exporter.get_database_property_map.return_value = {}

        with patch("claude_diary.cli.notion_ops.load_config", return_value=_config()), \
             patch.dict("os.environ", {}, clear=True), \
             patch("claude_diary.cli.notion_ops.NotionHierarchicalExporter", return_value=exporter):
            cmd_notion_ops(_args(year=2026, stale_days=3))

        exporter.query_database_rows.assert_called_once_with("db1")
        exporter.get_database_property_map.assert_called_once_with("db1")
        captured = capsys.readouterr()
        assert "[agent-diary diary-notion ops]" in captured.out
        assert "Rows: 2 total, 1 active" in captured.out
        assert "Blocked: 1" in captured.out
        assert "Today-plan candidates:" in captured.out
        assert "Verification candidates:" in captured.out
        assert "Task Groups:" in captured.out
        assert "blocked: 토큰 확인" in captured.out
        assert "Projects:" in captured.out

    def test_json_output(self, capsys):
        exporter = MagicMock()
        exporter.resolve_existing_database.return_value = "db1"
        exporter.query_database_rows.return_value = [_row("row1")]
        exporter.get_database_property_map.return_value = {}

        with patch("claude_diary.cli.notion_ops.load_config", return_value=_config()), \
             patch.dict("os.environ", {}, clear=True), \
             patch("claude_diary.cli.notion_ops.NotionHierarchicalExporter", return_value=exporter):
            cmd_notion_ops(_args(json_output=True))

        captured = capsys.readouterr()
        assert '"counts"' in captured.out
        assert '"row1"' in captured.out
