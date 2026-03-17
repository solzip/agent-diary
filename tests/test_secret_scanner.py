"""Tests for secret scanner."""

from claude_diary.lib.secret_scanner import scan_and_mask, scan_entry_data


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
