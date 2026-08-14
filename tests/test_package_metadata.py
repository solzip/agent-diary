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


MANIFEST = (ROOT / "MANIFEST.in").read_text(encoding="utf-8")


class TestTheSdistCarriesWhatItsOwnTestsRead:
    """The sdist ships `tests/`, which makes those tests a promise.

    Several of them read the repository rather than the package — the plugin
    manifests, the CI matrix, the release workflow, the CHANGELOG extractor.
    None of that arrived in the sdist, so unpacking it and running pytest gave
    2 collection errors, 4 failures and 14 errors: the suite could not even be
    collected, and nothing said so, because nobody unpacks their own sdist.

    Reading the paths back out of the test files rather than listing them here
    keeps this honest — a test that starts reading a new repository file is
    caught by this one instead of by whoever runs the sdist next.
    """

    #: Shipped by the build backend rather than by MANIFEST.in.
    ALREADY_SHIPPED = {"src", "tests", "pyproject.toml", "MANIFEST.in"}

    def _repo_paths_the_tests_read(self):
        paths = set()
        for test_file in sorted((ROOT / "tests").glob("test_*.py")):
            text = test_file.read_text(encoding="utf-8")
            for match in re.finditer(r'ROOT\s*/\s*"([^"]+)"', text):
                paths.add(match.group(1))
        return paths - self.ALREADY_SHIPPED

    def test_every_repository_path_the_tests_read_is_in_the_manifest(self):
        missing = [p for p in sorted(self._repo_paths_the_tests_read())
                   if p not in MANIFEST]
        assert not missing, (
            "the tests read these repository paths and MANIFEST.in does not ship them, "
            "so `pytest` inside an unpacked sdist fails on files that are simply absent: "
            "%s" % ", ".join(missing)
        )

    def test_the_documentation_link_is_shipped_too(self):
        """The PyPI sidebar promises this file; the package it describes should
        carry it. The rest of docs/ is design notes the package has no use for."""
        target = re.search(r"/blob/main/(docs/[^\"]+)", _urls()["Documentation"]).group(1)
        assert target in MANIFEST, "%s is advertised on PyPI but not shipped" % target

    def test_the_guard_can_tell_a_shipped_path_from_a_missing_one(self):
        """An extractor that quietly finds nothing would make the check above
        pass against an empty MANIFEST.in."""
        found = self._repo_paths_the_tests_read()
        assert found, "no repository paths were extracted — the pattern stopped matching"
        assert ".github" in found, "the CI-matrix test reads .github and should be picked up"
        assert "no-such-directory" not in MANIFEST, "the membership test does not discriminate"
