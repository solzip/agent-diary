"""Markdown formatter — converts entry_data to diary markdown."""

import os
from datetime import datetime, timezone, timedelta

from claude_diary.i18n import get_label


def format_entry(entry_data, lang="ko"):
    """Format entry_data into a markdown diary entry."""
    L = lambda key: get_label(key, lang)
    time = entry_data.get("time", "")
    project = entry_data.get("project", "unknown")

    lines = []
    lines.append("### ⏰ %s | 📁 `%s`" % (time, project))
    lines.append("")

    # Categories
    categories = entry_data.get("categories", [])
    if categories:
        cat_str = " ".join("`%s`" % c for c in categories)
        lines.append("**🏷️ %s:** %s" % (L("categories"), cat_str))
        lines.append("")

    # User prompts
    prompts = entry_data.get("user_prompts", [])
    if prompts:
        lines.append("**📋 %s:**" % L("task_requests"))
        for i, prompt in enumerate(prompts[:5], 1):
            short = prompt.replace("\n", " ").strip()
            if len(short) > 150:
                short = short[:150] + "..."
            lines.append("  %d. %s" % (i, short))
        lines.append("")

    # Files created
    created = entry_data.get("files_created", [])
    if created:
        lines.append("**📄 %s:**" % L("files_created"))
        for f in created[:15]:
            lines.append("  - `%s`" % f)
        lines.append("")

    # Files modified
    modified = entry_data.get("files_modified", [])
    if modified:
        lines.append("**✏️ %s:**" % L("files_modified"))
        for f in modified[:15]:
            lines.append("  - `%s`" % f)
        lines.append("")

    # Git info
    git_info = entry_data.get("git_info")
    if git_info:
        lines.append("**🔀 %s:**" % L("git"))
        branch = git_info.get("branch", "")
        if branch:
            lines.append("  - 🌿 %s: `%s`" % (L("branch"), branch))
        for commit in git_info.get("commits", [])[:5]:
            lines.append("  - %s: `%s` %s" % (L("commit"), commit["hash"], commit["message"]))
        lines.append("")

    # Code stats
    code_stats = entry_data.get("code_stats")
    if code_stats and (code_stats.get("added", 0) > 0 or code_stats.get("deleted", 0) > 0):
        added = code_stats.get("added", 0)
        deleted = code_stats.get("deleted", 0)
        files = code_stats.get("files", 0)
        lines.append("**📊 %s:** +%d / -%d lines (%d files)" % (L("code_stats"), added, deleted, files))
        lines.append("")

    # Commands
    commands = entry_data.get("commands_run", [])
    trivial = {"ls", "pwd", "cat", "echo", "cd", "which", "type", "clear"}
    significant = [c for c in commands if c.strip().split()[0] not in trivial][:10]
    if significant:
        lines.append("**⚡ %s:**" % L("commands"))
        for cmd in significant:
            short = cmd[:120] + ("..." if len(cmd) > 120 else "")
            lines.append("  - `%s`" % short)
        lines.append("")

    # Summary hints
    hints = entry_data.get("summary_hints", [])
    if hints:
        lines.append("**📝 %s:**" % L("summary"))
        for hint in hints[:5]:
            lines.append("  - %s" % hint)
        lines.append("")

    # Issues
    errors = entry_data.get("errors_encountered", [])
    if errors:
        lines.append("**⚠️ %s:**" % L("issues"))
        for err in errors[:3]:
            lines.append("  - %s" % err)
        lines.append("")

    # Secrets masked count
    masked = entry_data.get("secrets_masked", 0)
    if masked > 0:
        lines.append("**🔒 %d %s**" % (masked, L("secrets_masked")))
        lines.append("")

    # Session ID
    session_id = entry_data.get("session_id", "unknown")
    lines.append("<details><summary>%s: <code>%s...</code></summary>" % (L("session_id"), session_id[:8]))
    lines.append("<code>%s</code>" % session_id)
    lines.append("</details>")
    lines.append("")
    lines.append("---")
    lines.append("")

    return "\n".join(lines)


def format_daily_header(date_str, lang="ko"):
    """Create daily diary file header."""
    L = lambda key: get_label(key, lang)

    tz_offset = 9  # Will be overridden by config
    local_tz = timezone(timedelta(hours=tz_offset))
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        weekday_idx = dt.weekday()
    except ValueError:
        weekday_idx = 0

    weekdays = get_label("weekdays", lang)
    suffix = get_label("weekday_suffix", lang)
    weekday = weekdays[weekday_idx]
    weekday_label = "%s%s" % (weekday, suffix) if suffix else weekday

    title = L("title")
    auto1 = L("auto_generated")
    auto2 = L("auto_appended")

    return "# 📓 %s — %s (%s)\n\n> %s\n> %s\n\n---\n\n" % (
        title, date_str, weekday_label, auto1, auto2
    )
