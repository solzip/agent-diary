"""Configuration management with XDG standard paths."""

import json
import os
import sys
from pathlib import Path

DEFAULT_CONFIG = {
    "lang": "ko",
    "timezone_offset": 9,
    "diary_dir": os.path.join(os.path.expanduser("~"), "working-diary"),
    "enrichment": {
        "git_info": True,
        "auto_category": True,
        "code_stats": True,
        "session_time": False,
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
    config = dict(DEFAULT_CONFIG)

    # 1. Environment variables (lowest priority override)
    env_lang = os.environ.get("CLAUDE_DIARY_LANG")
    if env_lang:
        config["lang"] = env_lang.lower()

    env_dir = os.environ.get("CLAUDE_DIARY_DIR")
    if env_dir:
        config["diary_dir"] = os.path.expanduser(env_dir)

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
            _deep_merge(config, file_config)
        except (json.JSONDecodeError, IOError):
            pass

    return config


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
