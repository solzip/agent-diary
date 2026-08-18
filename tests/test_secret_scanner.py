"""Tests for secret scanner."""

import re
from pathlib import Path

from claude_diary.lib.secret_scanner import (
    BASIC_PATTERNS,
    scan_and_mask,
    scan_entry_data,
)

ROOT = Path(__file__).resolve().parent.parent


class TestScanAndMask:
    def test_password_detection(self):
        text = "password=mysecretpass123"
        masked, count = scan_and_mask(text)
        assert "mysecretpass123" not in masked
        assert count > 0

    def test_api_key_detection(self):
        text = "api_key=abcdef123456"
        masked, count = scan_and_mask(text)
        assert "abcdef123456" not in masked
        assert count > 0

    def test_openai_key(self):
        text = "Using key sk-abcdefghijklmnopqrstuvwx"
        masked, count = scan_and_mask(text)
        assert "sk-abcdefghijklmnopqrstuvwx" not in masked
        assert "****" in masked

    def test_github_pat(self):
        text = "ghp_aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789"
        masked, count = scan_and_mask(text)
        assert "ghp_" not in masked
        assert count > 0

    def test_aws_key(self):
        text = "AKIAIOSFODNN7EXAMPLE"
        masked, count = scan_and_mask(text)
        assert "AKIAIOSFODNN7EXAMPLE" not in masked

    def test_bearer_token(self):
        text = "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.test"
        masked, count = scan_and_mask(text)
        assert "eyJhbGciOiJIUzI1NiJ9" not in masked

    def test_no_false_positive_on_normal_text(self):
        text = "This is a normal sentence about programming"
        masked, count = scan_and_mask(text)
        assert masked == text
        assert count == 0

    def test_empty_string(self):
        masked, count = scan_and_mask("")
        assert masked == ""
        assert count == 0

    def test_none_input(self):
        masked, count = scan_and_mask(None)
        assert masked is None
        assert count == 0


class TestScanEntryData:
    def test_masks_prompts(self):
        entry = {
            "user_prompts": ["set password=secret123 in config"],
            "summary_hints": [],
            "commands_run": [],
        }
        total = scan_entry_data(entry)
        assert total > 0
        assert "secret123" not in entry["user_prompts"][0]

    def test_masks_commands(self):
        entry = {
            "user_prompts": [],
            "summary_hints": [],
            "commands_run": ["export API_KEY=sk-abcdefghijklmnopqrstuvwxyz123456"],
        }
        total = scan_entry_data(entry)
        assert total > 0

    def test_sets_secrets_masked_count(self):
        entry = {
            "user_prompts": ["token=abc123secret"],
            "summary_hints": ["Used password=test"],
            "commands_run": [],
        }
        scan_entry_data(entry)
        assert entry["secrets_masked"] > 0


class TestTheDocumentedPatternCountMatchesTheCode:
    """Both READMEs print how many patterns ship built in, and that number has
    already been wrong twice.

    The CHANGELOG's 2.0.0 entry said "11+ patterns" while `BASIC_PATTERNS`
    held 9. By 4.12.0 the list had grown to 12 and both READMEs still said
    "11+". Nothing in the suite read either number, so neither could fail —
    the count was prose, and prose does not drift loudly.

    These assertions build the expected text from `BASIC_PATTERNS`, so adding
    a pattern fails here until both READMEs move in the same commit, which is
    what CLAUDE.md asks for anyway.
    """

    def test_the_english_readme_states_the_current_count(self):
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        assert "%d built-in patterns for API keys" % len(BASIC_PATTERNS) in text

    def test_the_korean_readme_states_the_current_count(self):
        text = (ROOT / "README.ko.md").read_text(encoding="utf-8")
        assert "기본 패턴 %d종" % len(BASIC_PATTERNS) in text

    def test_the_english_readme_carries_the_count_exactly_once(self):
        """A second mention drifts on its own. The pattern also matches the
        older `11+ patterns` wording, so a leftover copy fails rather than
        hiding behind different phrasing."""
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        found = re.findall(r"(\d+)\+?\s+(?:built-in\s+)?patterns", text)
        assert found == [str(len(BASIC_PATTERNS))], found

    def test_the_korean_readme_carries_the_count_exactly_once(self):
        text = (ROOT / "README.ko.md").read_text(encoding="utf-8")
        found = re.findall(r"(\d+)종", text)
        assert found == [str(len(BASIC_PATTERNS))], found
