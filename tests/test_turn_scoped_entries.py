"""An entry covers one turn, not the opening of the session again.

The Stop Hook fires once per assistant turn and used to re-read the transcript
from line 1 every time, then print the first five prompts it found. Turn 1
recorded requests 1-5; turn 400 recorded requests 1-5. Measured across one real
diary, 5,904 of 6,971 entries (85%) were copies of an earlier entry in the same
session, and the sixth request of a session was never written down at all.

Replaying a real 3,119-line transcript turn by turn after the fix: 42 entries
carrying prompts, 41 distinct sets, and the one repeat is
`[Request interrupted by user for tool use]` arriving three times because it
genuinely did.
"""

import json
import multiprocessing as mp
import os
import re
import sys

import pytest

from claude_diary.lib.parser import parse_transcript
from claude_diary.lib.progress import read_position, record_position


def _user(text, ts="2026-07-01T10:00:00Z"):
    return json.dumps({"type": "user", "timestamp": ts,
                       "message": {"content": [{"type": "text", "text": text}]}}) + "\n"


def _grow(path, *chunks):
    with open(path, "a", encoding="utf-8") as f:
        for c in chunks:
            f.write(c)
    return sum(1 for _ in open(path, encoding="utf-8"))


class TestParsingFromWhereItStopped:
    def test_the_first_lines_are_skipped(self, tmp_path):
        t = tmp_path / "t.jsonl"
        _grow(str(t), _user("first request"), _user("second request"))
        result = parse_transcript(str(t), start_line=1)
        assert result["user_prompts"] == ["second request"]

    def test_the_position_is_absolute(self, tmp_path):
        """It counts lines seen, including skipped ones, because that is what
        the next turn resumes from."""
        t = tmp_path / "t.jsonl"
        _grow(str(t), _user("alpha one"), _user("beta two"), _user("gamma three"))
        assert parse_transcript(str(t), start_line=2)["lines_read"] == 3

    def test_starting_past_the_end_yields_nothing(self, tmp_path):
        t = tmp_path / "t.jsonl"
        _grow(str(t), _user("only one"))
        assert parse_transcript(str(t), start_line=5)["user_prompts"] == []

    def test_zero_reads_everything(self, tmp_path):
        t = tmp_path / "t.jsonl"
        _grow(str(t), _user("alpha one"), _user("beta two"))
        assert len(parse_transcript(str(t), start_line=0)["user_prompts"]) == 2

    def test_a_line_cap_counts_from_the_resume_point(self, tmp_path):
        """Otherwise resuming at line 900 with a 1,000-line cap would read a
        hundred lines and call it a session."""
        t = tmp_path / "t.jsonl"
        _grow(str(t), *[_user("request %d" % i) for i in range(10)])
        result = parse_transcript(str(t), start_line=5, max_lines=3)
        assert len(result["user_prompts"]) == 3


class TestRememberingThePosition:
    def test_nothing_stored_is_not_the_same_as_zero(self, tmp_path):
        """Zero means "read from the start"; None means "never seen", and the
        caller answers those differently."""
        assert read_position(str(tmp_path), "s1", None) is None

    def test_it_survives_a_restart(self, tmp_path):
        t = tmp_path / "t.jsonl"
        _grow(str(t), _user("alpha one"))
        record_position(str(tmp_path), "s1", str(t), 1)
        assert read_position(str(tmp_path), "s1", str(t)) == 1

    def test_a_shorter_transcript_resets_it(self, tmp_path):
        """Replaced or truncated: resuming inside it would skip content that
        now sits at a different offset."""
        t = tmp_path / "t.jsonl"
        _grow(str(t), _user("alpha one"), _user("beta two"), _user("gamma three"))
        record_position(str(tmp_path), "s1", str(t), 3)
        t.write_text(_user("replaced"), encoding="utf-8")
        assert read_position(str(tmp_path), "s1", str(t)) == 0

    def test_a_different_transcript_resets_it(self, tmp_path):
        t1, t2 = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
        _grow(str(t1), _user("alpha one"), _user("beta two"))
        _grow(str(t2), _user("xray nine"), _user("yankee ten"))
        record_position(str(tmp_path), "s1", str(t1), 2)
        assert read_position(str(tmp_path), "s1", str(t2)) == 0

    def test_a_vanished_transcript_is_pruned(self, tmp_path):
        """65% of the sessions in one diary no longer have a transcript;
        without pruning the file only grows."""
        gone, alive = tmp_path / "gone.jsonl", tmp_path / "alive.jsonl"
        _grow(str(gone), _user("alpha one"))
        _grow(str(alive), _user("alpha one"))
        record_position(str(tmp_path), "old", str(gone), 1)
        gone.unlink()
        record_position(str(tmp_path), "new", str(alive), 1)

        data = json.loads((tmp_path / ".session_progress.json").read_text(encoding="utf-8"))
        assert "old" not in data
        assert "new" in data

    def test_a_corrupt_file_is_kept_rather_than_overwritten(self, tmp_path):
        progress = tmp_path / ".session_progress.json"
        progress.write_text('{"s1": {"lines": 5', encoding="utf-8")
        assert read_position(str(tmp_path), "s1", None) is None
        assert (tmp_path / ".session_progress.json.corrupt").exists()


class TestTheWholeTurnIsRecorded:
    def test_more_than_five_prompts_in_one_turn_all_appear(self, tmp_path):
        """The cut was in the formatter, so turn-scoped parsing alone would
        have left a six-prompt turn truncated at five."""
        from claude_diary.formatter import format_entry

        entry = {
            "session_id": "s", "date": "2026-07-01", "time": "10:00:00",
            "project": "p", "cwd": "/tmp",
            "user_prompts": ["request %d" % i for i in range(8)],
            "files_created": [], "files_modified": [], "commands_run": [],
            "summary_hints": [], "errors_encountered": [], "categories": [],
            "git_info": None, "code_stats": None,
        }
        text = format_entry(entry, "ko")
        assert "request 7" in text
        assert len(re.findall(r"^  \d+\. request", text, re.M)) == 8


WORKERS = 8


def _record_one(payload):
    src, diary, i = payload
    if src not in sys.path:
        sys.path.insert(0, src)
    from claude_diary.lib.progress import record_position

    transcript = os.path.join(diary, "t%d.jsonl" % i)
    with open(transcript, "w", encoding="utf-8") as f:
        f.write('{"type": "user"}\n')
    record_position(diary, "session-%02d" % i, transcript, i + 1)
    return i


def _src_root():
    import claude_diary
    return os.path.dirname(os.path.dirname(os.path.abspath(claude_diary.__file__)))


class TestConcurrentSessions:
    """Read-modify-write on one file, and two sessions ending in the same
    second is ordinary here — the same reason the diary and the counter take a
    lock. Separate processes rather than threads, for the reason in
    test_concurrent_writes.py."""

    def test_no_position_is_lost(self, tmp_path):
        diary = tmp_path / "diary"
        diary.mkdir()
        with mp.Pool(WORKERS) as pool:
            pool.map(_record_one, [(_src_root(), str(diary), i) for i in range(WORKERS)])

        data = json.loads((diary / ".session_progress.json").read_text(encoding="utf-8"))
        assert len(data) == WORKERS
        assert sorted(v["lines"] for v in data.values()) == list(range(1, WORKERS + 1))

    def test_nothing_is_left_behind(self, tmp_path):
        diary = tmp_path / "diary"
        diary.mkdir()
        with mp.Pool(WORKERS) as pool:
            pool.map(_record_one, [(_src_root(), str(diary), i) for i in range(WORKERS)])
        assert list(diary.glob("*.lock")) == []
        assert list(diary.glob("*.tmp*")) == []


class TestUpgradingMidSession:
    """The first turn after upgrading, in a session the old code has already
    written entries for. Reading from 0 would write one last copy of the whole
    backlog — the defect being fixed, one final time."""

    def _setup(self, tmp_path):
        diary = tmp_path / "diary"
        diary.mkdir()
        t = tmp_path / "t.jsonl"
        _grow(str(t), _user("alpha one"), _user("beta two"), _user("gamma three"))
        return diary, t

    def test_a_session_already_in_the_diary_records_nothing(self, tmp_path, monkeypatch):
        from claude_diary import core

        diary, t = self._setup(tmp_path)
        (diary / "2026-07-01.md").write_text(
            "### ⏰ 10:00:00 | 📁 `p`\n\n<code>known-session</code>\n", encoding="utf-8")
        monkeypatch.setenv("APPDATA", str(tmp_path / "cfg"))
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
        monkeypatch.setenv("CLAUDE_DIARY_DIR", str(diary))

        assert core.process_session("known-session", str(t), str(tmp_path)) is False
        assert read_position(str(diary), "known-session", str(t)) == 3

    def test_a_new_session_reads_from_the_beginning(self, tmp_path, monkeypatch):
        from claude_diary import core

        diary, t = self._setup(tmp_path)
        monkeypatch.setenv("APPDATA", str(tmp_path / "cfg"))
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
        monkeypatch.setenv("CLAUDE_DIARY_DIR", str(diary))

        assert core.process_session("brand-new", str(t), str(tmp_path)) is True
        written = "".join(p.read_text(encoding="utf-8") for p in diary.glob("*.md"))
        assert "alpha one" in written and "gamma three" in written


class TestSuccessiveTurns:
    """The regression for the 85%: each entry carries its own turn only."""

    def _run(self, tmp_path, monkeypatch, session, transcript, text):
        from claude_diary import core

        diary = tmp_path / "diary"
        diary.mkdir(exist_ok=True)
        _grow(str(transcript), _user(text))
        monkeypatch.setenv("APPDATA", str(tmp_path / "cfg"))
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
        monkeypatch.setenv("CLAUDE_DIARY_DIR", str(diary))
        core.process_session(session, str(transcript), str(tmp_path))
        return diary

    def test_each_entry_holds_only_its_own_turn(self, tmp_path, monkeypatch):
        t = tmp_path / "t.jsonl"
        for text in ("first request", "second request", "third request"):
            diary = self._run(tmp_path, monkeypatch, "s1", t, text)

        written = "".join(p.read_text(encoding="utf-8") for p in diary.glob("*.md"))
        chunks = written.split("### ⏰")[1:]
        assert len(chunks) == 3
        assert "first request" in chunks[0] and "second" not in chunks[0]
        assert "second request" in chunks[1] and "first" not in chunks[1]
        assert "third request" in chunks[2] and "second" not in chunks[2]

    def test_a_failed_write_does_not_advance_the_position(self, tmp_path, monkeypatch):
        """Otherwise the turn that failed is dropped entirely."""
        from claude_diary import core

        diary = tmp_path / "diary"
        diary.mkdir()
        t = tmp_path / "t.jsonl"
        _grow(str(t), _user("the only request"))
        monkeypatch.setenv("APPDATA", str(tmp_path / "cfg"))
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
        monkeypatch.setenv("CLAUDE_DIARY_DIR", str(diary))

        def boom(*a, **kw):
            raise OSError("disk full")

        monkeypatch.setattr(core, "append_entry", boom)
        with pytest.raises(SystemExit):
            core.process_session("s1", str(t), str(tmp_path))

        assert read_position(str(diary), "s1", str(t)) is None
