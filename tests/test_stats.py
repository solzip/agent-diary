"""Tests for statistics engine."""

import os

from claude_diary.lib.stats import parse_daily_file


class TestParseDailyFileBasic:
    def test_nonexistent_file(self):
        result = parse_daily_file("/nonexistent/2026-03-17.md")
        assert result["sessions"] == 0
        assert result["projects"] == set()

    def test_empty_file(self, tmp_path):
        f = tmp_path / "2026-03-17.md"
        f.write_text("", encoding="utf-8")
        result = parse_daily_file(str(f))
        assert result["sessions"] == 0
        assert result["projects"] == set()
        assert result["files_created"] == []
        assert result["files_modified"] == []

    def test_unreadable_file(self, tmp_path):
        """File that causes an encoding error on read."""
        f = tmp_path / "2026-03-17.md"
        f.write_bytes(b"\x80\x81\x82")
        # Force an error by making file unreadable via a mock
        from unittest.mock import patch, mock_open
        with patch("builtins.open", side_effect=PermissionError("no access")):
            result = parse_daily_file(str(f))
        assert result["sessions"] == 0


class TestParseDailyFileSessions:
    def test_counts_sessions(self, tmp_path):
        content = (
            "# 2026-03-17\n"
            "### \u23f0 10:00:00\n"
            "Some work\n"
            "### \u23f0 14:00:00\n"
            "More work\n"
            "### \u23f0 18:00:00\n"
            "Even more work\n"
        )
        f = tmp_path / "2026-03-17.md"
        f.write_text(content, encoding="utf-8")
        result = parse_daily_file(str(f))
        assert result["sessions"] == 3


class TestParseDailyFileProjects:
    def test_extracts_projects(self, tmp_path):
        content = (
            "### \u23f0 10:00:00\n"
            "\U0001f4c1 `my-project`\n"
            "### \u23f0 14:00:00\n"
            "\U0001f4c1 `other-project`\n"
        )
        f = tmp_path / "2026-03-17.md"
        f.write_text(content, encoding="utf-8")
        result = parse_daily_file(str(f))
        assert result["projects"] == {"my-project", "other-project"}

    def test_duplicate_projects(self, tmp_path):
        content = (
            "### \u23f0 10:00:00\n"
            "\U0001f4c1 `my-project`\n"
            "### \u23f0 14:00:00\n"
            "\U0001f4c1 `my-project`\n"
        )
        f = tmp_path / "2026-03-17.md"
        f.write_text(content, encoding="utf-8")
        result = parse_daily_file(str(f))
        assert result["projects"] == {"my-project"}


class TestParseDailyFileFiles:
    def test_extracts_files_created_korean(self, tmp_path):
        content = (
            "### \u23f0 10:00:00\n"
            "\uc0dd\uc131\ub41c \ud30c\uc77c:\n"
            "  - `src/app.py`\n"
            "  - `src/util.py`\n"
        )
        f = tmp_path / "2026-03-17.md"
        f.write_text(content, encoding="utf-8")
        result = parse_daily_file(str(f))
        assert "src/app.py" in result["files_created"]
        assert "src/util.py" in result["files_created"]

    def test_extracts_files_created_english(self, tmp_path):
        content = (
            "### \u23f0 10:00:00\n"
            "Files Created:\n"
            "  - `main.js`\n"
        )
        f = tmp_path / "2026-03-17.md"
        f.write_text(content, encoding="utf-8")
        result = parse_daily_file(str(f))
        assert "main.js" in result["files_created"]

    def test_extracts_files_modified_korean(self, tmp_path):
        content = (
            "### \u23f0 10:00:00\n"
            "\uc218\uc815\ub41c \ud30c\uc77c:\n"
            "  - `config.yaml`\n"
        )
        f = tmp_path / "2026-03-17.md"
        f.write_text(content, encoding="utf-8")
        result = parse_daily_file(str(f))
        assert "config.yaml" in result["files_modified"]

    def test_extracts_files_modified_english(self, tmp_path):
        content = (
            "### \u23f0 10:00:00\n"
            "Files Modified:\n"
            "  - `index.html`\n"
        )
        f = tmp_path / "2026-03-17.md"
        f.write_text(content, encoding="utf-8")
        result = parse_daily_file(str(f))
        assert "index.html" in result["files_modified"]


class TestParseDailyFileTasks:
    def test_extracts_tasks_korean(self, tmp_path):
        content = (
            "### \u23f0 10:00:00\n"
            "\uc791\uc5c5 \uc694\uc57d:\n"
            "  - \ub85c\uadf8\uc778 \uae30\ub2a5 \uad6c\ud604\n"
            "  - \ud14c\uc2a4\ud2b8 \uc791\uc131\n"
        )
        f = tmp_path / "2026-03-17.md"
        f.write_text(content, encoding="utf-8")
        result = parse_daily_file(str(f))
        assert len(result["tasks"]) == 2
        assert "\ub85c\uadf8\uc778 \uae30\ub2a5 \uad6c\ud604" in result["tasks"]

    def test_extracts_tasks_english(self, tmp_path):
        content = (
            "### \u23f0 10:00:00\n"
            "Work Summary:\n"
            "  - Implemented auth module\n"
        )
        f = tmp_path / "2026-03-17.md"
        f.write_text(content, encoding="utf-8")
        result = parse_daily_file(str(f))
        assert "Implemented auth module" in result["tasks"]


class TestParseDailyFileIssues:
    def test_extracts_issues_korean(self, tmp_path):
        content = (
            "### \u23f0 10:00:00\n"
            "\ubc1c\uc0dd\ud55c \uc774\uc288:\n"
            "  - DB \uc5f0\uacb0 \uc2e4\ud328\n"
        )
        f = tmp_path / "2026-03-17.md"
        f.write_text(content, encoding="utf-8")
        result = parse_daily_file(str(f))
        assert "DB \uc5f0\uacb0 \uc2e4\ud328" in result["issues"]

    def test_extracts_issues_english(self, tmp_path):
        content = (
            "### \u23f0 10:00:00\n"
            "Issues Encountered:\n"
            "  - Timeout on API call\n"
        )
        f = tmp_path / "2026-03-17.md"
        f.write_text(content, encoding="utf-8")
        result = parse_daily_file(str(f))
        assert "Timeout on API call" in result["issues"]


class TestParseDailyFileCategories:
    def test_extracts_categories_korean(self, tmp_path):
        content = (
            "### \u23f0 10:00:00\n"
            "\uce74\ud14c\uace0\ub9ac: `backend`\n"
        )
        f = tmp_path / "2026-03-17.md"
        f.write_text(content, encoding="utf-8")
        result = parse_daily_file(str(f))
        assert "backend" in result["categories"]

    def test_extracts_categories_english(self, tmp_path):
        content = (
            "### \u23f0 10:00:00\n"
            "Categories: `frontend`\n"
        )
        f = tmp_path / "2026-03-17.md"
        f.write_text(content, encoding="utf-8")
        result = parse_daily_file(str(f))
        assert "frontend" in result["categories"]


class TestParseDailyFileRawEntries:
    def test_extracts_task_requests_korean(self, tmp_path):
        content = (
            "### \u23f0 10:00:00\n"
            "\uc791\uc5c5 \uc694\uccad:\n"
            "  1. \ub85c\uadf8\uc778 \ubc84\uadf8 \uc218\uc815\n"
            "  2. \ud14c\uc2a4\ud2b8 \ucf54\ub4dc \ucd94\uac00\n"
        )
        f = tmp_path / "2026-03-17.md"
        f.write_text(content, encoding="utf-8")
        result = parse_daily_file(str(f))
        assert len(result["raw_entries"]) == 2
        assert "\ub85c\uadf8\uc778 \ubc84\uadf8 \uc218\uc815" in result["raw_entries"]

    def test_extracts_task_requests_english(self, tmp_path):
        content = (
            "### \u23f0 10:00:00\n"
            "Task Requests:\n"
            "  1. Fix authentication\n"
            "  2. Write unit tests\n"
        )
        f = tmp_path / "2026-03-17.md"
        f.write_text(content, encoding="utf-8")
        result = parse_daily_file(str(f))
        assert "Fix authentication" in result["raw_entries"]
        assert "Write unit tests" in result["raw_entries"]


class TestParseDailyFileFullDocument:
    def test_full_diary_entry(self, tmp_path):
        content = (
            "# \U0001f4dd 2026-03-17\n\n"
            "### \u23f0 10:00:00\n"
            "\U0001f4c1 `my-app`\n\n"
            "\uce74\ud14c\uace0\ub9ac: `feature`\n\n"
            "\uc0dd\uc131\ub41c \ud30c\uc77c:\n"
            "  - `src/new.py`\n\n"
            "\uc218\uc815\ub41c \ud30c\uc77c:\n"
            "  - `src/old.py`\n\n"
            "\uc791\uc5c5 \uc694\uc57d:\n"
            "  - Added new feature\n\n"
            "\ubc1c\uc0dd\ud55c \uc774\uc288:\n"
            "  - Minor typo\n\n"
            "\uc791\uc5c5 \uc694\uccad:\n"
            "  1. Build the feature\n\n"
            "### \u23f0 14:00:00\n"
            "\U0001f4c1 `other-app`\n"
        )
        f = tmp_path / "2026-03-17.md"
        f.write_text(content, encoding="utf-8")
        result = parse_daily_file(str(f))
        assert result["sessions"] == 2
        assert "my-app" in result["projects"]
        assert "other-app" in result["projects"]
        assert "src/new.py" in result["files_created"]
        assert "src/old.py" in result["files_modified"]
        assert "feature" in result["categories"]
        assert len(result["tasks"]) >= 1
        assert len(result["issues"]) >= 1
        assert "Build the feature" in result["raw_entries"]
