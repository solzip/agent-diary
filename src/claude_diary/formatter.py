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
      [body_intro callout]   - one top-level executive summary
      ## 결과                 - up to 3 checked outcome items
      ## 작업 한눈에          - context/scope/approach/outcome table
      ## 영향                 - impact bullets
      ## 검증                 - checked verification items
      ## 리스크 / 다음 액션    - one risk callout + unchecked next-step/support items
      ## 부록                 - collapsed developer/raw evidence toggles

    Skipped sections render no heading (page doesn't get noisy with empty heads).
    Long strings are truncated to RICH_TEXT_LIMIT (Notion rich_text caps at 2000).
    """
    L = lambda key: get_label(key, lang)
    blocks = []

    intro = (task.get("body_intro") or "").strip()
    if intro:
        blocks.append(_callout(intro, "📌"))

    _add_results_section(blocks, task, L)
    _add_snapshot_section(blocks, task, L)
    _add_bullet_section(blocks, L("impact"), task.get("impact"), 3)
    _add_verification_section(blocks, task, L)
    _add_risks_next_actions_section(blocks, task, L)

    appendix = _build_appendix_blocks(task, git_info, L)
    if appendix:
        blocks.append(_heading(L("appendix")))
        blocks.extend(appendix)

    return blocks


def _add_results_section(blocks, task, L):
    items = _limited_texts(task.get("summary_hints") or task.get("summary"), 3)
    if not items:
        items = _limited_texts(task.get("outcome"), 1)
    if not items:
        return
    blocks.append(_heading(L("results")))
    for item in items:
        blocks.append(_to_do(item, checked=True))


def _add_snapshot_section(blocks, task, L):
    pairs = [
        (L("context"), task.get("work_context") or task.get("context")),
        (L("scope"), task.get("work_scope") or task.get("scope")),
        (L("approach"), task.get("approach")),
        (L("outcome"), task.get("outcome")),
    ]
    rows = [[L("item"), L("content")]]
    for label, value in pairs:
        texts = _limited_texts(value, 1)
        if texts:
            rows.append([label, texts[0]])
    if len(rows) > 1:
        blocks.append(_heading(L("work_snapshot")))
        blocks.append(_table(rows))


def _add_verification_section(blocks, task, L):
    section_blocks = []
    for v in _limited_texts(task.get("verification"), 3):
        section_blocks.append(_to_do(v, checked=True))
    if section_blocks:
        blocks.append(_heading(L("verification")))
        blocks.extend(section_blocks)


def _add_risks_next_actions_section(blocks, task, L):
    section_blocks = []
    risks = _limited_texts(task.get("risks") or task.get("cautions"), 2)
    if risks:
        section_blocks.append(_callout("\n".join(risks), "⚠️"))
    for n in _limited_texts(task.get("next_steps"), 2):
        section_blocks.append(_to_do("%s: %s" % (L("next_steps"), n), checked=False))
    for s in _limited_texts(task.get("support_needed"), 1):
        section_blocks.append(_to_do("%s: %s" % (L("support_needed"), s), checked=False))
    if section_blocks:
        blocks.append(_heading(L("risks_next_actions")))
        blocks.extend(section_blocks)


def _build_appendix_blocks(task, git_info, L):
    blocks = []
    developer = _build_developer_evidence_items(task, git_info, L)
    raw = _build_raw_evidence_items(task, L)

    if developer:
        blocks.append(_toggle(L("developer_evidence"), [_bullet(item) for item in developer]))
    if raw:
        blocks.append(_toggle(L("raw_evidence"), [_bullet(item) for item in raw]))
    return blocks


def _build_developer_evidence_items(task, git_info, L):
    evidence = []

    for c in _limited_texts(task.get("key_changes"), 3):
        evidence.append("%s: %s" % (L("key_changes"), c))

    for c in _limited_texts(task.get("code_change_highlights") or task.get("code_changes"), 3):
        evidence.append("%s: %s" % (L("code_change_highlights"), c))

    for d in _limited_texts(task.get("decisions"), 2):
        evidence.append("%s: %s" % (L("decisions"), d))

    for n in _limited_texts(task.get("implementation_notes"), 2):
        evidence.append("%s: %s" % (L("implementation_notes"), n))

    modified = _as_text_list(task.get("files_modified"))
    created = _as_text_list(task.get("files_created"))
    if modified:
        evidence.append("%s: %s" % (L("files_modified"), _join_limited(modified, 6)))
    if created:
        evidence.append("%s: %s" % (L("files_created"), _join_limited(created, 6)))

    commands = _significant_commands(task.get("commands_run"))
    for c in commands[:3]:
        evidence.append("%s: %s" % (L("commands"), _truncate(c, 500)))

    if git_info:
        branch = git_info.get("branch", "")
        commits = git_info.get("commits", [])
        stat = git_info.get("diff_stat") or {}
        if branch:
            evidence.append("%s: %s" % (L("branch"), branch))
        for c in commits[:3]:
            short_hash = c.get("short_hash") or (c.get("hash") or "")[:7]
            msg = c.get("message", "")
            evidence.append("%s: %s" % (L("commit"), _truncate("%s  %s" % (short_hash, msg), 500)))
        if stat.get("added") or stat.get("deleted"):
            evidence.append("%s: +%d / -%d (%d files)" % (
                L("code_stats"), stat.get("added", 0), stat.get("deleted", 0), stat.get("files", 0)
            ))

    errors = _as_text_list(task.get("errors") or task.get("errors_encountered"))
    for e in errors[:2]:
        evidence.append("%s: %s" % (L("issues"), _truncate(e, 500)))

    return evidence


def _build_raw_evidence_items(task, L):
    raw = []
    for p in _limited_texts(task.get("user_prompts"), 3):
        raw.append("%s: %s" % (L("task_requests"), p))
    return raw


def _significant_commands(commands):
    trivial = {"ls", "pwd", "cat", "echo", "cd", "which", "type", "clear"}
    sig = []
    for c in _as_text_list(commands):
        first = c.strip().split()[0] if c.strip() else ""
        if first and first not in trivial:
            sig.append(c)
    return sig


def _labeled_texts(label, items, max_items, limit=500):
    return ["%s: %s" % (label, item) for item in _limited_texts(items, max_items, limit)]


def _limited_texts(items, max_items, limit=500):
    texts = [_truncate(item.replace("\n", " ").strip(), limit) for item in _as_text_list(items)]
    return [item for item in texts if item][:max_items]


def _join_limited(items, max_items, limit=500):
    texts = _limited_texts(items, max_items, limit)
    extra = len(_as_text_list(items)) - len(texts)
    suffix = " (+%d more)" % extra if extra > 0 else ""
    return _truncate(", ".join(texts) + suffix, limit)


def _add_bullet_section(blocks, title, items, max_items, limit=500):
    """Append a heading and bullet list if items contain usable text."""
    texts = _limited_texts(items, max_items, limit)
    if not texts:
        return
    blocks.append(_heading(title))
    for item in texts:
        blocks.append(_bullet(item))


def _add_callout_section(blocks, title, items, max_items, icon, limit=500):
    """Append a heading and compact callouts if items contain usable text."""
    texts = _limited_texts(items, max_items, limit)
    if not texts:
        return
    blocks.append(_heading(title))
    for item in texts:
        blocks.append(_callout(item, icon))


def _as_text_list(value):
    """Normalize scalar or list-like task fields into strings."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if item is not None]
    return [str(value)]


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


def _callout(text, emoji):
    return {
        "object": "block",
        "type": "callout",
        "callout": {
            "rich_text": _rich_text(text),
            "icon": {"type": "emoji", "emoji": emoji},
        },
    }


def _to_do(text, checked=False):
    return {
        "object": "block",
        "type": "to_do",
        "to_do": {
            "rich_text": _rich_text(text),
            "checked": checked,
        },
    }


def _table(rows):
    width = len(rows[0]) if rows else 0
    return {
        "object": "block",
        "type": "table",
        "table": {
            "table_width": width,
            "has_column_header": True,
            "has_row_header": False,
            "children": [_table_row(row, width) for row in rows],
        },
    }


def _table_row(cells, width):
    normalized = list(cells[:width])
    while len(normalized) < width:
        normalized.append("")
    return {
        "object": "block",
        "type": "table_row",
        "table_row": {
            "cells": [_rich_text(cell) for cell in normalized],
        },
    }


def _toggle(text, children):
    return {
        "object": "block",
        "type": "toggle",
        "toggle": {
            "rich_text": _rich_text(text),
            "children": children,
        },
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
