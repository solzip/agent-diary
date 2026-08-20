"""Three gaps between what this tool says it does and what it did.

Its purpose is to record everything done with an AI, keep the thread between
sessions, and leave enough to tell whether the work was going well. Measured
against that:

  - it read 2,000 lines of each transcript, which was 67% of this corpus, and
    said nothing about the rest
  - it had an `Issues Encountered` section filled in 20 of 6,921 entries, and
    those twenty were the parser's own failures rather than the session's
  - the branch, the one thread it observes rather than being told, was written
    into the Markdown and left out of the index, so nothing could follow a
    piece of work across days
"""

import json

import pytest

from claude_diary.lib.parser import ERROR_LIMIT, parse_transcript
from claude_diary.lib.secret_scanner import scan_entry_data


def _line(obj):
    return json.dumps(obj, ensure_ascii=False) + "\n"


def _user_text(text, ts="2026-07-01T10:00:00Z"):
    return _line({"type": "user", "timestamp": ts,
                  "message": {"content": [{"type": "text", "text": text}]}})


def _tool_error(text, ts="2026-07-01T10:00:00Z"):
    return _line({"type": "user", "timestamp": ts, "message": {"content": [
        {"type": "tool_result", "is_error": True, "content": text}
    ]}})


def _write(tmp_path, name, chunks):
    path = tmp_path / name
    path.write_text("".join(chunks), encoding="utf-8")
    return str(path)


class TestItReadsTheWholeTranscript:
    def test_a_long_transcript_is_read_to_the_end(self, tmp_path):
        """2,000 lines was the old ceiling. The end of a session is where it
        concluded, and that is what the ceiling threw away."""
        chunks = [_user_text("prompt %d" % i, ts="2026-07-01T10:00:%02dZ" % (i % 60))
                  for i in range(2500)]
        result = parse_transcript(_write(tmp_path, "long.jsonl", chunks))
        assert len(result["user_prompts"]) == 2500

    def test_the_last_timestamp_is_the_real_one(self, tmp_path):
        """One real session was recorded as ending on 2026-07-02 while its
        transcript ran to 07-08, because the end was never read."""
        chunks = [_user_text("early", ts="2026-07-02T00:00:00Z")] * 2400
        chunks.append(_user_text("late", ts="2026-07-08T11:24:30Z"))
        result = parse_transcript(_write(tmp_path, "span.jsonl", chunks))
        assert result["session_end"] == "2026-07-08T11:24:30Z"

    def test_an_explicit_cap_is_still_honoured(self, tmp_path):
        chunks = [_user_text("prompt %d" % i) for i in range(100)]
        result = parse_transcript(_write(tmp_path, "capped.jsonl", chunks), max_lines=10)
        assert len(result["user_prompts"]) == 10

    def test_hitting_the_cap_is_written_into_the_entry(self, tmp_path):
        """Truncating is a defensible choice; doing it quietly is not."""
        chunks = [_user_text("prompt %d" % i) for i in range(100)]
        result = parse_transcript(_write(tmp_path, "capped.jsonl", chunks), max_lines=10)
        assert result.get("truncated_at") == 10
        assert any("stopped at 10 lines" in e for e in result["errors_encountered"])

    def test_a_short_transcript_says_nothing_about_truncation(self, tmp_path):
        result = parse_transcript(_write(tmp_path, "short.jsonl", [_user_text("hi there")]))
        assert result.get("truncated_at") is None
        assert result["errors_encountered"] == []


class TestItRecordsWhatWentWrong:
    def test_a_failed_tool_call_is_recorded(self, tmp_path):
        path = _write(tmp_path, "err.jsonl", [_tool_error("File does not exist.")])
        assert parse_transcript(path)["errors_encountered"] == ["File does not exist."]

    def test_a_successful_tool_call_is_not(self, tmp_path):
        ok = _line({"type": "user", "message": {"content": [
            {"type": "tool_result", "is_error": False, "content": "all good"}]}})
        assert parse_transcript(_write(tmp_path, "ok.jsonl", [ok]))["errors_encountered"] == []

    def test_the_exit_code_is_not_the_message(self, tmp_path):
        """A shell failure leads with `Exit code 1` and puts the reason on the
        next line. Taking the first line literally recorded `Exit code 1` nine
        times in one session."""
        path = _write(tmp_path, "exit.jsonl", [
            _tool_error("Exit code 1\nTraceback (most recent call last):\n  File ...")
        ])
        recorded = parse_transcript(path)["errors_encountered"][0]
        assert recorded.startswith("Exit code 1: Traceback")

    def test_repeats_are_recorded_once(self, tmp_path):
        chunks = [_tool_error("File does not exist.")] * 5
        assert len(parse_transcript(_write(tmp_path, "dup.jsonl", chunks))["errors_encountered"]) == 1

    def test_the_list_is_capped(self, tmp_path):
        """Twelve failures per session on average; an entry that is mostly
        error text is not a work log."""
        chunks = [_tool_error("failure number %d" % i) for i in range(ERROR_LIMIT + 15)]
        assert len(parse_transcript(_write(tmp_path, "many.jsonl", chunks))["errors_encountered"]) == ERROR_LIMIT

    def test_the_truncation_note_survives_a_full_error_list(self, tmp_path):
        """The note is appended after the cap is already reached, and it is the
        one line that must not be crowded out."""
        chunks = [_tool_error("failure %d" % i) for i in range(ERROR_LIMIT + 5)]
        result = parse_transcript(_write(tmp_path, "both.jsonl", chunks), max_lines=5)
        assert any("stopped at 5 lines" in e for e in result["errors_encountered"])

    def test_errors_are_scanned_for_secrets(self):
        """Raw tool output is the field most likely to carry something that
        should not be written down, and it was not being scanned."""
        entry = {
            "user_prompts": [], "summary_hints": [], "commands_run": [],
            "errors_encountered": ["auth failed for token sk-abcdefghijklmnopqrstuvwxyz012345"],
        }
        masked = scan_entry_data(entry)
        assert masked > 0
        assert "sk-abcdefghijklmnopqrstuvwxyz012345" not in entry["errors_encountered"][0]


class TestItKeepsTheThread:
    def _entry(self, project, branch, session_id):
        return {
            "date": "2026-07-01", "time": "10:00:00", "project": project,
            "session_id": session_id, "user_prompts": ["x"],
            "files_created": [], "files_modified": [], "categories": [],
            "git_info": {"branch": branch, "commits": []}, "code_stats": None,
        }

    def test_the_branch_reaches_the_index(self, tmp_path):
        """It was written into the Markdown and left out of the index, so
        following a piece of work across days meant re-reading every file."""
        from claude_diary.indexer import load_index, update_index

        diary = tmp_path / "d"
        diary.mkdir()
        update_index(str(diary), self._entry("proj", "feature/x", "s1"))
        assert load_index(str(diary))["entries"][0]["branch"] == "feature/x"

    def test_sessions_on_one_branch_are_counted(self, tmp_path):
        from claude_diary.indexer import count_branch_sessions, update_index

        diary = tmp_path / "d"
        diary.mkdir()
        for i in range(3):
            update_index(str(diary), self._entry("proj", "feature/x", "s%d" % i))
        update_index(str(diary), self._entry("proj", "main", "other"))
        update_index(str(diary), self._entry("elsewhere", "feature/x", "other2"))

        assert count_branch_sessions(str(diary), "proj", "feature/x") == 3

    def test_one_session_counts_once_however_many_turns_it_wrote(self, tmp_path):
        """The count was `sum(1 for ...)` over index rows, which was the same
        number as sessions until 4.9.0 made an entry a turn. The test above
        gave its three entries three different ids, so it kept passing while
        the count was really counting turns."""
        from claude_diary.indexer import count_branch_sessions, update_index

        diary = tmp_path / "d"
        diary.mkdir()
        for _ in range(15):
            update_index(str(diary), self._entry("proj", "feature/x", "one-session"))

        assert count_branch_sessions(str(diary), "proj", "feature/x") == 1

    def test_rows_with_no_session_id_cannot_inflate_the_count(self, tmp_path):
        """4 of 7,269 rows in a real index have no id. They are one unknown,
        not one each — an unattributable row inflating the number is the
        defect, not the fix for it."""
        from claude_diary.indexer import count_branch_sessions, update_index

        diary = tmp_path / "d"
        diary.mkdir()
        for _ in range(4):
            update_index(str(diary), self._entry("proj", "feature/x", ""))
        update_index(str(diary), self._entry("proj", "feature/x", "s1"))

        assert count_branch_sessions(str(diary), "proj", "feature/x") == 2

    def test_a_missing_branch_counts_as_no_thread(self, tmp_path):
        from claude_diary.indexer import count_branch_sessions

        diary = tmp_path / "d"
        diary.mkdir()
        assert count_branch_sessions(str(diary), "proj", "") == 0

    @pytest.mark.parametrize("ordinal,expected", [(0, False), (1, False), (12, True)])
    def test_the_entry_says_where_it_sits(self, ordinal, expected):
        """The first session on a branch has no thread behind it to point at,
        so it is not numbered."""
        from claude_diary.formatter import format_entry

        entry = self._entry("proj", "feature/x", "s1")
        entry.update({"commands_run": [], "summary_hints": [],
                      "errors_encountered": [], "cwd": "/tmp"})
        if ordinal:
            entry["branch_session_ordinal"] = ordinal
        text = format_entry(entry, "ko")
        assert ("(#%d)" % ordinal in text) is expected

    def test_reindex_recovers_the_branch_from_the_markdown(self, tmp_path):
        """The index is derived, so a rebuild has to put back what the
        incremental path writes — the failure 4.8.0 was about."""
        from claude_diary.indexer import load_index, reindex_all

        diary = tmp_path / "d"
        diary.mkdir()
        (diary / "2026-07-01.md").write_text(
            "### ⏰ 10:00:00 | 📁 `proj`\n\n"
            "**🔀 Git:**\n  - 🌿 브랜치: `feature/x`\n\n---\n",
            encoding="utf-8",
        )
        assert reindex_all(str(diary)) == 1
        assert load_index(str(diary))["entries"][0]["branch"] == "feature/x"


class TestTheOrdinalCountsOtherSessionsNotThisOne:
    """4.12.0 made the count sessions instead of turns, but core still adds 1
    to a count that includes the session being written: turn 1 puts the
    session in the index, so turn 2 of the very first session on a branch
    computed ordinal 2 and stamped `(#2)` on a thread with nothing behind it.
    """

    def _turn(self, text, ts):
        return json.dumps({"type": "user", "timestamp": ts,
                           "message": {"content": [{"type": "text", "text": text}]}}) + "\n"

    def _run_two_turns(self, tmp_path, monkeypatch, session_id, transcript_name):
        import os
        from unittest.mock import patch

        from claude_diary.core import process_session

        monkeypatch.setenv("APPDATA", str(tmp_path))
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        monkeypatch.setenv("CLAUDE_DIARY_DIR", str(tmp_path / "diary"))

        transcript = tmp_path / transcript_name
        with patch("claude_diary.core.collect_git_info") as mock_git:
            mock_git.return_value = {"branch": "feature/x", "commits": [],
                                     "diff_stat": None}
            transcript.write_text(self._turn("first request", "2026-07-01T10:00:00Z"),
                                  encoding="utf-8")
            assert process_session(session_id, str(transcript), str(tmp_path)) is True
            with open(transcript, "a", encoding="utf-8") as f:
                f.write(self._turn("second request", "2026-07-01T10:05:00Z"))
            assert process_session(session_id, str(transcript), str(tmp_path)) is True

        diary_dir = tmp_path / "diary"
        return "\n".join(
            (diary_dir / name).read_text(encoding="utf-8")
            for name in os.listdir(diary_dir) if name.endswith(".md")
        )

    def test_every_turn_of_the_first_session_is_unnumbered(self, tmp_path, monkeypatch):
        """Turn 2 arrives with the session already indexed by turn 1. That is
        still the first session on the branch, so still no number."""
        text = self._run_two_turns(tmp_path, monkeypatch, "session-one", "t1.jsonl")
        assert "(#" not in text

    def test_the_second_session_is_numbered_2_on_every_turn(self, tmp_path, monkeypatch):
        text1 = self._run_two_turns(tmp_path, monkeypatch, "session-one", "t1.jsonl")
        assert "(#" not in text1
        text2 = self._run_two_turns(tmp_path, monkeypatch, "session-two", "t2.jsonl")
        assert text2.count("(#2)") == 2
        assert "(#3)" not in text2

    def test_the_count_can_leave_out_the_session_being_written(self, tmp_path):
        from claude_diary.indexer import count_branch_sessions, update_index

        diary = tmp_path / "d"
        diary.mkdir()
        entry = {
            "date": "2026-07-01", "time": "10:00:00", "project": "proj",
            "session_id": "current", "user_prompts": ["x"],
            "files_created": [], "files_modified": [], "categories": [],
            "git_info": {"branch": "feature/x", "commits": []}, "code_stats": None,
        }
        update_index(str(diary), entry)
        update_index(str(diary), dict(entry, session_id="earlier"))

        assert count_branch_sessions(str(diary), "proj", "feature/x") == 2
        assert count_branch_sessions(
            str(diary), "proj", "feature/x", exclude_session_id="current"
        ) == 1
