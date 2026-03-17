"""Team management — team config, member management, team CLI commands."""

import json
import os
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path

from claude_diary.config import load_config
from claude_diary.lib.stats import parse_daily_file


def load_team_config(team_repo_path):
    """Load .team-config.json from a team repo."""
    config_path = os.path.join(team_repo_path, ".team-config.json")
    if not os.path.exists(config_path):
        return None
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def get_team_repo_path(config=None):
    """Get the team repo local path from config."""
    if config is None:
        config = load_config()
    team = config.get("team", {})
    path = team.get("repo_path", "")
    return os.path.expanduser(path) if path else None


def init_team(repo_url, member_name=None):
    """Initialize team mode — clone repo and configure.

    Args:
        repo_url: Git clone URL for team diary repo
        member_name: Team member name (defaults to OS username)
    """
    config = load_config()

    if not member_name:
        member_name = os.environ.get("USER") or os.environ.get("USERNAME") or "unknown"

    # Clone team repo
    diary_dir = os.path.expanduser(config.get("diary_dir", "~/working-diary"))
    team_repo_path = os.path.join(diary_dir, ".team-repo")

    if os.path.exists(team_repo_path):
        print("  [ok] Team repo already exists: %s" % team_repo_path)
    else:
        print("  Cloning team repo...")
        try:
            result = subprocess.run(
                ["git", "clone", repo_url, team_repo_path],
                capture_output=True, text=True, timeout=60
            )
            if result.returncode != 0:
                print("  [error] Clone failed: %s" % result.stderr.strip())
                return False
            print("  [ok] Cloned: %s" % team_repo_path)
        except Exception as e:
            print("  [error] Clone failed: %s" % str(e))
            return False

    # Load team config
    team_config = load_team_config(team_repo_path)
    if team_config:
        print("  [ok] Team: %s" % team_config.get("team_name", "unknown"))
        print("  [ok] Members: %s" % ", ".join(team_config.get("members", [])))

        # Merge team security rules (team overrides personal, strengthen only)
        team_security = team_config.get("security", {})
        if team_security:
            if "security" not in config:
                config["security"] = {}
            # Merge mask_paths (additive)
            existing = set(config["security"].get("mask_paths", []))
            existing.update(team_security.get("mask_paths", []))
            config["security"]["mask_paths"] = sorted(existing)
            # Merge content_filters (additive)
            existing_filters = set(config["security"].get("content_filters", []))
            existing_filters.update(team_security.get("content_filters", []))
            config["security"]["content_filters"] = sorted(existing_filters)
            print("  [ok] Team security rules loaded")

    # Update personal config
    config.setdefault("team", {})
    config["team"]["repo_path"] = team_repo_path
    config["team"]["repo_url"] = repo_url
    config["team"]["member_name"] = member_name
    config["team"]["push_strategy"] = "auto"

    # Auto-enable GitHub exporter for team
    config.setdefault("exporters", {})
    config["exporters"]["github"] = {
        "enabled": True,
        "mode": "repo",
        "local_path": team_repo_path,
        "member_name": member_name,
    }

    from claude_diary.config import save_config
    save_config(config)
    print("  [ok] Config updated with team settings")

    # Create member directory
    member_dir = os.path.join(team_repo_path, "members", member_name)
    Path(member_dir).mkdir(parents=True, exist_ok=True)
    print("  [ok] Member directory: %s" % member_dir)

    return True


def team_stats(team_repo_path, month=None):
    """Generate team statistics from the team repo."""
    config = load_config()
    tz_offset = config.get("timezone_offset", 9)
    local_tz = timezone(timedelta(hours=tz_offset))
    now = datetime.now(local_tz)

    if month:
        year, mon = month.split("-")
        year, mon = int(year), int(mon)
    else:
        year, mon = now.year, now.month

    members_dir = os.path.join(team_repo_path, "members")
    if not os.path.isdir(members_dir):
        print("No members directory found in team repo.")
        return

    import calendar
    _, days_in_month = calendar.monthrange(year, mon)

    member_stats = {}
    all_projects = Counter()
    total_sessions = 0

    for member_name in sorted(os.listdir(members_dir)):
        member_path = os.path.join(members_dir, member_name)
        if not os.path.isdir(member_path):
            continue

        m_sessions = 0
        m_projects = Counter()
        m_categories = Counter()
        m_files = 0

        for day in range(1, days_in_month + 1):
            date_str = "%04d-%02d-%02d" % (year, mon, day)
            filepath = os.path.join(member_path, "%s.md" % date_str)
            stats = parse_daily_file(filepath)
            m_sessions += stats["sessions"]
            for p in stats["projects"]:
                m_projects[p] += stats["sessions"]
                all_projects[p] += stats["sessions"]
            for c in stats.get("categories", []):
                m_categories[c] += 1
            m_files += len(stats["files_modified"]) + len(stats["files_created"])

        if m_sessions > 0:
            member_stats[member_name] = {
                "sessions": m_sessions,
                "projects": m_projects,
                "categories": m_categories,
                "files": m_files,
            }
            total_sessions += m_sessions

    return {
        "total_sessions": total_sessions,
        "members": member_stats,
        "projects": all_projects,
        "month": "%04d-%02d" % (year, mon),
    }


def print_team_stats(stats_data):
    """Print team stats to terminal."""
    if not stats_data or not stats_data["members"]:
        print("No team activity found.")
        return

    month = stats_data["month"]
    total = stats_data["total_sessions"]
    members = stats_data["members"]
    projects = stats_data["projects"]

    print()
    width = 52
    print("+" + "=" * width + "+")
    print("|  Team Stats — %s%s|" % (month, " " * (width - 17 - len(month))))
    print("+" + "=" * width + "+")
    print()
    print("  Members: %d  |  Sessions: %d  |  Projects: %d" % (
        len(members), total, len(projects)
    ))
    print()

    if projects:
        print("  Projects:")
        max_count = max(projects.values())
        for proj, count in projects.most_common(10):
            bar_len = int(count / max_count * 16)
            bar = "+" * bar_len + " " * (16 - bar_len)
            # Show per-member breakdown
            breakdown = []
            for m, ms in members.items():
                mc = ms["projects"].get(proj, 0)
                if mc > 0:
                    breakdown.append("%s:%d" % (m, mc))
            bd_str = " (%s)" % " ".join(breakdown) if breakdown else ""
            print("  %-16s %s %d%s" % (proj, bar, count, bd_str))
        print()

    print("  Members:")
    max_sessions = max(m["sessions"] for m in members.values())
    for name, ms in sorted(members.items(), key=lambda x: -x[1]["sessions"]):
        bar_len = int(ms["sessions"] / max_sessions * 16)
        bar = "+" * bar_len + " " * (16 - bar_len)
        cats = " ".join("%s(%d)" % (c, n) for c, n in ms["categories"].most_common(3))
        print("  %-10s %s %d  %s" % (name, bar, ms["sessions"], cats))
    print()
    print("+" + "=" * width + "+")


def team_weekly_report(team_repo_path, target_date=None, lang="ko"):
    """Generate team weekly report."""
    config = load_config()
    tz_offset = config.get("timezone_offset", 9)
    local_tz = timezone(timedelta(hours=tz_offset))

    if target_date:
        from datetime import date as date_cls
        target = datetime.strptime(target_date, "%Y-%m-%d").date()
    else:
        target = datetime.now(local_tz).date()

    monday = target - timedelta(days=target.weekday())
    dates = [monday + timedelta(days=i) for i in range(7)]
    week_num = monday.isocalendar()[1]

    members_dir = os.path.join(team_repo_path, "members")
    if not os.path.isdir(members_dir):
        return None

    lines = []
    if lang == "ko":
        lines.append("# Team Weekly Report — W%d" % week_num)
    else:
        lines.append("# Team Weekly Report — W%d" % week_num)
    lines.append("### %s ~ %s" % (monday.strftime("%Y-%m-%d"), dates[-1].strftime("%Y-%m-%d")))
    lines.append("")

    total_sessions = 0
    member_summaries = {}

    for member_name in sorted(os.listdir(members_dir)):
        member_path = os.path.join(members_dir, member_name)
        if not os.path.isdir(member_path):
            continue

        m_sessions = 0
        m_tasks = []
        m_projects = set()
        m_categories = Counter()

        for date in dates:
            date_str = date.strftime("%Y-%m-%d")
            filepath = os.path.join(member_path, "%s.md" % date_str)
            stats = parse_daily_file(filepath)
            m_sessions += stats["sessions"]
            m_tasks.extend(stats["tasks"][:3])
            m_projects |= stats["projects"]
            for c in stats.get("categories", []):
                m_categories[c] += 1

        if m_sessions > 0:
            total_sessions += m_sessions
            member_summaries[member_name] = {
                "sessions": m_sessions,
                "tasks": m_tasks,
                "projects": m_projects,
                "categories": m_categories,
            }

    lines.append("| Item | Count |")
    lines.append("|------|-------|")
    lines.append("| Total Sessions | **%d** |" % total_sessions)
    lines.append("| Active Members | **%d** |" % len(member_summaries))
    lines.append("")

    for name, summary in member_summaries.items():
        cats = " ".join("%s(%d)" % (c, n) for c, n in summary["categories"].most_common(3))
        lines.append("### %s (%d sessions)" % (name, summary["sessions"]))
        lines.append("- Projects: %s" % ", ".join("`%s`" % p for p in summary["projects"]))
        if cats:
            lines.append("- Categories: %s" % cats)
        if summary["tasks"]:
            for t in summary["tasks"][:3]:
                lines.append("  - %s" % t)
        lines.append("")

    report = "\n".join(lines)

    # Save
    weekly_dir = os.path.join(team_repo_path, "weekly")
    Path(weekly_dir).mkdir(parents=True, exist_ok=True)
    filename = "team-W%02d_%s.md" % (week_num, monday.strftime("%Y-%m-%d"))
    filepath = os.path.join(weekly_dir, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(report)

    return report, filepath
