"""Tests for markdown formatter."""

from claude_diary.formatter import format_entry, format_daily_header


class TestFormatEntry:
    def test_basic_entry_korean(self):
        entry = {
            "time": "15:30:00",
            "project": "my-app",
            "session_id": "test-12345678",
            "categories": ["feature"],
            "user_prompts": ["Fix the login bug"],
            "files_created": ["src/auth.py"],
            "files_modified": ["src/main.py"],
            "commands_run": ["npm test"],
            "summary_hints": ["Fixed login issue"],
            "errors_encountered": [],
            "git_info": None,
            "code_stats": None,
            "secrets_masked": 0,
        }
        result = format_entry(entry, lang="ko")
        assert "15:30:00" in result
        assert "my-app" in result
        assert "작업 요청" in result
        assert "생성된 파일" in result
        assert "수정된 파일" in result
        assert "test-123" in result

    def test_basic_entry_english(self):
        entry = {
            "time": "10:00:00",
            "project": "test",
            "session_id": "abc12345678",
            "categories": [],
            "user_prompts": ["Hello"],
            "files_created": [],
            "files_modified": [],
            "commands_run": [],
            "summary_hints": [],
            "errors_encountered": [],
            "git_info": None,
            "code_stats": None,
            "secrets_masked": 0,
        }
        result = format_entry(entry, lang="en")
        assert "Task Requests" in result
        assert "Session ID" in result

    def test_git_info_displayed(self):
        entry = {
            "time": "10:00:00", "project": "test", "session_id": "abc12345678",
            "categories": [], "user_prompts": [], "files_created": [],
            "files_modified": [], "commands_run": [], "summary_hints": [],
            "errors_encountered": [],
            "git_info": {
                "branch": "feature/auth",
                "commits": [{"hash": "abc1234", "message": "feat: add auth"}],
                "diff_stat": {"added": 50, "deleted": 10, "files": 3},
            },
            "code_stats": {"added": 50, "deleted": 10, "files": 3},
            "secrets_masked": 0,
        }
        result = format_entry(entry, lang="ko")
        assert "feature/auth" in result
        assert "abc1234" in result
        assert "+50 / -10" in result

    def test_secrets_masked_shown(self):
        entry = {
            "time": "10:00:00", "project": "test", "session_id": "abc12345678",
            "categories": [], "user_prompts": [], "files_created": [],
            "files_modified": [], "commands_run": [], "summary_hints": [],
            "errors_encountered": [], "git_info": None, "code_stats": None,
            "secrets_masked": 3,
        }
        result = format_entry(entry, lang="ko")
        assert "3" in result
        assert "마스킹" in result


class TestFormatDailyHeader:
    def test_korean_header(self):
        header = format_daily_header("2026-03-17", lang="ko")
        assert "작업일지" in header
        assert "2026-03-17" in header
        assert "화" in header

    def test_english_header(self):
        header = format_daily_header("2026-03-17", lang="en")
        assert "Work Diary" in header
        assert "Tue" in header

    def test_invalid_date(self):
        header = format_daily_header("invalid", lang="ko")
        assert "작업일지" in header
