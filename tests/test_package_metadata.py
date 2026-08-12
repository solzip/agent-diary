"""What the PyPI page claims has to match what the repository actually is.

For most people who ever look at this project, the PyPI page is the only page
they see, and its sidebar is whatever `[project.urls]` says. A link that 404s
there is worse than a missing one, and a Python version claimed in the
classifiers but absent from the CI matrix is a promise nothing checks.

Regex rather than `tomllib`, because the floor here is Python 3.8 and
`tomllib` arrived in 3.11 — the same reason `_pyproject_version` in
test_codex_plugin.py parses this file by hand.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
CI = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")


def _section(name):
    """Return the raw body of a `[section]` in pyproject.toml."""
    match = re.search(
        r"^\[%s\]\n(.*?)(?=^\[|\Z)" % re.escape(name), PYPROJECT, re.M | re.S
    )
    return match.group(1) if match else ""


def _urls():
    return dict(re.findall(r'^(\w+) = "([^"]+)"', _section("project.urls"), re.M))


def _classifiers():
    block = re.search(r"classifiers = \[(.*?)\]", PYPROJECT, re.S).group(1)
    return re.findall(r'"([^"]+)"', block)


class TestTheSidebarLinksGoSomewhere:
    @pytest.mark.parametrize("key", ["Homepage", "Repository", "Changelog",
                                     "Documentation", "Issues"])
    def test_the_link_is_declared(self, key):
        assert key in _urls(), "[project.urls] is missing %s" % key

    @pytest.mark.parametrize("key", ["Changelog", "Documentation"])
    def test_the_file_it_points_at_exists_in_this_repository(self, key):
        """These two name a path in the repo, so a rename breaks them and
        nothing else would notice."""
        url = _urls()[key]
        match = re.search(r"/blob/main/(.+)$", url)
        assert match, "%s should point at a file in this repository: %s" % (key, url)
        assert (ROOT / match.group(1)).is_file(), "%s -> %s does not exist" % (
            key, match.group(1),
        )

    def test_every_url_points_at_this_repository(self):
        """The old package still carries links to `claude-code-hooks-diary`."""
        for key, url in _urls().items():
            assert "solzip/agent-diary" in url, "%s points elsewhere: %s" % (key, url)


class TestTheClassifiersAreClaimsWeCanBack:
    def _ci_python_versions(self):
        block = re.search(r'python-version: \[(.*?)\]', CI).group(1)
        return set(re.findall(r'"([\d.]+)"', block))

    def test_the_python_versions_match_the_ci_matrix(self):
        """A version in the classifiers is a support claim. A version in the
        matrix is a tested one. They have to be the same set."""
        claimed = {
            c.rsplit(" ", 1)[1]
            for c in _classifiers()
            if c.startswith("Programming Language :: Python :: 3.")
        }
        assert claimed == self._ci_python_versions(), (
            "classifiers claim %s, CI tests %s"
            % (sorted(claimed), sorted(self._ci_python_versions()))
        )

    def test_requires_python_matches_the_lowest_tested_version(self):
        floor = min(self._ci_python_versions(), key=lambda v: [int(p) for p in v.split(".")])
        assert 'requires-python = ">=%s"' % floor in PYPROJECT

    def test_os_independent_is_claimed_because_ci_runs_three(self):
        assert "Operating System :: OS Independent" in _classifiers()
        for os_name in ("ubuntu-latest", "macos-latest", "windows-latest"):
            assert os_name in CI, "claiming OS Independent while CI drops %s" % os_name

    def test_the_license_classifier_matches_the_declared_license(self):
        assert 'license = {text = "MIT"}' in PYPROJECT
        assert "License :: OSI Approved :: MIT License" in _classifiers()


class TestTheRetiredNameRedirectsRatherThanShipsCode:
    """`claude-diary` was this project's name up to 4.2.0 and still receives
    installs. `packaging/claude-diary/` is the release that turns those into
    installs of the current package.

    The thing that would break it is shipping modules: both distributions would
    then own `claude_diary/`, and whichever pip unpacked last would win.
    """

    SHIM = ROOT / "packaging" / "claude-diary" / "pyproject.toml"

    @pytest.fixture
    def shim(self):
        return self.SHIM.read_text(encoding="utf-8")

    def test_it_exists(self):
        assert self.SHIM.is_file()

    def test_it_claims_the_old_distribution_name(self, shim):
        assert 'name = "claude-diary"' in shim

    def test_it_ships_no_modules(self, shim):
        assert re.search(r"^packages = \[\]$", shim, re.M), (
            "the redirect must not ship `claude_diary`; agent-diary already does"
        )

    def test_it_depends_on_the_current_package(self, shim):
        assert re.search(r'dependencies = \["agent-diary>=[\d.]+"\]', shim)

    def test_its_version_beats_the_one_on_pypi(self, shim):
        """4.2.0 is published. A lower version would never be resolved."""
        version = re.search(r'^version = "([^"]+)"', shim, re.M).group(1)
        parts = [int(p) for p in version.split(".")]
        assert parts > [4, 2, 0], "%s would lose to the published 4.2.0" % version

    def test_the_floor_it_pins_is_a_version_that_exists(self, shim):
        """The floor has to be a release that shipped, or pip resolves nothing."""
        floor = re.search(r'agent-diary>=([\d.]+)"', shim).group(1)
        released = re.findall(r"^## \[([\d.]+)\]", (ROOT / "CHANGELOG.md").read_text(
            encoding="utf-8"), re.M)
        assert floor in released, "%s is not in the changelog" % floor
