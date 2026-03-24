#!/usr/bin/env python
"""claude-diary CLI — search, filter, stats, and manage your work diary."""

import argparse
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path

from claude_diary.config import load_config, save_config, get_config_path, migrate_from_env
from claude_diary.i18n import get_label
from claude_diary.indexer import load_index
from claude_diary.lib.stats import parse_daily_file
from claude_diary.writer import ensure_diary_dir


def main():
    parser = argparse.ArgumentParser(
        prog="claude-diary",
        description="Auto-generated work diary from Claude Code sessions",
    )
    from claude_diary import __version__
    parser.add_argument("--version", action="version", version="claude-diary %s" % __version__)

    sub = parser.add_subparsers(dest="command")

    # search
    p_search = sub.add_parser("search", help="Search diary entries by keyword")
    p_search.add_argument("keyword", help="Keyword to search")
    p_search.add_argument("--project", "-p", help="Filter by project")
    p_search.add_argument("--category", "-c", help="Filter by category")
    p_search.add_argument("--from", dest="date_from", help="Start date (YYYY-MM-DD)")
    p_search.add_argument("--to", dest="date_to", help="End date (YYYY-MM-DD)")
    p_search.add_argument("--json", dest="json_output", action="store_true", help="Output as JSON")

    # filter
    p_filter = sub.add_parser("filter", help="Filter diary entries")
    p_filter.add_argument("--project", "-p", help="Filter by project")
    p_filter.add_argument("--category", "-c", help="Filter by category")
    p_filter.add_argument("--month", "-m", help="Filter by month (YYYY-MM)")
    p_filter.add_argument("--json", dest="json_output", action="store_true", help="Output as JSON")

    # trace
    p_trace = sub.add_parser("trace", help="Trace file change history")
    p_trace.add_argument("filepath", help="File path or glob pattern to trace")
    p_trace.add_argument("--project", "-p", help="Filter by project")

    # stats
    p_stats = sub.add_parser("stats", help="Show terminal dashboard")
    p_stats.add_argument("--month", "-m", help="Month (YYYY-MM)")
    p_stats.add_argument("--project", "-p", help="Filter by project")

    # weekly
    p_weekly = sub.add_parser("weekly", help="Generate weekly summary")
    p_weekly.add_argument("date", nargs="?", help="Any date in target week (YYYY-MM-DD)")

    # config
    p_config = sub.add_parser("config", help="View or update configuration")
    p_config.add_argument("--set", dest="set_value", help="Set config (key=value)")
    p_config.add_argument("--add-exporter", help="Add exporter (interactive)")

    # init
    p_init = sub.add_parser("init", help="Initialize claude-diary setup")
    p_init.add_argument("--team", dest="team_repo", help="Team repo URL for team mode")

    # migrate
    sub.add_parser("migrate", help="Migrate v1.0 env vars to config.json")

    # team
    p_team = sub.add_parser("team", help="Team management commands")
    p_team.add_argument("action", nargs="?", default="stats",
                        choices=["stats", "weekly", "monthly", "init", "add-member"],
                        help="Team action")
    p_team.add_argument("--project", "-p", help="Filter by project")
    p_team.add_argument("--member", help="Filter by member")
    p_team.add_argument("--month", "-m", help="Month (YYYY-MM)")
    p_team.add_argument("--repo", help="Team repo URL (for init)")
    p_team.add_argument("--name", help="Member name (for init/add-member)")
    p_team.add_argument("--role", default="member", help="Role (for add-member)")

    # reindex
    sub.add_parser("reindex", help="Rebuild search index")

    # audit
    p_audit = sub.add_parser("audit", help="View audit log and verify integrity")
    p_audit.add_argument("--days", type=int, help="Show entries from last N days")
    p_audit.add_argument("--verify", action="store_true", help="Verify source code checksum")
    p_audit.add_argument("-n", type=int, default=10, help="Number of entries (default: 10)")

    # delete
    p_delete = sub.add_parser("delete", help="Delete a diary session entry")
    p_delete.add_argument("--last", action="store_true", help="Delete the last session entry")
    p_delete.add_argument("--session", help="Delete by session ID prefix")

    # dashboard
    p_dashboard = sub.add_parser("dashboard", help="Generate HTML dashboard")
    p_dashboard.add_argument("--serve", action="store_true", help="Start local server")
    p_dashboard.add_argument("--port", type=int, default=8787, help="Server port (default: 8787)")
    p_dashboard.add_argument("--months", type=int, default=3, help="Months of data (default: 3)")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return

    commands = {
        "search": cmd_search,
        "filter": cmd_filter,
        "trace": cmd_trace,
        "stats": cmd_stats,
        "weekly": cmd_weekly,
        "config": cmd_config,
        "init": cmd_init,
        "migrate": cmd_migrate,
        "reindex": cmd_reindex,
        "team": cmd_team,
        "audit": cmd_audit,
        "delete": cmd_delete,
        "dashboard": cmd_dashboard,
    }

    fn = commands.get(args.command)
    if fn:
        fn(args)


# ── Search ──

def cmd_search(args):
    config = load_config()
    lang = config.get("lang", "ko")
    L = lambda key: get_label(key, lang)
    diary_dir = os.path.expanduser(config["diary_dir"])
    keyword = args.keyword.lower()

    index = load_index(diary_dir)
    entries = index.get("entries", [])

    # Auto-reindex if no index but diary files exist
    if not entries:
        diary_files = list(Path(diary_dir).glob("*.md"))
        if diary_files:
            print(L("cli_no_index"))
            from claude_diary.indexer import reindex_all
            reindex_all(diary_dir)
            index = load_index(diary_dir)
            entries = index.get("entries", [])

    if not entries:
        entries = _fallback_search_from_files(diary_dir, keyword)
        if not entries:
            print(L("cli_no_results") % args.keyword)
            return
        for e in entries:
            print("%s | %s | %s" % (e["date"], e["project"], e["line"]))
        return

    results = []
    for e in entries:
        # Date range filter
        if args.date_from and e["date"] < args.date_from:
            continue
        if args.date_to and e["date"] > args.date_to:
            continue
        # Project filter
        if args.project and args.project.lower() != e.get("project", "").lower():
            continue
        # Category filter
        if args.category and args.category.lower() not in [c.lower() for c in e.get("categories", [])]:
            continue
        # Keyword match
        searchable = " ".join(e.get("keywords", []) + e.get("files", []) + e.get("categories", []))
        if keyword in searchable.lower() or keyword in e.get("project", "").lower():
            results.append(e)

    if not results:
        print("No results found for '%s'" % args.keyword)
        return

    if getattr(args, 'json_output', False):
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return

    print(L("cli_found_entries") % len(results))
    print()
    for e in results:
        cats = ",".join(e.get("categories", [])) or "uncategorized"
        stats = ""
        if e.get("lines_added", 0) > 0 or e.get("lines_deleted", 0) > 0:
            stats = " | +%d/-%d" % (e["lines_added"], e["lines_deleted"])
        print("  %s %s | %-20s | %-12s%s" % (
            e["date"], e.get("time", "")[:5], e.get("project", ""), cats, stats
        ))


def _fallback_search_from_files(diary_dir, keyword):
    """Search directly from .md files when no index exists."""
    results = []
    for f in sorted(Path(diary_dir).glob("*.md")):
        try:
            content = f.read_text(encoding="utf-8")
        except Exception:
            continue
        for line in content.split("\n"):
            if keyword in line.lower():
                date = f.stem
                project = ""
                pm = re.search(r'📁 `([^`]+)`', content)
                if pm:
                    project = pm.group(1)
                results.append({"date": date, "project": project, "line": line.strip()[:100]})
                break
    return results


# ── Filter ──

def cmd_filter(args):
    config = load_config()
    lang = config.get("lang", "ko")
    diary_dir = os.path.expanduser(config["diary_dir"])
    index = load_index(diary_dir)
    entries = index.get("entries", [])

    if not entries:
        print("No index found. Run 'claude-diary reindex' first.")
        return

    results = []
    for e in entries:
        if args.project and args.project.lower() != e.get("project", "").lower():
            continue
        if args.category and args.category.lower() not in [c.lower() for c in e.get("categories", [])]:
            continue
        if args.month and not e["date"].startswith(args.month):
            continue
        results.append(e)

    if not results:
        print(get_label("cli_no_match", lang))
        return

    print(get_label("cli_found_entries", lang) % len(results))
    print()
    for e in results:
        cats = ",".join(e.get("categories", [])) or "-"
        print("  %s %s | %-20s | %s" % (
            e["date"], e.get("time", "")[:5], e.get("project", ""), cats
        ))


# ── Trace ──

def cmd_trace(args):
    config = load_config()
    diary_dir = os.path.expanduser(config["diary_dir"])
    index = load_index(diary_dir)
    entries = index.get("entries", [])
    target = args.filepath.lower().replace("\\", "/")

    results = []
    for e in entries:
        if args.project and args.project.lower() != e.get("project", "").lower():
            continue
        for f in e.get("files", []):
            if target in f.lower():
                results.append((e, f))
                break

    if not results:
        print("No history found for '%s'" % args.filepath)
        return

    print("File trace for '%s' (%d entries):" % (args.filepath, len(results)))
    print()
    for e, f in results:
        cats = ",".join(e.get("categories", [])) or "-"
        print("  %s | %-20s | %-12s | %s" % (e["date"], e.get("project", ""), cats, f))


# ── Stats ──

def cmd_stats(args):
    config = load_config()
    diary_dir = os.path.expanduser(config["diary_dir"])
    tz_offset = config.get("timezone_offset", 9)
    local_tz = timezone(timedelta(hours=tz_offset))

    # Determine date range
    if args.month:
        try:
            year, month = args.month.split("-")
            year, month = int(year), int(month)
            if not (1 <= month <= 12):
                print("Invalid month: %s (use YYYY-MM, month 1-12)" % args.month)
                return
        except (ValueError, TypeError):
            print("Invalid month format: %s (use YYYY-MM)" % args.month)
            return
    else:
        now = datetime.now(local_tz)
        year, month = now.year, now.month

    # Collect stats for the month
    import calendar
    _, days_in_month = calendar.monthrange(year, month)

    total_sessions = 0
    all_projects = Counter()
    all_categories = Counter()
    daily_sessions = {}
    total_files_created = 0
    total_files_modified = 0

    for day in range(1, days_in_month + 1):
        date_str = "%04d-%02d-%02d" % (year, month, day)
        filepath = os.path.join(diary_dir, "%s.md" % date_str)
        stats = parse_daily_file(filepath)

        sessions = stats["sessions"]
        if args.project:
            if args.project not in stats["projects"]:
                continue

        total_sessions += sessions
        daily_sessions[day] = sessions
        for p in stats["projects"]:
            all_projects[p] += sessions
        for c in stats.get("categories", []):
            all_categories[c] += 1
        total_files_created += len(stats["files_created"])
        total_files_modified += len(stats["files_modified"])

    # Render terminal dashboard
    month_str = "%04d-%02d" % (year, month)
    print()
    _print_box_top("Working Diary Stats — %s" % month_str)
    print()
    print("  Sessions: %d  |  Projects: %d  |  Created: %d  |  Modified: %d" % (
        total_sessions, len(all_projects), total_files_created, total_files_modified
    ))
    print()

    if all_projects:
        print("  Projects:")
        max_count = max(all_projects.values()) if all_projects else 1
        for proj, count in all_projects.most_common(10):
            bar_len = int(count / max_count * 16)
            bar = "█" * bar_len + "░" * (16 - bar_len)
            print("  %-20s %s %d" % (proj, bar, count))
        print()

    if all_categories:
        print("  Categories:")
        for cat, count in all_categories.most_common(10):
            print("  %-12s %d" % (cat, count))
        print()

    # Daily activity
    weekdays = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]
    print("  Daily:")
    week_line = "  "
    for day in range(1, days_in_month + 1):
        s = daily_sessions.get(day, 0)
        if s == 0:
            week_line += "·"
        elif s < 3:
            week_line += "░"
        elif s < 6:
            week_line += "▓"
        else:
            week_line += "█"
    print(week_line)
    print()
    _print_box_bottom()


def _get_terminal_width():
    """Get terminal width, defaulting to 52."""
    try:
        import shutil
        return min(max(shutil.get_terminal_size().columns - 2, 40), 100)
    except Exception:
        return 52


def _print_box_top(title):
    width = _get_terminal_width()
    print("╔" + "═" * width + "╗")
    print("║  📊 %-*s║" % (width - 4, title))
    print("╠" + "═" * width + "╣")


def _print_box_bottom():
    print("╚" + "═" * _get_terminal_width() + "╝")


# ── Weekly ──

def cmd_weekly(args):
    config = load_config()
    diary_dir = os.path.expanduser(config["diary_dir"])
    lang = config.get("lang", "ko")
    tz_offset = config.get("timezone_offset", 9)
    local_tz = timezone(timedelta(hours=tz_offset))

    if args.date:
        try:
            target = datetime.strptime(args.date, "%Y-%m-%d").date()
        except ValueError:
            print("Invalid date format: %s (use YYYY-MM-DD)" % args.date)
            return
    else:
        target = datetime.now(local_tz).date()

    # Calculate week range
    monday = target - timedelta(days=target.weekday())
    dates = [monday + timedelta(days=i) for i in range(7)]
    sunday = dates[-1]
    week_num = monday.isocalendar()[1]

    weekday_names_ko = ["월", "화", "수", "목", "금", "토", "일"]
    weekday_names_en = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    weekday_names = weekday_names_ko if lang == "ko" else weekday_names_en

    total_sessions = 0
    all_projects = set()
    all_tasks = []
    daily_stats = []

    for i, date in enumerate(dates):
        date_str = date.strftime("%Y-%m-%d")
        filepath = os.path.join(diary_dir, "%s.md" % date_str)
        stats = parse_daily_file(filepath)
        total_sessions += stats["sessions"]
        all_projects |= stats["projects"]
        all_tasks.extend(stats["tasks"])
        daily_stats.append({"date": date_str, "weekday": weekday_names[i], "stats": stats})

    # Generate and save report
    week_str = "%s ~ %s" % (monday.strftime("%Y-%m-%d"), sunday.strftime("%Y-%m-%d"))

    lines = []
    if lang == "ko":
        lines.append("# 📊 주간 작업 리포트 — W%d" % week_num)
    else:
        lines.append("# 📊 Weekly Work Report — W%d" % week_num)
    lines.append("### %s" % week_str)
    lines.append("")
    lines.append("| %s | %s |" % (
        "항목" if lang == "ko" else "Item",
        "수치" if lang == "ko" else "Count"
    ))
    lines.append("|------|------|")
    lines.append("| %s | **%d** |" % ("총 세션" if lang == "ko" else "Total Sessions", total_sessions))
    active = sum(1 for d in daily_stats if d["stats"]["sessions"] > 0)
    lines.append("| %s | **%d** / 7 |" % ("활동일" if lang == "ko" else "Active Days", active))
    lines.append("| %s | **%d** |" % ("프로젝트" if lang == "ko" else "Projects", len(all_projects)))
    lines.append("")

    for ds in daily_stats:
        s = ds["stats"]["sessions"]
        if s == 0:
            lines.append("### %s (%s) — _%s_" % (
                ds["weekday"], ds["date"],
                "활동 없음" if lang == "ko" else "No activity"
            ))
        else:
            lines.append("### %s (%s) — %d%s" % (
                ds["weekday"], ds["date"], s,
                "회 세션" if lang == "ko" else " sessions"
            ))
            if ds["stats"]["tasks"]:
                for t in ds["stats"]["tasks"][:3]:
                    lines.append("  - %s" % t)
        lines.append("")

    report = "\n".join(lines)

    # Save
    weekly_dir = os.path.join(diary_dir, "weekly")
    Path(weekly_dir).mkdir(parents=True, exist_ok=True)
    filename = "W%02d_%s.md" % (week_num, monday.strftime("%Y-%m-%d"))
    filepath = os.path.join(weekly_dir, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(report)

    print(report)
    print("---")
    print("Saved: %s" % filepath)


# ── Config ──

def cmd_config(args):
    config = load_config()

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
        save_config(config)
        print("Set %s = %s" % (key, value))
        return

    # Display current config
    print("Config path: %s" % get_config_path())
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

    save_config(config)
    print("Exporter '%s' added and enabled." % name)


# ── Init ──

def cmd_init(args):
    config = load_config()
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
    ensure_diary_dir(diary_dir)
    print("  [ok] Diary directory: %s" % diary_dir)

    # Save config
    save_config(config)
    print("  [ok] Config: %s" % get_config_path())

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


# ── Migrate ──

def cmd_migrate(args):
    print("Migrating v1.0 environment variables to config.json...")
    config = migrate_from_env()
    print("  lang: %s" % config["lang"])
    print("  diary_dir: %s" % config["diary_dir"])
    print("  timezone_offset: %s" % config["timezone_offset"])
    print()
    print("Config saved: %s" % get_config_path())
    print("Note: Environment variables still work as fallback.")


# ── Reindex ──

def cmd_reindex(args):
    from claude_diary.indexer import reindex_all
    config = load_config()
    diary_dir = os.path.expanduser(config["diary_dir"])

    print("Rebuilding search index...")
    count = reindex_all(diary_dir)
    index_path = os.path.join(diary_dir, ".diary_index.json")
    print("Indexed %d sessions." % count)
    print("Index: %s" % index_path)


# ── Team ──

def cmd_team(args):
    from claude_diary.team import (
        init_team, get_team_repo_path, team_stats,
        print_team_stats, team_weekly_report
    )

    if args.action == "init":
        repo_url = args.repo
        if not repo_url:
            repo_url = input("Team repo URL: ").strip()
        name = args.name
        if not name:
            name = input("Your name: ").strip()
        print("Initializing team mode...")
        init_team(repo_url, name)
        print("\nDone! Sessions will auto-push to team repo.")
        return

    config = load_config()
    repo_path = get_team_repo_path(config)
    if not repo_path or not os.path.isdir(repo_path):
        print("Team not configured. Run: claude-diary team init --repo <url>")
        return

    if args.action == "stats":
        data = team_stats(repo_path, month=args.month)
        print_team_stats(data)

    elif args.action in ("weekly", "monthly"):
        lang = config.get("lang", "ko")
        result = team_weekly_report(repo_path, lang=lang)
        if result:
            report, filepath = result
            print(report)
            print("---")
            print("Saved: %s" % filepath)
        else:
            print("No team data found.")

    elif args.action == "add-member":
        from claude_diary.team import validate_member_name
        name = args.name or input("Member name: ").strip()
        try:
            validate_member_name(name)
        except ValueError as e:
            print(str(e))
            return
        role = args.role
        team_config_path = os.path.join(repo_path, ".team-config.json")
        tc = {}
        if os.path.exists(team_config_path):
            with open(team_config_path, "r") as f:
                tc = json.load(f)
        tc.setdefault("members", [])
        tc.setdefault("roles", {})
        if name not in tc["members"]:
            tc["members"].append(name)
        tc["roles"][name] = role
        with open(team_config_path, "w") as f:
            json.dump(tc, f, indent=2, ensure_ascii=False)
        # Create member dir
        Path(os.path.join(repo_path, "members", name)).mkdir(parents=True, exist_ok=True)
        print("Added member '%s' with role '%s'" % (name, role))


# ── Audit ──

def cmd_audit(args):
    from claude_diary.lib.audit import read_audit_log, verify_checksum
    config = load_config()
    diary_dir = os.path.expanduser(config["diary_dir"])

    if args.verify:
        is_valid, current, last = verify_checksum(diary_dir)
        if is_valid:
            print("Checksum OK: %s" % current)
        else:
            print("WARNING: Checksum mismatch!")
            print("  Current:  %s" % current)
            print("  Last log: %s" % last)
            print("  Source files may have been modified since last Hook execution.")
        return

    entries = read_audit_log(diary_dir, days=args.days, limit=args.n)

    if not entries:
        print("No audit log entries found.")
        return

    print("Audit log (%d entries):" % len(entries))
    print()
    for e in entries:
        ts = e.get("timestamp", "")[:19]
        sid = e.get("session_id", "")[:8]
        masked = e.get("secrets_masked", 0)
        written = len(e.get("files_written", []))
        exporters = e.get("exporters_called", [])
        failed = e.get("exporters_failed", [])

        line = "  %s | session:%s | wrote:%d" % (ts, sid, written)
        if masked > 0:
            line += " | secrets_masked:%d" % masked
        if exporters:
            line += " | exporters:%s" % ",".join(exporters)
        if failed:
            line += " | FAILED:%s" % ",".join(failed)
        print(line)


# ── Delete ──

def cmd_delete(args):
    config = load_config()
    diary_dir = os.path.expanduser(config["diary_dir"])
    tz_offset = config.get("timezone_offset", 9)
    local_tz = timezone(timedelta(hours=tz_offset))

    if args.last:
        today = datetime.now(local_tz).strftime("%Y-%m-%d")
        filepath = os.path.join(diary_dir, "%s.md" % today)
        if not os.path.exists(filepath):
            print("No diary file for today (%s)" % today)
            return

        # Confirmation prompt
        confirm = input("Delete last session entry from %s? [y/N]: " % today).strip().lower()
        if confirm not in ("y", "yes"):
            print("Cancelled.")
            return

        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        # Split by session markers and remove last
        parts = content.split("### ⏰")
        if len(parts) <= 1:
            print("No session entries found in today's diary.")
            return

        # Remove last entry (everything after last "### ⏰")
        new_content = "### ⏰".join(parts[:-1])
        # Remove trailing "---\n\n" if present
        new_content = new_content.rstrip()
        if new_content.endswith("---"):
            new_content = new_content[:-3].rstrip()
        new_content += "\n\n"

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(new_content)

        print("Last session entry deleted from %s" % filepath)
        return

    if args.session:
        # Search all files for session ID and remove that entry
        found = False
        for f in sorted(Path(diary_dir).glob("*.md")):
            try:
                content = f.read_text(encoding="utf-8")
            except Exception:
                continue
            if args.session in content:
                parts = content.split("### ⏰")
                new_parts = [parts[0]]
                for part in parts[1:]:
                    if args.session not in part:
                        new_parts.append(part)
                    else:
                        found = True
                new_content = "### ⏰".join(new_parts).rstrip() + "\n"
                f.write_text(new_content, encoding="utf-8")
                print("Session %s deleted from %s" % (args.session, f.name))
                break

        if not found:
            print("Session '%s' not found." % args.session)
        return

    print("Specify --last or --session <id>")


# ── Dashboard ──

def cmd_dashboard(args):
    from claude_diary.dashboard import generate_dashboard, serve_dashboard
    config = load_config()
    diary_dir = os.path.expanduser(config["diary_dir"])

    path = generate_dashboard(diary_dir, months=args.months)
    print("Dashboard generated: %s" % path)

    if args.serve:
        serve_dashboard(diary_dir, port=args.port)
    else:
        import webbrowser
        webbrowser.open("file://%s" % os.path.abspath(path))


if __name__ == "__main__":
    main()
