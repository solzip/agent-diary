"""Tests for hook.py — stdin parsing, type validation, error handling."""

import json
import sys
from io import StringIO
from unittest.mock import patch, MagicMock

import pytest

from claude_diary.hook import main


class TestHookStdinParsing:
    """Test JSON parsing from stdin."""

    @patch("claude_diary.hook.process_session")
    def test_valid_json_parsed(self, mock_process):
        mock_process.return_value = True
        input_data = {
            "session_id": "sess-001",
            "transcript_path": "/tmp/transcript.jsonl",
            "cwd": "/home/user/project",
        }

        with patch("sys.stdin", StringIO(json.dumps(input_data))):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0

        mock_process.assert_called_once_with("sess-001", "/tmp/transcript.jsonl", "/home/user/project")

    def test_invalid_json_exits_gracefully(self):
        with patch("sys.stdin", StringIO("not valid json!!!")):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0

    def test_empty_stdin_exits_gracefully(self):
        with patch("sys.stdin", StringIO("")):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0

    @patch("claude_diary.hook.process_session")
    def test_missing_keys_use_defaults(self, mock_process):
        mock_process.return_value = True
        input_data = {}  # No session_id, transcript_path, cwd

        with patch("sys.stdin", StringIO(json.dumps(input_data))):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0

        mock_process.assert_called_once_with("unknown", "", "")

    @patch("claude_diary.hook.process_session")
    def test_partial_keys(self, mock_process):
        mock_process.return_value = True
        input_data = {"session_id": "partial-001"}

        with patch("sys.stdin", StringIO(json.dumps(input_data))):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0

        mock_process.assert_called_once_with("partial-001", "", "")


class TestHookTypeValidation:
    """Test type coercion for non-string inputs."""

    @patch("claude_diary.hook.process_session")
    def test_non_string_session_id_defaults_to_unknown(self, mock_process):
        mock_process.return_value = True
        input_data = {
            "session_id": 12345,  # int instead of str
            "transcript_path": "/tmp/t.jsonl",
            "cwd": "/tmp",
        }

        with patch("sys.stdin", StringIO(json.dumps(input_data))):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0

        mock_process.assert_called_once_with("unknown", "/tmp/t.jsonl", "/tmp")

    @patch("claude_diary.hook.process_session")
    def test_non_string_transcript_path_defaults_to_empty(self, mock_process):
        mock_process.return_value = True
        input_data = {
            "session_id": "sess-001",
            "transcript_path": ["not", "a", "string"],
            "cwd": "/tmp",
        }

        with patch("sys.stdin", StringIO(json.dumps(input_data))):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0

        mock_process.assert_called_once_with("sess-001", "", "/tmp")

    @patch("claude_diary.hook.process_session")
    def test_non_string_cwd_defaults_to_empty(self, mock_process):
        mock_process.return_value = True
        input_data = {
            "session_id": "sess-001",
            "transcript_path": "/tmp/t.jsonl",
            "cwd": None,
        }

        with patch("sys.stdin", StringIO(json.dumps(input_data))):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0

        mock_process.assert_called_once_with("sess-001", "/tmp/t.jsonl", "")

    @patch("claude_diary.hook.process_session")
    def test_all_non_string_types(self, mock_process):
        mock_process.return_value = True
        input_data = {
            "session_id": {"nested": True},
            "transcript_path": 999,
            "cwd": False,
        }

        with patch("sys.stdin", StringIO(json.dumps(input_data))):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0

        mock_process.assert_called_once_with("unknown", "", "")


class TestHookErrorHandling:
    """Test that errors in process_session never block Claude Code exit."""

    @patch("claude_diary.hook.process_session")
    def test_process_session_exception_exits_zero(self, mock_process):
        mock_process.side_effect = RuntimeError("unexpected crash")
        input_data = {
            "session_id": "err-001",
            "transcript_path": "/tmp/t.jsonl",
            "cwd": "/tmp",
        }

        with patch("sys.stdin", StringIO(json.dumps(input_data))):
            with pytest.raises(SystemExit) as exc_info:
                main()
            # Must exit 0 — never block Claude Code
            assert exc_info.value.code == 0

    @patch("claude_diary.hook.process_session")
    def test_process_session_keyboard_interrupt(self, mock_process):
        mock_process.side_effect = KeyboardInterrupt()
        input_data = {
            "session_id": "err-002",
            "transcript_path": "/tmp/t.jsonl",
            "cwd": "/tmp",
        }

        with patch("sys.stdin", StringIO(json.dumps(input_data))):
            with pytest.raises((SystemExit, KeyboardInterrupt)):
                main()

    @patch("claude_diary.hook.process_session")
    def test_successful_run_exits_zero(self, mock_process):
        mock_process.return_value = True
        input_data = {
            "session_id": "ok-001",
            "transcript_path": "/tmp/t.jsonl",
            "cwd": "/tmp",
        }

        with patch("sys.stdin", StringIO(json.dumps(input_data))):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0

    def test_json_array_input_exits_gracefully(self):
        """Even valid JSON that isn't a dict should be handled."""
        with patch("sys.stdin", StringIO(json.dumps([1, 2, 3]))):
            with pytest.raises((SystemExit, AttributeError)):
                main()
