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

The stream keeps its own encoding rather than being forced to UTF-8: on a
legacy console that encoding is what the terminal will actually render, and
switching it turns correct Hangul into mojibake to save an em dash. Anyone who
wants every character can still set `PYTHONIOENCODING=utf-8`, which is what the
reporter used to get past this.

What changed after that first fix is *what* is drawn in place of the missing
character. `errors="replace"` stopped the crash but printed `?`, and `stats`
draws its charts out of block elements — so every bar became a row of question
marks, which reads as a broken program rather than as a chart. The encoding
error handler below substitutes the nearest ASCII instead: `█` becomes `#`,
`╔═╗` becomes `+=+`, an em dash becomes a hyphen.
"""

import codecs
import sys

#: What to draw instead, when the console cannot draw the real thing.
#:
#: Every entry is the same length as the character it replaces. `stats` draws
#: boxes and bars by counting characters, so a substitution that changes the
#: count moves the right border and turns a chart into a ragged one. A
#: single-character emoji is doubly wide in most terminals, so a one-character
#: ASCII stand-in is if anything better aligned than the original.
#:
#: Anything not listed falls back to `*` rather than `?`: these are decoration,
#: and a question mark reads as something having gone wrong.
_ASCII_FOR = {
    # bars and shading — the reason this exists. `stats` drew its charts in
    # block elements, and on cp949 every bar came out as a row of `?`.
    "█": "#", "▓": "+", "░": "-",
    # box drawing
    "═": "=", "║": "|",
    "╔": "+", "╗": "+", "╚": "+", "╝": "+", "╠": "+", "╣": "+",
    # punctuation this project uses in prose. cp949 carries U+2015 but not the
    # em dash, which is what the original bug report tripped over.
    "—": "-", "–": "-", "⋯": "~",
    # status marks
    "✓": "v", "✅": "v", "✗": "x", "❌": "x",
}


ERROR_HANDLER = "agent_diary_ascii"


def _substitute(error):
    """Encoding error handler: draw the nearest ASCII rather than `?`.

    Registered on the stream itself instead of wrapping call sites. There are
    29 `print` calls in `stats` alone and diary content reaches the terminal
    from half a dozen other commands, all of it carrying the `⏰`/`📁` that
    every entry header is built from. One handler covers every one of them,
    including the ones written after this.

    Only the terminal is affected. Files are opened with their own encoding —
    `weekly` writes its report in UTF-8 and then prints it, and only the
    printed copy passes through here.
    """
    chunk = error.object[error.start:error.end]
    return ("".join(_ASCII_FOR.get(char, "*") for char in chunk), error.end)


codecs.register_error(ERROR_HANDLER, _substitute)


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
        if (getattr(stream, "errors", None) or "") == ERROR_HANDLER:
            continue
        encoding = (getattr(stream, "encoding", None) or "").lower().replace("-", "")
        if encoding in ("utf8", "utf8mb4"):
            continue  # nothing to lose, so nothing to do
        try:
            reconfigure(errors=ERROR_HANDLER)
        except (ValueError, OSError):
            # Detached or already closed. Losing the safety net beats raising
            # from the function whose whole job is to stop a raise.
            pass
