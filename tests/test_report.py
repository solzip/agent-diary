"""Tests for `agent-diary report`."""

import json
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from claude_diary.cli.report import (
    _is_reportable,
    _load_narrative,
    _resolve_period,
    cmd_report,
)


def _args(**kw):
    base = dict(date_from=None, date_to=None, month=None, days=None,
                project=None, output=None, detail=False, json=False)
    base.update(kw)
    return SimpleNamespace(**base)


def _entry(session_id, project, requests=(), summary=()):
    lines = ["### ⏰ 10:00:00 | 📁 `%s`" % project, ""]
    if requests:
        lines.append("**📋 작업 요청:**")
        for i, r in enumerate(requests, 1):
            lines.append("  %d. %s" % (i, r))
        lines.append("")
    if summary:
        lines.append("**📝 작업 요약:**")
        for s in summary:
            lines.append("  - %s" % s)
        lines.append("")
    lines.append("<details><summary>x</summary>")
    lines.append("<code>%s</code>" % session_id)
    lines.append("</details>")
    lines.append("")
    return "\n".join(lines)


def _diary(tmp_path, day, entries):
    d = tmp_path / "diary"
    d.mkdir(exist_ok=True)
    (d / ("%s.md" % day)).write_text(
        "# header\n\n---\n" + "\n---\n".join(entries), encoding="utf-8")
    return d


def _index(diary_dir, records):
    (diary_dir / ".diary_index.json").write_text(
        json.dumps({"entries": records}, ensure_ascii=False), encoding="utf-8")


class TestResolvePeriod:
    def test_defaults_to_the_last_seven_days(self):
        start, end = _resolve_period(_args())
        assert end == date.today()
        assert (end - start).days == 6

    def test_month(self):
        start, end = _resolve_period(_args(month="2026-02"))
        assert start.isoformat() == "2026-02-01"
        assert end.isoformat() == "2026-02-28"

    def test_month_rolls_over_december(self):
        start, end = _resolve_period(_args(month="2026-12"))
        assert end.isoformat() == "2026-12-31"

    def test_days_includes_today(self):
        start, end = _resolve_period(_args(days=1))
        assert start == end == date.today()

    def test_explicit_range(self):
        start, end = _resolve_period(_args(date_from="2026-01-05", date_to="2026-01-09"))
        assert (end - start).days == 4

    def test_selectors_are_mutually_exclusive(self):
        with pytest.raises(ValueError, match="choose one"):
            _resolve_period(_args(month="2026-02", days=3))

    def test_reversed_range_is_rejected(self):
        with pytest.raises(ValueError, match="after"):
            _resolve_period(_args(date_from="2026-02-10", date_to="2026-02-01"))

    def test_bad_formats_are_rejected(self):
        with pytest.raises(ValueError, match="YYYY-MM"):
            _resolve_period(_args(month="Feb 2026"))
        with pytest.raises(ValueError, match="YYYY-MM-DD"):
            _resolve_period(_args(date_from="05/01/2026"))


class TestReportable:
    def test_harness_bookkeeping_is_dropped(self):
        assert _is_reportable("[Request interrupted by user for tool use]") is False
        assert _is_reportable("<command-name>/clear</command-name>") is False

    def test_a_bare_instruction_is_not_a_description_of_work(self):
        assert _is_reportable("2번으로 가자") is False
        assert _is_reportable("ㄱㄱ") is False

    def test_real_content_survives(self):
        assert _is_reportable("Added JWT verification middleware") is True


class TestNarrativeIsPerEntry:
    def test_a_day_with_two_projects_does_not_mix_their_prose(self, tmp_path):
        """The reason parse_daily_file is not reused: it aggregates a whole
        day, so it cannot say which sentence belongs to which project."""
        diary = _diary(tmp_path, "2026-07-01", [
            _entry("sess-alpha-0001", "alpha", summary=["Wired up the alpha exporter"]),
            _entry("sess-beta-0002", "beta", summary=["Fixed the beta parser"]),
        ])
        found = _load_narrative(str(diary), date(2026, 7, 1), date(2026, 7, 1))
        assert found["sess-alpha-0001"]["summary"] == ["Wired up the alpha exporter"]
        assert found["sess-beta-0002"]["summary"] == ["Fixed the beta parser"]


class TestCmdReport:
    def _setup(self, tmp_path, day="2026-07-01"):
        diary = _diary(tmp_path, day, [
            _entry("sess-alpha-0001", "alpha",
                   requests=["please add the alpha exporter"],
                   summary=["Wired up the alpha exporter"]),
            _entry("sess-beta-0002", "beta", summary=["Fixed the beta parser"]),
        ])
        _index(diary, [
            {"session_id": "sess-alpha-0001", "date": day, "time": "10:00:00",
             "project": "alpha", "categories": ["feature"],
             "files": ["a.py"], "lines_added": 10, "lines_deleted": 2,
             "git_commits": ["abc1234"]},
            {"session_id": "sess-beta-0002", "date": day, "time": "11:00:00",
             "project": "beta", "categories": ["bugfix"],
             "files": ["b.py"], "lines_added": 3, "lines_deleted": 1,
             "git_commits": []},
        ])
        return {"diary_dir": str(diary), "lang": "en", "exporters": {}}

    def test_renders_a_document_with_totals(self, tmp_path, capsys):
        cfg = self._setup(tmp_path)
        with patch("claude_diary.cli.report.load_config", return_value=cfg):
            cmd_report(_args(date_from="2026-07-01", date_to="2026-07-01"))
        out = capsys.readouterr().out
        assert "# Work report — 2026-07-01 ~ 2026-07-01" in out
        assert "2 session(s)" in out
        assert "+13 / -3 lines" in out
        assert "1 commit(s)" in out
        assert "## alpha — 1 session(s)" in out
        assert "Wired up the alpha exporter" in out

    def test_project_filter_excludes_the_other_project_entirely(self, tmp_path, capsys):
        cfg = self._setup(tmp_path)
        with patch("claude_diary.cli.report.load_config", return_value=cfg):
            cmd_report(_args(date_from="2026-07-01", date_to="2026-07-01", project="alpha"))
        out = capsys.readouterr().out
        assert "alpha" in out
        assert "beta" not in out
        assert "Fixed the beta parser" not in out

    def test_summaries_are_preferred_over_raw_requests(self, tmp_path, capsys):
        cfg = self._setup(tmp_path)
        with patch("claude_diary.cli.report.load_config", return_value=cfg):
            cmd_report(_args(date_from="2026-07-01", date_to="2026-07-01", project="alpha"))
        out = capsys.readouterr().out
        assert "Wired up the alpha exporter" in out
        assert "please add the alpha exporter" not in out

    def test_detail_adds_the_requests_back(self, tmp_path, capsys):
        cfg = self._setup(tmp_path)
        with patch("claude_diary.cli.report.load_config", return_value=cfg):
            cmd_report(_args(date_from="2026-07-01", date_to="2026-07-01",
                             project="alpha", detail=True))
        out = capsys.readouterr().out
        assert "please add the alpha exporter" in out

    def test_falls_back_to_requests_and_says_so(self, tmp_path, capsys):
        diary = _diary(tmp_path, "2026-07-02", [
            _entry("sess-gamma-0003", "gamma", requests=["build the gamma importer please"]),
        ])
        _index(diary, [{"session_id": "sess-gamma-0003", "date": "2026-07-02", "time": "09:00:00",
                        "project": "gamma", "categories": [], "files": [],
                        "lines_added": 0, "lines_deleted": 0, "git_commits": []}])
        cfg = {"diary_dir": str(diary), "lang": "en", "exporters": {}}
        with patch("claude_diary.cli.report.load_config", return_value=cfg):
            cmd_report(_args(date_from="2026-07-02", date_to="2026-07-02"))
        out = capsys.readouterr().out
        assert "build the gamma importer please" in out
        assert "No work summary was recorded" in out

    def test_a_project_with_no_narrative_says_so_rather_than_looking_empty(
            self, tmp_path, capsys):
        diary = tmp_path / "diary"
        diary.mkdir()
        _index(diary, [{"session_id": "sess-delta-0004", "date": "2026-07-03", "time": "09:00:00",
                        "project": "delta", "categories": [], "files": [],
                        "lines_added": 0, "lines_deleted": 0, "git_commits": []}])
        cfg = {"diary_dir": str(diary), "lang": "en", "exporters": {}}
        with patch("claude_diary.cli.report.load_config", return_value=cfg):
            cmd_report(_args(date_from="2026-07-03", date_to="2026-07-03"))
        out = capsys.readouterr().out
        assert "## delta — 1 session(s)" in out
        assert "no summaries or requests were captured" in out

    def test_writes_to_a_file_when_asked(self, tmp_path, capsys):
        cfg = self._setup(tmp_path)
        target = tmp_path / "out" / "july.md"
        with patch("claude_diary.cli.report.load_config", return_value=cfg):
            cmd_report(_args(date_from="2026-07-01", date_to="2026-07-01",
                             output=str(target)))
        assert target.exists()
        assert "# Work report" in target.read_text(encoding="utf-8")
        assert "-> " in capsys.readouterr().out

    def test_json_output_is_machine_readable(self, tmp_path, capsys):
        cfg = self._setup(tmp_path)
        with patch("claude_diary.cli.report.load_config", return_value=cfg):
            cmd_report(_args(date_from="2026-07-01", date_to="2026-07-01", json=True))
        payload = json.loads(capsys.readouterr().out)
        assert payload["sessions"] == 2
        assert payload["projects"] == {"alpha": 1, "beta": 1}
        assert payload["lines_added"] == 13

    def test_an_empty_period_says_so_instead_of_printing_an_empty_document(
            self, tmp_path, capsys):
        cfg = self._setup(tmp_path)
        with patch("claude_diary.cli.report.load_config", return_value=cfg):
            cmd_report(_args(date_from="2020-01-01", date_to="2020-01-02"))
        out = capsys.readouterr().out
        assert "No sessions between" in out
        assert "# Work report" not in out

    def test_a_bad_selector_exits_two(self, tmp_path):
        cfg = self._setup(tmp_path)
        with patch("claude_diary.cli.report.load_config", return_value=cfg), \
             pytest.raises(SystemExit) as exc:
            cmd_report(_args(month="nonsense"))
        assert exc.value.code == 2

    def test_a_busy_day_is_capped_and_says_how_many_were_left_out(
            self, tmp_path, capsys):
        many = ["Did the thing number %d in some detail" % i for i in range(20)]
        diary = _diary(tmp_path, "2026-07-04", [
            _entry("sess-omega-0005", "omega", summary=many),
        ])
        _index(diary, [{"session_id": "sess-omega-0005", "date": "2026-07-04",
                        "time": "09:00:00", "project": "omega", "categories": [],
                        "files": [], "lines_added": 0, "lines_deleted": 0,
                        "git_commits": []}])
        cfg = {"diary_dir": str(diary), "lang": "en", "exporters": {}}
        with patch("claude_diary.cli.report.load_config", return_value=cfg):
            cmd_report(_args(date_from="2026-07-04", date_to="2026-07-04"))
        out = capsys.readouterr().out
        assert "more, see the diary" in out
