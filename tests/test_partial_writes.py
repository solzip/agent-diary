"""A write that fails partway must not take more than itself down.

The diary is appended to as UTF-8 text, and a disk that fills stops on a byte
boundary rather than a character one. Half a Korean character makes the file
undecodable, and every reader that opened it strictly then reported the day as
empty — `parse_daily_file` returned zero sessions for a file whose entries were
still plainly visible, and `reindex` skipped the day on the strength of that
zero. Two defences, and both are here: the writer rolls back a failed append,
and the readers tolerate a file that was already damaged (by a killed process,
which no rollback can help).
"""

import builtins
import errno
import json

import pytest

from claude_diary.indexer import reindex_all
from claude_diary.lib.stats import parse_daily_file
from claude_diary.writer import append_entry, update_session_count

ENTRY = (
    "### ⏰ 10:00:%02d | 📁 `프로젝트`\n\n"
    "**📋 작업 요청:**\n  1. 한글이 섞인 작업 요청입니다\n\n"
    "**📝 작업 요약:**\n  - 무언가 완료했습니다\n\n---\n"
)


@pytest.fixture
def diary(tmp_path):
    d = tmp_path / "diary"
    d.mkdir()
    for i in range(3):
        append_entry(str(d), "2026-07-01", ENTRY % i)
    return d


class TestRollbackOnFailedAppend:
    """The append is the only writer that can leave a broken file behind."""

    def _fill_disk_after(self, monkeypatch, target_name, allowed_bytes):
        """Let `allowed_bytes` of the append land, then raise ENOSPC.

        Byte-level on purpose: an earlier attempt cut on character boundaries
        and never reproduced the failure, because that is exactly the case
        that stays decodable.
        """
        real_open = builtins.open

        class Budget:
            def __init__(self, path, mode):
                self._f = real_open(path, "ab" if "a" in mode else "wb")
                self._left = allowed_bytes

            def write(self, s):
                b = s.encode("utf-8")
                if len(b) > self._left:
                    self._f.write(b[:self._left])
                    self._f.flush()
                    self._left = 0
                    raise OSError(errno.ENOSPC, "No space left on device")
                self._left -= len(b)
                return self._f.write(b)

            def flush(self):
                self._f.flush()

            def close(self):
                self._f.close()

            def __enter__(self):
                return self

            def __exit__(self, *a):
                self.close()

        def patched(file, mode="r", *a, **kw):
            if target_name in str(file) and ("a" in mode or "w" in mode):
                return Budget(str(file), mode)
            return real_open(file, mode, *a, **kw)

        monkeypatch.setattr(builtins, "open", patched)

    # Fractions of the entry rather than fixed byte counts: the interesting
    # cuts are the ones that land inside a character, and where those fall
    # depends on the entry's own length.
    @pytest.mark.parametrize("fraction", [0.0, 0.05, 0.33, 0.5, 0.75, 0.95])
    def test_the_file_still_decodes(self, diary, monkeypatch, fraction):
        entry = ENTRY % 9
        allowed = int(len(entry.encode("utf-8")) * fraction)
        before = (diary / "2026-07-01.md").read_bytes()
        self._fill_disk_after(monkeypatch, "2026-07-01.md", allowed)

        with pytest.raises(OSError):
            append_entry(str(diary), "2026-07-01", entry)

        monkeypatch.undo()
        after = (diary / "2026-07-01.md").read_bytes()
        after.decode("utf-8")          # the point: this must not raise
        assert after == before, "a failed append left bytes behind"

    @pytest.mark.parametrize("fraction", [0.05, 0.33, 0.5, 0.75, 0.95])
    def test_the_day_is_still_readable_by_every_reader(self, diary, monkeypatch, fraction):
        entry = ENTRY % 9
        allowed = int(len(entry.encode("utf-8")) * fraction)
        self._fill_disk_after(monkeypatch, "2026-07-01.md", allowed)
        with pytest.raises(OSError):
            append_entry(str(diary), "2026-07-01", entry)
        monkeypatch.undo()

        assert parse_daily_file(str(diary / "2026-07-01.md"))["sessions"] == 3
        assert reindex_all(str(diary)) == 3

    def test_an_append_that_fits_still_lands(self, diary, monkeypatch):
        """The rollback must not fire on the ordinary path."""
        entry = ENTRY % 9
        self._fill_disk_after(monkeypatch, "2026-07-01.md",
                              len(entry.encode("utf-8")))
        append_entry(str(diary), "2026-07-01", entry)
        monkeypatch.undo()
        assert parse_daily_file(str(diary / "2026-07-01.md"))["sessions"] == 4


class TestReadersTolerateADamagedFile:
    """A process killed mid-append cannot roll anything back, so the readers
    have to cope with what it left."""

    def _truncate_mid_character(self, path):
        raw = path.read_bytes()
        cut = len(raw)
        while cut > 0:
            try:
                raw[:cut].decode("utf-8")
            except UnicodeDecodeError:
                break
            cut -= 1
        assert cut > 0, "test data had no multi-byte character to cut"
        path.write_bytes(raw[:cut])

    def test_parse_daily_file_still_sees_the_entries(self, diary):
        path = diary / "2026-07-01.md"
        self._truncate_mid_character(path)
        with pytest.raises(UnicodeDecodeError):
            path.read_text(encoding="utf-8")

        # The last entry is cut, but the ones before it are intact and must
        # not vanish along with it.
        assert parse_daily_file(str(path))["sessions"] >= 2

    def test_reindex_does_not_skip_the_day(self, diary):
        self._truncate_mid_character(diary / "2026-07-01.md")
        assert reindex_all(str(diary)) >= 2

    def test_an_appended_entry_after_the_damage_is_still_found(self, diary):
        path = diary / "2026-07-01.md"
        self._truncate_mid_character(path)
        append_entry(str(diary), "2026-07-01", ENTRY % 9)
        assert parse_daily_file(str(path))["sessions"] >= 3


class TestTheCounterFileSurvives:
    def test_a_failed_temp_write_leaves_no_temp_file(self, diary, monkeypatch):
        update_session_count(str(diary), "2026-07-01")
        before = (diary / ".session_counts.json").read_bytes()

        real_open = builtins.open

        def patched(file, mode="r", *a, **kw):
            if ".tmp" in str(file):
                raise OSError(errno.ENOSPC, "No space left on device")
            return real_open(file, mode, *a, **kw)

        monkeypatch.setattr(builtins, "open", patched)
        with pytest.raises(OSError):
            update_session_count(str(diary), "2026-07-01")
        monkeypatch.undo()

        assert (diary / ".session_counts.json").read_bytes() == before
        assert list(diary.glob("*.tmp*")) == []

    def test_a_corrupt_counter_is_kept_rather_than_overwritten(self, diary):
        update_session_count(str(diary), "2026-07-01")
        counts = diary / ".session_counts.json"
        counts.write_text(json.dumps({"2026-06-01": 40, "2026-06-02": 55})[:20],
                          encoding="utf-8")

        update_session_count(str(diary), "2026-07-01")

        kept = diary / ".session_counts.json.corrupt"
        assert kept.exists(), "three months of counts were silently replaced"
        assert "2026-06-01" in kept.read_text(encoding="utf-8")

    def test_a_counter_holding_the_wrong_shape_does_not_crash_the_hook(self, diary):
        (diary / ".session_counts.json").write_text("[1, 2, 3]", encoding="utf-8")
        assert update_session_count(str(diary), "2026-07-01") == 1
