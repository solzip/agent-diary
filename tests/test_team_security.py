"""Tests for team security module."""

import os
from claude_diary.lib.team_security import (
    mask_paths, filter_content, filter_entry_data,
    should_skip_session, check_access, apply_access_filter,
)


class TestMaskPaths:
    def test_masks_credentials(self):
        files = ["/app/credentials/key.py", "/app/src/main.py"]
        masked = mask_paths(files, ["**/credentials/**"])
        assert masked[0] == "[MASKED]"
        assert masked[1] == "/app/src/main.py"

    def test_masks_env_files(self):
        files = ["/app/.env.local", "/app/src/config.py"]
        masked = mask_paths(files, ["**/.env*"])
        assert masked[0] == "[MASKED]"
        assert masked[1] == "/app/src/config.py"

    def test_masks_secrets_dir(self):
        files = ["/app/secrets/key.pem"]
        masked = mask_paths(files, ["**/secrets/**"])
        assert masked[0] == "[MASKED]"

    def test_no_false_positive(self):
        files = ["/app/src/main.py", "/app/utils/helper.py"]
        masked = mask_paths(files, ["**/credentials/**"])
        assert masked == files

    def test_empty_patterns(self):
        files = ["/app/secrets/key.py"]
        assert mask_paths(files, []) == files

    def test_empty_files(self):
        assert mask_paths([], ["**/secrets/**"]) == []


class TestFilterContent:
    def test_redact_mode(self):
        text = "Fixed the salary calculation bug"
        result = filter_content(text, ["salary"], mode="redact")
        assert "salary" not in result.lower()
        assert "[REDACTED]" in result

    def test_skip_mode(self):
        text = "Updated salary module"
        result = filter_content(text, ["salary"], mode="skip")
        assert result is None

    def test_no_match(self):
        text = "Fixed the login bug"
        result = filter_content(text, ["salary"], mode="redact")
        assert result == text

    def test_empty_keywords(self):
        text = "Some text"
        assert filter_content(text, [], mode="redact") == text

    def test_empty_text(self):
        assert filter_content("", ["salary"]) == ""


class TestFilterEntryData:
    def test_redact_prompts(self):
        entry = {
            "user_prompts": ["Fix the salary bug"],
            "summary_hints": ["Updated payroll"],
            "commands_run": [],
        }
        result = filter_entry_data(entry, ["salary", "payroll"], mode="redact")
        assert result is True
        assert "salary" not in entry["user_prompts"][0].lower()

    def test_skip_entire_session(self):
        entry = {
            "user_prompts": ["Check salary details"],
            "summary_hints": [],
            "commands_run": [],
        }
        result = filter_entry_data(entry, ["salary"], mode="skip")
        assert result is False


class TestShouldSkipSession:
    def test_env_var_skip(self, monkeypatch):
        monkeypatch.setenv("CLAUDE_DIARY_SKIP", "1")
        assert should_skip_session("/some/dir", {}) is True

    def test_env_var_no_skip(self, monkeypatch):
        monkeypatch.setenv("CLAUDE_DIARY_SKIP", "0")
        assert should_skip_session("/some/dir", {}) is False

    def test_project_skip(self):
        config = {"skip_projects": ["personal-notes"]}
        assert should_skip_session("/home/sol/personal-notes", config) is True
        assert should_skip_session("/home/sol/work-project", config) is False

    def test_no_skip_default(self, monkeypatch):
        monkeypatch.delenv("CLAUDE_DIARY_SKIP", raising=False)
        assert should_skip_session("/dir", {}) is False


class TestCheckAccess:
    def test_own_diary_always_full(self):
        assert check_access("member", "sol", "sol") == "full"

    def test_admin_sees_all(self):
        assert check_access("admin", "sol", "alex") == "full"

    def test_member_sees_summary(self):
        assert check_access("member", "sol", "alex") == "summary"

    def test_lead_same_project_full(self):
        assert check_access("lead", "sol", "alex", "app", ["app"]) == "full"

    def test_lead_different_project(self):
        result = check_access("lead", "sol", "alex", "other", ["app"])
        assert result == "full"  # lead sees full for others_diary


class TestApplyAccessFilter:
    def test_full_access(self):
        entry = {"date": "2026-03-17", "user_prompts": ["secret stuff"], "project": "app"}
        result = apply_access_filter(entry, "full")
        assert result == entry

    def test_summary_access(self):
        entry = {
            "date": "2026-03-17", "time": "10:00", "project": "app",
            "categories": ["feature"], "code_stats": {"added": 10},
            "user_prompts": ["secret stuff"], "git_info": {"branch": "main"},
        }
        result = apply_access_filter(entry, "summary")
        assert "user_prompts" not in result
        assert result["project"] == "app"
        assert result["categories"] == ["feature"]

    def test_none_access(self):
        result = apply_access_filter({"date": "2026-03-17"}, "none")
        assert result == {}
