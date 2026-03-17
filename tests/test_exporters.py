"""Tests for exporters (base, loader, slack, obsidian)."""

import json
import os
from unittest.mock import patch, MagicMock

from claude_diary.exporters.base import BaseExporter
from claude_diary.exporters.loader import load_exporters, run_exporters


SAMPLE_ENTRY = {
    "date": "2026-03-17",
    "time": "15:00:00",
    "project": "test-app",
    "categories": ["feature"],
    "user_prompts": ["Add login"],
    "files_created": [],
    "files_modified": ["src/auth.py"],
    "commands_run": ["npm test"],
    "summary_hints": ["Login implemented"],
    "git_info": {"branch": "main", "commits": [], "diff_stat": {"added": 10, "deleted": 2, "files": 1}},
    "code_stats": {"added": 10, "deleted": 2, "files": 1},
    "secrets_masked": 0,
}


class TestBaseExporter:
    def test_not_implemented(self):
        exp = BaseExporter({})
        try:
            exp.export({})
            assert False, "Should raise"
        except NotImplementedError:
            pass

    def test_trust_level_default(self):
        assert BaseExporter.TRUST_LEVEL == "custom"


class TestLoadExporters:
    def test_empty_config(self):
        assert load_exporters({"exporters": {}}) == []

    def test_disabled_exporter(self):
        config = {"exporters": {"slack": {"enabled": False, "webhook_url": "https://hooks.slack.com/test"}}}
        assert load_exporters(config) == []

    def test_invalid_config_rejected(self):
        config = {"exporters": {"slack": {"enabled": True, "webhook_url": "invalid"}}}
        loaded = load_exporters(config)
        assert len(loaded) == 0

    def test_valid_slack_loaded(self):
        config = {"exporters": {"slack": {"enabled": True, "webhook_url": "https://hooks.slack.com/test"}}}
        loaded = load_exporters(config)
        assert len(loaded) == 1
        assert loaded[0][0] == "slack"

    def test_nonexistent_exporter(self):
        config = {"exporters": {"nonexistent": {"enabled": True}}}
        loaded = load_exporters(config)
        assert len(loaded) == 0


class TestRunExporters:
    def test_success(self):
        mock_exp = MagicMock()
        mock_exp.export.return_value = True
        result = run_exporters([("test", mock_exp)], SAMPLE_ENTRY)
        assert "test" in result["success"]
        assert result["failed"] == []

    def test_failure_caught(self):
        mock_exp = MagicMock()
        mock_exp.export.side_effect = Exception("Network error")
        result = run_exporters([("test", mock_exp)], SAMPLE_ENTRY)
        assert "test" in result["failed"]


class TestSlackExporter:
    def test_validate_config(self):
        from claude_diary.exporters.slack import SlackExporter
        assert SlackExporter({"webhook_url": "https://hooks.slack.com/test"}).validate_config()
        assert not SlackExporter({"webhook_url": "invalid"}).validate_config()
        assert not SlackExporter({}).validate_config()

    @patch("urllib.request.urlopen")
    def test_export_success(self, mock_urlopen):
        from claude_diary.exporters.slack import SlackExporter
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_urlopen.return_value = mock_resp

        exp = SlackExporter({"webhook_url": "https://hooks.slack.com/test"})
        result = exp.export(SAMPLE_ENTRY)
        assert result is True
        mock_urlopen.assert_called_once()


class TestObsidianExporter:
    def test_validate_config(self, tmp_path):
        from claude_diary.exporters.obsidian import ObsidianExporter
        assert ObsidianExporter({"vault_path": str(tmp_path)}).validate_config()
        assert not ObsidianExporter({"vault_path": "/nonexistent"}).validate_config()
        assert not ObsidianExporter({}).validate_config()

    def test_export_creates_file(self, tmp_path):
        from claude_diary.exporters.obsidian import ObsidianExporter
        exp = ObsidianExporter({"vault_path": str(tmp_path)})
        result = exp.export(SAMPLE_ENTRY)
        assert result is True
        diary_file = tmp_path / "claude-diary" / "2026-03-17.md"
        assert diary_file.exists()
        content = diary_file.read_text(encoding="utf-8")
        assert "test-app" in content
        assert "feature" in content
