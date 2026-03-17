"""Tests for auto-categorizer."""

from claude_diary.lib.categorizer import categorize


class TestCategorize:
    def test_feature_detection_korean(self):
        entry = {"user_prompts": ["새로운 기능을 구현해줘"], "summary_hints": [], "commands_run": [], "files_created": [], "files_modified": []}
        cats = categorize(entry)
        assert "feature" in cats

    def test_bugfix_detection_english(self):
        entry = {"user_prompts": ["fix the login bug"], "summary_hints": [], "commands_run": [], "files_created": [], "files_modified": []}
        cats = categorize(entry)
        assert "bugfix" in cats

    def test_refactor_detection(self):
        entry = {"user_prompts": ["refactor the authentication module"], "summary_hints": [], "commands_run": [], "files_created": [], "files_modified": []}
        cats = categorize(entry)
        assert "refactor" in cats

    def test_docs_from_file_extension(self):
        entry = {"user_prompts": ["update the file"], "summary_hints": [], "commands_run": [], "files_created": [], "files_modified": ["README.md"]}
        cats = categorize(entry)
        assert "docs" in cats

    def test_test_from_file_pattern(self):
        entry = {"user_prompts": ["check this"], "summary_hints": [], "commands_run": [], "files_created": ["test_auth.py"], "files_modified": []}
        cats = categorize(entry)
        assert "test" in cats

    def test_max_three_categories(self):
        entry = {"user_prompts": ["implement new feature, fix bug, refactor code, update docs, add tests"], "summary_hints": [], "commands_run": [], "files_created": [], "files_modified": []}
        cats = categorize(entry)
        assert len(cats) <= 3

    def test_empty_entry(self):
        entry = {"user_prompts": [], "summary_hints": [], "commands_run": [], "files_created": [], "files_modified": []}
        cats = categorize(entry)
        assert cats == []

    def test_custom_rules(self):
        entry = {"user_prompts": ["perf optimization needed"], "summary_hints": [], "commands_run": [], "files_created": [], "files_modified": []}
        custom = {"performance": ["perf", "optimization", "benchmark"]}
        cats = categorize(entry, custom_rules=custom)
        assert "performance" in cats
