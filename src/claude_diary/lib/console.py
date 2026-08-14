"""Printing must not be able to end the command.

A user on a Korean Windows console ran `diary-notion push --dry-run` and it
died before writing anything:

    UnicodeEncodeError: 'cp949' codec can't encode character '\\u2014'
      at notion_push/__init__.py, in cmd_notion_push -> print(preview)

cp949 encodes Hangul and `→` perfectly well. What it has no room for is the
punctuation and emoji this project writes everywhere: `—` (U+2014, it carries
U+2015 instead), `✓`, and the `⏰`/`📁` that every diary entry header is built
from. Measured across `src/`: **206 string literals contain a character cp949
cannot encode**, in 8+ modules — and that is before any diary content, which
carries the emoji by construction.

So wrapping the one `print` that was reported would have left 205 of them. The
fix belongs where the streams are set up, once, at every entry point.

`errors="replace"` rather than forcing UTF-8: on a legacy console the encoding
is what the terminal will actually render, and switching it to UTF-8 turns
correct Hangul into mojibake to save an em dash. Replacing gives the reverse
trade — the Korean stays readable and the dash becomes `?`. Anyone who wants
every character can still set `PYTHONIOENCODING=utf-8`, which is what the
reporter used to get past this.
"""

import sys


def make_output_unbreakable():
    """Stop `print` from raising on characters the console cannot encode.

    Idempotent, and a no-op where it is already safe: a stream that is already
    UTF-8, or one that pytest and friends have swapped for something without
    `reconfigure`, is left exactly as it was.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue  # replaced by a capture object; not ours to touch
        if (getattr(stream, "errors", None) or "") in ("replace", "backslashreplace"):
            continue
        encoding = (getattr(stream, "encoding", None) or "").lower().replace("-", "")
        if encoding in ("utf8", "utf8mb4"):
            continue  # nothing to lose, so nothing to do
        try:
            reconfigure(errors="replace")
        except (ValueError, OSError):
            # Detached or already closed. Losing the safety net beats raising
            # from the function whose whole job is to stop a raise.
            pass
