"""A diary file that cannot be opened must not vanish without a word.

Three commands walked `*.md` and used `except Exception: continue`. The
answers they gave afterwards were indistinguishable from the truthful ones:

    reindex          3 days -> "2 entries indexed"        one day gone
    search           3 files contain it -> 2 hits         no note
    delete --session in an unreadable file -> "not found" the opposite of true

Measured by injecting the OSError the handler catches, the same way the disk
full case is reproduced elsewhere in this suite.
"""

import json
import pathlib

import pytest

DAY = "### ⏰ 10:00:00 | \U0001f4c1 `proj`\n\n- keyword-here\n\n"


@pytest.fixture
def diary(tmp_path):
    for name in ("2026-08-10", "2026-08-11", "2026-08-12"):
        (tmp_path / ("%s.md" % name)).write_text(
            "# %s\n\n%s" % (name, DAY), encoding="utf-8")
    return tmp_path


@pytest.fixture
def deny_one(monkeypatch):
    """Refuse exactly one day file, the way a permission would."""
    real = pathlib.Path.read_text

    def denied(self, *a, **kw):
        if self.name == "2026-08-11.md":
            raise OSError(13, "Permission denied")
        return real(self, *a, **kw)

    monkeypatch.setattr(pathlib.Path, "read_text", denied)


class TestReindex:
    def test_the_day_is_still_missing_from_the_index(self, diary, deny_one):
        """Not fixed, and not fixable here — the file cannot be read. What
        changes is whether the user is told."""
        from claude_diary.indexer import reindex_all

        reindex_all(str(diary))
        index = json.load(open(str(diary / ".diary_index.json"), encoding="utf-8"))
        assert sorted({e["date"] for e in index["entries"]}) == ["2026-08-10", "2026-08-12"]

    def test_it_says_which_file_and_what_it_costs(self, diary, deny_one, caplog):
        from claude_diary.indexer import reindex_all

        reindex_all(str(diary))
        messages = " ".join(r.getMessage() for r in caplog.records)
        assert "2026-08-11.md" in messages
        assert "search" in messages.lower() or "stats" in messages.lower()

    def test_a_clean_run_says_nothing(self, diary, caplog):
        from claude_diary.indexer import reindex_all

        reindex_all(str(diary))
        assert not [r for r in caplog.records if "could not be read" in str(r.msg)]


class TestTheIndexFailingToSave:
    """Never blocks diary writing — that part was right. But a search served
    from a stale index looks exactly like a search with no results."""

    def test_it_says_the_index_is_now_out_of_date(self, diary, monkeypatch, caplog):
        import os as os_mod

        from claude_diary.indexer import _save_index

        monkeypatch.setattr(
            os_mod, "replace",
            lambda s, d: (_ for _ in ()).throw(OSError(28, "No space left")))
        _save_index(str(diary / ".diary_index.json"), {"entries": []})

        messages = " ".join(r.getMessage() for r in caplog.records)
        assert "out of date" in messages
        assert "reindex" in messages

    def test_it_still_does_not_raise(self, diary, monkeypatch):
        import os as os_mod

        from claude_diary.indexer import _save_index

        monkeypatch.setattr(
            os_mod, "replace",
            lambda s, d: (_ for _ in ()).throw(OSError(28, "No space left")))
        _save_index(str(diary / ".diary_index.json"), {"entries": []})

    def test_a_successful_save_says_nothing(self, diary, caplog):
        from claude_diary.indexer import _save_index

        _save_index(str(diary / ".diary_index.json"), {"entries": []})
        assert not [r for r in caplog.records if "out of date" in r.getMessage()]


class TestSearchFallback:
    def test_the_note_names_the_file(self, diary, deny_one, capsys):
        from claude_diary.cli.search import _fallback_search_from_files

        results = _fallback_search_from_files(str(diary), "keyword-here")
        out = capsys.readouterr().out
        assert len(results) == 2
        assert "2026-08-11.md" in out

    def test_a_clean_search_prints_no_note(self, diary, capsys):
        from claude_diary.cli.search import _fallback_search_from_files

        results = _fallback_search_from_files(str(diary), "keyword-here")
        assert len(results) == 3
        assert capsys.readouterr().out == ""


class TestDeleteBySession:
    def _args(self, session):
        class A:
            pass
        a = A()
        a.session = session
        a.last = False
        return a

    def test_not_found_is_qualified_when_a_file_was_skipped(
        self, diary, deny_one, capsys, monkeypatch
    ):
        """The session may be sitting in the file that could not be opened,
        so an unqualified "not found" is the one answer that must not be
        given."""
        from claude_diary.cli import maintenance

        monkeypatch.setattr(maintenance._cli, "load_config",
                            lambda: {"diary_dir": str(diary), "lang": "ko"})
        maintenance.cmd_delete(self._args("no-such-session"))
        out = capsys.readouterr().out
        assert "not found" in out
        assert "2026-08-11.md" in out

    def test_a_clean_not_found_stays_unqualified(self, diary, capsys, monkeypatch):
        from claude_diary.cli import maintenance

        monkeypatch.setattr(maintenance._cli, "load_config",
                            lambda: {"diary_dir": str(diary), "lang": "ko"})
        maintenance.cmd_delete(self._args("no-such-session"))
        out = capsys.readouterr().out
        assert "not found" in out
        assert "could not be read" not in out
