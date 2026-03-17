"""Tests for configuration management."""

import json
import os
import tempfile
import pytest

from claude_diary.config import load_config, save_config, get_config_dir, DEFAULT_CONFIG


class TestLoadConfig:
    def test_defaults(self, monkeypatch):
        monkeypatch.delenv("CLAUDE_DIARY_LANG", raising=False)
        monkeypatch.delenv("CLAUDE_DIARY_DIR", raising=False)
        monkeypatch.delenv("CLAUDE_DIARY_TZ_OFFSET", raising=False)
        monkeypatch.setenv("XDG_CONFIG_HOME", "/nonexistent_config_dir")
        monkeypatch.setenv("APPDATA", "/nonexistent_config_dir")
        config = load_config()
        assert config["lang"] == "ko"
        assert config["timezone_offset"] == 9

    def test_env_var_override(self, monkeypatch):
        monkeypatch.setenv("CLAUDE_DIARY_LANG", "en")
        monkeypatch.setenv("CLAUDE_DIARY_TZ_OFFSET", "-5")
        monkeypatch.setenv("XDG_CONFIG_HOME", "/nonexistent_config_dir")
        monkeypatch.setenv("APPDATA", "/nonexistent_config_dir")
        config = load_config()
        assert config["lang"] == "en"
        assert config["timezone_offset"] == -5

    def test_config_file_overrides_env(self, monkeypatch, tmp_path):
        monkeypatch.setenv("CLAUDE_DIARY_LANG", "en")
        config_dir = tmp_path / "claude-diary"
        config_dir.mkdir()
        config_file = config_dir / "config.json"
        config_file.write_text(json.dumps({"lang": "ko"}))
        # Set both XDG and APPDATA so it works on all platforms
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        monkeypatch.setenv("APPDATA", str(tmp_path))
        config = load_config()
        # config.json > env vars
        assert config["lang"] == "ko"

    def test_invalid_tz_offset_ignored(self, monkeypatch):
        monkeypatch.setenv("CLAUDE_DIARY_TZ_OFFSET", "not_a_number")
        monkeypatch.setenv("XDG_CONFIG_HOME", "/nonexistent_config_dir")
        monkeypatch.setenv("APPDATA", "/nonexistent_config_dir")
        config = load_config()
        assert config["timezone_offset"] == 9  # default


class TestSaveConfig:
    def test_creates_directory_and_file(self, monkeypatch, tmp_path):
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        monkeypatch.setenv("APPDATA", str(tmp_path))
        save_config({"lang": "en", "timezone_offset": -5})
        config_file = tmp_path / "claude-diary" / "config.json"
        assert config_file.exists()
        data = json.loads(config_file.read_text())
        assert data["lang"] == "en"
