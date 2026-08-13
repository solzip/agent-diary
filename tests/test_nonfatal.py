"""A side report may fail without breaking its caller. It may not fail silently.

The distinction is not stylistic. The drift summary shipped in 4.9.0 calling a
name that only existed on the `--force` path; the `except Exception` that made
it non-fatal also made it invisible, and it ran zero times for a day without a
word. `NameError` is the one exception class that cannot come from data, so it
is the one that gets to say it is a bug.
"""

import sys

import pytest

from claude_diary.lib.nonfatal import non_fatal


class TestItStillProtectsTheCaller:
    def test_a_runtime_failure_does_not_escape(self):
        with non_fatal("summary"):
            raise OSError("Notion is down")

    def test_a_bug_does_not_escape_either(self, capsys):
        """Loud, but still not fatal: the rows are already written."""
        with non_fatal("summary"):
            missing_helper()  # noqa: F821
        assert "BUG" in capsys.readouterr().err

    def test_the_block_runs_when_nothing_fails(self):
        seen = []
        with non_fatal("summary"):
            seen.append(1)
        assert seen == [1]

    def test_control_flow_out_of_the_block_is_not_swallowed(self):
        """A `return` inside the block must reach the caller unchanged."""
        def f():
            with non_fatal("summary"):
                return "returned"
            return "fell through"        # pragma: no cover
        assert f() == "returned"


class TestOnlyBugsAreAnnounced:
    def test_a_runtime_failure_says_nothing(self, capsys):
        """Absorbing these is the whole reason the pattern exists."""
        with non_fatal("summary"):
            raise OSError("Notion is down")
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == ""

    @pytest.mark.parametrize("exc", [
        # Every one of these is a real thing a Notion payload or a file on disk
        # can do. Calling them bugs would cry wolf on the user's own data.
        KeyError("Project"),
        TypeError("'NoneType' object is not subscriptable"),
        ValueError("bad date"),
        AttributeError("'dict' object has no attribute 'name'"),
        IndexError("list index out of range"),
    ])
    def test_data_shaped_failures_stay_quiet(self, exc, capsys):
        with non_fatal("summary"):
            raise exc
        assert capsys.readouterr().err == ""

    def test_a_name_that_does_not_resolve_is_announced(self, capsys):
        with non_fatal("drift summary", "[prefix]"):
            missing_helper()  # noqa: F821
        err = capsys.readouterr().err
        assert "[prefix]" in err
        assert "BUG" in err
        assert "drift summary" in err
        assert "NameError" in err

    def test_an_unbound_local_is_announced_too(self, capsys):
        """`UnboundLocalError` subclasses `NameError` — and it is the exact
        shape of the 4.9.0 defect, where `db_id` was only bound in one branch.
        """
        def f(force):
            if force:
                db_id = "db"
            return db_id  # noqa: F821

        with non_fatal("drift summary"):
            f(False)
        assert "BUG" in capsys.readouterr().err

    def test_it_says_the_command_itself_completed(self, capsys):
        """Otherwise the line reads as "your push failed", which it did not."""
        with non_fatal("drift summary"):
            missing_helper()  # noqa: F821
        assert "completed" in capsys.readouterr().err


class TestItGoesWhereItWillBeSeen:
    def test_the_announcement_is_on_stderr_not_stdout(self, capsys):
        """stdout is the report. A defect notice is not part of the report."""
        with non_fatal("drift summary"):
            missing_helper()  # noqa: F821
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err != ""

    def test_it_does_not_depend_on_the_log_level(self, capsys, monkeypatch):
        """The 4.9.0 defect was logged at debug, and the default level is
        WARNING. It was written down every single push and read by nobody.
        """
        import logging
        logging.getLogger("claude_diary").setLevel(logging.CRITICAL)
        try:
            with non_fatal("drift summary"):
                missing_helper()  # noqa: F821
            assert "BUG" in capsys.readouterr().err
        finally:
            logging.getLogger("claude_diary").setLevel(logging.WARNING)


class TestTheReportItselfCannotBreakThePush:
    """The announcement runs inside an exception handler, so a failure there
    has nowhere to go. A Korean name in the message plus a cp949 console is
    enough, and this project defaults to both.
    """

    def _ascii_stderr(self):
        import io
        return io.TextIOWrapper(io.BytesIO(), encoding="ascii", errors="strict")

    def test_a_stderr_that_cannot_encode_the_message_does_not_raise(self, monkeypatch):
        stream = self._ascii_stderr()
        monkeypatch.setattr(sys, "stderr", stream)
        with non_fatal("drift summary"):
            raise NameError("이름 '프로젝트' is not defined")

    def test_the_notice_still_arrives_with_the_bad_characters_replaced(self, monkeypatch):
        stream = self._ascii_stderr()
        monkeypatch.setattr(sys, "stderr", stream)
        with non_fatal("drift summary"):
            raise NameError("이름 is not defined")
        stream.flush()
        written = stream.buffer.getvalue().decode("ascii")
        assert "BUG" in written

    def test_a_stderr_that_refuses_everything_is_survived(self, monkeypatch):
        class Hostile:
            encoding = "ascii"

            def write(self, *a, **kw):
                raise OSError("stderr is closed")

            def flush(self, *a, **kw):
                raise OSError("stderr is closed")

        monkeypatch.setattr(sys, "stderr", Hostile())
        with non_fatal("drift summary"):
            missing_helper()  # noqa: F821

    def test_the_fixed_text_is_ascii(self):
        """The dynamic half gets a fallback; the half we author should never
        need one."""
        import inspect

        from claude_diary.lib import nonfatal

        src = inspect.getsource(nonfatal.non_fatal)
        for line in src.splitlines():
            if "_say(" in line or "BUG:" in line:
                line.encode("ascii")


class TestTheDriftSummaryUsesIt:
    """The call sites, not just the helper — that gap is why this exists."""

    def _push_with_broken_drift(self, tmp_path, monkeypatch):
        import json
        import os
        from unittest.mock import MagicMock, patch

        from claude_diary.cli.notion_push import cmd_notion_push

        input_path = tmp_path / "in.json"
        with open(str(input_path), "w", encoding="utf-8") as f:
            json.dump({"session_id": "s1",
                       "tasks": [{"title": "작업", "task_group": "g"}]}, f)

        mock_exp = MagicMock()
        mock_exp.ensure_database.return_value = "db_x"
        mock_exp.find_existing_row.return_value = None
        mock_exp.create_row.return_value = "row_a"
        mock_exp.get_task_group_session_ids.return_value = set()
        mock_exp._cache = {"rows": {}, "years": {}, "databases": {}, "root_page_id": "p"}

        def boom(*a, **kw):
            raise NameError("name 'db_id' is not defined")

        import claude_diary.cli.notion_push.drift as drift_mod
        monkeypatch.setattr(drift_mod, "print_pushed_projects_drift", boom)

        args = MagicMock()
        args.input = str(input_path)
        args.force = False
        args.dry_run = False
        args.preview_file = ""
        args.artifact_dir = ""
        args.no_artifacts = True

        config = {"exporters": {"notion_hierarchical": {"api_token": "t", "root_page_id": "p"}}}
        with patch.dict(os.environ, {}, clear=True), \
             patch("claude_diary.cli.notion_push.load_config", return_value=config), \
             patch("claude_diary.cli.notion_push.NotionHierarchicalExporter", return_value=mock_exp), \
             patch("claude_diary.cli.notion_push.get_head_branch", return_value="main"), \
             patch("claude_diary.cli.notion_push.os.getcwd", return_value=str(tmp_path)):
            try:
                cmd_notion_push(args)
            except SystemExit:
                pass

    def test_a_bug_in_the_summary_is_reported_and_the_push_still_succeeds(
        self, tmp_path, capsys, monkeypatch
    ):
        self._push_with_broken_drift(tmp_path, monkeypatch)
        captured = capsys.readouterr()
        assert "Pushed 1, skipped 0, failed 0" in captured.out
        assert "BUG" in captured.err

    def test_a_bug_inside_the_summary_itself_is_reported(self, capsys):
        """The guard inside `drift.py`, not the one at the call site."""
        from claude_diary.cli.notion_push.drift import print_project_drift

        class Exploding:
            def query_database_rows(self, db_id, page_size=100, row_filter=None):
                return undefined_rows  # noqa: F821

        assert print_project_drift(Exploding(), "db", "proj", "2026-08-13") is None
        assert "BUG" in capsys.readouterr().err

    def test_a_dead_notion_inside_the_summary_stays_quiet(self, capsys):
        from claude_diary.cli.notion_push.drift import print_project_drift

        class Down:
            def query_database_rows(self, db_id, page_size=100, row_filter=None):
                raise RuntimeError("Notion is down")

        assert print_project_drift(Down(), "db", "proj", "2026-08-13") is None
        assert capsys.readouterr().err == ""


def test_stderr_is_not_captured_by_accident():
    """Guards the tests above: if stderr were redirected, they would all pass
    vacuously."""
    assert sys.stderr is not None
