"""Tests for core pipeline."""

import json
import os
import tempfile

from claude_diary.core import process_session, _extract_project_name


class TestExtractProjectName:
    def test_unix_path(self):
        assert _extract_project_name("/home/sol/my-project") == "my-project"

    def test_windows_path(self):
        assert _extract_project_name("C:\\Users\\sol\\my-project") == "my-project"

    def test_trailing_slash(self):
        assert _extract_project_name("/home/sol/my-project/") == "my-project"

    def test_empty(self):
        assert _extract_project_name("") == "unknown"

    def test_none(self):
        assert _extract_project_name(None) == "unknown"


class TestProcessSession:
    def test_empty_transcript_skipped(self, tmp_path, monkeypatch):
        monkeypatch.setenv("APPDATA", str(tmp_path))
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

        transcript = tmp_path / "empty.jsonl"
        transcript.write_text("")

        result = process_session("test-001", str(transcript), str(tmp_path))
        assert result is False

    def test_valid_transcript_creates_diary(self, tmp_path, monkeypatch):
        monkeypatch.setenv("APPDATA", str(tmp_path))
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        monkeypatch.setenv("CLAUDE_DIARY_DIR", str(tmp_path / "diary"))

        transcript = tmp_path / "session.jsonl"
        entries = [
            {"type": "user", "message": {"content": [{"type": "text", "text": "Implement login feature"}]}, "timestamp": "2026-03-17T10:00:00Z"},
            {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Write", "input": {"file_path": "/tmp/auth.py"}}]}, "timestamp": "2026-03-17T10:01:00Z"},
        ]
        transcript.write_text("\n".join(json.dumps(e) for e in entries))

        result = process_session("test-002", str(transcript), str(tmp_path))
        assert result is True

        # Check diary file exists
        diary_dir = str(tmp_path / "diary")
        diary_files = [f for f in os.listdir(diary_dir) if f.endswith(".md")]
        assert len(diary_files) > 0

    def test_opt_out_skips(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CLAUDE_DIARY_SKIP", "1")
        monkeypatch.setenv("APPDATA", str(tmp_path))
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

        transcript = tmp_path / "session.jsonl"
        transcript.write_text(json.dumps({
            "type": "user", "message": {"content": [{"type": "text", "text": "Do something"}]},
            "timestamp": "2026-03-17T10:00:00Z"
        }))

        result = process_session("test-003", str(transcript), str(tmp_path))
        assert result is False
