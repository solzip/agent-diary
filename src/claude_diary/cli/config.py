"""Config, init, and migrate commands."""

import json
import os
from pathlib import Path

import claude_diary.cli as _cli


def cmd_config(args):
    config = _cli.load_config()

    if args.add_exporter:
        _add_exporter_interactive(config, args.add_exporter)
        return

    if args.set_value:
        key, _, value = args.set_value.partition("=")
        key = key.strip()
        value = value.strip()
        if key == "lang":
            if value not in ("ko", "en"):
                print("Invalid lang: %s (use 'ko' or 'en')" % value)
                return
            config[key] = value
        elif key == "diary_dir":
            config[key] = value
        elif key == "timezone_offset":
            try:
                tz = int(value)
                if not (-12 <= tz <= 14):
                    print("Invalid timezone_offset: %s (range: -12 to 14)" % value)
                    return
                config[key] = tz
            except ValueError:
                print("Invalid timezone_offset: %s (must be integer)" % value)
                return
        else:
            print("Unknown config key: %s (available: lang, diary_dir, timezone_offset)" % key)
            return
        _cli.save_config(config)
        print("Set %s = %s" % (key, value))
        return

    # Display current config
    print("Config path: %s" % _cli.get_config_path())
    print()
    for key, value in sorted(config.items()):
        if key == "exporters":
            print("exporters:")
            for name, exp in value.items():
                enabled = exp.get("enabled", False)
                status = "enabled" if enabled else "disabled"
                details = []
                for k, v in exp.items():
                    if k == "enabled":
                        continue
                    if k in ("api_token", "token", "webhook_url") and isinstance(v, str) and len(v) > 8:
                        v = v[:4] + "..." + v[-4:]
                    details.append("%s=%s" % (k, v))
                detail_str = " (%s)" % ", ".join(details) if details else ""
                print("  %s: %s%s" % (name, status, detail_str))
        elif isinstance(value, dict):
            print("%s: %s" % (key, json.dumps(value, ensure_ascii=False)))
        else:
            print("%s: %s" % (key, value))


def _add_exporter_interactive(config, name):
    if "exporters" not in config:
        config["exporters"] = {}

    if name == "notion":
        token = input("Notion API token: ").strip()
        db_id = input("Notion Database ID: ").strip()
        config["exporters"]["notion"] = {
            "enabled": True,
            "api_token": token,
            "database_id": db_id,
        }
    elif name in ("slack", "discord"):
        url = input("%s Webhook URL: " % name.capitalize()).strip()
        config["exporters"][name] = {"enabled": True, "webhook_url": url}
    elif name == "obsidian":
        path = input("Obsidian vault path: ").strip()
        config["exporters"]["obsidian"] = {"enabled": True, "vault_path": path}
    elif name == "github":
        repo = input("GitHub repo (owner/repo): ").strip()
        mode = input("Mode (repo/wiki/issue) [repo]: ").strip() or "repo"
        config["exporters"]["github"] = {"enabled": True, "repo": repo, "mode": mode}
    else:
        print("Unknown exporter: %s" % name)
        return

    _cli.save_config(config)
    print("Exporter '%s' added and enabled." % name)


def cmd_init(args):
    config = _cli.load_config()
    diary_dir = os.path.expanduser(config["diary_dir"])

    # Team mode init
    if hasattr(args, 'team_repo') and args.team_repo:
        from claude_diary.team import init_team
        print("Initializing claude-diary (team mode)...")
        print()
        init_team(args.team_repo)
        return

    print("Initializing claude-diary...")
    print()

    # Create diary directory
    _cli.ensure_diary_dir(diary_dir)
    print("  [ok] Diary directory: %s" % diary_dir)

    # Save config
    _cli.save_config(config)
    print("  [ok] Config: %s" % _cli.get_config_path())

    # Register Stop Hook
    claude_settings = os.path.join(os.path.expanduser("~"), ".claude", "settings.json")
    if os.path.exists(claude_settings):
        try:
            with open(claude_settings, "r", encoding="utf-8") as f:
                settings = json.load(f)
        except (json.JSONDecodeError, IOError, ValueError):
            settings = {}

        if "hooks" not in settings:
            settings["hooks"] = {}
        if "Stop" not in settings["hooks"]:
            settings["hooks"]["Stop"] = []

        # Check if already registered
        already = False
        for group in settings["hooks"]["Stop"]:
            for h in group.get("hooks", []):
                if "hook.py" in h.get("command", "") or "claude_diary" in h.get("command", ""):
                    already = True
                    break

        if not already:
            hook_cmd = "python -m claude_diary.hook"
            settings["hooks"]["Stop"].append({
                "hooks": [{"type": "command", "command": hook_cmd}]
            })
            with open(claude_settings, "w", encoding="utf-8") as f:
                json.dump(settings, f, indent=2, ensure_ascii=False)
            print("  [ok] Stop Hook registered: %s" % hook_cmd)
        else:
            print("  [ok] Stop Hook already registered")
    else:
        # Create settings.json with hook registration
        claude_dir = os.path.join(os.path.expanduser("~"), ".claude")
        Path(claude_dir).mkdir(parents=True, exist_ok=True)
        hook_cmd = "python -m claude_diary.hook"
        settings = {
            "hooks": {
                "Stop": [{"hooks": [{"type": "command", "command": hook_cmd}]}]
            }
        }
        with open(claude_settings, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)
        print("  [ok] Created %s with Stop Hook" % claude_settings)

    print()
    print("Done! Claude Code sessions will be auto-logged.")
    print("  View diary: cat %s/$(date +%%Y-%%m-%%d).md" % diary_dir)


def cmd_migrate(args):
    print("Migrating v1.0 environment variables to config.json...")
    config = _cli.migrate_from_env()
    print("  lang: %s" % config["lang"])
    print("  diary_dir: %s" % config["diary_dir"])
    print("  timezone_offset: %s" % config["timezone_offset"])
    print()
    print("Config saved: %s" % _cli.get_config_path())
    print("Note: Environment variables still work as fallback.")
