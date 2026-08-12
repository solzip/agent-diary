"""Concurrent Stop Hooks must not lose entries.

Each session ending fires its own `python -m claude_diary.hook` process, so
two sessions finishing together means two processes writing one day file.
Before the lock, twelve concurrent writers produced nine entries and a
session count of four — silent loss of the tool's whole output.

Separate processes rather than threads: threads share a file object and an
interpreter, and would pass while the real thing failed.
"""

import json
import multiprocessing as mp
import os
import re
import sys

import pytest

WORKERS = 8


def _write_one(payload):
    """Runs in a fresh process; imports inside because of spawn on Windows."""
    src, diary_dir, i = payload
    if src not in sys.path:
        sys.path.insert(0, src)
    from claude_diary.writer import append_entry, update_session_count

    body = ("filler for entry %d " % i) * 100
    text = (
        "### ⏰ 10:00:%02d | 📁 `proj-%02d`\n\n"
        "**📋 작업 요청:**\n  1. %s\n\n"
        "<details><summary>x</summary>\n"
        "<code>sess-%08d-0000-0000-0000-000000000000</code>\n"
        "</details>\n\n---\n"
    ) % (i, i, body, i)
    append_entry(diary_dir, "2026-07-01", text)
    update_session_count(diary_dir, "2026-07-01")
    return i


def _src_root():
    import claude_diary
    return os.path.dirname(os.path.dirname(os.path.abspath(claude_diary.__file__)))


@pytest.fixture
def written(tmp_path):
    diary = tmp_path / "diary"
    diary.mkdir()
    src = _src_root()
    with mp.Pool(WORKERS) as pool:
        pool.map(_write_one, [(src, str(diary), i) for i in range(WORKERS)])
    return diary


def test_no_entry_is_lost(written):
    content = (written / "2026-07-01.md").read_text(encoding="utf-8")
    assert len(re.findall(r"^### ⏰", content, re.M)) == WORKERS


def test_every_session_id_survives(written):
    content = (written / "2026-07-01.md").read_text(encoding="utf-8")
    ids = set(re.findall(r"^<code>(sess-\d{8}-.*)</code>$", content, re.M))
    assert len(ids) == WORKERS


def test_the_daily_header_is_written_once(written):
    """Unlocked, the exists-then-create let several processes each write one."""
    content = (written / "2026-07-01.md").read_text(encoding="utf-8")
    assert len(re.findall(r"^# ", content, re.M)) == 1


def test_the_session_count_is_not_lost_to_a_read_modify_write(written):
    counts = json.loads((written / ".session_counts.json").read_text(encoding="utf-8"))
    assert counts["2026-07-01"] == WORKERS


def test_no_lock_files_are_left_behind(written):
    assert list(written.glob("*.lock")) == []
    assert list(written.glob("*.tmp*")) == []


class TestFileLock:
    def test_it_is_exclusive(self, tmp_path):
        from claude_diary.lib.filelock import FileLock
        target = str(tmp_path / "thing")
        with FileLock(target) as outer:
            assert outer.acquired
            with FileLock(target, timeout=0.05) as inner:
                assert not inner.acquired, "a second holder got in"

    def test_it_releases(self, tmp_path):
        from claude_diary.lib.filelock import FileLock
        target = str(tmp_path / "thing")
        with FileLock(target):
            pass
        with FileLock(target, timeout=0.05) as again:
            assert again.acquired

    def test_a_stale_lock_is_broken_rather_than_waited_on(self, tmp_path):
        """A hook that dies holding the lock must not block every session
        after it. Losing one entry is the bug being fixed; hanging forever
        would be worse."""
        import time
        from claude_diary.lib import filelock
        target = str(tmp_path / "thing")
        lock_path = target + ".lock"
        open(lock_path, "w").write("999999 0")
        old = time.time() - (filelock.STALE_AFTER_SECONDS + 5)
        os.utime(lock_path, (old, old))

        with filelock.FileLock(target, timeout=2.0) as lock:
            assert lock.acquired

    def test_failure_to_acquire_degrades_instead_of_raising(self, tmp_path):
        """The diary is best-effort. A lock we cannot take must not turn into
        an exception that loses the entry entirely."""
        from claude_diary.lib.filelock import FileLock
        target = str(tmp_path / "thing")
        with FileLock(target):
            with FileLock(target, timeout=0.05) as blocked:
                assert blocked.acquired is False  # no raise
