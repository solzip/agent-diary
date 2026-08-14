"""This repository is public, and a docstring is an easy place to leak a home
directory into it.

One did: an explanation of why transcript folders cannot be matched back to a
path used the author's own `C:\\Users\\<name>\\...` as its example, and it
reached GitHub, the PyPI sdist and the wheel before anyone read it as anything
but an example.

The guard deliberately does not name anybody. It asks the machine running the
tests where its home directory is and checks that no tracked file quotes it,
so the check is about whoever is typing rather than about one person. On CI
that home path appears nowhere and the test is a no-op — which is correct,
because CI is not where this mistake gets made. It gets made on a laptop.
"""

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _tracked_text_files():
    listing = subprocess.run(
        ["git", "ls-files"], cwd=str(ROOT), capture_output=True, text=True
    )
    for name in listing.stdout.split():
        path = ROOT / name
        try:
            yield name, path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # binary or unreadable: nothing to read a path out of


def _flatten(text):
    """Make separators comparable.

    The leak was written inside a docstring as `C:\\\\Users\\\\...`, so the
    bytes on disk carry doubled backslashes that a naive search for the real
    path would miss. Collapse runs of backslashes and treat both separators
    the same before comparing.
    """
    while "\\\\" in text:
        text = text.replace("\\\\", "\\")
    return text.replace("/", "\\").lower()


class TestNoLocalPathsAreCommitted:
    def test_no_tracked_file_quotes_this_machines_home_directory(self):
        home = _flatten(str(Path.home()))
        # A home directory shallower than two components ("/root") is too
        # generic to match on without inviting false positives.
        if len(home.strip("\\").split("\\")) < 2:
            pytest.skip("home directory %r is too generic to search for" % home)

        offenders = [
            name for name, text in _tracked_text_files() if home in _flatten(text)
        ]
        assert not offenders, (
            "these tracked files contain this machine's home directory (%s), which is "
            "a real person's name on a public repository — use a placeholder path "
            "instead: %s" % (home, ", ".join(offenders))
        )

    def test_the_guard_can_actually_see_a_leak(self):
        """Without this, the test above passes on any machine whose home path
        happens never to appear — including one where the reader assumed it was
        checking something."""
        home = str(Path.home())
        planted = "example: %s\\Desktop\\notes" % home.replace("\\", "\\\\")
        assert _flatten(home) in _flatten(planted)
