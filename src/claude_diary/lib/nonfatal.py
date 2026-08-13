"""Swallowing a failure is a choice. Swallowing a bug is an accident.

Several places in this tool run something that must not be allowed to break
its caller — a summary printed after rows are already in Notion, a lookup that
only decorates the output. The shape is always the same:

    try:
        side_report()
    except Exception as e:
        logger.debug("... skipped: %s", e)

The intent is right and the net is too wide. In 4.9.0 the drift summary was
called with a name that only existed on the ``--force`` path; every ordinary
push raised ``NameError`` into that handler, which logs at a level nobody
runs at. The feature shipped, ran zero times, and said nothing for a day.

``NameError`` is the discriminator, and it is the only one worth treating this
way. A dead network, a changed Notion payload, a malformed file — those arrive
as ``OSError``, ``KeyError``, ``TypeError``, ``ValueError``, and every one of
them is a real runtime condition that this pattern exists to absorb. A name
that does not resolve is never data. It is always a defect in this program,
and it will still be there on the next run.

So ``NameError`` (and ``UnboundLocalError``, which subclasses it) gets a line
on stderr that names itself as a bug, and everything else keeps the quiet
debug log it had. The caller is not interrupted either way: the report the
guard protects has already done its work by the time this runs, and turning a
completed command into a failed one is the outcome the broad handler was
written to prevent.
"""

import sys
from contextlib import contextmanager

from claude_diary.log import get_logger

logger = get_logger("claude_diary.lib.nonfatal")


def _say(line):
    """Put one line on stderr, whatever stderr happens to be able to encode.

    This runs inside an exception handler, which is the one place a failure
    has nowhere left to go: an unencodable character here turns a bug report
    into a crash, and a crash is exactly what the guard promised not to do.
    It takes a Korean name in the message and a cp949 console to get there,
    and in this project both are the default.
    """
    try:
        print(line, file=sys.stderr)
        return
    except Exception:
        pass
    try:
        enc = getattr(sys.stderr, "encoding", None) or "ascii"
        print(line.encode(enc, "replace").decode(enc, "replace"), file=sys.stderr)
    except Exception:
        # Nothing is left to report with. Losing the notice beats raising.
        logger.debug("could not report a defect on stderr: %s", line[:200])


@contextmanager
def non_fatal(what, prefix=""):
    """Run a block that must not break its caller, but must not vanish either.

    ``what`` names the thing being attempted, in the user's terms — it is
    printed, so "drift summary" rather than "print_project_drift".

    ``prefix`` is the command's own output prefix, so the line lands in the
    same column as everything else the command printed.
    """
    try:
        yield
    except NameError as e:
        # Not "skipped". A name that does not resolve means this code has
        # never run here, so saying so plainly is the whole point.
        head = "%s%s" % (prefix + " " if prefix else "", "BUG:")
        _say("%s %s failed with %s: %s" % (head, what, type(e).__name__, e))
        _say("%s   a defect in agent-diary, not in your data - "
             "the command itself completed" % (prefix or " "))
        logger.debug("%s failed: %r", what, e)
    except Exception as e:
        logger.debug("%s skipped: %s", what, e)
