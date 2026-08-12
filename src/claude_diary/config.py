"""Configuration management with XDG standard paths."""

import copy
import json
import os
import sys
from pathlib import Path

DEFAULT_CONFIG = {
    "lang": "ko",
    "timezone_offset": 9,
    "diary_dir": os.path.join(os.path.expanduser("~"), "working-diary"),
    "manual_diary_dir": os.path.join(os.path.expanduser("~"), "working-diary", "manual"),
    "enrichment": {
        "git_info": True,
        "auto_category": True,
        "code_stats": True,
        "session_time": False,
    },
    "formatting": {
        # Prefix each commit line with the gitmoji for its Conventional Commit
        # type. Off by default: the diary is a permanent record and emoji in
        # it is a taste not everyone shares.
        "gitmoji": False,
    },
    "exporters": {},
    "custom_categories": {},
}


def get_config_dir():
    """Return XDG-standard config directory path.
    Linux/macOS: ~/.config/claude-diary/
    Windows: %APPDATA%/claude-diary/
    """
    if sys.platform == "win32":
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
    else:
        base = os.environ.get("XDG_CONFIG_HOME", os.path.join(os.path.expanduser("~"), ".config"))
    return os.path.join(base, "claude-diary")


def get_config_path():
    """Return full path to config.json."""
    return os.path.join(get_config_dir(), "config.json")


def load_config():
    """Load config from config.json, falling back to environment variables.
    Priority: config.json > environment variables > defaults.
    """
    # Deep, not shallow: `_deep_merge` writes into the nested dicts it is
    # given, and a shallow copy hands it the module-level defaults themselves.
    # One config.json with `enrichment.git_info: false` in it permanently
    # changed what "default" meant for the rest of the process.
    config = copy.deepcopy(DEFAULT_CONFIG)

    # 1. Environment variables (lowest priority override)
    env_lang = os.environ.get("CLAUDE_DIARY_LANG")
    if env_lang:
        config["lang"] = env_lang.lower()

    env_dir = os.environ.get("CLAUDE_DIARY_DIR")
    if env_dir:
        config["diary_dir"] = os.path.expanduser(env_dir)

    env_manual_dir = os.environ.get("CLAUDE_DIARY_MANUAL_DIR")
    if env_manual_dir:
        config["manual_diary_dir"] = os.path.expanduser(env_manual_dir)

    env_tz = os.environ.get("CLAUDE_DIARY_TZ_OFFSET")
    if env_tz:
        try:
            config["timezone_offset"] = int(env_tz)
        except ValueError:
            pass

    # 2. config.json (highest priority — overrides env vars)
    config_path = get_config_path()
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                file_config = json.load(f)
        except (json.JSONDecodeError, IOError, UnicodeDecodeError, ValueError) as e:
            # Falling back to defaults silently meant a corrupt file turned
            # exporters off and moved a custom diary_dir back to the default
            # with nothing said about it. The diary kept being written, just
            # somewhere else and without the exports.
            _logger().warning(
                "%s is unreadable (%s); using defaults. "
                "Custom diary_dir and exporters are NOT in effect.",
                config_path, e,
            )
            file_config = {}

        if not isinstance(file_config, dict):
            _logger().warning(
                "%s does not contain a JSON object; using defaults.", config_path
            )
            file_config = {}

        # Check before merging, and drop the bad keys rather than substituting
        # defaults for them. A wrong type in the file is the file's layer
        # failing; the layers underneath it — the environment variables, then
        # the defaults — are still good and should be what shows through.
        # Substituting afterwards overrode a perfectly valid CLAUDE_DIARY_DIR
        # with the default path.
        _drop_wrong_types(file_config, config_path)
        _deep_merge(config, file_config)

    return config


def _logger():
    from claude_diary.log import get_logger
    return get_logger("claude_diary.config")


# Keys the pipeline uses without checking, and what they have to be. A wrong
# type here used to reach `os.path.expanduser(12345)` and `"yes".get(...)`,
# both outside the try that guards the write, so the Stop Hook exited 1 and
# the session went unrecorded — a typo in a config file costing an entry.
_EXPECTED_TYPES = {
    "lang": str,
    "timezone_offset": int,
    "diary_dir": str,
    "manual_diary_dir": str,
    "enrichment": dict,
    "formatting": dict,
    "exporters": dict,
    "custom_categories": dict,
    "security": dict,
}


def _drop_wrong_types(file_config, source):
    """Remove values whose type the pipeline cannot use, and say so."""
    for key, expected in _EXPECTED_TYPES.items():
        if key not in file_config:
            continue
        value = file_config[key]
        # bool is an int subclass, and a boolean timezone is not a timezone.
        if isinstance(value, expected) and not (expected is int and isinstance(value, bool)):
            continue
        _logger().warning(
            "%s: %s should be %s but is %s; ignoring it.",
            source, key, expected.__name__, type(value).__name__,
        )
        del file_config[key]


def save_config(config):
    """Save config to config.json. Sets file permission 600 on Unix."""
    config_dir = get_config_dir()
    Path(config_dir).mkdir(parents=True, exist_ok=True)

    config_path = get_config_path()
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

    # Unix: restrict permissions (owner only)
    if sys.platform != "win32":
        try:
            os.chmod(config_path, 0o600)
        except OSError:
            pass


def migrate_from_env():
    """Migrate v1.0 environment variables to config.json.
    Returns the migrated config.
    """
    config = load_config()
    save_config(config)
    return config


def _deep_merge(base, override):
    """Merge override dict into base dict (in-place, recursive)."""
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
