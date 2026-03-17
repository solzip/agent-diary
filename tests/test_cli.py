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
    cmd_stats,
    cmd_weekly,
    cmd_config,
    cmd_reindex,
    cmd_audit,
    cmd_delete,
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
