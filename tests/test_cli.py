"""Tests for CLI core commands."""

import json
import os
import sys
from argparse import Namespace

import pytest
from unittest.mock import patch, MagicMock, mock_open

from claude_diary.cli import (
    main,
    cmd_search,
    cmd_filter,
    cmd_trace,
    cmd_stats,
    cmd_weekly,
    cmd_config,
    cmd_reindex,
    cmd_audit,
    cmd_delete,
    cmd_init,
    cmd_migrate,
    cmd_team,
    cmd_dashboard,
    _fallback_search_from_files,
    _add_exporter_interactive,
    _print_box_top,
    _print_box_bottom,
    _get_terminal_width,
)


# ── Helper fixtures ──

@pytest.fixture
def base_config(tmp_path):
    """Return a minimal config dict pointing diary_dir at tmp_path."""
    return {
        "lang": "en",
        "timezone_offset": 9,
        "diary_dir": str(tmp_path),
        "enrichment": {},
        "exporters": {},
    }


@pytest.fixture
def sample_index_entries():
    """Return a list of sample index entries for search/filter tests."""
    return [
        {
            "date": "2026-03-10",
            "time": "10:30:00",
            "project": "my-app",
            "categories": ["feature"],
            "files": ["src/app.py"],
            "keywords": ["login", "auth", "implement"],
            "lines_added": 50,
            "lines_deleted": 10,
            "session_id": "sess-001",
        },
        {
            "date": "2026-03-12",
            "time": "14:00:00",
            "project": "my-app",
            "categories": ["bugfix"],
            "files": ["src/utils.py"],
            "keywords": ["fix", "null", "crash"],
            "lines_added": 5,
            "lines_deleted": 3,
            "session_id": "sess-002",
        },
        {
            "date": "2026-03-15",
            "time": "09:00:00",
            "project": "other-proj",
            "categories": ["docs"],
            "files": ["README.md"],
            "keywords": ["docs", "readme", "update"],
            "lines_added": 20,
            "lines_deleted": 0,
            "session_id": "sess-003",
        },
    ]


# ── cmd_search tests ──

class TestCmdSearch:

    @patch("claude_diary.cli.load_index")
    @patch("claude_diary.cli.load_config")
    def test_search_finds_matching_keyword(self, mock_config, mock_index,
                                           base_config, sample_index_entries, capsys):
        mock_config.return_value = base_config
        mock_index.return_value = {"entries": sample_index_entries}

        args = Namespace(
            keyword="login", project=None, category=None,
            date_from=None, date_to=None, json_output=False,
        )
        cmd_search(args)
        captured = capsys.readouterr()
        assert "my-app" in captured.out
        assert "1" in captured.out  # "Found 1 entries"

    @patch("claude_diary.cli.load_index")
    @patch("claude_diary.cli.load_config")
    def test_search_no_results(self, mock_config, mock_index,
                               base_config, sample_index_entries, capsys):
        mock_config.return_value = base_config
        mock_index.return_value = {"entries": sample_index_entries}

        args = Namespace(
            keyword="nonexistent_xyz", project=None, category=None,
            date_from=None, date_to=None, json_output=False,
        )
        cmd_search(args)
        captured = capsys.readouterr()
        assert "No results found" in captured.out

    @patch("claude_diary.cli.load_index")
    @patch("claude_diary.cli.load_config")
    def test_search_json_output(self, mock_config, mock_index,
                                base_config, sample_index_entries, capsys):
        mock_config.return_value = base_config
        mock_index.return_value = {"entries": sample_index_entries}

        args = Namespace(
            keyword="login", project=None, category=None,
            date_from=None, date_to=None, json_output=True,
        )
        cmd_search(args)
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert isinstance(data, list)
        assert len(data) >= 1

    @patch("claude_diary.cli.load_index")
    @patch("claude_diary.cli.load_config")
    def test_search_with_project_filter(self, mock_config, mock_index,
                                        base_config, sample_index_entries, capsys):
        mock_config.return_value = base_config
        mock_index.return_value = {"entries": sample_index_entries}

        args = Namespace(
            keyword="docs", project="other-proj", category=None,
            date_from=None, date_to=None, json_output=False,
        )
        cmd_search(args)
        captured = capsys.readouterr()
        assert "other-proj" in captured.out


# ── cmd_filter tests ──

class TestCmdFilter:

    @patch("claude_diary.cli.load_index")
    @patch("claude_diary.cli.load_config")
    def test_filter_by_project(self, mock_config, mock_index,
                               base_config, sample_index_entries, capsys):
        mock_config.return_value = base_config
        mock_index.return_value = {"entries": sample_index_entries}

        args = Namespace(project="my-app", category=None, month=None, json_output=False)
        cmd_filter(args)
        captured = capsys.readouterr()
        assert "2" in captured.out  # "Found 2 entries"
        assert "other-proj" not in captured.out

    @patch("claude_diary.cli.load_index")
    @patch("claude_diary.cli.load_config")
    def test_filter_no_match(self, mock_config, mock_index,
                             base_config, sample_index_entries, capsys):
        mock_config.return_value = base_config
        mock_index.return_value = {"entries": sample_index_entries}

        args = Namespace(project="nonexistent", category=None, month=None, json_output=False)
        cmd_filter(args)
        captured = capsys.readouterr()
        assert "No entries match" in captured.out

    @patch("claude_diary.cli.load_index")
    @patch("claude_diary.cli.load_config")
    def test_filter_no_index(self, mock_config, mock_index,
                             base_config, capsys):
        mock_config.return_value = base_config
        mock_index.return_value = {"entries": []}

        args = Namespace(project=None, category=None, month=None, json_output=False)
        cmd_filter(args)
        captured = capsys.readouterr()
        assert "No index found" in captured.out


# ── cmd_stats tests ──

class TestCmdStats:

    @patch("claude_diary.cli.parse_daily_file")
    @patch("claude_diary.cli.load_config")
    def test_stats_valid_month(self, mock_config, mock_parse, base_config, capsys):
        mock_config.return_value = base_config
        mock_parse.return_value = {
            "sessions": 0, "projects": set(), "files_created": [],
            "files_modified": [], "tasks": [], "categories": [],
        }

        args = Namespace(month="2026-03", project=None)
        cmd_stats(args)
        captured = capsys.readouterr()
        assert "2026-03" in captured.out

    @patch("claude_diary.cli.load_config")
    def test_stats_invalid_month_format(self, mock_config, base_config, capsys):
        mock_config.return_value = base_config

        args = Namespace(month="invalid", project=None)
        cmd_stats(args)
        captured = capsys.readouterr()
        assert "Invalid month format" in captured.out

    @patch("claude_diary.cli.load_config")
    def test_stats_month_out_of_range(self, mock_config, base_config, capsys):
        mock_config.return_value = base_config

        args = Namespace(month="2026-13", project=None)
        cmd_stats(args)
        captured = capsys.readouterr()
        assert "Invalid month" in captured.out


# ── cmd_weekly tests ──

class TestCmdWeekly:

    @patch("claude_diary.cli.parse_daily_file")
    @patch("claude_diary.cli.load_config")
    def test_weekly_generates_report(self, mock_config, mock_parse,
                                     base_config, tmp_path, capsys):
        mock_config.return_value = base_config
        mock_parse.return_value = {
            "sessions": 2, "projects": {"my-proj"},
            "files_created": [], "files_modified": [],
            "tasks": ["Implemented feature X"], "categories": ["feature"],
        }

        args = Namespace(date="2026-03-17")
        cmd_weekly(args)
        captured = capsys.readouterr()
        assert "Weekly Work Report" in captured.out or "\uc8fc\uac04 \uc791\uc5c5 \ub9ac\ud3ec\ud2b8" in captured.out
        assert "Saved:" in captured.out

    @patch("claude_diary.cli.load_config")
    def test_weekly_invalid_date(self, mock_config, base_config, capsys):
        mock_config.return_value = base_config

        args = Namespace(date="not-a-date")
        cmd_weekly(args)
        captured = capsys.readouterr()
        assert "Invalid date format" in captured.out


# ── cmd_config tests ──

class TestCmdConfig:

    @patch("claude_diary.cli.get_config_path", return_value="/fake/config.json")
    @patch("claude_diary.cli.load_config")
    def test_config_display(self, mock_config, mock_path, base_config, capsys):
        mock_config.return_value = base_config

        args = Namespace(set_value=None, add_exporter=None)
        cmd_config(args)
        captured = capsys.readouterr()
        assert "Config path:" in captured.out
        assert "lang: en" in captured.out

    @patch("claude_diary.cli.save_config")
    @patch("claude_diary.cli.load_config")
    def test_config_set_lang(self, mock_config, mock_save, base_config, capsys):
        mock_config.return_value = base_config

        args = Namespace(set_value="lang=en", add_exporter=None)
        cmd_config(args)
        captured = capsys.readouterr()
        assert "Set lang = en" in captured.out
        mock_save.assert_called_once()

    @patch("claude_diary.cli.load_config")
    def test_config_set_invalid_lang(self, mock_config, base_config, capsys):
        mock_config.return_value = base_config

        args = Namespace(set_value="lang=fr", add_exporter=None)
        cmd_config(args)
        captured = capsys.readouterr()
        assert "Invalid lang" in captured.out

    @patch("claude_diary.cli.load_config")
    def test_config_set_unknown_key(self, mock_config, base_config, capsys):
        mock_config.return_value = base_config

        args = Namespace(set_value="unknown_key=value", add_exporter=None)
        cmd_config(args)
        captured = capsys.readouterr()
        assert "Unknown config key" in captured.out

    @patch("claude_diary.cli.save_config")
    @patch("claude_diary.cli.load_config")
    def test_config_set_timezone_offset(self, mock_config, mock_save, base_config, capsys):
        mock_config.return_value = base_config

        args = Namespace(set_value="timezone_offset=5", add_exporter=None)
        cmd_config(args)
        captured = capsys.readouterr()
        assert "Set timezone_offset = 5" in captured.out

    @patch("claude_diary.cli.load_config")
    def test_config_set_invalid_timezone(self, mock_config, base_config, capsys):
        mock_config.return_value = base_config

        args = Namespace(set_value="timezone_offset=abc", add_exporter=None)
        cmd_config(args)
        captured = capsys.readouterr()
        assert "Invalid timezone_offset" in captured.out


# ── cmd_reindex tests ──

class TestCmdReindex:

    @patch("claude_diary.indexer.reindex_all", return_value=5)
    @patch("claude_diary.cli.load_config")
    def test_reindex_runs(self, mock_config, mock_reindex, base_config, tmp_path, capsys):
        mock_config.return_value = base_config

        args = Namespace()
        cmd_reindex(args)
        captured = capsys.readouterr()
        assert "Indexed 5 sessions" in captured.out
        mock_reindex.assert_called_once()


# ── cmd_audit tests ──

class TestCmdAudit:

    @patch("claude_diary.cli.load_config")
    def test_audit_no_entries(self, mock_config, base_config, capsys):
        mock_config.return_value = base_config

        with patch("claude_diary.lib.audit.read_audit_log", return_value=[]):
            args = Namespace(verify=False, days=None, n=10)
            cmd_audit(args)
            captured = capsys.readouterr()
            assert "No audit log entries found" in captured.out

    @patch("claude_diary.cli.load_config")
    def test_audit_shows_entries(self, mock_config, base_config, capsys):
        mock_config.return_value = base_config

        fake_entries = [
            {
                "timestamp": "2026-03-17T10:00:00+09:00",
                "session_id": "abcdef1234567890",
                "files_written": ["2026-03-17.md"],
                "secrets_masked": 2,
                "exporters_called": ["github"],
                "exporters_failed": [],
            },
        ]
        with patch("claude_diary.lib.audit.read_audit_log", return_value=fake_entries):
            args = Namespace(verify=False, days=None, n=10)
            cmd_audit(args)
            captured = capsys.readouterr()
            assert "Audit log (1 entries)" in captured.out
            assert "abcdef12" in captured.out
            assert "secrets_masked:2" in captured.out

    @patch("claude_diary.cli.load_config")
    def test_audit_verify_ok(self, mock_config, base_config, capsys):
        mock_config.return_value = base_config

        with patch("claude_diary.lib.audit.verify_checksum",
                    return_value=(True, "sha256:abc123", "sha256:abc123")):
            args = Namespace(verify=True, days=None, n=10)
            cmd_audit(args)
            captured = capsys.readouterr()
            assert "Checksum OK" in captured.out


# ── cmd_delete tests ──

class TestCmdDelete:

    @patch("claude_diary.cli.load_config")
    def test_delete_no_flag(self, mock_config, base_config, capsys):
        mock_config.return_value = base_config

        args = Namespace(last=False, session=None)
        cmd_delete(args)
        captured = capsys.readouterr()
        assert "Specify --last or --session" in captured.out

    @patch("claude_diary.cli.load_config")
    def test_delete_last_no_file(self, mock_config, base_config, capsys):
        mock_config.return_value = base_config

        args = Namespace(last=True, session=None)
        cmd_delete(args)
        captured = capsys.readouterr()
        assert "No diary file for today" in captured.out

    @patch("builtins.input", return_value="y")
    @patch("claude_diary.cli.load_config")
    def test_delete_last_confirmed(self, mock_config, mock_input,
                                   base_config, tmp_path, capsys):
        mock_config.return_value = base_config

        # Create today's diary with two sessions
        from datetime import datetime, timezone, timedelta
        local_tz = timezone(timedelta(hours=9))
        today = datetime.now(local_tz).strftime("%Y-%m-%d")
        diary_file = tmp_path / ("%s.md" % today)
        diary_file.write_text(
            "# Diary\n\n### \u23f0 10:00:00\nFirst session\n\n---\n\n"
            "### \u23f0 14:00:00\nSecond session\n",
            encoding="utf-8",
        )

        args = Namespace(last=True, session=None)
        cmd_delete(args)
        captured = capsys.readouterr()
        assert "deleted" in captured.out.lower()

        # Verify the file was modified: second session should be removed
        content = diary_file.read_text(encoding="utf-8")
        assert "First session" in content
        assert "Second session" not in content

    @patch("claude_diary.cli.load_config")
    def test_delete_session_not_found(self, mock_config, base_config, capsys):
        mock_config.return_value = base_config

        args = Namespace(last=False, session="nonexistent")
        cmd_delete(args)
        captured = capsys.readouterr()
        assert "not found" in captured.out.lower()


# ── main() tests ──

class TestMain:

    def test_no_args_prints_help(self, capsys):
        with patch("sys.argv", ["claude-diary"]):
            main()
        captured = capsys.readouterr()
        assert "usage:" in captured.out.lower() or "claude-diary" in captured.out.lower()

    def test_version_flag(self, capsys):
        with patch("sys.argv", ["claude-diary", "--version"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "4.1.0" in captured.out

    @patch("claude_diary.cli.cmd_trace")
    def test_main_dispatches_trace(self, mock_cmd, capsys):
        with patch("sys.argv", ["claude-diary", "trace", "some/file.py"]):
            main()
        mock_cmd.assert_called_once()

    @patch("claude_diary.cli.cmd_init")
    def test_main_dispatches_init(self, mock_cmd, capsys):
        with patch("sys.argv", ["claude-diary", "init"]):
            main()
        mock_cmd.assert_called_once()

    @patch("claude_diary.cli.cmd_migrate")
    def test_main_dispatches_migrate(self, mock_cmd, capsys):
        with patch("sys.argv", ["claude-diary", "migrate"]):
            main()
        mock_cmd.assert_called_once()

    @patch("claude_diary.cli.cmd_team")
    def test_main_dispatches_team(self, mock_cmd, capsys):
        with patch("sys.argv", ["claude-diary", "team", "stats"]):
            main()
        mock_cmd.assert_called_once()

    @patch("claude_diary.cli.cmd_dashboard")
    def test_main_dispatches_dashboard(self, mock_cmd, capsys):
        with patch("sys.argv", ["claude-diary", "dashboard"]):
            main()
        mock_cmd.assert_called_once()


# ── cmd_trace tests ──

class TestCmdTrace:

    @patch("claude_diary.cli.load_index")
    @patch("claude_diary.cli.load_config")
    def test_trace_finds_file(self, mock_config, mock_index,
                              base_config, sample_index_entries, capsys):
        mock_config.return_value = base_config
        mock_index.return_value = {"entries": sample_index_entries}

        args = Namespace(filepath="src/app.py", project=None)
        cmd_trace(args)
        captured = capsys.readouterr()
        assert "File trace" in captured.out
        assert "1 entries" in captured.out
        assert "my-app" in captured.out

    @patch("claude_diary.cli.load_index")
    @patch("claude_diary.cli.load_config")
    def test_trace_no_history(self, mock_config, mock_index,
                              base_config, sample_index_entries, capsys):
        mock_config.return_value = base_config
        mock_index.return_value = {"entries": sample_index_entries}

        args = Namespace(filepath="nonexistent/file.py", project=None)
        cmd_trace(args)
        captured = capsys.readouterr()
        assert "No history found" in captured.out

    @patch("claude_diary.cli.load_index")
    @patch("claude_diary.cli.load_config")
    def test_trace_with_project_filter(self, mock_config, mock_index,
                                       base_config, sample_index_entries, capsys):
        mock_config.return_value = base_config
        mock_index.return_value = {"entries": sample_index_entries}

        args = Namespace(filepath="src/app.py", project="other-proj")
        cmd_trace(args)
        captured = capsys.readouterr()
        assert "No history found" in captured.out


# ── _fallback_search_from_files tests ──

class TestFallbackSearchFromFiles:

    def test_fallback_finds_keyword(self, tmp_path):
        md_file = tmp_path / "2026-03-10.md"
        md_file.write_text(
            "# Diary\n\n### session\n📁 `my-project`\nImplemented login feature\n",
            encoding="utf-8",
        )
        results = _fallback_search_from_files(str(tmp_path), "login")
        assert len(results) == 1
        assert results[0]["date"] == "2026-03-10"
        assert results[0]["project"] == "my-project"

    def test_fallback_no_match(self, tmp_path):
        md_file = tmp_path / "2026-03-10.md"
        md_file.write_text("# Diary\n\nSome content\n", encoding="utf-8")
        results = _fallback_search_from_files(str(tmp_path), "nonexistent")
        assert results == []

    def test_fallback_empty_dir(self, tmp_path):
        results = _fallback_search_from_files(str(tmp_path), "anything")
        assert results == []

    def test_fallback_no_project_marker(self, tmp_path):
        md_file = tmp_path / "2026-03-10.md"
        md_file.write_text("# Diary\nSome login content\n", encoding="utf-8")
        results = _fallback_search_from_files(str(tmp_path), "login")
        assert len(results) == 1
        assert results[0]["project"] == ""


# ── cmd_search auto-reindex and fallback paths ──

class TestCmdSearchFallbackPaths:

    @patch("claude_diary.cli.load_index")
    @patch("claude_diary.cli.load_config")
    def test_search_auto_reindex(self, mock_config, mock_index,
                                 base_config, tmp_path, capsys):
        """When no index entries exist but diary files do, auto-reindex is triggered."""
        mock_config.return_value = base_config
        # First call returns empty, second call (after reindex) returns entries
        mock_index.side_effect = [
            {"entries": []},
            {"entries": [{"date": "2026-03-10", "time": "10:00", "project": "proj",
                          "categories": ["feat"], "files": [], "keywords": ["login"],
                          "lines_added": 0, "lines_deleted": 0}]},
        ]
        # Create a diary file so auto-reindex triggers
        (tmp_path / "2026-03-10.md").write_text("# Diary\nlogin stuff\n", encoding="utf-8")

        with patch("claude_diary.indexer.reindex_all") as mock_reindex:
            args = Namespace(
                keyword="login", project=None, category=None,
                date_from=None, date_to=None, json_output=False,
            )
            cmd_search(args)
            mock_reindex.assert_called_once()
            captured = capsys.readouterr()
            assert "Found 1" in captured.out

    @patch("claude_diary.cli._fallback_search_from_files")
    @patch("claude_diary.cli.load_index")
    @patch("claude_diary.cli.load_config")
    def test_search_fallback_with_results(self, mock_config, mock_index,
                                          mock_fallback, base_config, tmp_path, capsys):
        """When index is empty and no diary files, fallback search is used."""
        mock_config.return_value = base_config
        mock_index.return_value = {"entries": []}
        mock_fallback.return_value = [
            {"date": "2026-03-10", "project": "proj", "line": "did login work"}
        ]

        args = Namespace(
            keyword="login", project=None, category=None,
            date_from=None, date_to=None, json_output=False,
        )
        cmd_search(args)
        captured = capsys.readouterr()
        assert "2026-03-10" in captured.out
        assert "proj" in captured.out

    @patch("claude_diary.cli._fallback_search_from_files")
    @patch("claude_diary.cli.load_index")
    @patch("claude_diary.cli.load_config")
    def test_search_fallback_no_results(self, mock_config, mock_index,
                                        mock_fallback, base_config, capsys):
        mock_config.return_value = base_config
        mock_index.return_value = {"entries": []}
        mock_fallback.return_value = []

        args = Namespace(
            keyword="login", project=None, category=None,
            date_from=None, date_to=None, json_output=False,
        )
        cmd_search(args)
        captured = capsys.readouterr()
        assert "login" in captured.out


# ── cmd_stats additional tests ──

class TestCmdStatsExtra:

    @patch("claude_diary.cli.parse_daily_file")
    @patch("claude_diary.cli.load_config")
    def test_stats_no_month_uses_current(self, mock_config, mock_parse, base_config, capsys):
        """When no --month given, current month is used (lines 304-305)."""
        mock_config.return_value = base_config
        mock_parse.return_value = {
            "sessions": 0, "projects": set(), "files_created": [],
            "files_modified": [], "tasks": [], "categories": [],
        }
        args = Namespace(month=None, project=None)
        cmd_stats(args)
        captured = capsys.readouterr()
        assert "Working Diary Stats" in captured.out

    @patch("claude_diary.cli.parse_daily_file")
    @patch("claude_diary.cli.load_config")
    def test_stats_with_project_filter(self, mock_config, mock_parse, base_config, capsys):
        """Test project filter path (lines 324-326)."""
        mock_config.return_value = base_config

        def fake_parse(filepath):
            if "01.md" in filepath:
                return {
                    "sessions": 3, "projects": {"my-app"},
                    "files_created": ["a.py"], "files_modified": ["b.py"],
                    "tasks": [], "categories": ["feature"],
                }
            return {
                "sessions": 1, "projects": {"other"},
                "files_created": [], "files_modified": [],
                "tasks": [], "categories": [],
            }
        mock_parse.side_effect = fake_parse

        args = Namespace(month="2026-03", project="my-app")
        cmd_stats(args)
        captured = capsys.readouterr()
        assert "Working Diary Stats" in captured.out

    @patch("claude_diary.cli.parse_daily_file")
    @patch("claude_diary.cli.load_config")
    def test_stats_with_projects_and_categories(self, mock_config, mock_parse, base_config, capsys):
        """Test project bar and categories printing (lines 348-360, 370-375)."""
        mock_config.return_value = base_config
        mock_parse.return_value = {
            "sessions": 5, "projects": {"my-app"},
            "project_sessions": {"my-app": 5},
            "files_created": ["a.py"], "files_modified": ["b.py"],
            "tasks": [], "categories": ["feature", "bugfix"],
        }
        args = Namespace(month="2026-01", project=None)
        cmd_stats(args)
        captured = capsys.readouterr()
        assert "Projects:" in captured.out
        assert "Categories:" in captured.out
        assert "my-app" in captured.out


# ── Box / terminal width helpers ──

class TestBoxHelpers:

    def test_print_box_top(self, capsys):
        _print_box_top("Test Title")
        captured = capsys.readouterr()
        assert "Test Title" in captured.out
        assert "╔" in captured.out

    def test_print_box_bottom(self, capsys):
        _print_box_bottom()
        captured = capsys.readouterr()
        assert "╚" in captured.out

    def test_get_terminal_width_fallback(self):
        with patch("shutil.get_terminal_size", side_effect=Exception("no terminal")):
            width = _get_terminal_width()
            assert width == 52

    def test_get_terminal_width_normal(self):
        mock_size = MagicMock()
        mock_size.columns = 80
        with patch("shutil.get_terminal_size", return_value=mock_size):
            width = _get_terminal_width()
            assert 40 <= width <= 100


# ── cmd_weekly additional tests ──

class TestCmdWeeklyExtra:

    @patch("claude_diary.cli.parse_daily_file")
    @patch("claude_diary.cli.load_config")
    def test_weekly_no_date_uses_current(self, mock_config, mock_parse,
                                         base_config, tmp_path, capsys):
        """Line 417: no date argument uses current date."""
        mock_config.return_value = base_config
        mock_parse.return_value = {
            "sessions": 0, "projects": set(),
            "files_created": [], "files_modified": [],
            "tasks": [], "categories": [],
        }
        args = Namespace(date=None)
        cmd_weekly(args)
        captured = capsys.readouterr()
        assert "Weekly Work Report" in captured.out
        assert "No activity" in captured.out

    @patch("claude_diary.cli.parse_daily_file")
    @patch("claude_diary.cli.load_config")
    def test_weekly_ko_lang(self, mock_config, mock_parse,
                            base_config, tmp_path, capsys):
        """Line 448: Korean weekday names and labels."""
        base_config["lang"] = "ko"
        mock_config.return_value = base_config
        mock_parse.return_value = {
            "sessions": 1, "projects": {"proj"},
            "files_created": [], "files_modified": [],
            "tasks": ["task1"], "categories": [],
        }
        args = Namespace(date="2026-03-17")
        cmd_weekly(args)
        captured = capsys.readouterr()
        assert "주간 작업 리포트" in captured.out


# ── cmd_config additional tests ──

class TestCmdConfigExtra:

    @patch("claude_diary.cli.save_config")
    @patch("claude_diary.cli.load_config")
    def test_config_set_diary_dir(self, mock_config, mock_save, base_config, capsys):
        """Line 515: set diary_dir."""
        mock_config.return_value = base_config
        args = Namespace(set_value="diary_dir=/new/path", add_exporter=None)
        cmd_config(args)
        captured = capsys.readouterr()
        assert "Set diary_dir = /new/path" in captured.out
        mock_save.assert_called_once()

    @patch("claude_diary.cli.load_config")
    def test_config_set_timezone_out_of_range(self, mock_config, base_config, capsys):
        """Lines 520-521: timezone_offset out of range."""
        mock_config.return_value = base_config
        args = Namespace(set_value="timezone_offset=20", add_exporter=None)
        cmd_config(args)
        captured = capsys.readouterr()
        assert "Invalid timezone_offset" in captured.out
        assert "range" in captured.out

    @patch("claude_diary.cli.get_config_path", return_value="/fake/config.json")
    @patch("claude_diary.cli.load_config")
    def test_config_display_with_exporters(self, mock_config, mock_path, capsys):
        """Lines 540-550: config display with exporters section."""
        config = {
            "lang": "en",
            "diary_dir": "~/.claude-diary",
            "timezone_offset": 9,
            "exporters": {
                "notion": {
                    "enabled": True,
                    "api_token": "secret-token-12345678",
                    "database_id": "db123",
                },
                "slack": {
                    "enabled": False,
                    "webhook_url": "https://hooks.slack.com/services/1234567890",
                },
            },
        }
        mock_config.return_value = config
        args = Namespace(set_value=None, add_exporter=None)
        cmd_config(args)
        captured = capsys.readouterr()
        assert "exporters:" in captured.out
        assert "notion: enabled" in captured.out
        assert "slack: disabled" in captured.out
        # Token should be masked
        assert "secr" in captured.out
        assert "5678" in captured.out


# ── _add_exporter_interactive tests ──

class TestAddExporterInteractive:

    @patch("claude_diary.cli.save_config")
    @patch("builtins.input", side_effect=["my-token", "my-db-id"])
    def test_add_notion_exporter(self, mock_input, mock_save, capsys):
        config = {"exporters": {}}
        _add_exporter_interactive(config, "notion")
        captured = capsys.readouterr()
        assert "Exporter 'notion' added" in captured.out
        assert config["exporters"]["notion"]["enabled"] is True
        assert config["exporters"]["notion"]["api_token"] == "my-token"
        assert config["exporters"]["notion"]["database_id"] == "my-db-id"
        mock_save.assert_called_once()

    @patch("claude_diary.cli.save_config")
    @patch("builtins.input", return_value="https://hooks.slack.com/xxx")
    def test_add_slack_exporter(self, mock_input, mock_save, capsys):
        config = {}
        _add_exporter_interactive(config, "slack")
        captured = capsys.readouterr()
        assert "Exporter 'slack' added" in captured.out
        assert config["exporters"]["slack"]["webhook_url"] == "https://hooks.slack.com/xxx"

    @patch("claude_diary.cli.save_config")
    @patch("builtins.input", return_value="https://discord.com/xxx")
    def test_add_discord_exporter(self, mock_input, mock_save, capsys):
        config = {"exporters": {}}
        _add_exporter_interactive(config, "discord")
        assert config["exporters"]["discord"]["enabled"] is True

    @patch("claude_diary.cli.save_config")
    @patch("builtins.input", return_value="/path/to/vault")
    def test_add_obsidian_exporter(self, mock_input, mock_save, capsys):
        config = {"exporters": {}}
        _add_exporter_interactive(config, "obsidian")
        assert config["exporters"]["obsidian"]["vault_path"] == "/path/to/vault"

    @patch("claude_diary.cli.save_config")
    @patch("builtins.input", side_effect=["owner/repo", "wiki"])
    def test_add_github_exporter(self, mock_input, mock_save, capsys):
        config = {"exporters": {}}
        _add_exporter_interactive(config, "github")
        assert config["exporters"]["github"]["repo"] == "owner/repo"
        assert config["exporters"]["github"]["mode"] == "wiki"

    def test_add_unknown_exporter(self, capsys):
        config = {"exporters": {}}
        _add_exporter_interactive(config, "unknown_xyz")
        captured = capsys.readouterr()
        assert "Unknown exporter" in captured.out


# ── cmd_init tests ──

class TestCmdInit:

    @patch("claude_diary.cli.get_config_path", return_value="/fake/config.json")
    @patch("claude_diary.cli.save_config")
    @patch("claude_diary.cli.ensure_diary_dir")
    @patch("claude_diary.cli.load_config")
    def test_init_basic(self, mock_config, mock_ensure, mock_save, mock_path,
                        base_config, capsys):
        mock_config.return_value = base_config
        # settings.json doesn't exist
        with patch("os.path.exists", return_value=False):
            args = Namespace(team_repo=None)
            cmd_init(args)
        captured = capsys.readouterr()
        assert "Initializing claude-diary" in captured.out
        assert "[ok] Diary directory" in captured.out
        assert "[ok] Config" in captured.out
        assert "Done!" in captured.out
        mock_ensure.assert_called_once()
        mock_save.assert_called_once()

    @patch("claude_diary.cli.get_config_path", return_value="/fake/config.json")
    @patch("claude_diary.cli.save_config")
    @patch("claude_diary.cli.ensure_diary_dir")
    @patch("claude_diary.cli.load_config")
    def test_init_with_existing_settings_no_hook(self, mock_config, mock_ensure,
                                                  mock_save, mock_path,
                                                  base_config, tmp_path, capsys):
        mock_config.return_value = base_config
        settings_file = tmp_path / ".claude" / "settings.json"
        settings_file.parent.mkdir(parents=True)
        settings_file.write_text('{"hooks": {}}', encoding="utf-8")

        with patch("os.path.exists", return_value=True), \
             patch("os.path.expanduser", return_value=str(tmp_path)), \
             patch("os.path.join", side_effect=lambda *a: "/".join(a)) as mock_join:
            # Need to properly handle os.path.join for settings path
            mock_join.side_effect = None
            mock_join.return_value = str(settings_file)
            # Just test with a real path approach
            pass

        # Simpler: use a mock for open to simulate the settings file
        settings_data = json.dumps({"hooks": {}})
        m_open = mock_open(read_data=settings_data)

        def exists_side_effect(path):
            return True

        with patch("os.path.exists", side_effect=exists_side_effect), \
             patch("builtins.open", m_open), \
             patch("os.path.expanduser", side_effect=lambda x: str(tmp_path) if x == "~" else x):
            args = Namespace(team_repo=None)
            cmd_init(args)

        captured = capsys.readouterr()
        assert "Initializing claude-diary" in captured.out
        assert "Stop Hook registered" in captured.out

    @patch("claude_diary.cli.get_config_path", return_value="/fake/config.json")
    @patch("claude_diary.cli.save_config")
    @patch("claude_diary.cli.ensure_diary_dir")
    @patch("claude_diary.cli.load_config")
    def test_init_hook_already_registered(self, mock_config, mock_ensure,
                                          mock_save, mock_path,
                                          base_config, tmp_path, capsys):
        mock_config.return_value = base_config
        settings_data = json.dumps({
            "hooks": {
                "Stop": [{"hooks": [{"type": "command", "command": "python -m claude_diary.hook"}]}]
            }
        })
        m_open = mock_open(read_data=settings_data)

        with patch("os.path.exists", return_value=True), \
             patch("builtins.open", m_open), \
             patch("os.path.expanduser", side_effect=lambda x: str(tmp_path) if x == "~" else x):
            args = Namespace(team_repo=None)
            cmd_init(args)

        captured = capsys.readouterr()
        assert "Stop Hook already registered" in captured.out

    @patch("claude_diary.cli.load_config")
    def test_init_team_mode(self, mock_config, base_config, capsys):
        mock_config.return_value = base_config
        with patch("claude_diary.team.init_team") as mock_team_init:
            args = Namespace(team_repo="https://github.com/org/team-diary")
            cmd_init(args)
            mock_team_init.assert_called_once_with("https://github.com/org/team-diary")
        captured = capsys.readouterr()
        assert "team mode" in captured.out


# ── cmd_migrate tests ──

class TestCmdMigrate:

    @patch("claude_diary.cli.get_config_path", return_value="/fake/config.json")
    @patch("claude_diary.cli.migrate_from_env")
    def test_migrate(self, mock_migrate, mock_path, capsys):
        mock_migrate.return_value = {
            "lang": "ko",
            "diary_dir": "~/.claude-diary",
            "timezone_offset": 9,
        }
        args = Namespace()
        cmd_migrate(args)
        captured = capsys.readouterr()
        assert "Migrating" in captured.out
        assert "lang: ko" in captured.out
        assert "diary_dir:" in captured.out
        assert "timezone_offset: 9" in captured.out
        assert "Config saved" in captured.out
        mock_migrate.assert_called_once()


# ── cmd_team tests ──

class TestCmdTeam:

    @patch("claude_diary.cli.load_config")
    def test_team_init_with_args(self, mock_config, base_config, capsys):
        mock_config.return_value = base_config
        with patch("claude_diary.team.init_team") as mock_init:
            args = Namespace(action="init", repo="https://example.com/repo",
                             name="Alice", role="member", project=None,
                             member=None, month=None)
            cmd_team(args)
            mock_init.assert_called_once_with("https://example.com/repo", "Alice")
        captured = capsys.readouterr()
        assert "Done!" in captured.out

    @patch("claude_diary.cli.load_config")
    def test_team_init_with_input(self, mock_config, base_config, capsys):
        mock_config.return_value = base_config
        with patch("claude_diary.team.init_team") as mock_init, \
             patch("builtins.input", side_effect=["https://example.com/repo", "Bob"]):
            args = Namespace(action="init", repo=None, name=None, role="member",
                             project=None, member=None, month=None)
            cmd_team(args)
            mock_init.assert_called_once_with("https://example.com/repo", "Bob")

    @patch("claude_diary.cli.load_config")
    def test_team_stats(self, mock_config, base_config, tmp_path, capsys):
        mock_config.return_value = base_config
        repo_path = str(tmp_path / "team-repo")
        os.makedirs(repo_path)

        with patch("claude_diary.team.get_team_repo_path", return_value=repo_path), \
             patch("claude_diary.team.team_stats", return_value={"members": []}) as mock_stats, \
             patch("claude_diary.team.print_team_stats") as mock_print:
            args = Namespace(action="stats", project=None, member=None,
                             month="2026-03", repo=None, name=None, role="member")
            cmd_team(args)
            mock_stats.assert_called_once()
            mock_print.assert_called_once()

    @patch("claude_diary.cli.load_config")
    def test_team_weekly(self, mock_config, base_config, tmp_path, capsys):
        mock_config.return_value = base_config
        repo_path = str(tmp_path / "team-repo")
        os.makedirs(repo_path)

        with patch("claude_diary.team.get_team_repo_path", return_value=repo_path), \
             patch("claude_diary.team.team_weekly_report", return_value=("# Report", "/path/report.md")):
            args = Namespace(action="weekly", project=None, member=None,
                             month=None, repo=None, name=None, role="member")
            cmd_team(args)
        captured = capsys.readouterr()
        assert "# Report" in captured.out
        assert "Saved:" in captured.out

    @patch("claude_diary.cli.load_config")
    def test_team_weekly_no_data(self, mock_config, base_config, tmp_path, capsys):
        mock_config.return_value = base_config
        repo_path = str(tmp_path / "team-repo")
        os.makedirs(repo_path)

        with patch("claude_diary.team.get_team_repo_path", return_value=repo_path), \
             patch("claude_diary.team.team_weekly_report", return_value=None):
            args = Namespace(action="weekly", project=None, member=None,
                             month=None, repo=None, name=None, role="member")
            cmd_team(args)
        captured = capsys.readouterr()
        assert "No team data found" in captured.out

    @patch("claude_diary.cli.load_config")
    def test_team_not_configured(self, mock_config, base_config, capsys):
        mock_config.return_value = base_config
        with patch("claude_diary.team.get_team_repo_path", return_value=None):
            args = Namespace(action="stats", project=None, member=None,
                             month=None, repo=None, name=None, role="member")
            cmd_team(args)
        captured = capsys.readouterr()
        assert "Team not configured" in captured.out

    @patch("claude_diary.cli.load_config")
    def test_team_add_member(self, mock_config, base_config, tmp_path, capsys):
        mock_config.return_value = base_config
        repo_path = str(tmp_path / "team-repo")
        os.makedirs(repo_path)

        # Create an empty team config
        tc_path = os.path.join(repo_path, ".team-config.json")
        with open(tc_path, "w") as f:
            json.dump({"members": [], "roles": {}}, f)

        with patch("claude_diary.team.get_team_repo_path", return_value=repo_path):
            args = Namespace(action="add-member", name="Charlie", role="admin",
                             project=None, member=None, month=None, repo=None)
            cmd_team(args)
        captured = capsys.readouterr()
        assert "Added member 'Charlie'" in captured.out
        assert "admin" in captured.out

        # Verify the config was written
        with open(tc_path) as f:
            tc = json.load(f)
        assert "Charlie" in tc["members"]
        assert tc["roles"]["Charlie"] == "admin"

    @patch("claude_diary.cli.load_config")
    def test_team_monthly(self, mock_config, base_config, tmp_path, capsys):
        mock_config.return_value = base_config
        repo_path = str(tmp_path / "team-repo")
        os.makedirs(repo_path)

        with patch("claude_diary.team.get_team_repo_path", return_value=repo_path), \
             patch("claude_diary.team.team_weekly_report", return_value=("# Monthly", "/path/m.md")):
            args = Namespace(action="monthly", project=None, member=None,
                             month=None, repo=None, name=None, role="member")
            cmd_team(args)
        captured = capsys.readouterr()
        assert "# Monthly" in captured.out


# ── cmd_audit verify mismatch ──

class TestCmdAuditExtra:

    @patch("claude_diary.cli.load_config")
    def test_audit_verify_mismatch(self, mock_config, base_config, capsys):
        """Lines 752-755: checksum mismatch path."""
        mock_config.return_value = base_config
        with patch("claude_diary.lib.audit.verify_checksum",
                    return_value=(False, "sha256:aaa", "sha256:bbb")):
            args = Namespace(verify=True, days=None, n=10)
            cmd_audit(args)
        captured = capsys.readouterr()
        assert "WARNING: Checksum mismatch" in captured.out
        assert "sha256:aaa" in captured.out
        assert "sha256:bbb" in captured.out


# ── cmd_delete additional tests ──

class TestCmdDeleteExtra:

    @patch("builtins.input", return_value="n")
    @patch("claude_diary.cli.load_config")
    def test_delete_last_cancelled(self, mock_config, mock_input,
                                   base_config, tmp_path, capsys):
        """Lines 802-803: user cancels deletion."""
        mock_config.return_value = base_config
        from datetime import datetime, timezone, timedelta
        local_tz = timezone(timedelta(hours=9))
        today = datetime.now(local_tz).strftime("%Y-%m-%d")
        diary_file = tmp_path / ("%s.md" % today)
        diary_file.write_text("# Diary\n\n### ⏰ 10:00\nSession 1\n", encoding="utf-8")

        args = Namespace(last=True, session=None)
        cmd_delete(args)
        captured = capsys.readouterr()
        assert "Cancelled" in captured.out

    @patch("builtins.input", return_value="y")
    @patch("claude_diary.cli.load_config")
    def test_delete_last_single_session(self, mock_config, mock_input,
                                        base_config, tmp_path, capsys):
        """Lines 811-812: no session entries (only one part after split)."""
        mock_config.return_value = base_config
        from datetime import datetime, timezone, timedelta
        local_tz = timezone(timedelta(hours=9))
        today = datetime.now(local_tz).strftime("%Y-%m-%d")
        diary_file = tmp_path / ("%s.md" % today)
        diary_file.write_text("# Diary\n\nJust a header, no sessions.\n", encoding="utf-8")

        args = Namespace(last=True, session=None)
        cmd_delete(args)
        captured = capsys.readouterr()
        assert "No session entries found" in captured.out

    @patch("claude_diary.cli.load_config")
    def test_delete_by_session_id_found(self, mock_config, base_config, tmp_path, capsys):
        """Lines 832-847: delete by session ID."""
        mock_config.return_value = base_config

        diary_file = tmp_path / "2026-03-10.md"
        diary_file.write_text(
            "# Diary\n\n### ⏰ 10:00\nsession_id: abc123\nFirst session\n\n---\n\n"
            "### ⏰ 14:00\nsession_id: def456\nSecond session\n",
            encoding="utf-8",
        )

        args = Namespace(last=False, session="abc123")
        cmd_delete(args)
        captured = capsys.readouterr()
        assert "abc123" in captured.out
        assert "deleted" in captured.out.lower()

        content = diary_file.read_text(encoding="utf-8")
        assert "abc123" not in content
        assert "def456" in content


# ── cmd_dashboard tests ──

class TestCmdDashboard:

    @patch("claude_diary.cli.load_config")
    def test_dashboard_generate_no_serve(self, mock_config, base_config, capsys):
        mock_config.return_value = base_config
        with patch("claude_diary.dashboard.generate_dashboard", return_value="/fake/dashboard.html") as mock_gen, \
             patch("webbrowser.open") as mock_browser:
            args = Namespace(serve=False, port=8787, months=3)
            cmd_dashboard(args)
            mock_gen.assert_called_once()
            mock_browser.assert_called_once()
        captured = capsys.readouterr()
        assert "Dashboard generated" in captured.out

    @patch("claude_diary.cli.load_config")
    def test_dashboard_generate_with_serve(self, mock_config, base_config, capsys):
        mock_config.return_value = base_config
        with patch("claude_diary.dashboard.generate_dashboard", return_value="/fake/dashboard.html"), \
             patch("claude_diary.dashboard.serve_dashboard") as mock_serve:
            args = Namespace(serve=True, port=9999, months=6)
            cmd_dashboard(args)
            mock_serve.assert_called_once_with(str(base_config["diary_dir"]), port=9999)
        captured = capsys.readouterr()
        assert "Dashboard generated" in captured.out


# ── cmd_search date/category filter edge cases ──

class TestCmdSearchFilters:

    @patch("claude_diary.cli.load_index")
    @patch("claude_diary.cli.load_config")
    def test_search_date_from_filter(self, mock_config, mock_index,
                                     base_config, sample_index_entries, capsys):
        """Line 165: date_from filter."""
        mock_config.return_value = base_config
        mock_index.return_value = {"entries": sample_index_entries}

        args = Namespace(
            keyword="my-app", project=None, category=None,
            date_from="2026-03-12", date_to=None, json_output=False,
        )
        cmd_search(args)
        captured = capsys.readouterr()
        # Should exclude 2026-03-10 entry
        assert "Found 1" in captured.out

    @patch("claude_diary.cli.load_index")
    @patch("claude_diary.cli.load_config")
    def test_search_date_to_filter(self, mock_config, mock_index,
                                   base_config, sample_index_entries, capsys):
        """Line 167: date_to filter."""
        mock_config.return_value = base_config
        mock_index.return_value = {"entries": sample_index_entries}

        args = Namespace(
            keyword="my-app", project=None, category=None,
            date_from=None, date_to="2026-03-11", json_output=False,
        )
        cmd_search(args)
        captured = capsys.readouterr()
        assert "Found 1" in captured.out

    @patch("claude_diary.cli.load_index")
    @patch("claude_diary.cli.load_config")
    def test_search_category_filter(self, mock_config, mock_index,
                                    base_config, sample_index_entries, capsys):
        """Line 173: category filter."""
        mock_config.return_value = base_config
        mock_index.return_value = {"entries": sample_index_entries}

        args = Namespace(
            keyword="my-app", project=None, category="bugfix",
            date_from=None, date_to=None, json_output=False,
        )
        cmd_search(args)
        captured = capsys.readouterr()
        assert "Found 1" in captured.out


# ── cmd_audit with failed exporters ──

class TestCmdAuditFailedExporters:

    @patch("claude_diary.cli.load_config")
    def test_audit_with_failed_exporters(self, mock_config, base_config, capsys):
        """Line 780: exporters_failed output."""
        mock_config.return_value = base_config
        fake_entries = [
            {
                "timestamp": "2026-03-17T10:00:00+09:00",
                "session_id": "abcdef1234567890",
                "files_written": ["2026-03-17.md"],
                "secrets_masked": 0,
                "exporters_called": ["notion"],
                "exporters_failed": ["slack"],
            },
        ]
        with patch("claude_diary.lib.audit.read_audit_log", return_value=fake_entries):
            args = Namespace(verify=False, days=None, n=10)
            cmd_audit(args)
        captured = capsys.readouterr()
        assert "FAILED:slack" in captured.out
