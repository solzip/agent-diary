"""Install/uninstall commands — register claude-diary hook in Claude Code settings."""

import json
import os
import sys


HOOK_COMMAND = "PYTHONIOENCODING=utf-8 python -m claude_diary.hook"

HOOK_ENTRY = {
    "type": "command",
    "command": HOOK_COMMAND,
}

DIARY_SLASH_COMMAND = """\
---
description: 현재 세션 작업일지를 <manual_dir>/<date>/<project>/<date>.md 에 기록 (있으면 append)
allowed-tools:
  - Bash
---

!`claude-diary write`
"""


def _get_slash_command_path():
    """Return path to ~/.claude/commands/diary.md."""
    home = os.path.expanduser("~")
    return os.path.join(home, ".claude", "commands", "diary.md")


def _get_claude_settings_path():
    """Return path to ~/.claude/settings.json."""
    home = os.path.expanduser("~")
    return os.path.join(home, ".claude", "settings.json")


def _load_claude_settings(path):
    """Load existing settings or return empty dict."""
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {}


def _save_claude_settings(path, settings):
    """Save settings to file, creating directory if needed."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)
        f.write("\n")


def _is_diary_hook(hook):
    """Check if a hook entry is a claude-diary hook."""
    command = hook.get("command", "")
    return "claude_diary.hook" in command


def _find_existing_hook(settings):
    """Check if claude-diary hook is already registered.
    Returns True if found.
    """
    hooks = settings.get("hooks", {})
    stop_hooks = hooks.get("Stop", [])
    for group in stop_hooks:
        for hook in group.get("hooks", []):
            if _is_diary_hook(hook):
                return True
    return False


def cmd_install(args):
    """Register claude-diary Stop hook + /diary slash command."""
    settings_path = _get_claude_settings_path()
    settings = _load_claude_settings(settings_path)

    if _find_existing_hook(settings):
        hook_status = "already installed"
    else:
        if "hooks" not in settings:
            settings["hooks"] = {}
        if "Stop" not in settings["hooks"]:
            settings["hooks"]["Stop"] = []
        settings["hooks"]["Stop"].append({"hooks": [HOOK_ENTRY]})
        _save_claude_settings(settings_path, settings)
        hook_status = "installed"

    # Slash command install runs unconditionally — fixes upgrade path for
    # users who installed before /diary was a feature.
    slash_path = _get_slash_command_path()
    slash_status = _install_slash_command(slash_path)

    print("claude-diary install:")
    print("  Hook: %s (%s)" % (HOOK_COMMAND, hook_status))
    print("  Settings: %s" % settings_path)
    print("  Slash command: %s (%s)" % (slash_path, slash_status))
    print()
    print("Stop Hook auto-writes a diary entry on session exit.")
    print("Type /diary inside any session to write a manual entry on demand.")


def _install_slash_command(path):
    """Create ~/.claude/commands/diary.md if missing.

    Returns 'installed', 'already exists', or 'failed: <reason>'.
    """
    if os.path.exists(path):
        return "already exists"
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(DIARY_SLASH_COMMAND)
        return "installed"
    except OSError as e:
        return "failed: %s" % e


def _uninstall_slash_command(path):
    """Remove ~/.claude/commands/diary.md if it matches our content."""
    if not os.path.exists(path):
        return "not present"
    try:
        with open(path, "r", encoding="utf-8") as f:
            existing = f.read()
        if "claude-diary write" not in existing:
            return "skipped (modified by user)"
        os.remove(path)
        return "removed"
    except OSError as e:
        return "failed: %s" % e


def cmd_uninstall(args):
    """Remove claude-diary Stop hook from ~/.claude/settings.json."""
    settings_path = _get_claude_settings_path()
    settings = _load_claude_settings(settings_path)

    if not _find_existing_hook(settings):
        print("claude-diary hook is not installed.")
        return

    # Remove diary hooks
    stop_hooks = settings.get("hooks", {}).get("Stop", [])
    new_stop = []
    for group in stop_hooks:
        remaining = [h for h in group.get("hooks", []) if not _is_diary_hook(h)]
        if remaining:
            new_stop.append({"hooks": remaining})

    settings["hooks"]["Stop"] = new_stop

    # Clean up empty structures
    if not settings["hooks"]["Stop"]:
        del settings["hooks"]["Stop"]
    if not settings["hooks"]:
        del settings["hooks"]

    _save_claude_settings(settings_path, settings)

    slash_path = _get_slash_command_path()
    slash_status = _uninstall_slash_command(slash_path)

    print("claude-diary hook uninstalled.")
    print("  Settings: %s" % settings_path)
    print("  Slash command: %s (%s)" % (slash_path, slash_status))
