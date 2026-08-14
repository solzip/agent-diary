"""Tests for statistics engine."""


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
        from unittest.mock import patch
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
    """The fixtures here used to write `Categories: \\`frontend\\`` \u2014 a form the
    writer has never produced. `formatter.py` emits a bold label line, and all
    7,040 category lines in a real 73-file diary carry it. Pinning the plain
    form kept a loose pattern alive that also matched the word "\uce74\ud14c\uace0\ub9ac" in
    ordinary prose and invented categories from whatever was in backticks
    beside it."""

    def _parse(self, tmp_path, content):
        f = tmp_path / "2026-03-17.md"
        f.write_text(content, encoding="utf-8")
        return parse_daily_file(str(f))

    def test_extracts_categories_korean(self, tmp_path):
        result = self._parse(tmp_path, "### \u23f0 10:00:00\n"
                                       "**\U0001f3f7\ufe0f \uce74\ud14c\uace0\ub9ac:** `backend`\n")
        assert "backend" in result["categories"]

    def test_extracts_categories_english(self, tmp_path):
        result = self._parse(tmp_path, "### \u23f0 10:00:00\n"
                                       "**\U0001f3f7\ufe0f Categories:** `frontend`\n")
        assert "frontend" in result["categories"]

    def test_it_keeps_every_category_not_just_the_first(self, tmp_path):
        """The defect this class exists for. 91.6% of a real diary's 7,131
        entries carry three categories, and the index and the stats were
        recording one: 20,424 categories in the files, 7,048 counted."""
        result = self._parse(tmp_path, "### \u23f0 10:00:00\n"
                                       "**\U0001f3f7\ufe0f \uce74\ud14c\uace0\ub9ac:** `docs` `feature` `test`\n")
        assert result["categories"] == ["docs", "feature", "test"]

    def test_two_entries_each_keep_their_own(self, tmp_path):
        result = self._parse(
            tmp_path,
            "### \u23f0 10:00:00\n**\U0001f3f7\ufe0f \uce74\ud14c\uace0\ub9ac:** `docs` `test`\n\n"
            "### \u23f0 11:00:00\n**\U0001f3f7\ufe0f \uce74\ud14c\uace0\ub9ac:** `bugfix`\n")
        assert sorted(result["categories"]) == ["bugfix", "docs", "test"]

    def test_the_word_in_prose_does_not_become_a_category(self, tmp_path):
        """Taken from a real entry: a commit message that happens to mention
        categories, with a hash in backticks right beside it. The old pattern
        turned that hash into a category."""
        result = self._parse(
            tmp_path,
            "### \u23f0 10:00:00\n"
            "**\U0001f3f7\ufe0f \uce74\ud14c\uace0\ub9ac:** `bugfix`\n\n"
            "- \ucee4\ubc0b: `f98c96ec5` fix: \uc2e0\uaddc \uce74\ud14c\uace0\ub9ac \uccab \ubd80\ud305 \ub808\uc774\uc2a4\n")
        assert result["categories"] == ["bugfix"]


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
            "**\U0001f3f7\ufe0f \uce74\ud14c\uace0\ub9ac:** `feature` `docs`\n\n"
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
        assert result["categories"] == ["feature", "docs"]
        assert len(result["tasks"]) >= 1
        assert len(result["issues"]) >= 1
        assert "Build the feature" in result["raw_entries"]
