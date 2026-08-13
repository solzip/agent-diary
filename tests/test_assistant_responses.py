"""What the assistant said, kept whole.

The diary recorded the request and then, for the answer, keyword-matched
sentence fragments cut on every `.` — which is why `run-local.sh` appears in
one real diary as `run-local` and `sh` on separate lines, 5,800 of 32,887
summary lines (17.6%) damaged that way.

Keeping the reply instead is only possible now that an entry covers one turn.
Before, a session's worth of replies would have been copied into every entry it
produced, and there were up to 400 of those per session.

Size is not a problem at turn scope: across one real session the assistant text
per turn has a median of 1,650 characters and a maximum of 4,735.
"""

import json

from claude_diary.formatter import format_entry
from claude_diary.lib.parser import RESPONSE_MIN_LENGTH, parse_transcript
from claude_diary.lib.secret_scanner import scan_entry_data

ANSWER = (
    "The build failed at `flow-sample` clean because Maven cannot delete the "
    "jar. On Windows that is a file lock: some process still has "
    "`flow-sample-1.13.3.jar` open, and a running JVM holds its own jar."
)


def _transcript(tmp_path, *records):
    path = tmp_path / "t.jsonl"
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return str(path)


def _assistant(text):
    return {"type": "assistant", "timestamp": "2026-07-01T10:00:00Z",
            "message": {"content": [{"type": "text", "text": text}]}}


class TestKeepingTheAnswer:
    def test_the_reply_is_recorded_verbatim(self, tmp_path):
        result = parse_transcript(_transcript(tmp_path, _assistant(ANSWER)))
        assert result["assistant_responses"] == [ANSWER]

    def test_a_filename_is_not_split_at_its_dot(self, tmp_path):
        """The specific damage: sentence splitting on every period."""
        result = parse_transcript(_transcript(tmp_path, _assistant(ANSWER)))
        kept = result["assistant_responses"][0]
        assert "flow-sample-1.13.3.jar" in kept
        assert "jar" not in [line.strip() for line in kept.splitlines()]

    def test_nothing_is_truncated(self, tmp_path):
        long_answer = "설명입니다. " * 800
        result = parse_transcript(_transcript(tmp_path, _assistant(long_answer)))
        assert result["assistant_responses"][0] == long_answer.strip()

    def test_notes_between_tool_calls_are_left_out(self, tmp_path):
        """Median block in one session is 61 characters — "상황부터
        파악하겠습니다." — and those are not answers."""
        result = parse_transcript(_transcript(
            tmp_path, _assistant("상황부터 파악하겠습니다."), _assistant(ANSWER)))
        assert result["assistant_responses"] == [ANSWER]

    def test_the_threshold_is_a_length_not_a_guess(self, tmp_path):
        just_under = "가" * (RESPONSE_MIN_LENGTH - 1)
        just_over = "나" * RESPONSE_MIN_LENGTH
        result = parse_transcript(_transcript(
            tmp_path, _assistant(just_under), _assistant(just_over)))
        assert result["assistant_responses"] == [just_over]

    def test_a_repeated_reply_is_recorded_once(self, tmp_path):
        result = parse_transcript(_transcript(
            tmp_path, _assistant(ANSWER), _assistant(ANSWER)))
        assert len(result["assistant_responses"]) == 1

    def test_a_plain_string_message_counts_too(self, tmp_path):
        record = {"type": "assistant", "timestamp": "2026-07-01T10:00:00Z",
                  "message": {"content": ANSWER}}
        result = parse_transcript(_transcript(tmp_path, record))
        assert result["assistant_responses"] == [ANSWER]

    def test_only_this_turn_is_collected(self, tmp_path):
        """The whole point of keeping replies at all — at session scope this
        would repeat in every entry."""
        path = _transcript(tmp_path, _assistant("첫 턴 " + ANSWER),
                           _assistant("둘째 턴 " + ANSWER))
        result = parse_transcript(path, start_line=1)
        assert len(result["assistant_responses"]) == 1
        assert result["assistant_responses"][0].startswith("둘째 턴")


class TestRenderingIt:
    def _entry(self, responses):
        return {
            "session_id": "s", "date": "2026-07-01", "time": "10:00:00",
            "project": "p", "cwd": "/tmp", "user_prompts": ["하나 물어봅니다"],
            "assistant_responses": responses, "files_created": [],
            "files_modified": [], "commands_run": [], "summary_hints": [],
            "errors_encountered": [], "categories": [], "git_info": None,
            "code_stats": None,
        }

    def test_the_section_appears(self):
        text = format_entry(self._entry([ANSWER]), "ko")
        assert "**💬 응답:**" in text
        assert "flow-sample-1.13.3.jar" in text

    def test_it_is_quoted_line_by_line(self):
        """A paragraph is not a list, and the answers contain their own."""
        text = format_entry(self._entry(["첫 줄입니다\n\n- 항목 하나\n- 항목 둘"]), "ko")
        assert "> 첫 줄입니다" in text
        assert "> - 항목 하나" in text

    def test_no_responses_means_no_heading(self):
        assert "응답" not in format_entry(self._entry([]), "ko")

    def test_english_gets_the_english_label(self):
        assert "**💬 Response:**" in format_entry(self._entry([ANSWER]), "en")


class TestSecretsInReplies:
    def test_a_reply_is_scanned(self):
        """Replies quote command output, file contents and configuration back
        at the reader, and unlike a prompt they are kept whole."""
        entry = {
            "user_prompts": [], "summary_hints": [], "commands_run": [],
            "errors_encountered": [],
            "assistant_responses": [
                "설정을 확인했습니다. 토큰은 sk-abcdefghijklmnopqrstuvwxyz012345 입니다."
            ],
        }
        assert scan_entry_data(entry) > 0
        assert "sk-abcdefghijklmnopqrstuvwxyz012345" not in entry["assistant_responses"][0]


class TestItReachesTheDiary:
    """Collecting the reply and rendering it are both covered above; this is
    the wiring between them, which is its own way to be broken."""

    def test_the_reply_is_written_into_the_entry(self, tmp_path, monkeypatch):
        from claude_diary import core

        diary = tmp_path / "diary"
        diary.mkdir()
        path = _transcript(
            tmp_path,
            {"type": "user", "timestamp": "2026-07-01T10:00:00Z",
             "message": {"content": [{"type": "text", "text": "왜 빌드가 깨졌나요"}]}},
            _assistant(ANSWER),
        )
        monkeypatch.setenv("APPDATA", str(tmp_path / "cfg"))
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
        monkeypatch.setenv("CLAUDE_DIARY_DIR", str(diary))

        assert core.process_session("s1", path, str(tmp_path)) is True
        written = "".join(p.read_text(encoding="utf-8") for p in diary.glob("*.md"))
        assert "flow-sample-1.13.3.jar" in written
        assert "💬" in written


class TestTheOldExtractorIsGone:
    def test_the_hook_no_longer_invents_summary_hints(self, tmp_path):
        """`summary_hints` stays in the schema — `write --input` takes them
        from agent-authored JSON — but the hook stopped manufacturing them."""
        result = parse_transcript(_transcript(tmp_path, _assistant(ANSWER)))
        assert result["summary_hints"] == []

    def test_the_function_itself_is_removed(self):
        from claude_diary.lib import parser
        assert not hasattr(parser, "_extract_summary_hints")
