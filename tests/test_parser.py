"""Tests for transcript parser."""

import json
import os
import tempfile
import pytest

from claude_diary.lib.parser import parse_transcript, get_session_time_range


def _write_transcript(lines):
    """Write a temporary JSONL transcript file."""
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False, encoding="utf-8")
    for entry in lines:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    f.close()
    return f.name


class TestParseTranscript:
    def test_empty_file(self, tmp_path):
        p = tmp_path / "empty.jsonl"
        p.write_text("")
        result = parse_transcript(str(p))
        assert result["user_prompts"] == []
        assert result["files_created"] == []

    def test_nonexistent_file(self):
        result = parse_transcript("/nonexistent/file.jsonl")
        assert result["user_prompts"] == []

    def test_user_message_extraction(self):
        path = _write_transcript([
            {"type": "user", "message": {"content": [{"type": "text", "text": "Fix the login bug"}]}, "timestamp": "2026-03-17T10:00:00Z"},
        ])
        try:
            result = parse_transcript(path)
            assert len(result["user_prompts"]) == 1
            assert "login bug" in result["user_prompts"][0]
        finally:
            os.unlink(path)

    def test_tool_use_extraction(self):
        path = _write_transcript([
            {"type": "assistant", "message": {"content": [
                {"type": "tool_use", "name": "Write", "input": {"file_path": "/tmp/test.py"}},
                {"type": "tool_use", "name": "Edit", "input": {"file_path": "/tmp/existing.py"}},
                {"type": "tool_use", "name": "Bash", "input": {"command": "npm test"}},
            ]}, "timestamp": "2026-03-17T10:01:00Z"},
        ])
        try:
            result = parse_transcript(path)
            assert len(result["files_created"]) == 1
            assert len(result["files_modified"]) == 1
            assert "npm test" in result["commands_run"]
            assert "Write" in result["tools_used"]
            assert "Edit" in result["tools_used"]
            assert "Bash" in result["tools_used"]
        finally:
            os.unlink(path)

    def test_noise_commands_filtered(self):
        path = _write_transcript([
            {"type": "assistant", "message": {"content": [
                {"type": "tool_use", "name": "Bash", "input": {"command": "ls -la"}},
                {"type": "tool_use", "name": "Bash", "input": {"command": "cat file.txt"}},
                {"type": "tool_use", "name": "Bash", "input": {"command": "npm run build"}},
            ]}, "timestamp": "2026-03-17T10:01:00Z"},
        ])
        try:
            result = parse_transcript(path)
            assert len(result["commands_run"]) == 1
            assert "npm run build" in result["commands_run"]
        finally:
            os.unlink(path)

    def test_summary_hints_extraction(self):
        path = _write_transcript([
            {"type": "assistant", "message": {"content": [
                {"type": "text", "text": "Circuit breaker pattern implemented successfully."},
            ]}, "timestamp": "2026-03-17T10:01:00Z"},
        ])
        try:
            result = parse_transcript(path)
            assert len(result["summary_hints"]) > 0
        finally:
            os.unlink(path)

    def test_short_prompts_filtered(self):
        path = _write_transcript([
            {"type": "user", "message": {"content": [{"type": "text", "text": "yes"}]}, "timestamp": "2026-03-17T10:00:00Z"},
        ])
        try:
            result = parse_transcript(path)
            assert len(result["user_prompts"]) == 0
        finally:
            os.unlink(path)


class TestSessionTimeRange:
    def test_extracts_timestamps(self):
        path = _write_transcript([
            {"type": "user", "timestamp": "2026-03-17T10:00:00Z", "message": {"content": "hello"}},
            {"type": "assistant", "timestamp": "2026-03-17T10:30:00Z", "message": {"content": "hi"}},
        ])
        try:
            start, end = get_session_time_range(path)
            assert start == "2026-03-17T10:00:00Z"
            assert end == "2026-03-17T10:30:00Z"
        finally:
            os.unlink(path)

    def test_nonexistent_file(self):
        start, end = get_session_time_range("/nonexistent")
        assert start is None
        assert end is None
