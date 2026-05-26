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


def build_notion_blocks(task, git_info=None, lang="ko"):
    """Build Notion API block list for a task page body.

    Body layout:
      [body_intro paragraph]
      ## 사용자 요청   - prompts
      ## 수정/생성 파일 - files (modified + created)
      ## 실행한 명령    - commands (trivial filtered out)
      ## Git 변경사항   - branch, commits, lines
      ## 발생한 에러    - errors (only if any)

    Skipped sections render no heading (page doesn't get noisy with empty heads).
    Long strings are truncated to RICH_TEXT_LIMIT (Notion rich_text caps at 2000).
    """
    L = lambda key: get_label(key, lang)
    blocks = []

    intro = (task.get("body_intro") or "").strip()
    if intro:
        blocks.append(_paragraph(intro))

    prompts = task.get("user_prompts") or []
    if prompts:
        blocks.append(_heading(L("task_requests")))
        for p in prompts[:5]:
            short = _truncate(p.replace("\n", " ").strip(), 500)
            if short:
                blocks.append(_bullet(short))

    modified = task.get("files_modified") or []
    created = task.get("files_created") or []
    if modified or created:
        blocks.append(_heading("%s / %s" % (L("files_modified"), L("files_created"))))
        for f in modified[:15]:
            blocks.append(_bullet(_truncate(f, 500)))
        for f in created[:15]:
            blocks.append(_bullet(_truncate("%s (+)" % f, 500)))

    commands = task.get("commands_run") or []
    trivial = {"ls", "pwd", "cat", "echo", "cd", "which", "type", "clear"}
    sig = []
    for c in commands:
        first = c.strip().split()[0] if c.strip() else ""
        if first and first not in trivial:
            sig.append(c)
    sig = sig[:10]
    if sig:
        blocks.append(_heading(L("commands")))
        for c in sig:
            blocks.append(_bullet(_truncate(c, 500)))

    if git_info:
        branch = git_info.get("branch", "")
        commits = git_info.get("commits", [])
        stat = git_info.get("diff_stat") or {}
        if branch or commits or stat.get("added") or stat.get("deleted"):
            blocks.append(_heading(L("git")))
            if branch:
                blocks.append(_paragraph("%s: %s" % (L("branch"), branch)))
            for c in commits[:10]:
                short_hash = c.get("short_hash") or (c.get("hash") or "")[:7]
                msg = c.get("message", "")
                blocks.append(_bullet(_truncate("%s  %s" % (short_hash, msg), 500)))
            if stat.get("added") or stat.get("deleted"):
                blocks.append(_paragraph("+%d / -%d (%d files)" % (
                    stat.get("added", 0), stat.get("deleted", 0), stat.get("files", 0)
                )))

    errors = task.get("errors") or []
    if errors:
        blocks.append(_heading(L("issues")))
        for e in errors[:5]:
            blocks.append(_bullet(_truncate(e, 500)))

    return blocks


def _paragraph(text):
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {"rich_text": _rich_text(text)},
    }


def _heading(text):
    return {
        "object": "block",
        "type": "heading_2",
        "heading_2": {"rich_text": _rich_text(text)},
    }


def _bullet(text):
    return {
        "object": "block",
        "type": "bulleted_list_item",
        "bulleted_list_item": {"rich_text": _rich_text(text)},
    }


def _rich_text(text):
    return [{"type": "text", "text": {"content": _truncate(text, 2000)}}]


def _truncate(text, n):
    if not text:
        return ""
    if len(text) <= n:
        return text
    return text[: n - 1] + "…"


def format_daily_header(date_str, lang="ko"):
    """Create daily diary file header."""
    L = lambda key: get_label(key, lang)

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
