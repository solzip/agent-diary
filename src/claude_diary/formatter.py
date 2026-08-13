"""Markdown formatter — converts entry_data to diary markdown."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from claude_diary.i18n import get_label
from claude_diary.lib.conventional import commit_type
from claude_diary.types import EntryData, GitInfo


DEFAULT_VERIFICATION_LIMIT = 3
PROMPT_OUTPUT_LIMIT = 15
APPENDIX_ITEM_LIMIT = 10

# https://gitmoji.dev conventions, keyed by Conventional Commit type.
GITMOJI = {
    "feat": "✨",
    "fix": "🐛",
    "refactor": "♻️",
    "docs": "📝",
    "style": "💄",
    "test": "✅",
    "chore": "🔧",
    "perf": "⚡",
    "ci": "👷",
    "build": "📦",
    "remove": "🔥",
    "deploy": "🚀",
    "security": "🔒",
    "upgrade": "⬆️",
    "format": "🎨",
}

def commit_gitmoji(message: str) -> str:
    """Return the gitmoji for a Conventional Commit subject, or "".

    Only the diary's rendering of a commit line uses this. The category
    headings deliberately do not: three gitmoji (📝, ⚡, 🔒) already mean
    something else there — Work Summary, Key Commands, and secrets masked —
    and the same glyph carrying two meanings in one entry is worse than no
    glyph at all.

    The type itself comes from `lib.conventional`, shared with the stats
    command so a message cannot be one type on the diary line and another in
    the count.
    """
    return GITMOJI.get(commit_type(message), "")


def format_entry(entry_data: EntryData, lang: str = "ko", gitmoji: bool = False) -> str:
    """Format entry_data into a markdown diary entry.

    `gitmoji` prefixes each commit line with the emoji for its Conventional
    Commit type. Off by default: this writes into the user's permanent
    record, and emoji in it is a taste some people do not share.
    """
    def L(key):
        return get_label(key, lang)

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
        # Every prompt in this turn, not the first five of the session. The cut
        # used to be here rather than in the parser, so moving the parser to a
        # turn boundary without removing it would keep the same defect at a
        # smaller scale — a turn with six prompts cut at five.
        for i, prompt in enumerate(prompts, 1):
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
            # The sequence number turns a branch name into a thread: reading
            # an entry tells you this is the twelfth session on this piece of
            # work rather than leaving you to count. Absent when the caller did
            # not resolve it, and never shown as "1st" — the first session on a
            # branch has no thread behind it to point at.
            ordinal = entry_data.get("branch_session_ordinal") or 0
            suffix = " (#%d)" % ordinal if ordinal > 1 else ""
            lines.append("  - 🌿 %s: `%s`%s" % (L("branch"), branch, suffix))
        for commit in git_info.get("commits", [])[:5]:
            message = commit["message"]
            if gitmoji:
                emoji = commit_gitmoji(message)
                if emoji:
                    message = "%s %s" % (emoji, message)
            lines.append("  - %s: `%s` %s" % (L("commit"), commit["hash"], message))
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


def build_notion_blocks(task: Dict[str, Any], git_info: Optional[GitInfo] = None,
                        lang: str = "ko") -> List[Dict[str, Any]]:
    """Build Notion API block list for a task page body.

    Body layout:
      [body_intro callout]   - one top-level executive summary
      ## 결과                 - outcomes, verification, then what is still open
      ## 결정 / 트레이드오프   - decision bullets
      ## 이슈 / 리스크        - risk bullets
      ## 다음 액션 / 지원      - unchecked next-step/support items
      ## 부록                 - collapsed work snapshot + developer/raw evidence

    What the page opens on is what the session produced. The context / scope /
    approach / state narrative says the same thing four more ways, so it is
    folded into the appendix instead of sitting above the results.

    Skipped sections render no heading (page doesn't get noisy with empty heads).
    Long strings are truncated to RICH_TEXT_LIMIT (Notion rich_text caps at 2000).
    """
    def L(key):
        return get_label(key, lang)

    blocks = []
    normalized = normalize_notion_task(task)

    intro = (normalized["summary"].get("intro") or "").strip()
    if intro:
        blocks.append(_callout(intro, "📌"))

    _add_results_section(blocks, normalized, L)
    _add_bullet_section(blocks, L("decisions"), normalized.get("decisions"), 2)
    _add_bullet_section(blocks, L("issues_risks"), normalized.get("risks"), 2)
    _add_next_actions_support_section(blocks, normalized, L)

    appendix = _build_appendix_blocks(normalized, git_info, L)
    if appendix:
        blocks.append(_heading(L("appendix")))
        blocks.extend(appendix)

    return blocks


def normalize_notion_task(task):
    """Normalize legacy flat task JSON and v2 nested task JSON for rendering."""
    summary = _dict_value(task.get("summary"))
    work = _dict_value(task.get("work"))
    appendix = _dict_value(task.get("appendix"))

    verification = _merge_texts(
        summary.get("verification"),
        task.get("verification"),
    )
    outcomes = _merge_texts(
        summary.get("outcomes"),
        summary.get("outcome"),
        task.get("summary_hints"),
        task.get("outcome"),
    )
    next_actions = _filter_noop_texts(_merge_texts(
        task.get("next_actions"),
        task.get("next_steps"),
        task.get("next_action"),
    ))
    risks = _merge_texts(
        task.get("risks"),
        task.get("cautions"),
        task.get("errors"),
        task.get("errors_encountered"),
    )
    appendix_errors = _merge_texts(
        appendix.get("errors"),
        task.get("errors"),
        task.get("errors_encountered"),
    )
    prompt_outputs = _merge_texts(
        appendix.get("prompt_outputs"),
        task.get("prompt_outputs"),
        task.get("test_results"),
        task.get("validation_results"),
        task.get("findings"),
    )
    verification_artifacts = _merge_texts(
        appendix.get("verification_artifacts"),
        task.get("verification_artifacts"),
    )
    if _is_verification_session_task(task):
        prompt_outputs = _merge_texts(verification, prompt_outputs)

    return {
        "summary": {
            "intro": _first_text(summary.get("intro"), task.get("body_intro")),
            "outcomes": outcomes,
            "verification": verification,
            "remaining": _filter_noop_texts(_merge_texts(summary.get("remaining"), task.get("remaining_work"))),
        },
        "work": {
            "context": _first_text(work.get("context"), task.get("work_context"), task.get("context")),
            "scope": _first_text(work.get("scope"), task.get("work_scope"), task.get("scope")),
            "approach": _first_text(work.get("approach"), task.get("approach")),
            "state": _first_text(work.get("state"), task.get("work_state"), task.get("outcome"), task.get("status")),
            "highlights": _merge_texts(work.get("highlights"), task.get("impact")),
        },
        "decisions": _merge_texts(task.get("decisions")),
        "risks": risks,
        "next_actions": next_actions,
        "support_needed": _filter_noop_texts(_merge_texts(task.get("support_needed"))),
        "appendix": {
            "key_changes": _merge_texts(
                appendix.get("key_changes"),
                task.get("key_changes"),
                task.get("code_change_highlights"),
                task.get("code_changes"),
            ),
            "implementation_notes": _merge_texts(
                appendix.get("implementation_notes"),
                task.get("implementation_notes"),
            ),
            "prompt_outputs": prompt_outputs,
            "verification_artifacts": verification_artifacts,
            "user_prompts": _merge_texts(appendix.get("user_prompts"), task.get("user_prompts")),
            "files_modified": _merge_texts(appendix.get("files_modified"), task.get("files_modified")),
            "files_created": _merge_texts(appendix.get("files_created"), task.get("files_created")),
            "commands_run": _merge_texts(appendix.get("commands_run"), task.get("commands_run")),
            "commit_hashes": _merge_texts(appendix.get("commit_hashes"), task.get("commit_hashes")),
            "errors": appendix_errors,
            "artifacts": appendix.get("artifacts") or task.get("artifacts") or [],
        },
        "status": task.get("status"),
        "purpose": task.get("purpose"),
        "task_group": task.get("task_group"),
        "categories": _as_text_list(task.get("categories")),
    }


def _add_results_section(blocks, task, L):
    """Render what the session produced — the reason the page exists.

    Given more room than the narrative sections: outcomes and verification are
    the concrete record, and `remaining` is the only unchecked item so an open
    box always means work that is genuinely still open.
    """
    summary = task.get("summary") or {}
    outcome_items = _limited_texts(summary.get("outcomes"), 4)
    verification_items = _limited_texts(summary.get("verification"), 3)
    remaining_items = _limited_texts(summary.get("remaining"), 2)
    items = []
    items.extend((item, True) for item in outcome_items)
    items.extend((item, True) for item in verification_items)
    items.extend((item, False) for item in remaining_items)
    if not items:
        return
    blocks.append(_heading(L("results")))
    for item, checked in items[:7]:
        blocks.append(_to_do(item, checked=checked))


def _build_work_snapshot_toggle(task, L):
    """Fold the context / scope / approach / state narrative into one toggle.

    Four prose restatements of the same session used to sit between the intro
    callout and the results. Kept for the record, collapsed so they no longer
    bury what was actually produced.
    """
    work = task.get("work") or {}
    pairs = [
        (L("context"), work.get("context")),
        (L("scope"), work.get("scope")),
        (L("approach"), work.get("approach")),
        (L("work_state"), work.get("state")),
    ]
    items = []
    for label, value in pairs:
        texts = _limited_texts(value, 1)
        if texts:
            items.append("%s: %s" % (label, texts[0]))
    if not items:
        return None
    return _toggle(L("work_snapshot"), [_bullet(item) for item in items])


def _add_next_actions_support_section(blocks, task, L):
    section_blocks = []
    for n in _limited_texts(task.get("next_actions"), 3):
        section_blocks.append(_to_do("%s: %s" % (L("next_actions"), n), checked=False))
    for s in _limited_texts(task.get("support_needed"), 2):
        section_blocks.append(_to_do("%s: %s" % (L("support_needed"), s), checked=False))
    if section_blocks:
        blocks.append(_heading(L("next_actions_support")))
        blocks.extend(section_blocks)


def _build_appendix_blocks(task, git_info, L):
    blocks = []
    prompt_outputs = _build_prompt_output_items(task)
    developer = _build_developer_evidence_items(task, L)
    command_file_commit = _build_command_file_commit_items(task, git_info, L)
    raw = _build_raw_evidence_items(task, L)

    snapshot = _build_work_snapshot_toggle(task, L)
    if snapshot:
        blocks.append(snapshot)
    if developer:
        blocks.append(_toggle(L("developer_evidence"), [_bullet(item) for item in developer]))
    if prompt_outputs:
        blocks.append(_toggle(L("prompt_outputs"), [_bullet(item) for item in prompt_outputs]))
    if raw:
        blocks.append(_toggle(L("raw_evidence"), [_bullet(item) for item in raw]))
    if command_file_commit:
        blocks.append(_toggle(
            L("command_file_commit_evidence"),
            [_bullet(item) for item in command_file_commit],
        ))
    return blocks


def _build_developer_evidence_items(task, L):
    evidence = []
    appendix = task.get("appendix") or {}
    work = task.get("work") or {}

    for c in _limited_texts(work.get("highlights"), 3):
        evidence.append("%s: %s" % (L("work_highlights"), c))

    for c in _limited_texts(appendix.get("key_changes"), APPENDIX_ITEM_LIMIT):
        evidence.append("%s: %s" % (L("key_changes"), c))

    for n in _limited_texts(appendix.get("implementation_notes"), APPENDIX_ITEM_LIMIT):
        evidence.append("%s: %s" % (L("implementation_notes"), n))

    return evidence


def _build_command_file_commit_items(task, git_info, L):
    evidence = []
    appendix = task.get("appendix") or {}

    modified = _as_text_list(appendix.get("files_modified"))
    created = _as_text_list(appendix.get("files_created"))
    if modified:
        evidence.append("%s: %s" % (L("files_modified"), _join_limited(modified, 6)))
    if created:
        evidence.append("%s: %s" % (L("files_created"), _join_limited(created, 6)))

    commands = _significant_commands(appendix.get("commands_run"))
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

    for h in _limited_texts(appendix.get("commit_hashes"), 3):
        evidence.append("%s: %s" % (L("commit"), h))

    errors = _as_text_list(appendix.get("errors"))
    for e in errors[:2]:
        evidence.append("%s: %s" % (L("issues"), _truncate(e, 500)))

    for a in _format_artifacts(appendix.get("artifacts"))[:5]:
        evidence.append("%s: %s" % (L("artifacts"), a))

    return evidence


def _build_raw_evidence_items(task, L):
    raw = []
    appendix = task.get("appendix") or {}
    for p in _limited_texts(appendix.get("user_prompts"), 3):
        raw.append("%s: %s" % (L("task_requests"), p))
    return raw


def _dict_value(value):
    return value if isinstance(value, dict) else {}


def _first_text(*values):
    for value in values:
        for item in _as_text_list(value):
            text = item.replace("\n", " ").strip()
            if text:
                return text
    return ""


def _merge_texts(*values):
    items = []
    for value in values:
        items.extend(_as_text_list(value))
    return dedupe_texts([item.replace("\n", " ").strip() for item in items if item and item.strip()])


def _format_artifacts(value):
    formatted = []
    if isinstance(value, dict):
        artifacts = [value]
    elif isinstance(value, (list, tuple)):
        artifacts = value
    else:
        artifacts = _as_text_list(value)
    for artifact in artifacts:
        if isinstance(artifact, dict):
            path = str(artifact.get("path") or "").strip()
            kind = str(artifact.get("kind") or "").strip()
            summary = str(artifact.get("summary") or "").strip()
            sha = str(artifact.get("sha256") or artifact.get("hash") or "").strip()
            parts = []
            if kind:
                parts.append(kind)
            if path:
                parts.append(path)
            text = ": ".join(parts) if parts else summary
            if summary and text != summary:
                text = "%s - %s" % (text, summary)
            if sha:
                text = "%s (sha256: %s)" % (text, sha[:12])
            if text:
                formatted.append(text)
        else:
            text = str(artifact).strip()
            if text:
                formatted.append(text)
    return formatted


def _significant_commands(commands):
    trivial = {"ls", "pwd", "cat", "echo", "cd", "which", "type", "clear"}
    sig = []
    for c in _as_text_list(commands):
        first = c.strip().split()[0] if c.strip() else ""
        if first and first not in trivial:
            sig.append(c)
    return sig


def _build_prompt_output_items(task):
    appendix = task.get("appendix") or {}
    items = []
    items.extend(_as_text_list(appendix.get("prompt_outputs")))
    items.extend(_as_text_list(appendix.get("verification_artifacts")))
    return dedupe_texts(_limited_texts(items, PROMPT_OUTPUT_LIMIT, limit=1000))


def _is_verification_session_task(task):
    tokens = [
        task.get("status"),
        task.get("purpose"),
        task.get("task_group"),
    ]
    tokens.extend(_as_text_list(task.get("categories")))
    haystack = " ".join(str(token or "").lower() for token in tokens)
    keywords = (
        "testing",
        "test",
        "qa",
        "verify",
        "verification",
        "validation",
        "review",
        "검증",
        "테스트",
        "테스터",
    )
    return any(keyword in haystack for keyword in keywords)


def dedupe_texts(items):
    seen = set()
    result = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _filter_noop_texts(items):
    return [item for item in _as_text_list(items) if not _is_noop_text(item)]


def _is_noop_text(value):
    text = str(value or "").strip().lower().strip(".")
    normalized = " ".join(text.split())
    noop_prefixes = (
        "no follow-up needed",
        "no follow up needed",
        "no further action",
        "no action needed",
        "not needed",
    )
    if any(normalized.startswith(prefix) for prefix in noop_prefixes):
        return True
    return normalized in {
        "",
        "none",
        "n/a",
        "na",
        "no follow-up needed",
        "no follow up needed",
        "no further action",
        "no action needed",
        "not needed",
        "없음",
        "해당 없음",
        "후속 조치 없음",
        "추가 조치 없음",
    }


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


def format_daily_header(date_str: str, lang: str = "ko") -> str:
    """Create daily diary file header."""
    def L(key):
        return get_label(key, lang)


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
