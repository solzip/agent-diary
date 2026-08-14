#!/usr/bin/env python3
"""Pull one version's section out of CHANGELOG.md.

`.github/workflows/release.yml` calls this. A `v*` tag publishes the package to
PyPI and nothing wrote the release notes, which is how eighteen tags ended up
with zero of them. The notes have to come from somewhere, and the only place
that already describes a release is its CHANGELOG section — so it is copied
verbatim rather than summarised, because a summary is a second thing to keep
true.

Two behaviours matter more than the parsing:

- **A missing section is an error, not an empty release.** The workflow runs
  this before publishing, so tagging a version the CHANGELOG never mentioned
  stops while it is still fixable. A PyPI version cannot be unpublished; a
  release title can be edited all day.
- **The title carries the CHANGELOG date.** GitHub stamps a release with the
  moment it was created, which for anything backfilled is not the day it
  shipped. The heading is the only record of when the version actually landed.

No `tomllib`, no third-party parser: this runs on the 3.8 floor the rest of
the project supports, and the heading format is fixed by Keep a Changelog.
"""

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CHANGELOG = ROOT / "CHANGELOG.md"

# `## [4.10.0] - 2026-08-13`, and older ones carry a suffix: `... (Phase D)`.
HEADING = re.compile(r"^## \[([^\]]+)\](.*)$")


def sections(text):
    """Return {version: (heading suffix, body)} for every `## [...]` heading.

    A section runs to the next heading or to the end of the file. `Unreleased`
    is included so the caller can refuse it by name instead of by absence —
    the two are different mistakes and deserve different messages.
    """
    lines = text.splitlines()
    heads = []
    for index, line in enumerate(lines):
        match = HEADING.match(line)
        if match:
            heads.append((index, match.group(1), match.group(2).strip().lstrip("-").strip()))

    found = {}
    for position, (index, version, suffix) in enumerate(heads):
        end = heads[position + 1][0] if position + 1 < len(heads) else len(lines)
        found[version] = (suffix, "\n".join(lines[index + 1:end]).strip("\n"))
    return found


def title_for(version, suffix):
    """`v4.10.0 — 2026-08-13`, or just the tag when the heading has no date."""
    return "v%s — %s" % (version, suffix) if suffix else "v%s" % version


def _force_utf8(stream):
    """Make a stream carry UTF-8 whatever the console claims it can encode.

    Both streams need this, not just stdout. The bodies are Korean and the
    titles contain an em dash, so printing them through a legacy code page
    raises UnicodeEncodeError at the end of an otherwise successful release —
    and the error messages interpolate a path, which on this project's own
    machines contains Hangul. An unreadable explanation of why the release
    stopped is barely better than no explanation.
    """
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure is not None:
        try:
            reconfigure(encoding="utf-8")
        except (ValueError, OSError):
            pass
    return stream


def _emit(text, output):
    if output is not None:
        output.write_text(text, encoding="utf-8")
        return
    _force_utf8(sys.stdout).write(text)


def _fail(message):
    _force_utf8(sys.stderr).write("changelog_section: %s\n" % message)
    return 1


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Print a CHANGELOG.md section so it can be used as release notes."
    )
    parser.add_argument("version", help="version as written in the heading; a leading 'v' is allowed")
    parser.add_argument("--title", action="store_true",
                        help="print the release title instead of the body")
    parser.add_argument("--output", type=Path, metavar="PATH",
                        help="write to this file as UTF-8 instead of stdout")
    parser.add_argument("--changelog", type=Path, default=DEFAULT_CHANGELOG,
                        help="defaults to the CHANGELOG.md beside this repository's root")
    args = parser.parse_args(argv)

    version = args.version.lstrip("v")
    if version.lower() == "unreleased":
        return _fail("[Unreleased] is not a release. Give it a version number and a date first.")

    if not args.changelog.is_file():
        return _fail("no such file: %s" % args.changelog)

    found = sections(args.changelog.read_text(encoding="utf-8"))
    if version not in found:
        released = [v for v in found if v.lower() != "unreleased"]
        return _fail(
            "%s has no section for %s, so this release would have no notes. "
            "Add the section before tagging. Sections present: %s"
            % (args.changelog.name, version, ", ".join(released) or "none")
        )

    suffix, body = found[version]
    if not body.strip():
        return _fail("%s's section for %s is empty." % (args.changelog.name, version))

    _emit((title_for(version, suffix) if args.title else body) + "\n", args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
