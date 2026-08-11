"""Tests for `working-diary diary-notion review`."""

from unittest.mock import MagicMock, patch

import pytest

from claude_diary.cli.notion_review import build_review_queue, cmd_notion_review


def _row(title, review_status="Needs Review", date="2026-06-02", archived=False,
         project="working-diary", status="Implementation", task_group=""):
    return {
        "id": "row_%s" % title,
        "archived": archived,
        "properties": {
            "Name": {"title": [{"plain_text": title}]},
            "Date": {"date": {"start": date}},
            "Project": {"select": {"name": project}},
            "Status": {"select": {"name": status}},
            "Task Group": {"select": {"name": task_group}} if task_group else {"select": None},
            "Review Status": {"select": {"name": review_status}} if review_status else {"select": None},
        },
    }


def _config():
    return {"exporters": {"notion_hierarchical": {"api_token": "t", "root_page_id": "p"}}}


def _args(apply_changes=False, year=2026):
    args = MagicMock()
    args.apply = apply_changes
    args.year = year
    return args


class TestBuildReviewQueue:
    def test_only_needs_review_rows_are_queued(self):
        rows = [
            _row("pending"),
            _row("done", review_status="Reviewed"),
            _row("deferred", review_status="Deferred"),
        ]
        assert [item["title"] for item in build_review_queue(rows)] == ["pending"]

    def test_rows_without_review_state_are_left_alone(self):
        # Pre-workflow rows must not be swept into a bulk --apply.
        assert build_review_queue([_row("legacy", review_status="")]) == []

    def test_archived_rows_are_excluded(self):
        assert build_review_queue([_row("gone", archived=True)]) == []

    def test_queue_is_newest_first(self):
        rows = [
            _row("older", date="2026-06-01"),
            _row("newest", date="2026-06-09"),
            _row("middle", date="2026-06-05"),
        ]
        assert [item["title"] for item in build_review_queue(rows)] == [
            "newest", "middle", "older",
        ]

    def test_queue_carries_context_for_the_listing(self):
        item = build_review_queue([_row("일지 렌더링 정리", task_group="notion-body")])[0]
        assert item["id"] == "row_일지 렌더링 정리"
        assert item["project"] == "working-diary"
        assert item["status"] == "Implementation"
        assert item["task_group"] == "notion-body"


class TestCmdNotionReview:
    def _exporter(self, rows):
        exporter = MagicMock()
        exporter.resolve_existing_database.return_value = "db1"
        exporter.query_database_rows.return_value = rows
        return exporter

    def _run(self, exporter, args):
        with patch("claude_diary.cli.notion_review.load_config", return_value=_config()), \
             patch.dict("os.environ", {}, clear=True), \
             patch("claude_diary.cli.notion_review.NotionHierarchicalExporter",
                   return_value=exporter), \
             patch("claude_diary.cli.notion_review.resolve_year_and_today",
                   return_value=(2026, "2026-06-10")):
            cmd_notion_review(args)

    def test_listing_does_not_write(self, capsys):
        exporter = self._exporter([_row("검토 대기 작업")])
        self._run(exporter, _args())

        exporter.update_row_review.assert_not_called()
        out = capsys.readouterr().out
        assert "Awaiting review: 1" in out
        assert "검토 대기 작업" in out
        assert "--apply" in out

    def test_apply_marks_each_queued_row_reviewed(self, capsys):
        exporter = self._exporter([_row("a"), _row("b")])
        with pytest.raises(SystemExit) as exc:
            self._run(exporter, _args(apply_changes=True))

        assert exc.value.code == 0
        assert exporter.update_row_review.call_count == 2
        assert exporter.update_row_review.call_args.args[1:] == ("Reviewed", "2026-06-10")
        assert "Marked reviewed: 2" in capsys.readouterr().out

    def test_empty_queue_writes_nothing_and_does_not_exit_nonzero(self, capsys):
        exporter = self._exporter([_row("done", review_status="Reviewed")])
        self._run(exporter, _args(apply_changes=True))

        exporter.update_row_review.assert_not_called()
        assert "Nothing awaiting review." in capsys.readouterr().out

    def test_partial_failure_reports_and_exits_nonzero(self, capsys):
        exporter = self._exporter([_row("a"), _row("b")])
        exporter.update_row_review.side_effect = [None, RuntimeError("boom")]
        with pytest.raises(SystemExit) as exc:
            self._run(exporter, _args(apply_changes=True))

        assert exc.value.code == 1
        captured = capsys.readouterr()
        assert "Marked reviewed: 1" in captured.out
        assert "boom" in captured.err

    def test_missing_database_exits_nonzero(self, capsys):
        exporter = MagicMock()
        exporter.resolve_existing_database.return_value = None
        with pytest.raises(SystemExit) as exc:
            self._run(exporter, _args())

        assert exc.value.code == 1
        assert "ensure" in capsys.readouterr().out
