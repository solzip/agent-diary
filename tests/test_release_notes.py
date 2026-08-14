"""A tag has to arrive with its release notes.

Eighteen tags reached GitHub with no notes at all, because publishing was
automatic and writing the notes was not. `scripts/changelog_section.py` closes
that, so the thing worth testing is not only that it parses a heading but that
the workflow actually calls it — the 4.9.0 drift-summary defect survived a day
with seventeen passing tests because every one of them called the function
directly and none of them ran the wiring.
"""

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "changelog_section.py"
CHANGELOG = ROOT / "CHANGELOG.md"
WORKFLOW = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")


def _load():
    spec = importlib.util.spec_from_file_location("changelog_section", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


changelog_section = _load()


def _run(*args):
    """Run the script the way the workflow does — as a process, not an import."""
    return subprocess.run(
        [sys.executable, str(SCRIPT)] + list(args),
        capture_output=True, text=True, encoding="utf-8",
    )


def _pyproject_version():
    """Regex, not tomllib: the floor is 3.8 and tomllib arrived in 3.11."""
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    return re.search(r'^version = "([^"]+)"', text, re.M).group(1)


class TestItFindsTheSection:
    def test_the_body_is_the_changelog_text_and_nothing_else(self):
        """Verbatim is the whole point. A summary is a second thing to keep true."""
        found = changelog_section.sections(CHANGELOG.read_text(encoding="utf-8"))
        suffix, body = found["4.10.0"]
        assert suffix == "2026-08-13"
        assert body.strip() in CHANGELOG.read_text(encoding="utf-8")
        assert not body.startswith("## ")

    def test_a_section_stops_at_the_next_version(self):
        """On a fixture, not on the real file: a release note legitimately
        mentions the version before it ("the 4.9.0 defect was exactly this
        shape"), so searching the prose for a version string proves nothing
        about where the section ended."""
        found = changelog_section.sections(
            "## [2.0.0] - 2026-02-02\n\n- second\n\n## [1.0.0] - 2026-01-01\n\n- first\n"
        )
        assert found["2.0.0"] == ("2026-02-02", "- second")
        assert found["1.0.0"] == ("2026-01-01", "- first")

    def test_the_last_section_runs_to_the_end_of_the_file(self):
        found = changelog_section.sections("## [1.0.0] - 2026-01-01\n\n- only\n")
        assert found["1.0.0"][1] == "- only"

    def test_the_version_being_released_has_a_section(self):
        """The guard that would have caught the drift before the tag existed.

        Fails on the pull request that bumps the version without writing the
        CHANGELOG entry, rather than in the release workflow after tagging."""
        version = _pyproject_version()
        found = changelog_section.sections(CHANGELOG.read_text(encoding="utf-8"))
        assert version in found, "pyproject is at %s and CHANGELOG.md has no section for it" % version
        assert found[version][1].strip(), "CHANGELOG.md's %s section is empty" % version

    def test_a_leading_v_is_accepted_because_the_tag_carries_one(self):
        assert _run("v4.10.0").returncode == 0


class TestTheTitleKeepsTheRealDate:
    def test_the_title_is_the_tag_and_the_changelog_date(self):
        """GitHub stamps a release with the moment it was created, which for
        anything backfilled is not the day it shipped."""
        assert changelog_section.title_for("4.10.0", "2026-08-13") == "v4.10.0 — 2026-08-13"

    def test_an_older_headings_suffix_survives(self):
        assert changelog_section.title_for("4.1.0", "2026-03-17 (Phase D)") == "v4.1.0 — 2026-03-17 (Phase D)"

    def test_a_heading_with_no_date_still_produces_a_title(self):
        assert changelog_section.title_for("9.9.9", "") == "v9.9.9"

    def test_the_command_prints_it(self):
        result = _run("4.10.0", "--title")
        assert result.returncode == 0
        assert result.stdout.strip() == "v4.10.0 — 2026-08-13"


class TestAMissingSectionStopsTheRelease:
    def test_an_unknown_version_exits_nonzero_and_names_it(self):
        result = _run("9.9.9")
        assert result.returncode == 1
        assert "9.9.9" in result.stderr
        assert not result.stdout

    def test_unreleased_is_refused_by_name(self, tmp_path):
        """Different mistake from a missing section, so a different message."""
        result = _run("Unreleased")
        assert result.returncode == 1
        assert "Unreleased" in result.stderr

    def test_an_empty_section_is_not_release_notes(self, tmp_path):
        fake = tmp_path / "CHANGELOG.md"
        fake.write_text("## [1.0.0] - 2026-01-01\n\n## [0.9.0] - 2025-12-01\n\n- something\n", encoding="utf-8")
        result = _run("1.0.0", "--changelog", str(fake))
        assert result.returncode == 1
        assert "empty" in result.stderr

    def test_a_missing_changelog_says_so_rather_than_tracebacking(self, tmp_path):
        result = _run("1.0.0", "--changelog", str(tmp_path / "nope.md"))
        assert result.returncode == 1
        assert "no such file" in result.stderr


class TestTheOutputSurvivesTheConsole:
    def test_the_file_is_utf8_whatever_the_platform_encoding_is(self, tmp_path):
        """The bodies are Korean. Writing them through a legacy code page turns
        the last step of a successful release into a UnicodeEncodeError."""
        out = tmp_path / "notes.md"
        assert _run("4.10.0", "--output", str(out)).returncode == 0
        body = out.read_text(encoding="utf-8")
        assert "`.export_queue.json`" in body
        assert "한 줄 요약" in body

    def test_nothing_is_written_when_the_lookup_fails(self, tmp_path):
        out = tmp_path / "notes.md"
        assert _run("9.9.9", "--output", str(out)).returncode == 1
        assert not out.exists()


class TestTheWorkflowActuallyCallsIt:
    """Every assertion here is about wiring. The script can be perfect and the
    release still ship without notes if the workflow does not run it."""

    def test_the_workflow_runs_the_script(self):
        assert "scripts/changelog_section.py" in WORKFLOW

    def test_it_has_permission_to_create_a_release(self):
        assert "contents: write" in WORKFLOW, "gh release create needs contents: write"
        assert "id-token: write" in WORKFLOW, "PyPI trusted publishing still needs this"

    def test_the_notes_are_read_before_the_package_is_published(self):
        """A tag the CHANGELOG never mentioned has to fail while it is still
        fixable. A PyPI version cannot be unpublished.

        Pinned to the invocation that writes the file, not to the script name:
        a comment mentioning the script, or a later call that only reads the
        title, would satisfy a looser check while the guard was gone."""
        assert WORKFLOW.index("--output release-notes.md") < WORKFLOW.index("gh-action-pypi-publish")

    def test_the_release_is_created_after_the_package_is_published(self):
        """So the notes never announce a version nobody can install yet."""
        assert WORKFLOW.index("gh-action-pypi-publish") < WORKFLOW.index("gh release create")
        assert WORKFLOW.index("gh-action-pypi-publish") < WORKFLOW.index("--notes-file release-notes.md")

    @pytest.mark.parametrize("fragment", ["gh release view", "gh release edit", "gh release create"])
    def test_rerunning_a_failed_release_is_safe(self, fragment):
        """`gh release create` fails if the release exists, and a re-run of a
        half-finished workflow is exactly when that happens."""
        assert fragment in WORKFLOW

    def test_the_tag_is_verified_so_a_typo_does_not_invent_one(self):
        assert "--verify-tag" in WORKFLOW
