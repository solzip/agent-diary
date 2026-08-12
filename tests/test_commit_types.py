"""Counting work by what the author declared, not by what they said.

`categories` are inferred from words in the conversation, and measured across
6,906 real entries they disagree with the commit prefixes on a third of the
entries that have both. The disagreement is lopsided: the keyword rules count
`test` about four times as often as `test:` commits exist, because saying
"tests pass" while fixing a bug is enough to classify the session as testing.

A commit type is not a better guess, it is not a guess. That is the whole
argument for the second axis, and also why the two are shown side by side
rather than one replacing the other — fewer than half of all entries carry a
commit, so replacing would trade a wrong number for a missing one.
"""

import pytest

from claude_diary.formatter import commit_gitmoji
from claude_diary.lib.conventional import commit_type
from claude_diary.lib.stats import parse_daily_file


class TestReadingTheType:
    @pytest.mark.parametrize("subject,expected", [
        ("feat: add a thing", "feat"),
        ("fix: stop losing entries", "fix"),
        ("docs(blog): working-diary", "docs"),
        ("refactor(core)!: change the shape", "refactor"),
        ("chore: v4.8.3", "chore"),
    ])
    def test_it_reads_the_type(self, subject, expected):
        assert commit_type(subject) == expected

    @pytest.mark.parametrize("subject", [
        "copy: reword the landing page",
        "memory: note the decision",
        "harness: add a case",
    ])
    def test_a_prefix_outside_the_specification_still_counts(self, subject):
        """These are all in use in one real diary. A tool that only accepted
        the eleven types in the spec would report those commits as untyped,
        which is a statement about the spec rather than about the work."""
        assert commit_type(subject) == subject.split(":")[0]

    @pytest.mark.parametrize("subject", [
        "",
        None,
        "no colon here",
        "Fix: capitalised is not the convention",
        "✨ feat: already carries an emoji",
        "WIP",
    ])
    def test_anything_else_is_untyped(self, subject):
        assert commit_type(subject) == ""

    def test_the_gitmoji_and_the_count_cannot_disagree(self):
        """Both read the type from the same function. A message that gets an
        emoji on its diary line has to be counted, and one that does not, not."""
        for subject in ["feat: x", "fix: y", "copy: z", "WIP", "docs(a)!: b"]:
            typed = bool(commit_type(subject))
            emoji = bool(commit_gitmoji(subject))
            assert emoji <= typed, subject


ENTRY = """### ⏰ 10:00:%02d | 📁 `proj`

**🏷️ 카테고리:** `feature`

**📋 작업 요청:**
  1. 작업 요청입니다

%s
---
"""
COMMITS = """**🔀 Git:**
  - 커밋: `abc1234` %s
"""


def _diary(tmp_path, *entries):
    path = tmp_path / "2026-07-01.md"
    path.write_text("# header\n\n" + "".join(entries), encoding="utf-8")
    return str(path)


class TestCountingThemInADay:
    def test_it_counts_commits_and_types(self, tmp_path):
        path = _diary(
            tmp_path,
            ENTRY % (1, COMMITS % "feat: one"),
            ENTRY % (2, COMMITS % "fix: two"),
            ENTRY % (3, COMMITS % "feat: three"),
        )
        stats = parse_daily_file(path)
        assert stats["commits"] == 3
        assert sorted(stats["commit_types"]) == ["feat", "feat", "fix"]

    def test_a_session_with_no_commit_is_not_counted_as_covered(self, tmp_path):
        path = _diary(
            tmp_path,
            ENTRY % (1, COMMITS % "feat: one"),
            ENTRY % (2, ""),
            ENTRY % (3, ""),
        )
        stats = parse_daily_file(path)
        assert stats["sessions"] == 3
        assert stats["sessions_with_commits"] == 1

    def test_several_commits_in_one_session_count_once_for_coverage(self, tmp_path):
        """Coverage answers "how much of the diary has this evidence", so it
        counts sessions; the type list counts commits. Conflating them is how
        the two blocks in `stats` would stop being comparable."""
        body = COMMITS % "feat: one" + "  - 커밋: `def5678` fix: two\n"
        path = _diary(tmp_path, ENTRY % (1, body))
        stats = parse_daily_file(path)
        assert stats["sessions_with_commits"] == 1
        assert stats["commits"] == 2

    def test_an_untyped_commit_counts_as_a_commit_but_not_as_a_type(self, tmp_path):
        path = _diary(tmp_path, ENTRY % (1, COMMITS % "WIP nothing declared"))
        stats = parse_daily_file(path)
        assert stats["commits"] == 1
        assert stats["commit_types"] == []

    def test_english_labels_work_too(self, tmp_path):
        path = tmp_path / "2026-07-02.md"
        path.write_text(
            "### ⏰ 10:00:01 | 📁 `proj`\n\n**🔀 Git:**\n"
            "  - Commit: `abc1234` feat: english\n\n---\n",
            encoding="utf-8",
        )
        stats = parse_daily_file(str(path))
        assert stats["commit_types"] == ["feat"]

    def test_a_day_with_no_commits_reports_zero_rather_than_nothing(self, tmp_path):
        path = _diary(tmp_path, ENTRY % (1, ""))
        stats = parse_daily_file(path)
        assert stats["commits"] == 0
        assert stats["sessions_with_commits"] == 0
        assert stats["commit_types"] == []


class TestWhatASessionLeftBehind:
    """Three observed states, not three guesses. The point of the third one is
    that a session which changed nothing has an outcome rather than a gap:
    reading and working something out is a result."""

    def test_a_commit_makes_it_committed(self, tmp_path):
        path = _diary(tmp_path, ENTRY % (1, COMMITS % "feat: one"))
        assert parse_daily_file(path)["outcomes"]["committed"] == 1

    def test_touched_files_without_a_commit_are_their_own_outcome(self, tmp_path):
        """The largest group in the real diary, and the one the commit-type
        axis cannot see: 51% of 6,921 entries changed something and committed
        nothing."""
        body = "**✏️ 수정된 파일:**\n  - `a.py`\n"
        path = _diary(tmp_path, ENTRY % (1, body))
        assert parse_daily_file(path)["outcomes"]["changed"] == 1

    def test_created_files_count_as_changed_too(self, tmp_path):
        body = "**📄 생성된 파일:**\n  - `a.py`\n"
        path = _diary(tmp_path, ENTRY % (1, body))
        assert parse_daily_file(path)["outcomes"]["changed"] == 1

    def test_a_nonzero_diff_counts_as_changed_without_a_file_list(self, tmp_path):
        """Some entries carry only the diff stat."""
        body = "**📊 변경 통계:** +596 / -23 lines (2 files)\n"
        path = _diary(tmp_path, ENTRY % (1, body))
        assert parse_daily_file(path)["outcomes"]["changed"] == 1

    def test_an_empty_diff_is_not_a_change(self, tmp_path):
        body = "**📊 변경 통계:** +0 / -0 lines (0 files)\n"
        path = _diary(tmp_path, ENTRY % (1, body))
        assert parse_daily_file(path)["outcomes"]["investigation"] == 1

    def test_changing_nothing_is_recorded_as_investigation(self, tmp_path):
        path = _diary(tmp_path, ENTRY % (1, ""))
        outcomes = parse_daily_file(path)["outcomes"]
        assert outcomes["investigation"] == 1
        assert outcomes["committed"] == 0
        assert outcomes["changed"] == 0

    def test_english_labels_are_recognised(self, tmp_path):
        path = tmp_path / "2026-07-03.md"
        path.write_text(
            "### ⏰ 10:00:01 | 📁 `proj`\n\n**Files Modified:**\n  - `a.py`\n\n---\n",
            encoding="utf-8",
        )
        assert parse_daily_file(str(path))["outcomes"]["changed"] == 1

    def test_every_session_lands_in_exactly_one_outcome(self, tmp_path):
        path = _diary(
            tmp_path,
            ENTRY % (1, COMMITS % "feat: one"),
            ENTRY % (2, "**✏️ 수정된 파일:**\n  - `a.py`\n"),
            ENTRY % (3, ""),
        )
        stats = parse_daily_file(path)
        assert sum(stats["outcomes"].values()) == stats["sessions"] == 3


class TestTheNumbersAreLabelledAsWhatTheyAre:
    """The two blocks count different things — sessions above, commits below —
    and the larger numbers are the less complete ones."""

    def _render(self, tmp_path, capsys, monkeypatch):
        from claude_diary.cli.stats import cmd_stats

        (tmp_path / "diary").mkdir()
        _diary(tmp_path / "diary", ENTRY % (1, COMMITS % "feat: one"),
               ENTRY % (2, ""))
        monkeypatch.setattr("claude_diary.cli.load_config",
                            lambda: {"diary_dir": str(tmp_path / "diary"),
                                     "timezone_offset": 9, "lang": "en"})
        cmd_stats(type("A", (), {"month": "2026-07", "project": None})())
        return capsys.readouterr().out

    def test_the_commit_block_states_its_coverage(self, tmp_path, capsys, monkeypatch):
        out = self._render(tmp_path, capsys, monkeypatch)
        assert "Commit types" in out
        assert "1 of 2 sessions" in out, out

    def test_the_sessions_the_commit_block_cannot_see_are_accounted_for(
        self, tmp_path, capsys, monkeypatch
    ):
        """A coverage fraction alone leaves the reader to wonder what the rest
        were. The outcomes block is what answers that."""
        out = self._render(tmp_path, capsys, monkeypatch)
        assert "Session outcomes" in out
        assert "investigation only" in out, out

    def test_the_category_block_says_it_is_guessed(self, tmp_path, capsys, monkeypatch):
        out = self._render(tmp_path, capsys, monkeypatch)
        assert "guessed" in out
