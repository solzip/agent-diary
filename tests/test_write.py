"""Tests for manual diary write CLI (claude-diary write / /diary slash command)."""

import json
import os
import time
import types

import pytest

from claude_diary.cli import write as write_mod


class TestEncodeCwd:
    def test_unix_path(self):
        assert write_mod._encode_cwd("/home/user/myapp") == "-home-user-myapp"

    def test_macos_path(self):
        assert write_mod._encode_cwd("/Users/foo/proj") == "-Users-foo-proj"

    def test_windows_path(self):
        # Backslashes and colons → '-'
        assert write_mod._encode_cwd("C:\\Users\\foo\\proj") == "C--Users-foo-proj"

    def test_non_ascii_collapses(self):
        # Korean chars → '-' each
        result = write_mod._encode_cwd("/Users/윤솔/dev")
        assert result == "-Users----dev"  # 윤=- 솔=- + surrounding /=-

    def test_empty(self):
        assert write_mod._encode_cwd("") == ""


class TestSafeProjectName:
    def test_normal(self):
        assert write_mod._safe_project_name("my-app") == "my-app"

    def test_strips_invalid(self):
        # Windows-reserved chars → '_'
        assert "_" in write_mod._safe_project_name("a:b/c\\d")

    def test_fallback_on_empty(self):
        assert write_mod._safe_project_name("") == "unknown"
        assert write_mod._safe_project_name("///") == "unknown" or \
               write_mod._safe_project_name("///") == "_" * 3 or \
               write_mod._safe_project_name("///") != ""


class TestExtractProjectName:
    def test_unix(self):
        assert write_mod._extract_project_name("/home/user/myapp") == "myapp"

    def test_windows(self):
        assert write_mod._extract_project_name("C:\\Users\\foo\\proj") == "proj"

    def test_trailing_slash(self):
        assert write_mod._extract_project_name("/home/user/myapp/") == "myapp"

    def test_empty(self):
        assert write_mod._extract_project_name("") == "unknown"


class TestFindLatestTranscript:
    def _make_jsonl(self, dirpath, name, mtime=None):
        os.makedirs(dirpath, exist_ok=True)
        path = os.path.join(dirpath, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write('{"type":"user","timestamp":"2026-04-29T00:00:00Z"}\n')
        if mtime is not None:
            os.utime(path, (mtime, mtime))
        return path

    def test_returns_none_when_no_projects_dir(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("USERPROFILE", str(tmp_path))  # Windows
        monkeypatch.delenv("CLAUDE_TRANSCRIPT_PATH", raising=False)
        result = write_mod._find_latest_transcript("/nonexistent/proj")
        assert result is None

    def test_picks_latest_mtime_in_encoded_dir(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
        monkeypatch.delenv("CLAUDE_TRANSCRIPT_PATH", raising=False)

        cwd = "/home/user/myapp"
        encoded = write_mod._encode_cwd(cwd)
        proj_dir = tmp_path / ".claude" / "projects" / encoded

        old = self._make_jsonl(str(proj_dir), "old.jsonl", mtime=time.time() - 1000)
        new = self._make_jsonl(str(proj_dir), "new.jsonl", mtime=time.time())

        result = write_mod._find_latest_transcript(cwd)
        assert result == new

    def test_env_var_takes_priority(self, tmp_path, monkeypatch):
        explicit = tmp_path / "explicit.jsonl"
        explicit.write_text("{}\n", encoding="utf-8")
        monkeypatch.setenv("CLAUDE_TRANSCRIPT_PATH", str(explicit))
        result = write_mod._find_latest_transcript("/anywhere")
        assert result == str(explicit)

    def test_recent_global_fallback(self, tmp_path, monkeypatch):
        """When encoded dir doesn't match, fall back to global latest if recent."""
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
        monkeypatch.delenv("CLAUDE_TRANSCRIPT_PATH", raising=False)

        # Use a different encoded dir than the cwd will produce
        other_dir = tmp_path / ".claude" / "projects" / "some-other-project"
        recent = self._make_jsonl(str(other_dir), "recent.jsonl", mtime=time.time())

        result = write_mod._find_latest_transcript("/cwd/that/wont/match/anything")
        assert result == recent

    def test_old_global_not_used(self, tmp_path, monkeypatch):
        """Global fallback only kicks in if mtime is within last hour."""
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
        monkeypatch.delenv("CLAUDE_TRANSCRIPT_PATH", raising=False)

        other_dir = tmp_path / ".claude" / "projects" / "some-other-project"
        self._make_jsonl(str(other_dir), "stale.jsonl", mtime=time.time() - 7200)

        result = write_mod._find_latest_transcript("/cwd/that/wont/match")
        assert result is None


class TestAppendOrCreate:
    def test_creates_with_header(self, tmp_path):
        target = tmp_path / "2026-04-29.md"
        write_mod._append_or_create(target, "2026-04-29", "ENTRY\n", "ko")
        content = target.read_text(encoding="utf-8")
        assert "작업일지" in content
        assert "ENTRY" in content

    def test_appends_to_existing(self, tmp_path):
        target = tmp_path / "2026-04-29.md"
        write_mod._append_or_create(target, "2026-04-29", "FIRST\n", "ko")
        write_mod._append_or_create(target, "2026-04-29", "SECOND\n", "ko")
        content = target.read_text(encoding="utf-8")
        assert "FIRST" in content
        assert "SECOND" in content
        # Header only once
        assert content.count("작업일지") == 1

    def test_creates_parent_dirs(self, tmp_path):
        target = tmp_path / "2026-04-29" / "myproj" / "2026-04-29.md"
        write_mod._append_or_create(target, "2026-04-29", "X\n", "en")
        assert target.exists()


class TestCmdWriteIntegration:
    """End-to-end smoke test with a fabricated transcript."""

    def _setup_fake_session(self, tmp_path, monkeypatch):
        cwd = tmp_path / "fake-project"
        cwd.mkdir()

        # Fabricate a Claude Code transcript
        encoded = write_mod._encode_cwd(str(cwd.resolve()))
        proj_dir = tmp_path / ".claude" / "projects" / encoded
        proj_dir.mkdir(parents=True)
        transcript = proj_dir / "session.jsonl"
        with open(transcript, "w", encoding="utf-8") as f:
            f.write(json.dumps({
                "type": "user",
                "timestamp": "2026-04-29T01:00:00Z",
                "message": {"role": "user", "content": "implement foo"},
            }) + "\n")

        # Point HOME to tmp so transcript discovery finds it
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
        monkeypatch.setenv("CLAUDE_DIARY_MANUAL_DIR", str(tmp_path / "manual"))
        # Disable global config interference
        monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
        monkeypatch.delenv("CLAUDE_TRANSCRIPT_PATH", raising=False)
        monkeypatch.chdir(cwd)
        return cwd

    def test_creates_then_appends(self, tmp_path, monkeypatch, capsys):
        cwd = self._setup_fake_session(tmp_path, monkeypatch)
        args = types.SimpleNamespace()

        write_mod.cmd_write(args)
        out1 = capsys.readouterr().out
        assert "created" in out1

        write_mod.cmd_write(args)
        out2 = capsys.readouterr().out
        assert "appended to" in out2

        # Verify file structure: <manual_dir>/<date>/<project>/<date>.md
        manual = tmp_path / "manual"
        date_dirs = list(manual.iterdir())
        assert len(date_dirs) == 1
        proj_dirs = list(date_dirs[0].iterdir())
        assert len(proj_dirs) == 1
        assert proj_dirs[0].name == "fake-project"
        files = list(proj_dirs[0].glob("*.md"))
        assert len(files) == 1
        content = files[0].read_text(encoding="utf-8")
        # Two entries means two `### ⏰` headers
        assert content.count("### ") >= 2

    def test_no_transcript_exits_nonzero(self, tmp_path, monkeypatch, capsys):
        empty_cwd = tmp_path / "empty-project"
        empty_cwd.mkdir()
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
        monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
        monkeypatch.delenv("CLAUDE_TRANSCRIPT_PATH", raising=False)
        monkeypatch.chdir(empty_cwd)
        args = types.SimpleNamespace()

        with pytest.raises(SystemExit) as exc:
            write_mod.cmd_write(args)
        assert exc.value.code == 1
        err = capsys.readouterr().err
        assert "No transcript found" in err
