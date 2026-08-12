"""Conventional Commit subjects — the one place that decides what a type is.

Two callers want the type of a commit for different reasons: the formatter
picks a gitmoji for the commit line, and the stats command counts work by
type. They were going to grow their own copy of this regex, and a commit
message that one of them recognised and the other did not would show up as a
diary line and a statistic that disagree.

This lives under `lib/` rather than in `formatter.py`, where the regex started,
because `lib/` is what the rest of the package imports from and not the other
way round.
"""

import re

# `type(scope)!: subject` — scope and the breaking-change bang are optional.
_CONVENTIONAL = re.compile(r"^([a-z]+)(?:\([^)]*\))?!?:")


def commit_type(message):
    """Return the Conventional Commit type of a subject line, or "".

    Any lowercase word before the colon counts, not just the types in the
    specification. Measured across one real diary, `copy:`, `memory:`,
    `temp:`, `content:` and `blog:` are all in use and all deliberate; the
    tool has no standing to tell someone their prefix is not a real one.
    """
    text = (message or "").strip()
    if not text:
        return ""
    # A message that already leads with an emoji is left alone; `ai-commit`
    # and similar tools may have put one there.
    if not text[0].isascii():
        return ""
    match = _CONVENTIONAL.match(text)
    return match.group(1) if match else ""
