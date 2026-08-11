"""Tests for `agent-diary doctor`."""

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from claude_diary.cli.doctor import (
    OK,
    STALE_AFTER_DAYS,
    WARN,
    _check_recent_activity,
    _latest_entry_date,
    cmd_doctor,
)


def _args(**kw):
    base = dict(notion=False)
    base.update(kw)
    return SimpleNamespace(**base)


def _config(diary_dir, **kw):
    base = {"diary_dir": str(diary_dir), "timezone_offset": 9, "exporters": {}}
    base.update(kw)
    return base


class TestLatestEntryDate:
    def test_reads_the_date_out_of_the_filename(self, tmp_path):
        for name in ("2026-07-01.md", "2026-08-03.md", "2026-07-15.md"):
            (tmp_path / name).write_text("x", encoding="utf-8")
        assert _latest_entry_date(str(tmp_path)).isoformat() == "2026-08-03"

    def test_ignores_files_that_are_not_dated_entries(self, tmp_path):
        (tmp_path / "2026-07-01.md").write_text("x", encoding="utf-8")
        (tmp_path / "README.md").write_text("x", encoding="utf-8")
        (tmp_path / "weekly-summary.md").write_text("x", encoding="utf-8")
        assert _latest_entry_date(str(tmp_path)).isoformat() == "2026-07-01"

    def test_missing_directory(self, tmp_path):
        assert _latest_entry_date(str(tmp_path / "nope")) is None


class TestRecentActivity:
    """The check the whole command exists for. Everything else can pass while
    the diary quietly stops filling in."""

    def _at(self, tmp_path, days_ago):
        from datetime import datetime, timedelta, timezone
        day = (datetime.now(timezone(timedelta(hours=9))) - timedelta(days=days_ago)).date()
        (tmp_path / ("%s.md" % day.isoformat())).write_text("x", encoding="utf-8")

    def test_a_long_silence_is_flagged(self, tmp_path):
        self._at(tmp_path, STALE_AFTER_DAYS + 5)
        check = _check_recent_activity(_config(tmp_path))
        assert check.status == WARN
        assert "days ago" in check.detail
        assert "install --force" in check.fix

    def test_a_recent_entry_passes(self, tmp_path):
        self._at(tmp_path, 1)
        assert _check_recent_activity(_config(tmp_path)).status == OK

    def test_a_weekend_does_not_cry_wolf(self, tmp_path):
        self._at(tmp_path, 3)
        assert _check_recent_activity(_config(tmp_path)).status == OK

    def test_no_entries_at_all_points_at_backfill(self, tmp_path):
        check = _check_recent_activity(_config(tmp_path))
        assert check.status == WARN
        assert "backfill" in check.fix


class TestCmdDoctor:
    def _settings(self, tmp_path, command="python -m claude_diary.hook"):
        path = tmp_path / "settings.json"
        path.write_text(json.dumps({
            "hooks": {"Stop": [{"hooks": [{"type": "command", "command": command}]}]}
        }), encoding="utf-8")
        return path

    def test_a_healthy_install_reports_no_failures(self, tmp_path, capsys):
        diary = tmp_path / "diary"
        diary.mkdir()
        from datetime import datetime, timedelta, timezone
        today = datetime.now(timezone(timedelta(hours=9))).date()
        (diary / ("%s.md" % today.isoformat())).write_text("x", encoding="utf-8")
        settings = self._settings(tmp_path)
        cfg = tmp_path / "config.json"
        cfg.write_text("{}", encoding="utf-8")

        with patch("claude_diary.cli.doctor.load_config", return_value=_config(diary)), \
             patch("claude_diary.cli.doctor.get_config_path", return_value=str(cfg)), \
             patch("claude_diary.cli.setup._get_claude_settings_path", return_value=str(settings)):
            cmd_doctor(_args())

        out = capsys.readouterr().out
        assert "0 failure(s)" in out
        assert "[fail]" not in out

    def test_a_missing_hook_fails_loudly(self, tmp_path, capsys):
        diary = tmp_path / "diary"
        diary.mkdir()
        settings = tmp_path / "settings.json"
        settings.write_text(json.dumps({"hooks": {}}), encoding="utf-8")
        cfg = tmp_path / "config.json"
        cfg.write_text("{}", encoding="utf-8")

        with patch("claude_diary.cli.doctor.load_config", return_value=_config(diary)), \
             patch("claude_diary.cli.doctor.get_config_path", return_value=str(cfg)), \
             patch("claude_diary.cli.setup._get_claude_settings_path", return_value=str(settings)), \
             pytest.raises(SystemExit) as exc:
            cmd_doctor(_args())

        out = capsys.readouterr().out
        assert "not registered" in out
        assert "install --force" in out
        assert exc.value.code == 1

    def test_a_hook_naming_another_module_reads_as_absent(self, tmp_path, capsys):
        """The near-miss during the rename to agent-diary.

        Had the import package been renamed, every installed settings.json
        would still hold a Stop Hook entry — pointing at a module that no
        longer exists. Hook detection matches on `claude_diary.hook`, so such
        an entry does not count as ours and this reports a failure rather
        than a reassuring tick. Loud is the correct outcome: the diary would
        have stopped without an error anywhere else.
        """
        diary = tmp_path / "diary"
        diary.mkdir()
        settings = self._settings(tmp_path, command="python -m agent_diary.hook")
        cfg = tmp_path / "config.json"
        cfg.write_text("{}", encoding="utf-8")

        with patch("claude_diary.cli.doctor.load_config", return_value=_config(diary)), \
             patch("claude_diary.cli.doctor.get_config_path", return_value=str(cfg)), \
             patch("claude_diary.cli.setup._get_claude_settings_path", return_value=str(settings)), \
             pytest.raises(SystemExit) as exc:
            cmd_doctor(_args())

        out = capsys.readouterr().out
        assert "[fail] stop hook" in out
        assert "not registered" in out
        assert exc.value.code == 1

    def test_a_recognised_hook_with_a_different_launcher_only_warns(self, tmp_path, capsys):
        """Still ours — it names the right module — but not the exact command
        `install` writes, so it is worth refreshing rather than failing."""
        diary = tmp_path / "diary"
        diary.mkdir()
        settings = self._settings(tmp_path, command="/usr/bin/python3 -m claude_diary.hook")
        cfg = tmp_path / "config.json"
        cfg.write_text("{}", encoding="utf-8")

        with patch("claude_diary.cli.doctor.load_config", return_value=_config(diary)), \
             patch("claude_diary.cli.doctor.get_config_path", return_value=str(cfg)), \
             patch("claude_diary.cli.setup._get_claude_settings_path", return_value=str(settings)):
            cmd_doctor(_args())

        out = capsys.readouterr().out
        assert "[warn] stop hook" in out
        assert "/usr/bin/python3" in out

    def test_missing_config_fails(self, tmp_path, capsys):
        diary = tmp_path / "diary"
        diary.mkdir()
        with patch("claude_diary.cli.doctor.load_config", return_value=_config(diary)), \
             patch("claude_diary.cli.doctor.get_config_path",
                   return_value=str(tmp_path / "absent.json")), \
             patch("claude_diary.cli.setup._get_claude_settings_path",
                   return_value=str(tmp_path / "no-settings.json")), \
             pytest.raises(SystemExit):
            cmd_doctor(_args())
        out = capsys.readouterr().out
        assert "agent-diary init" in out

    def test_privacy_line_says_plainly_when_nothing_is_excluded(self, tmp_path, capsys):
        """Prompts are stored as written and both limits are opt-in, so the
        default state is worth stating rather than leaving to memory."""
        diary = tmp_path / "diary"
        diary.mkdir()
        cfg = tmp_path / "config.json"
        cfg.write_text("{}", encoding="utf-8")

        with patch("claude_diary.cli.doctor.load_config", return_value=_config(diary)), \
             patch("claude_diary.cli.doctor.get_config_path", return_value=str(cfg)), \
             patch("claude_diary.cli.setup._get_claude_settings_path",
                   return_value=str(tmp_path / "none.json")):
            cmd_doctor(_args())

        out = capsys.readouterr().out
        assert "recording everything" in out

    def test_privacy_line_counts_the_rules_in_force(self, tmp_path, capsys):
        diary = tmp_path / "diary"
        diary.mkdir()
        cfg = tmp_path / "config.json"
        cfg.write_text("{}", encoding="utf-8")
        conf = _config(diary, skip_projects=["~/clients", "scratch"],
                       security={"additional_secret_patterns": ["acme-corp"]})

        with patch("claude_diary.cli.doctor.load_config", return_value=conf), \
             patch("claude_diary.cli.doctor.get_config_path", return_value=str(cfg)), \
             patch("claude_diary.cli.setup._get_claude_settings_path",
                   return_value=str(tmp_path / "none.json")):
            cmd_doctor(_args())

        out = capsys.readouterr().out
        assert "2 skipped project rule(s)" in out
        assert "1 extra redaction pattern(s)" in out
        assert "recording everything" not in out

    def test_notion_is_not_contacted_unless_asked(self, tmp_path, capsys):
        diary = tmp_path / "diary"
        diary.mkdir()
        cfg = tmp_path / "config.json"
        cfg.write_text("{}", encoding="utf-8")
        conf = _config(diary, exporters={
            "notion_hierarchical": {"api_token": "t", "root_page_id": "p"}})

        with patch("claude_diary.cli.doctor.load_config", return_value=conf), \
             patch("claude_diary.cli.doctor.get_config_path", return_value=str(cfg)), \
             patch("claude_diary.cli.setup._get_claude_settings_path",
                   return_value=str(tmp_path / "none.json")), \
             patch("claude_diary.exporters.notion_hierarchical."
                   "NotionHierarchicalExporter") as mock_exp:
            cmd_doctor(_args(notion=False))

        out = capsys.readouterr().out
        assert "not checked" in out
        mock_exp.assert_not_called()

    def test_notion_check_never_creates_the_database(self, tmp_path, capsys):
        """Same rule as dry-run: a health check must not bring anything into
        existence, so it reads the cache instead of calling ensure_database."""
        diary = tmp_path / "diary"
        diary.mkdir()
        cfg = tmp_path / "config.json"
        cfg.write_text("{}", encoding="utf-8")
        conf = _config(diary, exporters={
            "notion_hierarchical": {"api_token": "t", "root_page_id": "p"}})

        from unittest.mock import MagicMock
        mock_exp = MagicMock()

        with patch("claude_diary.cli.doctor.load_config", return_value=conf), \
             patch("claude_diary.cli.doctor.get_config_path", return_value=str(cfg)), \
             patch("claude_diary.cli.setup._get_claude_settings_path",
                   return_value=str(tmp_path / "none.json")), \
             patch("claude_diary.exporters.notion_hierarchical.NotionHierarchicalExporter",
                   return_value=mock_exp), \
             patch("claude_diary.lib.notion_cache.get_database", return_value=None):
            cmd_doctor(_args(notion=True))

        out = capsys.readouterr().out
        mock_exp.ensure_database.assert_not_called()
        mock_exp.ensure_year_page.assert_not_called()
        assert "diary-notion ensure" in out
