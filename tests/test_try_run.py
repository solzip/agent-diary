"""`try` has to be safe to run, or it is worse than not having it.

Seeing what this tool would record used to mean letting it record. The obvious
way to avoid that — export `CLAUDE_DIARY_DIR` and run the hook — does not
work, because `config.json` wins over the environment by design, so the diary
path stays whatever `init` wrote. That trap caught this project's own test
suite twice, once writing five entries into a diary with five months of
history in it.

So the tests that matter here are not about output. They are: nothing outside
the sandbox is touched, no exporter can fire, and the sandbox is cleaned up
even when the run fails.
"""

import io
import json
import os

import pytest

from claude_diary.cli import try_run


class Recorder:
    """Captures the subprocess call `try` would make."""

    def __init__(self, entry_text=None, stderr=""):
        self.entry_text = entry_text
        self.stderr = stderr
        self.env = None
        self.payload = None
        self.cmd = None
        # Captured while the run is in progress; the sandbox is gone by the
        # time the assertions run, which is the point of it.
        self.config_home_contents = None

    def __call__(self, cmd, input=None, env=None, **kwargs):
        self.cmd = cmd
        self.env = env
        self.payload = json.loads(input)
        self.config_home_contents = sorted(os.listdir(env["APPDATA"]))
        if self.entry_text is not None:
            diary = env["CLAUDE_DIARY_DIR"]
            io.open(os.path.join(diary, "2026-07-01.md"), "w", encoding="utf-8").write(
                "# header\n\n" + self.entry_text
            )

        class Result:
            stdout = ""
            stderr = self.stderr
        return Result()


def _args(tmp_path, **kw):
    transcript = tmp_path / "t.jsonl"
    if not transcript.exists():
        transcript.write_text(
            json.dumps({"type": "user", "cwd": str(tmp_path),
                        "message": {"content": "hello"}}) + "\n",
            encoding="utf-8",
        )
    defaults = {"transcript": str(transcript), "cwd": None, "session_id": None}
    defaults.update(kw)
    return type("Args", (), defaults)()


class TestItCannotTouchTheRealThing:
    def test_the_diary_directory_is_a_sandbox(self, tmp_path, monkeypatch, capsys):
        recorder = Recorder("### ⏰ 10:00:00 | 📁 `p`\n")
        monkeypatch.setattr(try_run.subprocess, "run", recorder)
        try_run.cmd_try(_args(tmp_path))

        diary = recorder.env["CLAUDE_DIARY_DIR"]
        assert "agent-diary-try-" in diary
        assert os.path.expanduser("~/working-diary") not in diary

    def test_config_lookup_is_redirected_on_every_platform(self, tmp_path, monkeypatch):
        """`config.json` beats the environment, so pointing only
        CLAUDE_DIARY_DIR at a sandbox writes into the real diary anyway. Both
        config-home variables have to move: APPDATA on Windows,
        XDG_CONFIG_HOME everywhere else."""
        recorder = Recorder("### ⏰ 10:00:00 | 📁 `p`\n")
        monkeypatch.setattr(try_run.subprocess, "run", recorder)
        try_run.cmd_try(_args(tmp_path))

        sandbox_root = recorder.env["CLAUDE_DIARY_DIR"]
        for key in ("APPDATA", "XDG_CONFIG_HOME"):
            assert "agent-diary-try-" in recorder.env[key], key
            assert recorder.env[key] != sandbox_root

    def test_no_config_means_no_exporter_can_fire(self, tmp_path, monkeypatch):
        """The one that would be unrecoverable: a trial run pushing a row into
        somebody's Notion database. With the config home empty there is no
        exporter configured to run."""
        recorder = Recorder("### ⏰ 10:00:00 | 📁 `p`\n")
        monkeypatch.setattr(try_run.subprocess, "run", recorder)
        try_run.cmd_try(_args(tmp_path))

        assert recorder.config_home_contents == []

    def test_it_runs_the_real_hook_entry_point(self, tmp_path, monkeypatch):
        """Not a reimplementation of it — the module Claude Code invokes."""
        recorder = Recorder("### ⏰ 10:00:00 | 📁 `p`\n")
        monkeypatch.setattr(try_run.subprocess, "run", recorder)
        try_run.cmd_try(_args(tmp_path))

        assert recorder.cmd[1:] == ["-m", "claude_diary.hook"]
        assert set(recorder.payload) == {"session_id", "transcript_path", "cwd"}


class TestItCleansUpAfterItself:
    def _sandboxes(self):
        import tempfile
        base = tempfile.gettempdir()
        return [n for n in os.listdir(base) if n.startswith("agent-diary-try-")]

    def test_the_sandbox_is_removed(self, tmp_path, monkeypatch):
        before = self._sandboxes()
        recorder = Recorder("### ⏰ 10:00:00 | 📁 `p`\n")
        monkeypatch.setattr(try_run.subprocess, "run", recorder)
        try_run.cmd_try(_args(tmp_path))
        assert self._sandboxes() == before

    def test_it_is_removed_even_when_the_hook_blows_up(self, tmp_path, monkeypatch):
        before = self._sandboxes()

        def explode(*a, **kw):
            raise RuntimeError("hook died")

        monkeypatch.setattr(try_run.subprocess, "run", explode)
        with pytest.raises(RuntimeError):
            try_run.cmd_try(_args(tmp_path))
        assert self._sandboxes() == before


class TestWhatItReports:
    def test_an_empty_session_is_explained_rather_than_left_blank(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(try_run.subprocess, "run", Recorder(None))
        assert try_run.cmd_try(_args(tmp_path)) == 0
        assert "recorded nothing" in capsys.readouterr().out

    def test_a_missing_transcript_is_an_error(self, tmp_path, capsys):
        args = _args(tmp_path, transcript=str(tmp_path / "nope.jsonl"))
        assert try_run.cmd_try(args) == 1

    def test_hook_stderr_is_surfaced(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(try_run.subprocess, "run",
                            Recorder("### ⏰ 10:00:00 | 📁 `p`\n", stderr="[diary] warning: x"))
        try_run.cmd_try(_args(tmp_path))
        assert "warning: x" in capsys.readouterr().out


class TestFindingThisDirectorysTranscript:
    def test_it_matches_on_the_recorded_cwd(self, tmp_path, monkeypatch):
        """Not on the folder name. Claude Code collapses every non-ASCII
        character in the path to a dash, so `...\\홍길동\\...\\문서\\...` becomes
        `C--Users-----Desktop----sol-working-diary` and cannot be mapped back."""
        projects = tmp_path / ".claude" / "projects" / "C--Users----Desktop----x"
        projects.mkdir(parents=True)
        work = tmp_path / "work"
        work.mkdir()
        (projects / "s.jsonl").write_text(
            json.dumps({"type": "user", "cwd": str(work)}) + "\n", encoding="utf-8")

        monkeypatch.setattr(os.path, "expanduser", lambda p: p.replace("~", str(tmp_path)))
        monkeypatch.chdir(work)
        assert try_run._latest_transcript_for_cwd() == str(projects / "s.jsonl")

    def test_another_directorys_transcript_is_not_used(self, tmp_path, monkeypatch):
        projects = tmp_path / ".claude" / "projects" / "other"
        projects.mkdir(parents=True)
        (projects / "s.jsonl").write_text(
            json.dumps({"type": "user", "cwd": str(tmp_path / "elsewhere")}) + "\n",
            encoding="utf-8")

        work = tmp_path / "work"
        work.mkdir()
        monkeypatch.setattr(os.path, "expanduser", lambda p: p.replace("~", str(tmp_path)))
        monkeypatch.chdir(work)
        assert try_run._latest_transcript_for_cwd() is None

    def test_a_subagent_transcript_is_never_offered(self, tmp_path, monkeypatch):
        """Subagents keep their own transcripts and they are fragments of a
        session, not one. `backfill` has excluded them since it was written —
        115 of 194 files in one real tree. Picking one here shows an entry made
        of somebody else's errand, which is what this did before the check.
        """
        projects = tmp_path / ".claude" / "projects" / "p" / "subagents"
        projects.mkdir(parents=True)
        work = tmp_path / "work"
        work.mkdir()
        (projects / "agent-abc.jsonl").write_text(
            json.dumps({"type": "user", "cwd": str(work), "agentId": "abc"}) + "\n",
            encoding="utf-8")

        monkeypatch.setattr(os.path, "expanduser", lambda p: p.replace("~", str(tmp_path)))
        monkeypatch.chdir(work)
        assert try_run._latest_transcript_for_cwd() is None

    def test_the_filename_prefix_alone_is_enough(self, tmp_path, monkeypatch):
        """The prefix is the cheap signal: it decides without opening the file.
        Tested on its own, with no `agentId`, or the field check masks it and
        the prefix could be deleted with every test still green."""
        projects = tmp_path / ".claude" / "projects" / "p"
        projects.mkdir(parents=True)
        work = tmp_path / "work"
        work.mkdir()
        (projects / "agent-no-field.jsonl").write_text(
            json.dumps({"type": "user", "cwd": str(work)}) + "\n", encoding="utf-8")

        monkeypatch.setattr(os.path, "expanduser", lambda p: p.replace("~", str(tmp_path)))
        monkeypatch.chdir(work)
        assert try_run._latest_transcript_for_cwd() is None

    def test_an_agent_id_is_caught_even_without_the_filename_prefix(self, tmp_path, monkeypatch):
        """Two signals, because the cheap one is the filename and the real one
        is the field."""
        projects = tmp_path / ".claude" / "projects" / "p"
        projects.mkdir(parents=True)
        work = tmp_path / "work"
        work.mkdir()
        (projects / "not-obviously-a-subagent.jsonl").write_text(
            json.dumps({"type": "user", "cwd": str(work), "agentId": "abc"}) + "\n",
            encoding="utf-8")

        monkeypatch.setattr(os.path, "expanduser", lambda p: p.replace("~", str(tmp_path)))
        monkeypatch.chdir(work)
        assert try_run._latest_transcript_for_cwd() is None
