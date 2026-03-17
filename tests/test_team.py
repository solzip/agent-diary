"""Tests for team management module."""

import json
import os

import pytest
from unittest.mock import patch, MagicMock
from collections import Counter

from claude_diary.team import (
    load_team_config,
    get_team_repo_path,
    team_stats,
    team_weekly_report,
)


class TestLoadTeamConfig:
    """Tests for load_team_config()."""

    def test_loads_valid_config(self, tmp_path):
        config_data = {"team_name": "alpha", "members": ["alice", "bob"]}
        config_file = tmp_path / ".team-config.json"
        config_file.write_text(json.dumps(config_data), encoding="utf-8")

        result = load_team_config(str(tmp_path))
        assert result is not None
        assert result["team_name"] == "alpha"
        assert result["members"] == ["alice", "bob"]

    def test_returns_none_when_file_missing(self, tmp_path):
        result = load_team_config(str(tmp_path))
        assert result is None

    def test_returns_none_on_invalid_json(self, tmp_path):
        config_file = tmp_path / ".team-config.json"
        config_file.write_text("not valid json {{{", encoding="utf-8")

        result = load_team_config(str(tmp_path))
        assert result is None

    def test_returns_none_on_empty_file(self, tmp_path):
        config_file = tmp_path / ".team-config.json"
        config_file.write_text("", encoding="utf-8")

        result = load_team_config(str(tmp_path))
        assert result is None


class TestGetTeamRepoPath:
    """Tests for get_team_repo_path()."""

    def test_returns_expanded_path(self):
        config = {"team": {"repo_path": "~/team-diary/.team-repo"}}
        result = get_team_repo_path(config)
        assert result is not None
        assert "~" not in result
        assert ".team-repo" in result

    def test_returns_none_when_team_not_configured(self):
        config = {}
        result = get_team_repo_path(config)
        assert result is None

    def test_returns_none_when_repo_path_empty(self):
        config = {"team": {"repo_path": ""}}
        result = get_team_repo_path(config)
        assert result is None

    def test_loads_config_when_none_passed(self, monkeypatch, tmp_path):
        """When config=None, load_config() is called automatically."""
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        monkeypatch.setenv("APPDATA", str(tmp_path))
        monkeypatch.delenv("CLAUDE_DIARY_DIR", raising=False)

        config_dir = tmp_path / "claude-diary"
        config_dir.mkdir()
        config_file = config_dir / "config.json"
        config_file.write_text(json.dumps({
            "team": {"repo_path": "/some/team/repo"}
        }))

        result = get_team_repo_path()
        assert result == "/some/team/repo"


class TestTeamStats:
    """Tests for team_stats()."""

    def _make_daily_file(self, member_path, date_str, sessions=1, project="my-proj"):
        """Helper to create a minimal diary .md file for a member."""
        filepath = os.path.join(member_path, "%s.md" % date_str)
        content_parts = []
        for _ in range(sessions):
            content_parts.append(
                "### \u23f0 10:00:00\n"
                "\U0001f4c1 `%s`\n"
                "Categories: `feature`\n"
                "Files Created:\n"
                "  - `src/app.py`\n"
                "Files Modified:\n"
                "  - `src/main.py`\n" % project
            )
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n---\n\n".join(content_parts))

    @patch("claude_diary.team.load_config")
    def test_member_stats_aggregated(self, mock_config, tmp_path):
        mock_config.return_value = {"timezone_offset": 9}

        members_dir = tmp_path / "members"
        alice_dir = members_dir / "alice"
        alice_dir.mkdir(parents=True)
        bob_dir = members_dir / "bob"
        bob_dir.mkdir(parents=True)

        self._make_daily_file(str(alice_dir), "2026-03-01", sessions=2, project="proj-a")
        self._make_daily_file(str(bob_dir), "2026-03-01", sessions=1, project="proj-b")

        result = team_stats(str(tmp_path), month="2026-03")
        assert result is not None
        assert result["month"] == "2026-03"
        assert result["total_sessions"] == 3
        assert "alice" in result["members"]
        assert "bob" in result["members"]
        assert result["members"]["alice"]["sessions"] == 2
        assert result["members"]["bob"]["sessions"] == 1

    @patch("claude_diary.team.load_config")
    def test_no_members_directory(self, mock_config, tmp_path, capsys):
        mock_config.return_value = {"timezone_offset": 9}

        result = team_stats(str(tmp_path), month="2026-03")
        captured = capsys.readouterr()
        assert "No members directory" in captured.out
        assert result is None

    @patch("claude_diary.team.load_config")
    def test_defaults_to_current_month(self, mock_config, tmp_path):
        mock_config.return_value = {"timezone_offset": 9}

        members_dir = tmp_path / "members"
        alice_dir = members_dir / "alice"
        alice_dir.mkdir(parents=True)

        result = team_stats(str(tmp_path))
        assert result is not None
        # Should contain a valid month string YYYY-MM
        assert len(result["month"]) == 7
        assert "-" in result["month"]

    @patch("claude_diary.team.load_config")
    def test_project_counter_across_members(self, mock_config, tmp_path):
        mock_config.return_value = {"timezone_offset": 9}

        members_dir = tmp_path / "members"
        alice_dir = members_dir / "alice"
        alice_dir.mkdir(parents=True)
        bob_dir = members_dir / "bob"
        bob_dir.mkdir(parents=True)

        self._make_daily_file(str(alice_dir), "2026-03-02", sessions=1, project="shared-proj")
        self._make_daily_file(str(bob_dir), "2026-03-02", sessions=3, project="shared-proj")

        result = team_stats(str(tmp_path), month="2026-03")
        assert result["projects"]["shared-proj"] == 4


class TestTeamWeeklyReport:
    """Tests for team_weekly_report()."""

    def _make_daily_file(self, member_path, date_str, sessions=1, project="proj"):
        filepath = os.path.join(member_path, "%s.md" % date_str)
        content_parts = []
        for _ in range(sessions):
            content_parts.append(
                "### \u23f0 10:00:00\n"
                "\U0001f4c1 `%s`\n"
                "Categories: `feature`\n"
                "Work Summary:\n"
                "  - Implemented feature X\n" % project
            )
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n---\n\n".join(content_parts))

    @patch("claude_diary.team.load_config")
    def test_generates_report(self, mock_config, tmp_path):
        mock_config.return_value = {"timezone_offset": 9}

        members_dir = tmp_path / "members"
        alice_dir = members_dir / "alice"
        alice_dir.mkdir(parents=True)

        # 2026-03-16 is a Monday
        self._make_daily_file(str(alice_dir), "2026-03-16", sessions=2, project="alpha")
        self._make_daily_file(str(alice_dir), "2026-03-17", sessions=1, project="alpha")

        result = team_weekly_report(str(tmp_path), target_date="2026-03-17")
        assert result is not None
        report, filepath = result
        assert "Team Weekly Report" in report
        assert "alice" in report
        assert os.path.exists(filepath)

    @patch("claude_diary.team.load_config")
    def test_returns_none_when_no_members_dir(self, mock_config, tmp_path):
        mock_config.return_value = {"timezone_offset": 9}

        result = team_weekly_report(str(tmp_path), target_date="2026-03-17")
        assert result is None

    @patch("claude_diary.team.load_config")
    def test_saves_report_file(self, mock_config, tmp_path):
        mock_config.return_value = {"timezone_offset": 9}

        members_dir = tmp_path / "members"
        alice_dir = members_dir / "alice"
        alice_dir.mkdir(parents=True)

        self._make_daily_file(str(alice_dir), "2026-03-16", sessions=1, project="beta")

        result = team_weekly_report(str(tmp_path), target_date="2026-03-16")
        assert result is not None
        report, filepath = result
        assert filepath.endswith(".md")
        assert "weekly" in filepath

        # Verify file content matches returned report
        with open(filepath, "r", encoding="utf-8") as f:
            saved = f.read()
        assert saved == report

    @patch("claude_diary.team.load_config")
    def test_defaults_to_current_date(self, mock_config, tmp_path):
        mock_config.return_value = {"timezone_offset": 9}

        members_dir = tmp_path / "members"
        alice_dir = members_dir / "alice"
        alice_dir.mkdir(parents=True)

        result = team_weekly_report(str(tmp_path))
        # With no activity, result has empty member summaries but still a report
        assert result is not None
        report, filepath = result
        assert "Team Weekly Report" in report
