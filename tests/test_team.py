"""Tests for team management module."""

import json
import os

import pytest
from unittest.mock import patch, MagicMock
from collections import Counter

from claude_diary.team import (
    load_team_config,
    get_team_repo_path,
    init_team,
    print_team_stats,
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

    @patch("claude_diary.team.load_config")
    def test_english_lang_header(self, mock_config, tmp_path):
        """Line 255: english lang path produces the same header."""
        mock_config.return_value = {"timezone_offset": 9}

        members_dir = tmp_path / "members"
        alice_dir = members_dir / "alice"
        alice_dir.mkdir(parents=True)

        result = team_weekly_report(str(tmp_path), target_date="2026-03-16", lang="en")
        assert result is not None
        report, _ = result
        assert "Team Weekly Report" in report

    @patch("claude_diary.team.load_config")
    def test_skips_non_directory_in_members(self, mock_config, tmp_path):
        """Line 265: files inside members/ are skipped."""
        mock_config.return_value = {"timezone_offset": 9}

        members_dir = tmp_path / "members"
        members_dir.mkdir(parents=True)
        # Create a regular file (not a directory) inside members/
        (members_dir / "README.md").write_text("hello", encoding="utf-8")

        result = team_weekly_report(str(tmp_path), target_date="2026-03-16")
        assert result is not None
        report, _ = result
        # No member summaries since there are no actual member dirs
        assert "Active Members | **0**" in report


class TestInitTeam:
    """Tests for init_team() — lines 43-115."""

    @patch("claude_diary.config.save_config")
    @patch("claude_diary.team.load_team_config")
    @patch("subprocess.run")
    @patch("claude_diary.team.load_config")
    @patch("claude_diary.team.Path")
    def test_clone_new_repo_success(
        self, mock_path_cls, mock_load_config, mock_subprocess, mock_load_team, mock_save_config, capsys
    ):
        mock_load_config.return_value = {"diary_dir": "/tmp/diary"}
        mock_subprocess.return_value = MagicMock(returncode=0)
        mock_load_team.return_value = None

        with patch("os.path.exists", return_value=False):
            result = init_team("https://github.com/team/repo.git", member_name="alice")

        assert result is True
        mock_subprocess.assert_called_once()
        mock_save_config.assert_called_once()
        captured = capsys.readouterr()
        assert "Cloning team repo" in captured.out
        assert "Cloned" in captured.out

    @patch("claude_diary.config.save_config")
    @patch("claude_diary.team.load_team_config")
    @patch("claude_diary.team.load_config")
    @patch("claude_diary.team.Path")
    def test_repo_already_exists(
        self, mock_path_cls, mock_load_config, mock_load_team, mock_save_config, capsys
    ):
        mock_load_config.return_value = {"diary_dir": "/tmp/diary"}
        mock_load_team.return_value = None

        with patch("os.path.exists", return_value=True):
            result = init_team("https://github.com/team/repo.git", member_name="bob")

        assert result is True
        captured = capsys.readouterr()
        assert "already exists" in captured.out

    @patch("claude_diary.team.load_team_config")
    @patch("subprocess.run")
    @patch("claude_diary.team.load_config")
    def test_clone_fails_nonzero_returncode(self, mock_load_config, mock_subprocess, mock_load_team, capsys):
        mock_load_config.return_value = {"diary_dir": "/tmp/diary"}
        mock_subprocess.return_value = MagicMock(returncode=1, stderr="fatal: repo not found")
        mock_load_team.return_value = None

        with patch("os.path.exists", return_value=False):
            result = init_team("https://github.com/team/repo.git", member_name="alice")

        assert result is False
        captured = capsys.readouterr()
        assert "[error] Clone failed" in captured.out

    @patch("claude_diary.team.load_team_config")
    @patch("subprocess.run", side_effect=OSError("network error"))
    @patch("claude_diary.team.load_config")
    def test_clone_fails_exception(self, mock_load_config, mock_subprocess, mock_load_team, capsys):
        mock_load_config.return_value = {"diary_dir": "/tmp/diary"}

        with patch("os.path.exists", return_value=False):
            result = init_team("https://github.com/team/repo.git", member_name="alice")

        assert result is False
        captured = capsys.readouterr()
        assert "network error" in captured.out

    @patch("claude_diary.config.save_config")
    @patch("claude_diary.team.load_team_config")
    @patch("claude_diary.team.load_config")
    @patch("claude_diary.team.Path")
    def test_team_config_loaded_with_security(
        self, mock_path_cls, mock_load_config, mock_load_team, mock_save_config, capsys
    ):
        mock_load_config.return_value = {
            "diary_dir": "/tmp/diary",
            "security": {"mask_paths": ["/old"], "content_filters": ["password"]},
        }
        mock_load_team.return_value = {
            "team_name": "alpha-team",
            "members": ["alice", "bob"],
            "security": {
                "mask_paths": ["/new", "/old"],
                "content_filters": ["secret", "password"],
            },
        }

        with patch("os.path.exists", return_value=True):
            result = init_team("https://github.com/team/repo.git", member_name="alice")

        assert result is True
        captured = capsys.readouterr()
        assert "alpha-team" in captured.out
        assert "alice, bob" in captured.out
        assert "security rules loaded" in captured.out

        saved_config = mock_save_config.call_args[0][0]
        assert "/new" in saved_config["security"]["mask_paths"]
        assert "/old" in saved_config["security"]["mask_paths"]
        assert "secret" in saved_config["security"]["content_filters"]
        assert "password" in saved_config["security"]["content_filters"]

    @patch("claude_diary.config.save_config")
    @patch("claude_diary.team.load_team_config")
    @patch("claude_diary.team.load_config")
    @patch("claude_diary.team.Path")
    def test_default_member_name_from_env(
        self, mock_path_cls, mock_load_config, mock_load_team, mock_save_config
    ):
        mock_load_config.return_value = {"diary_dir": "/tmp/diary"}
        mock_load_team.return_value = None

        with patch("os.path.exists", return_value=True), \
             patch.dict(os.environ, {"USER": "envuser"}, clear=False):
            result = init_team("https://github.com/team/repo.git")

        assert result is True
        saved_config = mock_save_config.call_args[0][0]
        assert saved_config["team"]["member_name"] == "envuser"

    @patch("claude_diary.config.save_config")
    @patch("claude_diary.team.load_team_config")
    @patch("claude_diary.team.load_config")
    @patch("claude_diary.team.Path")
    def test_config_sets_team_and_exporter(
        self, mock_path_cls, mock_load_config, mock_load_team, mock_save_config
    ):
        mock_load_config.return_value = {"diary_dir": "/tmp/diary"}
        mock_load_team.return_value = None

        with patch("os.path.exists", return_value=True):
            init_team("https://github.com/team/repo.git", member_name="carol")

        saved_config = mock_save_config.call_args[0][0]
        assert saved_config["team"]["repo_url"] == "https://github.com/team/repo.git"
        assert saved_config["team"]["member_name"] == "carol"
        assert saved_config["team"]["push_strategy"] == "auto"
        assert saved_config["exporters"]["github"]["enabled"] is True
        assert saved_config["exporters"]["github"]["member_name"] == "carol"

    @patch("claude_diary.config.save_config")
    @patch("claude_diary.team.load_team_config")
    @patch("claude_diary.team.load_config")
    @patch("claude_diary.team.Path")
    def test_team_config_no_security_section(
        self, mock_path_cls, mock_load_config, mock_load_team, mock_save_config, capsys
    ):
        """Team config exists but has no security key — security merge is skipped."""
        mock_load_config.return_value = {"diary_dir": "/tmp/diary"}
        mock_load_team.return_value = {
            "team_name": "beta",
            "members": ["dave"],
        }

        with patch("os.path.exists", return_value=True):
            result = init_team("https://github.com/team/repo.git", member_name="dave")

        assert result is True
        captured = capsys.readouterr()
        assert "beta" in captured.out
        assert "security rules loaded" not in captured.out


class TestPrintTeamStats:
    """Tests for print_team_stats() — lines 184-228."""

    def test_no_data(self, capsys):
        print_team_stats(None)
        captured = capsys.readouterr()
        assert "No team activity found." in captured.out

    def test_empty_members(self, capsys):
        print_team_stats({"members": {}, "total_sessions": 0, "projects": Counter(), "month": "2026-03"})
        captured = capsys.readouterr()
        assert "No team activity found." in captured.out

    def test_prints_formatted_stats(self, capsys):
        stats_data = {
            "month": "2026-03",
            "total_sessions": 5,
            "members": {
                "alice": {
                    "sessions": 3,
                    "projects": Counter({"proj-a": 2, "proj-b": 1}),
                    "categories": Counter({"feature": 2, "bugfix": 1}),
                    "files": 10,
                },
                "bob": {
                    "sessions": 2,
                    "projects": Counter({"proj-a": 2}),
                    "categories": Counter({"feature": 1}),
                    "files": 5,
                },
            },
            "projects": Counter({"proj-a": 4, "proj-b": 1}),
        }

        print_team_stats(stats_data)
        captured = capsys.readouterr()

        assert "Team Stats" in captured.out
        assert "2026-03" in captured.out
        assert "Members: 2" in captured.out
        assert "Sessions: 5" in captured.out
        assert "Projects: 2" in captured.out
        assert "proj-a" in captured.out
        assert "proj-b" in captured.out
        assert "alice" in captured.out
        assert "bob" in captured.out

    def test_prints_stats_no_projects(self, capsys):
        """When projects counter is empty, skip projects section."""
        stats_data = {
            "month": "2026-03",
            "total_sessions": 1,
            "members": {
                "alice": {
                    "sessions": 1,
                    "projects": Counter(),
                    "categories": Counter(),
                    "files": 0,
                },
            },
            "projects": Counter(),
        }

        print_team_stats(stats_data)
        captured = capsys.readouterr()
        assert "Team Stats" in captured.out
        assert "Members: 1" in captured.out

    def test_member_breakdown_in_projects(self, capsys):
        """Verify per-member breakdown appears next to project counts."""
        stats_data = {
            "month": "2026-01",
            "total_sessions": 4,
            "members": {
                "alice": {
                    "sessions": 3,
                    "projects": Counter({"shared": 3}),
                    "categories": Counter(),
                    "files": 0,
                },
                "bob": {
                    "sessions": 1,
                    "projects": Counter({"shared": 1}),
                    "categories": Counter(),
                    "files": 0,
                },
            },
            "projects": Counter({"shared": 4}),
        }

        print_team_stats(stats_data)
        captured = capsys.readouterr()
        assert "alice:3" in captured.out
        assert "bob:1" in captured.out


class TestTeamStatsNonDirSkip:
    """Test that non-directory entries in members/ are skipped (line 146)."""

    def _make_daily_file(self, member_path, date_str, sessions=1, project="my-proj"):
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
    def test_file_in_members_dir_skipped(self, mock_config, tmp_path):
        """A plain file inside members/ should be skipped, not crash."""
        mock_config.return_value = {"timezone_offset": 9}

        members_dir = tmp_path / "members"
        alice_dir = members_dir / "alice"
        alice_dir.mkdir(parents=True)
        self._make_daily_file(str(alice_dir), "2026-03-01", sessions=1)

        # Create a non-directory entry
        (members_dir / ".gitkeep").write_text("", encoding="utf-8")

        result = team_stats(str(tmp_path), month="2026-03")
        assert result is not None
        assert ".gitkeep" not in result["members"]
        assert "alice" in result["members"]

    @patch("claude_diary.team.load_config")
    def test_file_counting(self, mock_config, tmp_path):
        """Line 146/163: files count aggregates files_modified + files_created."""
        mock_config.return_value = {"timezone_offset": 9}

        members_dir = tmp_path / "members"
        alice_dir = members_dir / "alice"
        alice_dir.mkdir(parents=True)
        self._make_daily_file(str(alice_dir), "2026-03-01", sessions=1)

        result = team_stats(str(tmp_path), month="2026-03")
        assert result["members"]["alice"]["files"] >= 1
