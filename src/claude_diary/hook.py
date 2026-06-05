#!/usr/bin/env python
"""Stop Hook entrypoint — thin wrapper called by Claude Code settings.json.

This script is registered in ~/.claude/settings.json as:
  "command": "python path/to/hook.py"

It reads session JSON from stdin and delegates to core.process_session().
"""

import os
import json
import sys

# Ensure the package is importable when running as a standalone script
_script_dir = os.path.dirname(os.path.abspath(__file__))
_src_dir = os.path.dirname(_script_dir)
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from claude_diary.core import process_session
from claude_diary.log import get_logger

logger = get_logger("claude_diary.hook")


def _configure_stdio():
    """Use UTF-8 for hook output without shell-specific env assignment."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass


def _load_stdin_json():
    stream = sys.stdin
    buffer = getattr(stream, "buffer", None)
    if buffer is not None:
        raw = buffer.read()
        text = raw.decode("utf-8-sig", errors="replace")
    else:
        text = stream.read()
    return json.loads(text)


def main():
    _configure_stdio()
    try:
        input_data = _load_stdin_json()
    except (json.JSONDecodeError, EOFError, ValueError):
        sys.exit(0)
    if not isinstance(input_data, dict):
        sys.exit(0)

    session_id = input_data.get("session_id", "unknown")
    transcript_path = input_data.get("transcript_path", "")
    cwd = input_data.get("cwd", "")

    # Validate inputs are strings
    if not isinstance(session_id, str):
        session_id = "unknown"
    if not isinstance(transcript_path, str):
        transcript_path = ""
    if not isinstance(cwd, str):
        cwd = ""

    try:
        process_session(session_id, transcript_path, cwd)
        sys.exit(0)
    except Exception as e:
        logger.error("Fatal error: %s", e)
        sys.exit(0)  # Never block Claude Code exit


if __name__ == "__main__":
    main()
