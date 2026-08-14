"""Inputs that cannot be read must not come back as inputs that were empty.

An audit of every broad `except` in `src/` found 82 of them, 39 with no trace
in the handler body at all. Most of those 39 turned out to be fine on a second
reading: they hand the failure to their caller as a return value or push it
onto a `failures` list the command prints later. What was left is this file's
subject — handlers whose failure path produces a value that is indistinguishable
from a real, empty, successful answer:

    a diary file that will not open   -> zero sessions, same as a quiet day
    an audit log that will not open   -> no entries, same as a tool never run
    a team config that will not parse -> None, same as "there is no team"
    a source file that will not hash  -> a checksum covering less than it says

and two functions that are called rarely enough that a `NameError` in them
would be absorbed by the same handler and read as an ordinary negative result.

The other 33 are deliberate and listed in `docs/plans/next-session.md`.
"""

import ast
import json

from pathlib import Path

import pytest

from claude_diary.lib import audit, git_info, stats
from claude_diary import team

ROOT = Path(__file__).resolve().parent.parent

#: Broad handlers whose body leaves no trace a grep can see. Every one of these
#: was read and kept on purpose — most hand the failure to their caller as a
#: return value or a `failures` list, which this scan cannot recognise, and the
#: rest are last-resort paths where reporting is what would break. Adding to
#: this set is a decision; arriving here by accident is the thing to catch.
DELIBERATELY_UNTRACED = {
    # failure travels back as a return value or an accumulated failure list
    ("cli/doctor.py", "_check_module_importable"),
    ("cli/doctor.py", "_check_notion"),
    ("cli/maintenance.py", "cmd_delete"),
    ("cli/notion_init.py", "_verify_access"),
    ("cli/notion_push/__init__.py", "cmd_notion_push"),
    ("cli/notion_push/artifacts.py", "_git_diff"),
    ("cli/notion_push/relations.py", "_wire_depends_on"),
    ("cli/notion_push/relations.py", "_wire_parent_tasks"),
    ("cli/notion_review.py", "_mark_reviewed"),
    ("cli/search.py", "_fallback_search_from_files"),
    ("exporters/discord.py", "export"),
    ("exporters/loader.py", "retry_queued"),
    ("exporters/notion_hierarchical.py", "short_error"),
    ("exporters/notion_views.py", "_create_view"),
    ("exporters/notion_views.py", "_update_view"),
    ("exporters/slack.py", "export"),
    ("indexer.py", "reindex_all"),
    ("lib/parser.py", "parse_transcript"),
    # runs on every entry, so a NameError dies on the first CI run anyway
    ("lib/git_info.py", "_get_branch"),
    ("lib/git_info.py", "_get_recent_commits"),
    ("lib/git_info.py", "get_commit_info"),
    ("lib/git_info.py", "get_diff_stat"),
    ("lib/git_info.py", "get_head_branch"),
    ("lib/git_info.py", "get_repo_root"),
    # cosmetic, and off by default
    ("cli/stats.py", "_get_terminal_width"),
    ("lib/parser.py", "get_session_time_range"),
    # the last place a report can be attempted from; it must not raise
    ("lib/nonfatal.py", "_say"),
}

_TRACE_MARKERS = ("logger", "print", "non_fatal", "warn", "Raise", "stderr", "_fail", "sys.exit")


def _exception_names(node_type):
    """Names in an `except` clause, dotted forms included.

    An earlier version of this scan read `except json.JSONDecodeError` as a
    bare `except` — the type is an `ast.Attribute`, not an `ast.Name` — and
    reported handlers that do not exist.
    """
    if node_type is None:
        return ["<bare>"]
    nodes = node_type.elts if isinstance(node_type, ast.Tuple) else [node_type]
    names = []
    for n in nodes:
        if isinstance(n, ast.Name):
            names.append(n.id)
        elif isinstance(n, ast.Attribute):
            names.append(n.attr)
    return names


def _sources():
    """Walk the tree rather than ask git.

    The sdist ships these tests and is not a git checkout, so `git ls-files`
    there returns nothing and every scan built on it silently passes.
    """
    for path in sorted((ROOT / "src" / "claude_diary").rglob("*.py")):
        if "__pycache__" not in path.parts:
            yield path


def _untraced_broad_handlers():
    found = set()
    for path in _sources():
        name = path.relative_to(ROOT).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        funcs = [n for n in ast.walk(tree)
                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            if not ({"Exception", "BaseException", "<bare>"} & set(_exception_names(node.type))):
                continue
            body = ast.dump(ast.Module(body=node.body, type_ignores=[]))
            if any(marker in body for marker in _TRACE_MARKERS):
                continue
            owner = [f.name for f in funcs
                     if f.lineno <= node.lineno <= (f.end_lineno or f.lineno)]
            found.add((name.replace("src/claude_diary/", ""), owner[-1] if owner else "<module>"))
    return found


class TestNoNewSilentHandlerArrivesUnnoticed:
    def test_the_untraced_handlers_are_the_ones_that_were_reviewed(self):
        found = _untraced_broad_handlers()
        added = sorted(found - DELIBERATELY_UNTRACED)
        assert not added, (
            "these broad `except` blocks leave no trace and were not part of the review. "
            "Either report the failure, or add them to DELIBERATELY_UNTRACED with the "
            "reason: %s" % ", ".join("%s:%s" % a for a in added)
        )

    def test_the_list_has_not_gone_stale(self):
        """An entry that no longer matches anything is a note about code that
        has moved on, and it would hide a real one arriving under that name."""
        gone = sorted(DELIBERATELY_UNTRACED - _untraced_broad_handlers())
        assert not gone, "no longer present, drop from the list: %s" % ", ".join(
            "%s:%s" % g for g in gone)

    def test_the_scan_finds_anything_at_all(self):
        """A scan that silently matched nothing would make both tests above
        pass while checking nothing."""
        assert len(_untraced_broad_handlers()) > 20


def _unopenable(monkeypatch, target_path, error=None):
    """Make exactly one path fail to open, leaving every other read alone.

    Injected rather than made real: on Windows an `icacls` denial does not
    apply to the file's owner, so the only portable way to reach the handler
    is to raise what the handler catches.
    """
    real_open = open
    failure = error or OSError("permission denied")

    def fake_open(path, *args, **kwargs):
        if str(path) == str(target_path):
            raise failure
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr("builtins.open", fake_open)


class TestADiaryFileThatWillNotOpen:
    def test_it_says_so_instead_of_reporting_a_quiet_day(self, tmp_path, monkeypatch, caplog):
        diary = tmp_path / "2026-08-14.md"
        diary.write_text("### ⏰ 10:00:00 | 📁 `p`\n", encoding="utf-8")
        _unopenable(monkeypatch, diary)

        with caplog.at_level("WARNING"):
            result = stats.parse_daily_file(str(diary))

        assert result["sessions"] == 0, "the empty result itself is unchanged"
        assert "could not read" in caplog.text
        assert str(diary) in caplog.text, "the message has to name the file"

    def test_a_readable_file_says_nothing(self, tmp_path, caplog):
        """A warning on every ordinary call would be worse than silence."""
        diary = tmp_path / "2026-08-14.md"
        diary.write_text("### ⏰ 10:00:00 | 📁 `p`\n", encoding="utf-8")
        with caplog.at_level("WARNING"):
            assert stats.parse_daily_file(str(diary))["sessions"] == 1
        assert caplog.text == ""


class TestAnAuditLogThatWillNotOpen:
    def test_it_says_so_instead_of_reporting_no_entries(self, tmp_path, monkeypatch, caplog):
        log = tmp_path / ".audit.jsonl"
        log.write_text(json.dumps({"timestamp": "2026-08-14T10:00:00"}) + "\n", encoding="utf-8")
        _unopenable(monkeypatch, log)

        with caplog.at_level("WARNING"):
            assert audit.read_audit_log(str(tmp_path)) == []
        assert "audit log" in caplog.text
        assert str(log) in caplog.text

    def test_a_missing_log_is_not_a_failure(self, tmp_path, caplog):
        """Never written and cannot be read are different, and only one of
        them is worth a warning."""
        with caplog.at_level("WARNING"):
            assert audit.read_audit_log(str(tmp_path)) == []
        assert caplog.text == ""


class TestAChecksumThatSkippedAFile:
    def test_it_reports_the_file_it_could_not_hash(self, monkeypatch, caplog):
        """A checksum that quietly covers fewer files is stable, plausible and
        wrong — the failure mode tamper detection exists to prevent."""
        target = git_info.__file__

        real_open = open

        def fake_open(path, *args, **kwargs):
            if str(path) == str(target):
                raise OSError("locked")
            return real_open(path, *args, **kwargs)

        monkeypatch.setattr("builtins.open", fake_open)
        with caplog.at_level("WARNING"):
            digest = audit._compute_source_checksum()

        assert digest.startswith("sha256:")
        assert "checksum skipped" in caplog.text
        assert "git_info.py" in caplog.text

    def test_an_ordinary_run_is_quiet(self, caplog):
        with caplog.at_level("WARNING"):
            assert audit._compute_source_checksum().startswith("sha256:")
        assert caplog.text == ""


class TestATeamConfigThatWillNotParse:
    def test_it_says_so_instead_of_behaving_as_if_there_were_no_team(self, tmp_path, caplog):
        (tmp_path / ".team-config.json").write_text("{ not json", encoding="utf-8")
        with caplog.at_level("WARNING"):
            assert team.load_team_config(str(tmp_path)) is None
        assert "team config" in caplog.text

    def test_no_config_at_all_is_not_a_failure(self, tmp_path, caplog):
        with caplog.at_level("WARNING"):
            assert team.load_team_config(str(tmp_path)) is None
        assert caplog.text == ""


class TestTheRarelyRunGitHelpers:
    """`non_fatal` reports `NameError` and stays quiet about everything else.

    That trade is only worth making where the code runs seldom enough that a
    first run in the wild is where the defect would surface. Both of these
    qualify: one labels Notion rows with a branch, the other existed for some
    time before anything called it.
    """

    def test_a_defect_in_the_branch_lookup_is_named_as_one(self, monkeypatch, capsys):
        def boom(*a, **k):
            raise NameError("name 'reslut' is not defined")

        monkeypatch.setattr(git_info.subprocess, "run", boom)
        monkeypatch.setattr(git_info, "get_head_branch", lambda cwd: "main")

        assert git_info.get_branch_for_commit("/repo", "abc1234") == "main"
        err = capsys.readouterr().err
        assert "BUG:" in err and "branch lookup" in err

    def test_a_dead_git_still_falls_back_quietly(self, monkeypatch, capsys):
        """An absent git is a runtime condition, not a defect, and the fallback
        is the designed answer for it."""
        def boom(*a, **k):
            raise OSError("git not found")

        monkeypatch.setattr(git_info.subprocess, "run", boom)
        monkeypatch.setattr(git_info, "get_head_branch", lambda cwd: "main")

        assert git_info.get_branch_for_commit("/repo", "abc1234") == "main"
        assert "BUG:" not in capsys.readouterr().err

    def test_a_defect_in_the_diff_stat_is_named_as_one(self, monkeypatch, capsys):
        def boom(*a, **k):
            raise NameError("name 'comit' is not defined")

        monkeypatch.setattr(git_info.subprocess, "run", boom)
        total = git_info.get_diff_stat_for_commits("/repo", ["abc1234", "def5678"])

        assert total == {"added": 0, "deleted": 0, "files": 0}, "the caller is not broken"
        err = capsys.readouterr().err
        assert err.count("BUG:") == 2, "one line per commit that failed"
        assert "abc1234" in err

    @pytest.mark.parametrize("hashes", [[], None])
    def test_nothing_to_do_reports_nothing(self, hashes, capsys):
        assert git_info.get_diff_stat_for_commits("/repo", hashes) == {
            "added": 0, "deleted": 0, "files": 0}
        assert capsys.readouterr().err == ""
