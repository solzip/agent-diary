"""The first five minutes: what a new user is shown, and whether it works.

Found by installing the published package into a sandbox with APPDATA and
USERPROFILE redirected, then running the commands a newcomer would run.
"""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from claude_diary.cli import GETTING_STARTED, main


@pytest.fixture
def sandbox_home(tmp_path, monkeypatch):
    """Redirect every path the tool derives from the user's home."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("APPDATA", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    return home


def _init(capsys):
    from claude_diary.cli.config import cmd_init
    cmd_init(SimpleNamespace(codex_only=False, codex=False))
    return capsys.readouterr().out


class TestInitClosingMessage:
    def test_it_does_not_print_a_shell_command_that_only_works_on_unix(
            self, sandbox_home, capsys):
        """It used to close with `cat <dir>/$(date +%Y-%m-%d).md`, which does
        nothing on the Windows this project supports and tests against."""
        out = _init(capsys)
        assert "$(date" not in out
        assert "%Y-%m-%d" not in out

    def test_it_names_todays_file_outright(self, sandbox_home, capsys):
        out = _init(capsys)
        assert "%s.md" % datetime.now().strftime("%Y-%m-%d") in out

    def test_it_points_at_backfill(self, sandbox_home, capsys):
        """Onboarding used to end at "sessions will be auto-logged", which is
        an instruction to go away and come back later. The history is already
        on disk, and offering it is the whole payoff."""
        out = _init(capsys)
        assert "backfill" in out

    def test_it_points_at_doctor(self, sandbox_home, capsys):
        out = _init(capsys)
        assert "doctor" in out


class TestGettingStarted:
    def test_the_epilog_leads_with_the_commands_that_matter(self):
        assert "start here" in GETTING_STARTED
        for command in ("init", "backfill", "doctor", "report", "search"):
            assert "agent-diary %s" % command in GETTING_STARTED

    @pytest.mark.parametrize(
        "command", ["init", "backfill", "doctor", "report", "search", "diary-notion"])
    def test_every_advertised_command_resolves(self, command, capsys):
        """An epilog recommending a command that does not exist is worse than
        no epilog. argparse exits 2 on an unknown one, 0 on --help."""
        with patch("sys.argv", ["agent-diary", command, "--help"]), \
             pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 0, "%s did not resolve" % command

    def test_bare_invocation_shows_the_route_in(self, capsys):
        with patch("sys.argv", ["agent-diary"]):
            main()
        out = capsys.readouterr().out
        assert "start here" in out
        assert "agent-diary init" in out


class TestDoctorOnAFreshMachine:
    def test_it_says_to_run_init(self, tmp_path, capsys):
        from claude_diary.cli.doctor import cmd_doctor
        with patch("claude_diary.cli.doctor.load_config",
                   return_value={"diary_dir": str(tmp_path / "diary"),
                                 "timezone_offset": 9, "exporters": {}}), \
             patch("claude_diary.cli.doctor.get_config_path",
                   return_value=str(tmp_path / "absent.json")), \
             patch("claude_diary.cli.setup._get_claude_settings_path",
                   return_value=str(tmp_path / "none.json")), \
             pytest.raises(SystemExit):
            cmd_doctor(SimpleNamespace(notion=False))
        assert "agent-diary init" in capsys.readouterr().out
