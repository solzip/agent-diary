"""Structured logging setup for claude-diary."""

import logging
import sys

_LOG_FORMAT = "[diary] %(message)s"
_configured = False


def get_logger(name):
    """Return a logger for the given module name.

    The first call configures the root 'claude_diary' logger with a stderr
    handler.  Subsequent calls just return child loggers.

    The default level is WARNING so hooks stay silent unless something goes
    wrong.  Users can override via ``log_level`` in config.json.
    """
    global _configured
    root = logging.getLogger("claude_diary")

    if not _configured:
        root.setLevel(logging.WARNING)
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter(_LOG_FORMAT))
        root.addHandler(handler)
        _configured = True

    return root if name == "claude_diary" else logging.getLogger(name)


def configure_from_config(config):
    """Apply ``log_level`` from config dict (if present).

    Accepts the string names recognised by :mod:`logging`:
    debug, info, warning, error, critical (case-insensitive).
    """
    level_str = config.get("log_level", "").upper()
    if level_str:
        numeric = getattr(logging, level_str, None)
        if isinstance(numeric, int):
            logging.getLogger("claude_diary").setLevel(numeric)
