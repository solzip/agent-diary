"""Tests for core pipeline."""

import json
import os
import tempfile
from unittest.mock import patch, MagicMock

from claude_diary.core import process_session, _extract_project_name, _supplement_from_git, _run_exporters


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


class TestGitEnrichment:
    """Test git_info enrichment branch in process_session."""

    def _make_transcript(self, tmp_path):
        transcript = tmp_path / "session.jsonl"
        entries = [
            {"type": "user", "message": {"content": [{"type": "text", "text": "Add tests"}]}, "timestamp": "2026-03-17T10:00:00Z"},
            {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Write", "input": {"file_path": "/tmp/test.py"}}]}, "timestamp": "2026-03-17T10:01:00Z"},
        ]
        transcript.write_text("\n".join(json.dumps(e) for e in entries))
        return str(transcript)

    @patch("claude_diary.core.collect_git_info")
    def test_git_info_populated_when_available(self, mock_git, tmp_path, monkeypatch):
        monkeypatch.setenv("APPDATA", str(tmp_path))
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        monkeypatch.setenv("CLAUDE_DIARY_DIR", str(tmp_path / "diary"))

        mock_git.return_value = {
            "branch": "feature/test",
            "commits": [{"hash": "abc1234", "message": "feat: add tests"}],
            "diff_stat": {"added": 30, "deleted": 5, "files": 2},
        }

        transcript = self._make_transcript(tmp_path)
        result = process_session("git-test-001", transcript, str(tmp_path))
        assert result is True
        mock_git.assert_called_once()

    @patch("claude_diary.core.collect_git_info")
    def test_git_info_none_when_not_repo(self, mock_git, tmp_path, monkeypatch):
        monkeypatch.setenv("APPDATA", str(tmp_path))
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        monkeypatch.setenv("CLAUDE_DIARY_DIR", str(tmp_path / "diary"))

        mock_git.return_value = None

        transcript = self._make_transcript(tmp_path)
        result = process_session("git-test-002", transcript, str(tmp_path))
        assert result is True

    @patch("claude_diary.core.collect_git_info")
    def test_git_enrichment_exception_handled(self, mock_git, tmp_path, monkeypatch):
        monkeypatch.setenv("APPDATA", str(tmp_path))
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        monkeypatch.setenv("CLAUDE_DIARY_DIR", str(tmp_path / "diary"))

        mock_git.side_effect = RuntimeError("git binary missing")

        transcript = self._make_transcript(tmp_path)
        result = process_session("git-test-003", transcript, str(tmp_path))
        # Should still succeed — git failure is non-critical
        assert result is True

    @patch("claude_diary.core.collect_git_info")
    def test_git_disabled_in_config(self, mock_git, tmp_path, monkeypatch):
        monkeypatch.setenv("APPDATA", str(tmp_path))
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        monkeypatch.setenv("CLAUDE_DIARY_DIR", str(tmp_path / "diary"))

        # Write config that disables git enrichment
        config_dir = tmp_path / "claude-diary"
        config_dir.mkdir()
        config_path = config_dir / "config.json"
        config_path.write_text(json.dumps({
            "enrichment": {"git_info": False, "auto_category": True, "code_stats": True}
        }))

        transcript = self._make_transcript(tmp_path)
        result = process_session("git-test-004", transcript, str(tmp_path))
        assert result is True
        mock_git.assert_not_called()


class TestCategoryEnrichment:
    """Test auto_category enrichment branch."""

    def _make_transcript(self, tmp_path):
        transcript = tmp_path / "session.jsonl"
        entries = [
            {"type": "user", "message": {"content": [{"type": "text", "text": "Fix authentication bug"}]}, "timestamp": "2026-03-17T10:00:00Z"},
        ]
        transcript.write_text("\n".join(json.dumps(e) for e in entries))
        return str(transcript)

    @patch("claude_diary.core.categorize")
    @patch("claude_diary.core.collect_git_info", return_value=None)
    def test_categorization_applied(self, mock_git, mock_cat, tmp_path, monkeypatch):
        monkeypatch.setenv("APPDATA", str(tmp_path))
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        monkeypatch.setenv("CLAUDE_DIARY_DIR", str(tmp_path / "diary"))

        mock_cat.return_value = ["bugfix", "auth"]

        transcript = self._make_transcript(tmp_path)
        result = process_session("cat-test-001", transcript, str(tmp_path))
        assert result is True
        mock_cat.assert_called_once()

    @patch("claude_diary.core.categorize")
    @patch("claude_diary.core.collect_git_info", return_value=None)
    def test_categorization_exception_handled(self, mock_git, mock_cat, tmp_path, monkeypatch):
        monkeypatch.setenv("APPDATA", str(tmp_path))
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        monkeypatch.setenv("CLAUDE_DIARY_DIR", str(tmp_path / "diary"))

        mock_cat.side_effect = ValueError("bad rule")

        transcript = self._make_transcript(tmp_path)
        result = process_session("cat-test-002", transcript, str(tmp_path))
        # Non-critical — should still succeed
        assert result is True


class TestSecretScan:
    """Test secret scanning enrichment branch."""

    @patch("claude_diary.core.scan_entry_data")
    @patch("claude_diary.core.collect_git_info", return_value=None)
    def test_secret_scan_runs(self, mock_git, mock_scan, tmp_path, monkeypatch):
        monkeypatch.setenv("APPDATA", str(tmp_path))
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        monkeypatch.setenv("CLAUDE_DIARY_DIR", str(tmp_path / "diary"))

        transcript = tmp_path / "session.jsonl"
        transcript.write_text(json.dumps({
            "type": "user", "message": {"content": [{"type": "text", "text": "Deploy API key setup"}]},
            "timestamp": "2026-03-17T10:00:00Z"
        }))

        result = process_session("sec-test-001", str(transcript), str(tmp_path))
        assert result is True
        mock_scan.assert_called_once()

    @patch("claude_diary.core.scan_entry_data")
    @patch("claude_diary.core.collect_git_info", return_value=None)
    def test_secret_scan_exception_handled(self, mock_git, mock_scan, tmp_path, monkeypatch):
        monkeypatch.setenv("APPDATA", str(tmp_path))
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        monkeypatch.setenv("CLAUDE_DIARY_DIR", str(tmp_path / "diary"))

        mock_scan.side_effect = RuntimeError("scan failed")

        transcript = tmp_path / "session.jsonl"
        transcript.write_text(json.dumps({
            "type": "user", "message": {"content": [{"type": "text", "text": "Add config"}]},
            "timestamp": "2026-03-17T10:00:00Z"
        }))

        result = process_session("sec-test-002", str(transcript), str(tmp_path))
        assert result is True


class TestTeamSecurityEnrichment:
    """Test team security filter branch (path masking + content filter)."""

    def _make_transcript(self, tmp_path):
        transcript = tmp_path / "session.jsonl"
        entries = [
            {"type": "user", "message": {"content": [{"type": "text", "text": "Update secret config"}]}, "timestamp": "2026-03-17T10:00:00Z"},
            {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Edit", "input": {"file_path": "/tmp/creds.env"}}]}, "timestamp": "2026-03-17T10:01:00Z"},
        ]
        transcript.write_text("\n".join(json.dumps(e) for e in entries))
        return str(transcript)

    @patch("claude_diary.core.collect_git_info", return_value=None)
    def test_content_filter_skip_mode(self, mock_git, tmp_path, monkeypatch):
        monkeypatch.setenv("APPDATA", str(tmp_path))
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        monkeypatch.setenv("CLAUDE_DIARY_DIR", str(tmp_path / "diary"))

        # Write config with content filter in skip mode
        config_dir = tmp_path / "claude-diary"
        config_dir.mkdir()
        config_path = config_dir / "config.json"
        config_path.write_text(json.dumps({
            "security": {
                "content_filters": ["secret"],
                "filter_mode": "skip"
            }
        }))

        transcript = self._make_transcript(tmp_path)
        result = process_session("team-test-001", transcript, str(tmp_path))
        # Session should be skipped because prompt contains "secret"
        assert result is False

    @patch("claude_diary.core.collect_git_info", return_value=None)
    def test_path_masking_applied(self, mock_git, tmp_path, monkeypatch):
        monkeypatch.setenv("APPDATA", str(tmp_path))
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        monkeypatch.setenv("CLAUDE_DIARY_DIR", str(tmp_path / "diary"))

        config_dir = tmp_path / "claude-diary"
        config_dir.mkdir()
        config_path = config_dir / "config.json"
        config_path.write_text(json.dumps({
            "security": {
                "mask_paths": ["*.env"]
            }
        }))

        transcript = self._make_transcript(tmp_path)
        result = process_session("team-test-002", transcript, str(tmp_path))
        assert result is True


class TestSupplementFromGit:
    """Test _supplement_from_git helper."""

    @patch("subprocess.run")
    def test_supplements_files_from_git_diff(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="src/main.py\nsrc/utils.py\n"
        )

        entry_data = {
            "files_modified": [],
            "files_created": [],
            "cwd": "/home/user/project",
        }
        git_info = {
            "diff_stat": {"files": 2, "added": 10, "deleted": 3},
        }

        _supplement_from_git(entry_data, git_info)
        assert len(entry_data["files_modified"]) == 2
        mock_run.assert_called_once()

    @patch("subprocess.run")
    def test_no_supplement_when_files_already_present(self, mock_run):
        entry_data = {
            "files_modified": ["existing.py"],
            "files_created": [],
            "cwd": "/home/user/project",
        }
        git_info = {
            "diff_stat": {"files": 2, "added": 10, "deleted": 3},
        }

        _supplement_from_git(entry_data, git_info)
        assert entry_data["files_modified"] == ["existing.py"]
        mock_run.assert_not_called()

    def test_no_supplement_when_no_diff(self):
        entry_data = {
            "files_modified": [],
            "files_created": [],
            "cwd": "/home/user/project",
        }
        git_info = {
            "diff_stat": {"files": 0, "added": 0, "deleted": 0},
        }

        _supplement_from_git(entry_data, git_info)
        assert entry_data["files_modified"] == []

    @patch("subprocess.run")
    def test_supplement_handles_subprocess_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="")

        entry_data = {
            "files_modified": [],
            "files_created": [],
            "cwd": "/home/user/project",
        }
        git_info = {
            "diff_stat": {"files": 2, "added": 10, "deleted": 3},
        }

        _supplement_from_git(entry_data, git_info)
        # Should not crash, files_modified stays empty
        assert entry_data["files_modified"] == []

    def test_no_supplement_when_cwd_empty(self):
        entry_data = {
            "files_modified": [],
            "files_created": [],
            "cwd": "",
        }
        git_info = {
            "diff_stat": {"files": 2, "added": 10, "deleted": 3},
        }

        _supplement_from_git(entry_data, git_info)
        assert entry_data["files_modified"] == []


class TestIndexEnrichment:
    """Test index update step in process_session."""

    @patch("claude_diary.core.update_index")
    @patch("claude_diary.core.collect_git_info", return_value=None)
    def test_index_update_called(self, mock_git, mock_index, tmp_path, monkeypatch):
        monkeypatch.setenv("APPDATA", str(tmp_path))
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        monkeypatch.setenv("CLAUDE_DIARY_DIR", str(tmp_path / "diary"))

        transcript = tmp_path / "session.jsonl"
        transcript.write_text(json.dumps({
            "type": "user", "message": {"content": [{"type": "text", "text": "Update docs"}]},
            "timestamp": "2026-03-17T10:00:00Z"
        }))

        result = process_session("idx-test-001", str(transcript), str(tmp_path))
        assert result is True
        mock_index.assert_called_once()

    @patch("claude_diary.core.update_index")
    @patch("claude_diary.core.collect_git_info", return_value=None)
    def test_index_failure_non_critical(self, mock_git, mock_index, tmp_path, monkeypatch):
        monkeypatch.setenv("APPDATA", str(tmp_path))
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        monkeypatch.setenv("CLAUDE_DIARY_DIR", str(tmp_path / "diary"))

        mock_index.side_effect = IOError("disk full")

        transcript = tmp_path / "session.jsonl"
        transcript.write_text(json.dumps({
            "type": "user", "message": {"content": [{"type": "text", "text": "Deploy app"}]},
            "timestamp": "2026-03-17T10:00:00Z"
        }))

        result = process_session("idx-test-002", str(transcript), str(tmp_path))
        # Index failure should not stop pipeline
        assert result is True


class TestExporterEnrichment:
    """Test _run_exporters helper."""

    @patch("claude_diary.exporters.loader.load_exporters", return_value=[])
    def test_no_exporters_configured(self, mock_load):
        config = {"diary_dir": "/tmp/diary", "exporters": {}}
        entry_data = {"date": "2026-03-17"}

        # Should not raise
        _run_exporters(config, entry_data)
        mock_load.assert_called_once()

    @patch("claude_diary.exporters.loader.run_exporters")
    @patch("claude_diary.exporters.loader.load_exporters")
    def test_exporters_called_when_present(self, mock_load, mock_run):
        mock_exporter = MagicMock()
        mock_load.return_value = [("slack", mock_exporter)]
        mock_run.return_value = {"success": ["slack"], "failed": []}

        config = {"diary_dir": "/tmp/diary", "exporters": {"slack": {"enabled": True}}}
        entry_data = {"date": "2026-03-17"}

        _run_exporters(config, entry_data)
        mock_run.assert_called_once()

    @patch("claude_diary.exporters.loader.run_exporters")
    @patch("claude_diary.exporters.loader.load_exporters")
    def test_failed_exporters_logged(self, mock_load, mock_run):
        mock_exporter = MagicMock()
        mock_load.return_value = [("slack", mock_exporter)]
        mock_run.return_value = {"success": [], "failed": ["slack"]}

        config = {"diary_dir": "/tmp/diary", "exporters": {"slack": {"enabled": True}}}
        entry_data = {"date": "2026-03-17"}

        # Should not raise even on failure
        _run_exporters(config, entry_data)


class TestAuditEnrichment:
    """Test audit log step in process_session."""

    @patch("claude_diary.core.audit_log")
    @patch("claude_diary.core.collect_git_info", return_value=None)
    def test_audit_log_called(self, mock_git, mock_audit, tmp_path, monkeypatch):
        monkeypatch.setenv("APPDATA", str(tmp_path))
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        monkeypatch.setenv("CLAUDE_DIARY_DIR", str(tmp_path / "diary"))

        transcript = tmp_path / "session.jsonl"
        transcript.write_text(json.dumps({
            "type": "user", "message": {"content": [{"type": "text", "text": "Build feature"}]},
            "timestamp": "2026-03-17T10:00:00Z"
        }))

        result = process_session("audit-test-001", str(transcript), str(tmp_path))
        assert result is True
        mock_audit.assert_called_once()
        call_kwargs = mock_audit.call_args
        assert call_kwargs[1]["session_id"] == "audit-test-001" or call_kwargs[0][1] == "audit-test-001"

    @patch("claude_diary.core.audit_log")
    @patch("claude_diary.core.collect_git_info", return_value=None)
    def test_audit_failure_non_critical(self, mock_git, mock_audit, tmp_path, monkeypatch):
        monkeypatch.setenv("APPDATA", str(tmp_path))
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        monkeypatch.setenv("CLAUDE_DIARY_DIR", str(tmp_path / "diary"))

        mock_audit.side_effect = OSError("permission denied")

        transcript = tmp_path / "session.jsonl"
        transcript.write_text(json.dumps({
            "type": "user", "message": {"content": [{"type": "text", "text": "Refactor code"}]},
            "timestamp": "2026-03-17T10:00:00Z"
        }))

        result = process_session("audit-test-002", str(transcript), str(tmp_path))
        # Audit failure should not stop pipeline
        assert result is True
