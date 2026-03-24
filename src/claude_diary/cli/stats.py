"""Stats and weekly report commands."""

import os
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path

import claude_diary.cli as _cli


def cmd_stats(args):
    config = _cli.load_config()
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
        stats = _cli.parse_daily_file(filepath)

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


def cmd_weekly(args):
    config = _cli.load_config()
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
        stats = _cli.parse_daily_file(filepath)
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
