"""A console that cannot encode the output must not end the command.

Reported from another project: `diary-notion push --dry-run` died on a Korean
Windows console before writing anything.

    UnicodeEncodeError: 'cp949' codec can't encode character '\\u2014'
      in cmd_notion_push -> print(preview)

The reported line was one of 206 string literals in `src/` that contain a
character cp949 has no room for, so wrapping it would have fixed one command
and left the rest. Measured across the commands that run without credentials,
**four of eleven crashed**: `stats` on `╔` at position 0, `weekly` on `📊`,
plus `report` and — worst of them — `doctor`, whose entire job is to tell you
whether the tool is working.

`hook.py` had done this correctly since it was written. The CLI never got it.

cp949 is used here because it is the encoding that produced the report, and
its codec ships with CPython everywhere, so this runs the same on the Linux
and macOS CI as it does on the machine that hit it.
"""

import json
import subprocess
import sys

import pytest

from claude_diary.lib.console import ERROR_HANDLER, make_output_unbreakable

#: Characters this project prints that cp949 cannot represent. It carries
#: U+2015 HORIZONTAL BAR but not U+2014 EM DASH, and no emoji at all.
UNENCODABLE = ["—", "╔", "\U0001f4ca", "✓"]


def _isolated(tmp_path, encoding):
    """Environment for a run that cannot touch the real diary.

    All three variables, because `config.json` deliberately wins over
    `CLAUDE_DIARY_DIR` alone — a test that got this wrong once wrote five
    entries into a real diary.
    """
    import os
    env = dict(os.environ)
    env["APPDATA"] = str(tmp_path / "appdata")
    env["XDG_CONFIG_HOME"] = str(tmp_path / "xdg")
    env["CLAUDE_DIARY_DIR"] = str(tmp_path / "diary")
    env["PYTHONIOENCODING"] = encoding
    env["PYTHONPATH"] = "src"
    for key in ("APPDATA", "XDG_CONFIG_HOME", "CLAUDE_DIARY_DIR"):
        (tmp_path / env[key].rsplit("\\", 1)[-1].rsplit("/", 1)[-1]).mkdir(exist_ok=True)
    (tmp_path / "diary" / "2026-08-14.md").write_text(
        "# 2026-08-14\n\n### ⏰ 10:00:00 | \U0001f4c1 `demo`\n\n"
        "- 작업 요약 — an em dash lives here\n",
        encoding="utf-8")
    return env


def _run(command, env):
    return subprocess.run(
        [sys.executable, "-m", "claude_diary"] + command.split(),
        capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)


class TestTheCommandsSurviveAKoreanConsole:
    @pytest.mark.parametrize("command", ["stats", "weekly", "doctor", "report --days 7"])
    def test_it_does_not_die_encoding_its_own_output(self, command, tmp_path):
        """All four of these crashed before the fix, `stats` on its first
        character.

        The property is that the command printed its answer, not that the
        answer was good news: `doctor` exits 1 when it finds no config, and
        that is the report working, not failing."""
        result = _run(command, _isolated(tmp_path, "cp949"))
        assert "UnicodeEncodeError" not in result.stderr, result.stderr[-400:]
        assert result.stdout.strip(), "printed nothing: %s" % result.stderr[-400:]

    def test_the_readable_output_is_still_readable(self, tmp_path):
        """Replacing rather than forcing UTF-8: Hangul is what cp949 is for,
        and it has to survive. Only what it cannot encode is lost."""
        result = _run("stats", _isolated(tmp_path, "cp949"))
        assert result.returncode == 0
        assert "demo" in result.stdout

    def test_utf8_consoles_lose_nothing(self, tmp_path):
        result = _run("stats", _isolated(tmp_path, "utf-8"))
        assert result.returncode == 0
        assert any(ch in result.stdout for ch in UNENCODABLE), (
            "a UTF-8 console should still get the box drawing and emoji")


class TestTheChartsStayCharts:
    """Not crashing was the first fix; being readable is this one.

    `errors="replace"` stopped the exception and printed `?`. `stats` draws its
    bars out of block elements, so every chart came out as a row of question
    marks — which reads as a broken program, not as a chart.
    """

    def _cp949(self, text):
        return text.encode("cp949", errors=ERROR_HANDLER).decode("cp949")

    @pytest.mark.parametrize("original,drawn", [
        ("████████", "########"),      # a full bar
        ("███░░░░░", "###-----"),      # a partial one
        ("▓▓", "++"),
        ("╔══╗", "+==+"),
        ("║ x ║", "| x |"),
        ("a — b", "a - b"),
        ("✓ done", "v done"),
        ("✗ failed", "x failed"),
    ])
    def test_it_draws_the_nearest_ascii(self, original, drawn):
        assert self._cp949(original) == drawn

    def test_substitutions_keep_the_length(self):
        """`stats` sizes its boxes by counting characters. A replacement of a
        different length moves the right border."""
        for original in ("█▓░", "╔═╗║╚╝╠╣", "—✓✗"):
            assert len(self._cp949(original)) == len(original)

    def test_an_unmapped_symbol_is_decoration_not_an_error(self):
        """`*` rather than `?`: a question mark reads as something having gone
        wrong, and an emoji this table has never heard of has not."""
        assert self._cp949("\U0001f984") == "*"

    def test_a_day_with_no_sessions_still_looks_like_one(self):
        """cp949 has `·`, so the first pass never saw it. An ASCII locale does
        not, and the month came out as 31 asterisks."""
        assert "·".encode("ascii", errors=ERROR_HANDLER).decode("ascii") == "."


class TestLosingWordsLooksDifferentFromLosingDecoration:
    """A `stats` run on an ASCII locale turned `주간 작업 리포트` into
    `** ** ***` — which reads as decoration, when it is the heading, gone."""

    def _ascii(self, text):
        return text.encode("ascii", errors=ERROR_HANDLER).decode("ascii")

    def test_letters_that_cannot_be_shown_are_marked_as_lost(self):
        assert self._ascii("주간") == "??"
        assert self._ascii("日本語") == "???"

    def test_digits_too(self):
        assert self._ascii("１２３") == "???"

    def test_symbols_stay_decoration(self):
        assert self._ascii("\U0001f4ca") == "*"
        assert self._ascii("→") == "*"

    def test_the_table_still_wins_over_the_rule(self):
        """`—` is punctuation, so the rule alone would make it `*`. It has a
        real ASCII equivalent and the table says so."""
        assert self._ascii("—") == "-"
        assert self._ascii("█") == "#"

    def test_an_ascii_locale_still_runs(self, tmp_path):
        result = _run("weekly", _isolated(tmp_path, "ascii"))
        assert "UnicodeEncodeError" not in result.stderr, result.stderr[-300:]
        assert result.stdout.strip()


class TestNothingIsSubstitutedThatDoesNotHaveToBe:
    def _cp949(self, text):
        return text.encode("cp949", errors=ERROR_HANDLER).decode("cp949")

    def test_what_the_console_can_encode_is_left_alone(self):
        assert self._cp949("한글과 → 화살표") == "한글과 → 화살표"

    def test_no_command_prints_a_question_mark_on_cp949(self, tmp_path):
        """The symptom this fix is named for."""
        for command in ("stats", "weekly", "report --days 7"):
            result = _run(command, _isolated(tmp_path, "cp949"))
            assert "?" not in result.stdout, "%s still prints `?`" % command

    def test_the_saved_report_keeps_the_real_characters(self, tmp_path):
        """The substitution is the terminal's problem, not the file's. `weekly`
        writes its report and then prints it; only the printed copy is
        degraded."""
        env = _isolated(tmp_path, "cp949")
        assert _run("weekly", env).returncode == 0
        saved = sorted((tmp_path / "diary" / "weekly").glob("*.md"))
        assert saved, "weekly wrote no file"
        text = saved[0].read_text(encoding="utf-8")
        assert "\U0001f4ca" in text and "—" in text

    def test_the_diary_file_is_untouched(self, tmp_path):
        """Entry headers are parsed on `### ⏰` elsewhere in this codebase."""
        env = _isolated(tmp_path, "cp949")
        _run("stats", env)
        diary = (tmp_path / "diary" / "2026-08-14.md").read_text(encoding="utf-8")
        assert "⏰" in diary and "\U0001f4c1" in diary


class TestTheHelperItself:
    def test_it_leaves_a_utf8_stream_alone(self, monkeypatch):
        class Stream:
            encoding = "UTF-8"
            errors = "strict"
            calls = 0

            def reconfigure(self, **kwargs):
                Stream.calls += 1

        monkeypatch.setattr(sys, "stdout", Stream())
        monkeypatch.setattr(sys, "stderr", Stream())
        make_output_unbreakable()
        assert Stream.calls == 0

    def test_it_relaxes_a_legacy_stream(self, monkeypatch):
        seen = {}

        class Stream:
            encoding = "cp949"
            errors = "strict"

            def reconfigure(self, **kwargs):
                seen.update(kwargs)

        monkeypatch.setattr(sys, "stdout", Stream())
        monkeypatch.setattr(sys, "stderr", Stream())
        make_output_unbreakable()
        assert seen == {"errors": ERROR_HANDLER}

    def test_a_captured_stream_without_reconfigure_is_not_touched(self, monkeypatch):
        """pytest and friends swap stdout for objects that have no such method;
        raising there would break every test in the suite instead of one."""
        class Captured:
            encoding = "cp949"

        monkeypatch.setattr(sys, "stdout", Captured())
        monkeypatch.setattr(sys, "stderr", Captured())
        make_output_unbreakable()  # must not raise

    def test_a_detached_stream_does_not_raise(self, monkeypatch):
        class Detached:
            encoding = "cp949"
            errors = "strict"

            def reconfigure(self, **kwargs):
                raise ValueError("underlying buffer has been detached")

        monkeypatch.setattr(sys, "stdout", Detached())
        monkeypatch.setattr(sys, "stderr", Detached())
        make_output_unbreakable()  # must not raise


class TestTheHookAlreadyHadThis:
    def test_the_hook_still_configures_its_own_streams(self):
        """It has since it was written; the CLI is what never got it. If this
        ever goes away, the Stop Hook starts dying on the same characters."""
        from pathlib import Path
        source = (Path(__file__).resolve().parent.parent
                  / "src" / "claude_diary" / "hook.py").read_text(encoding="utf-8")
        assert "_configure_stdio" in source
        assert 'errors="replace"' in source

    def test_the_hook_survives_a_legacy_console(self, tmp_path):
        """End to end, because the hook is the path that runs unattended and
        has nobody to report to when it dies."""
        import os
        env = dict(os.environ)
        env.update({
            "APPDATA": str(tmp_path / "appdata"),
            "XDG_CONFIG_HOME": str(tmp_path / "xdg"),
            "CLAUDE_DIARY_DIR": str(tmp_path / "diary"),
            "PYTHONIOENCODING": "cp949",
            "PYTHONPATH": "src",
        })
        transcript = tmp_path / "s.jsonl"
        transcript.write_text(json.dumps({
            "type": "user", "cwd": str(tmp_path),
            "message": {"role": "user", "content": "요약 — dash"},
        }) + "\n", encoding="utf-8")
        payload = json.dumps({"session_id": "s", "transcript_path": str(transcript),
                              "cwd": str(tmp_path)})
        result = subprocess.run(
            [sys.executable, "-m", "claude_diary.hook"], input=payload, env=env,
            capture_output=True, text=True, encoding="utf-8", errors="replace")
        assert "UnicodeEncodeError" not in result.stderr, result.stderr[-400:]
