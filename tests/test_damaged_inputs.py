"""Damaged inputs must degrade, not delete.

Two of these were measured as total, traceless loss: a transcript with one bad
byte produced no diary entry and no audit line, and a config file with a typo
in it exited the hook with a stack trace before the write. Both look exactly
like a quiet day.
"""

import json
import os
import time
from pathlib import Path

import pytest

from claude_diary.lib.parser import parse_transcript


def _isolate_config_home(tmp_path, monkeypatch):
    """Point config lookup at a temporary directory on every platform."""
    base = tmp_path / "config-home"
    base.mkdir(exist_ok=True)
    monkeypatch.setenv("APPDATA", str(base))            # Windows
    monkeypatch.setenv("XDG_CONFIG_HOME", str(base))    # Linux, macOS
    return base


def _line(text, ts="2026-07-01T10:00:00Z"):
    return json.dumps({
        "type": "user", "timestamp": ts,
        "message": {"content": [{"type": "text", "text": text}]},
    }, ensure_ascii=False) + "\n"


GOOD = _line("실제로 한 작업입니다 정말로").encode("utf-8")


class TestABrokenTranscript:
    """Text IO decodes in chunks, so a bad byte anywhere used to surface
    before the first line was yielded — losing the good lines that preceded
    it, not just the bad one."""

    def _write(self, tmp_path, name, payload):
        p = tmp_path / name
        p.write_bytes(payload)
        return str(p)

    def test_lines_before_the_bad_byte_survive(self, tmp_path):
        path = self._write(
            tmp_path, "mid.jsonl",
            GOOD * 3 + b'{"type":"user","message":{"content":"\xff bad"}}\n' + GOOD * 3,
        )
        assert len(parse_transcript(path)["user_prompts"]) >= 6

    def test_lines_after_the_bad_byte_survive(self, tmp_path):
        path = self._write(
            tmp_path, "first.jsonl", b"\xff\xfe\x00\x01\n" + GOOD * 5)
        assert len(parse_transcript(path)["user_prompts"]) == 5

    def test_a_whole_file_in_the_wrong_codec_still_yields_a_session(self, tmp_path):
        """Windows Korean default. Mojibake beats nothing: an entry with
        damaged text can be read and repaired, a missing one cannot."""
        path = self._write(
            tmp_path, "cp949.jsonl", (_line("한글 작업 요청입니다") * 5).encode("cp949"))
        assert len(parse_transcript(path)["user_prompts"]) > 0

    def test_a_truncated_last_line_costs_only_that_line(self, tmp_path):
        path = self._write(tmp_path, "tail.jsonl", GOOD * 3 + b'{"type":"user","mess')
        assert len(parse_transcript(path)["user_prompts"]) == 3

    def test_the_session_still_reaches_the_diary(self, tmp_path, monkeypatch):
        """The end of the pipeline is what matters: `has_content` was false,
        so `process_session` returned before writing anything at all — no
        entry, no audit line, and the parse error thrown away with them."""
        from claude_diary.core import process_session

        diary = tmp_path / "diary"
        _isolate_config_home(tmp_path, monkeypatch)
        monkeypatch.setenv("CLAUDE_DIARY_DIR", str(diary))

        path = self._write(
            tmp_path, "e2e.jsonl",
            GOOD * 3 + b'{"type":"user","message":{"content":"\xff bad"}}\n' + GOOD * 3,
        )
        assert process_session("sess-broken", path, r"C:\fake\proj") is True
        written = list(diary.glob("*.md"))
        assert written and "### " in written[0].read_text(encoding="utf-8", errors="replace")


class TestABrokenConfig:
    @pytest.fixture(autouse=True)
    def _isolate(self, tmp_path, monkeypatch):
        # Both variables: `get_config_dir` reads APPDATA on Windows and
        # XDG_CONFIG_HOME everywhere else, so setting one of them isolates
        # the test on one platform and silently reads the developer's real
        # config on the other.
        _isolate_config_home(tmp_path, monkeypatch)
        from claude_diary.config import get_config_dir

        self.config_dir = Path(get_config_dir())
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.config_dir / "config.json"

    def _load(self, body):
        from claude_diary.config import load_config
        self.path.write_text(body, encoding="utf-8")
        return load_config()

    @pytest.mark.parametrize("body", ['{"lang":"ko","diary_dir":"D:/x', "", '{"a":1}\x00'])
    def test_unreadable_falls_back_but_says_so(self, body, caplog):
        with caplog.at_level("WARNING"):
            config = self._load(body)
        assert config["lang"] == "ko"
        assert "unreadable" in caplog.text or "JSON object" in caplog.text, \
            "a corrupt config turned exporters off with nothing said"

    def test_a_wrong_type_does_not_reach_the_pipeline(self):
        """`os.path.expanduser(12345)` raised outside the try that guards the
        write, so the hook exited 1 and the session went unrecorded."""
        config = self._load('{"diary_dir": 12345}')
        assert isinstance(config["diary_dir"], str)
        assert os.path.expanduser(config["diary_dir"])

    def test_a_wrong_type_on_a_nested_section_does_not_reach_it_either(self):
        config = self._load('{"enrichment": "yes"}')
        assert config["enrichment"].get("git_info") is True

    def test_a_boolean_is_not_accepted_as_a_timezone(self):
        config = self._load('{"timezone_offset": true}')
        assert config["timezone_offset"] == 9

    def test_a_top_level_array_is_rejected(self, caplog):
        with caplog.at_level("WARNING"):
            config = self._load("[1, 2, 3]")
        assert config["lang"] == "ko"

    def test_loading_one_config_does_not_change_the_defaults(self):
        """`dict(DEFAULT_CONFIG)` is shallow, so `_deep_merge` used to write
        straight into the module-level nested dicts."""
        from claude_diary.config import DEFAULT_CONFIG

        before = json.dumps(DEFAULT_CONFIG, sort_keys=True, default=str)
        self._load('{"enrichment": {"git_info": false}, "formatting": {"gitmoji": true}}')
        after = json.dumps(DEFAULT_CONFIG, sort_keys=True, default=str)
        assert before == after, "loading a config rewrote the defaults"

    def test_a_valid_config_is_left_alone(self):
        config = self._load(json.dumps({
            "lang": "en", "timezone_offset": 0, "diary_dir": "D:/diary",
            "exporters": {"slack": {"webhook": "x"}},
        }))
        assert config["lang"] == "en"
        assert config["timezone_offset"] == 0
        assert config["diary_dir"] == "D:/diary"
        assert "slack" in config["exporters"]

    def test_a_wrong_type_does_not_override_the_environment(self, monkeypatch):
        """The layer below the file has to show through. Substituting the
        hardcoded default instead sent entries to ~/working-diary while
        CLAUDE_DIARY_DIR pointed somewhere else entirely — which is how this
        test suite once wrote into a real diary."""
        monkeypatch.setenv("CLAUDE_DIARY_DIR", "D:/from-the-environment")
        config = self._load('{"diary_dir": 12345}')
        assert config["diary_dir"] == "D:/from-the-environment"

    def test_the_hook_still_writes_with_a_broken_config(self, tmp_path, monkeypatch):
        from claude_diary.core import process_session

        self.path.write_text('{"diary_dir": 12345, "enrichment": "yes"}', encoding="utf-8")
        transcript = tmp_path / "t.jsonl"
        transcript.write_bytes(GOOD * 3)
        diary = tmp_path / "diary"
        monkeypatch.setenv("CLAUDE_DIARY_DIR", str(diary))

        assert process_session("sess-cfg", str(transcript), r"C:\fake\proj") is True
        assert list(diary.glob("*.md")), "the entry did not land in the configured directory"


class TestAnUnwritableDirectory:
    def test_the_lock_gives_up_immediately(self, tmp_path, monkeypatch):
        """Waiting out the timeout cost 10s per lock — 20s of a Stop Hook
        holding the end of a session — for a directory that was never going
        to accept a lock file."""
        from claude_diary.lib import filelock

        target = str(tmp_path / "thing")
        real_open = os.open

        def denied(path, flags, *a, **kw):
            if str(path).endswith(".lock"):
                raise OSError(13, "Permission denied")
            return real_open(path, flags, *a, **kw)

        monkeypatch.setattr(os, "open", denied)

        start = time.monotonic()
        with filelock.FileLock(target, timeout=5.0) as lock:
            assert lock.acquired is False
        assert time.monotonic() - start < 1.0, "waited out a timeout it could not win"

    def test_a_held_lock_is_still_waited_on(self, tmp_path):
        """The fast path must not swallow ordinary contention."""
        from claude_diary.lib.filelock import FileLock

        target = str(tmp_path / "thing")
        with FileLock(target):
            start = time.monotonic()
            with FileLock(target, timeout=0.5) as blocked:
                assert blocked.acquired is False
            assert time.monotonic() - start >= 0.4, "gave up without waiting"
