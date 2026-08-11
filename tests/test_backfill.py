"""Tests for `agent-diary backfill`."""

import json
from datetime import timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from claude_diary.cli.backfill import (
    _parse_since,
    _parse_timestamp,
    _project_of,
    _read_head,
    _recorded_session_ids,
    cmd_backfill,
)


def _write_transcript(root, project_dir, session_id, cwd, started, extra=None):
    d = root / project_dir
    d.mkdir(parents=True, exist_ok=True)
    path = d / ("%s.jsonl" % session_id)
    records = [
        {"type": "mode", "sessionId": session_id},
        {"type": "user", "cwd": cwd, "timestamp": started,
         "message": {"content": [{"type": "text", "text": "add login"}]}},
        {"type": "assistant", "timestamp": started,
         "message": {"content": [{"type": "tool_use", "name": "Write",
                                  "input": {"file_path": "%s/auth.py" % cwd}}]}},
    ]
    records.extend(extra or [])
    path.write_text("\n".join(json.dumps(r) for r in records), encoding="utf-8")
    return path


def _args(**kw):
    base = dict(since=None, limit=None, dry_run=False, transcripts=None)
    base.update(kw)
    return SimpleNamespace(**base)


class TestTimestampParsing:
    def test_trailing_z_is_accepted(self):
        """fromisoformat only learned to read Z in 3.11; this project is 3.8."""
        parsed = _parse_timestamp("2026-08-11T02:42:51.696Z")
        assert parsed is not None
        assert parsed.tzinfo is not None
        assert parsed.astimezone(timezone.utc).hour == 2

    def test_offset_form_is_accepted(self):
        parsed = _parse_timestamp("2026-08-11T11:42:51+09:00")
        assert parsed.astimezone(timezone.utc).hour == 2

    def test_naive_is_treated_as_utc(self):
        parsed = _parse_timestamp("2026-08-11T02:42:51")
        assert parsed.tzinfo is timezone.utc

    def test_garbage_is_none(self):
        assert _parse_timestamp("not a date") is None
        assert _parse_timestamp("") is None

    def test_since_must_be_a_date(self):
        assert _parse_since("2026-08-01") is not None
        assert _parse_since("08/01/2026") is None
        assert _parse_since(None) is None


class TestDiscovery:
    def test_cwd_and_timestamp_come_from_the_transcript(self, tmp_path):
        p = _write_transcript(tmp_path, "encoded-dir", "sess-1", "/home/u/proj",
                              "2026-07-01T10:00:00Z")
        cwd, started, is_subagent = _read_head(str(p))
        assert cwd == "/home/u/proj"
        assert started.astimezone(timezone.utc).strftime("%Y-%m-%d") == "2026-07-01"
        assert is_subagent is False

    def test_a_transcript_without_a_cwd_is_skipped(self, tmp_path):
        d = tmp_path / "d"
        d.mkdir()
        path = d / "sess-x.jsonl"
        path.write_text(json.dumps({"type": "user", "timestamp": "2026-07-01T10:00:00Z"}),
                        encoding="utf-8")
        assert _read_head(str(path)) is None

    def test_malformed_lines_do_not_abort_the_scan(self, tmp_path):
        d = tmp_path / "d"
        d.mkdir()
        path = d / "sess-y.jsonl"
        path.write_text(
            "not json\n"
            + json.dumps({"type": "user", "cwd": "/w", "timestamp": "2026-07-01T10:00:00Z"}),
            encoding="utf-8",
        )
        cwd, _, _ = _read_head(str(path))
        assert cwd == "/w"

    def test_subagent_transcripts_are_not_sessions(self, tmp_path, capsys):
        """Subagents get their own transcript file. On a real tree they were
        115 of 194, so importing them would fill the diary with fragments."""
        transcripts = tmp_path / "projects"
        diary = tmp_path / "diary"
        _write_transcript(transcripts, "enc", "sess-real", "/home/u/proj",
                          "2026-07-05T01:00:00Z")
        # named like a subagent
        _write_transcript(transcripts, "enc", "agent-abc123", "/home/u/proj",
                          "2026-07-05T01:05:00Z")
        # marked as one, but named like a session
        d = transcripts / "enc"
        (d / "00000000-1111-2222-3333-444444444444.jsonl").write_text(
            "\n".join(json.dumps(r) for r in [
                {"type": "user", "agentId": "a1", "cwd": "/home/u/proj",
                 "timestamp": "2026-07-05T01:06:00Z"},
            ]),
            encoding="utf-8",
        )
        cfg = {"diary_dir": str(diary), "timezone_offset": 9,
               "enrichment": {"git_info": False}, "exporters": {}}

        with patch("claude_diary.cli.backfill.load_config", return_value=cfg), \
             patch("claude_diary.core.load_config", return_value=cfg):
            cmd_backfill(_args(transcripts=str(transcripts), dry_run=True))

        out = capsys.readouterr().out
        assert "1 session transcript(s)" in out
        assert "subagent transcripts : 2" in out
        assert "sess-real"[:8] in out
        assert "agent-ab" not in out

    def test_project_name_from_either_separator(self):
        assert _project_of("/home/u/my-app") == "my-app"
        assert _project_of("C:\\Users\\u\\my-app") == "my-app"
        assert _project_of("") == "unknown"


class TestRecordedSessionIds:
    def test_reads_the_full_id_the_writer_emits(self, tmp_path):
        (tmp_path / "2026-07-01.md").write_text(
            "### entry\n\n"
            "<details><summary>Session ID: <code>abc12345...</code></summary>\n"
            "<code>abc12345-6789-4abc-8def-000000000001</code>\n"
            "</details>\n",
            encoding="utf-8",
        )
        found = _recorded_session_ids(str(tmp_path))
        assert "abc12345-6789-4abc-8def-000000000001" in found
        # the truncated summary form must not be mistaken for an id
        assert "abc12345..." not in found

    def test_missing_directory_is_empty_not_an_error(self, tmp_path):
        assert _recorded_session_ids(str(tmp_path / "nope")) == set()


class TestBackfill:
    def _config(self, diary_dir):
        return {"diary_dir": str(diary_dir), "timezone_offset": 9,
                "enrichment": {"git_info": False, "auto_category": True,
                               "code_stats": False, "session_time": True},
                "exporters": {}}

    def test_files_the_entry_under_the_day_it_was_worked(self, tmp_path, capsys):
        """The whole point: an imported session belongs to its own date, not
        to the day the import ran."""
        transcripts = tmp_path / "projects"
        diary = tmp_path / "diary"
        _write_transcript(transcripts, "enc", "sess-old", "/home/u/proj",
                          "2026-07-01T01:00:00Z")

        with patch("claude_diary.cli.backfill.load_config", return_value=self._config(diary)), \
             patch("claude_diary.core.load_config", return_value=self._config(diary)):
            cmd_backfill(_args(transcripts=str(transcripts)))

        # 01:00Z at +09:00 is the 1st, 10:00 local
        written = sorted(p.name for p in diary.glob("*.md"))
        assert written == ["2026-07-01.md"]
        assert "10:00" in (diary / "2026-07-01.md").read_text(encoding="utf-8")

    def test_running_twice_does_not_duplicate(self, tmp_path, capsys):
        transcripts = tmp_path / "projects"
        diary = tmp_path / "diary"
        _write_transcript(transcripts, "enc", "sess-dup", "/home/u/proj",
                          "2026-07-02T01:00:00Z")
        cfg = self._config(diary)

        with patch("claude_diary.cli.backfill.load_config", return_value=cfg), \
             patch("claude_diary.core.load_config", return_value=cfg):
            cmd_backfill(_args(transcripts=str(transcripts)))
            first = (diary / "2026-07-02.md").read_text(encoding="utf-8")
            capsys.readouterr()
            cmd_backfill(_args(transcripts=str(transcripts)))

        out = capsys.readouterr().out
        assert "already in the diary : 1" in out
        assert "to import            : 0" in out
        assert (diary / "2026-07-02.md").read_text(encoding="utf-8") == first

    def test_dry_run_writes_nothing(self, tmp_path, capsys):
        transcripts = tmp_path / "projects"
        diary = tmp_path / "diary"
        _write_transcript(transcripts, "enc", "sess-dry", "/home/u/proj",
                          "2026-07-03T01:00:00Z")
        cfg = self._config(diary)

        with patch("claude_diary.cli.backfill.load_config", return_value=cfg), \
             patch("claude_diary.core.load_config", return_value=cfg):
            cmd_backfill(_args(transcripts=str(transcripts), dry_run=True))

        out = capsys.readouterr().out
        assert "--dry-run, nothing written" in out
        assert "sess-dry"[:8] in out
        assert not diary.exists() or not list(diary.glob("*.md"))

    def test_since_and_limit_narrow_the_set(self, tmp_path, capsys):
        transcripts = tmp_path / "projects"
        diary = tmp_path / "diary"
        for i, day in enumerate(["2026-06-01", "2026-07-01", "2026-07-02"]):
            _write_transcript(transcripts, "enc", "sess-%d" % i, "/home/u/proj",
                              "%sT01:00:00Z" % day)
        cfg = self._config(diary)

        with patch("claude_diary.cli.backfill.load_config", return_value=cfg), \
             patch("claude_diary.core.load_config", return_value=cfg):
            cmd_backfill(_args(transcripts=str(transcripts), since="2026-07-01",
                               limit=1, dry_run=True))

        out = capsys.readouterr().out
        assert "before --since       : 1" in out
        assert "beyond --limit       : 1" in out
        assert "to import            : 1" in out

    def test_oldest_first(self, tmp_path, capsys):
        transcripts = tmp_path / "projects"
        diary = tmp_path / "diary"
        _write_transcript(transcripts, "enc", "sess-new", "/home/u/proj",
                          "2026-07-09T01:00:00Z")
        _write_transcript(transcripts, "enc", "sess-old", "/home/u/proj",
                          "2026-07-04T01:00:00Z")
        cfg = self._config(diary)

        with patch("claude_diary.cli.backfill.load_config", return_value=cfg), \
             patch("claude_diary.core.load_config", return_value=cfg):
            cmd_backfill(_args(transcripts=str(transcripts), dry_run=True))

        out = capsys.readouterr().out
        assert out.index("2026-07-04") < out.index("2026-07-09")

    def test_missing_transcript_root_explains_itself(self, tmp_path, capsys):
        cfg = self._config(tmp_path / "diary")
        with patch("claude_diary.cli.backfill.load_config", return_value=cfg):
            cmd_backfill(_args(transcripts=str(tmp_path / "absent")))
        out = capsys.readouterr().out
        assert "No transcripts found" in out
        assert "--transcripts" in out

    def test_bad_since_is_rejected_before_any_work(self, tmp_path):
        transcripts = tmp_path / "projects"
        transcripts.mkdir()
        cfg = self._config(tmp_path / "diary")
        with patch("claude_diary.cli.backfill.load_config", return_value=cfg), \
             pytest.raises(SystemExit) as exc:
            cmd_backfill(_args(transcripts=str(transcripts), since="July 1st"))
        assert exc.value.code == 2
