"""The search index is a read-modify-write of the whole file.

The lock added for the diary covered `append_entry` and
`update_session_count` and stopped there, which left the index writing the
same way it always had: load everything, add one, write everything back.
That is worse than a lost append — the last writer keeps its own entry and
discards every entry the others added in the meantime. Measured unlocked at
forty concurrent sessions: the diary kept all forty, the index kept two.

Separate processes rather than threads, for the reason given in
test_concurrent_writes.py.
"""

import json
import multiprocessing as mp
import os
import sys

import pytest

WORKERS = 8


def _index_one(payload):
    src, diary_dir, i = payload
    if src not in sys.path:
        sys.path.insert(0, src)
    from claude_diary.indexer import update_index

    update_index(diary_dir, {
        "date": "2026-07-01",
        "time": "10:00:%02d" % i,
        "project": "proj-%02d" % i,
        "categories": ["feature"],
        "files_created": ["a-%02d.py" % i],
        "files_modified": [],
        "user_prompts": ["작업 요청 number %d" % i],
        "session_id": "sess-%08d" % i,
        "git_info": None,
        "code_stats": None,
    })
    return i


def _src_root():
    import claude_diary
    return os.path.dirname(os.path.dirname(os.path.abspath(claude_diary.__file__)))


@pytest.fixture
def indexed(tmp_path):
    diary = tmp_path / "diary"
    diary.mkdir()
    src = _src_root()
    with mp.Pool(WORKERS) as pool:
        pool.map(_index_one, [(src, str(diary), i) for i in range(WORKERS)])
    return diary


def _entries(diary):
    return json.loads((diary / ".diary_index.json").read_text(encoding="utf-8"))["entries"]


def test_no_index_entry_is_lost(indexed):
    assert len(_entries(indexed)) == WORKERS


def test_every_session_id_reaches_the_index(indexed):
    ids = {e["session_id"] for e in _entries(indexed)}
    assert len(ids) == WORKERS


def test_the_index_is_valid_json_afterwards(indexed):
    """A non-atomic write of a large index can be interrupted halfway."""
    json.loads((indexed / ".diary_index.json").read_text(encoding="utf-8"))


def test_nothing_is_left_behind(indexed):
    assert list(indexed.glob("*.lock")) == []
    assert list(indexed.glob("*.tmp*")) == []


class TestACorruptIndexIsNotSilentlyDiscarded:
    def _seed(self, diary, n):
        from claude_diary.indexer import update_index
        for i in range(n):
            update_index(str(diary), {
                "date": "2026-07-01", "time": "10:00:%02d" % i,
                "project": "p", "categories": [], "files_created": [],
                "files_modified": [], "user_prompts": ["x"],
                "session_id": "sess-%d" % i, "git_info": None, "code_stats": None,
            })

    def test_the_old_bytes_are_kept(self, tmp_path):
        diary = tmp_path / "diary"
        diary.mkdir()
        self._seed(diary, 5)

        index = diary / ".diary_index.json"
        raw = index.read_bytes()
        damaged = raw[:len(raw) // 2]
        index.write_bytes(damaged)                  # killed mid-write

        self._seed(diary, 1)

        kept = diary / ".diary_index.json.corrupt"
        assert kept.exists(), "a truncated index was silently replaced by one entry"
        assert kept.read_bytes() == damaged, "the salvageable bytes were not kept intact"

    def test_reindex_puts_it_back(self, tmp_path):
        """The index is derived, so the real repair is a rebuild."""
        from claude_diary.indexer import reindex_all
        from claude_diary.writer import append_entry

        diary = tmp_path / "diary"
        diary.mkdir()
        entry = (
            "### ⏰ 10:00:%02d | 📁 `proj`\n\n"
            "**📋 작업 요청:**\n  1. 작업 요청입니다\n\n"
            "<details><summary>x</summary>\n<code>sess-0000000%d</code>\n"
            "</details>\n\n---\n"
        )
        for i in range(4):
            append_entry(str(diary), "2026-07-01", entry % (i, i))

        (diary / ".diary_index.json").write_text("{ broken", encoding="utf-8")
        assert reindex_all(str(diary)) == 4
        assert len(_entries(diary)) == 4

    def test_an_index_of_the_wrong_shape_does_not_crash(self, tmp_path):
        diary = tmp_path / "diary"
        diary.mkdir()
        (diary / ".diary_index.json").write_text('["not", "an", "index"]', encoding="utf-8")
        self._seed(diary, 1)
        assert len(_entries(diary)) == 1
