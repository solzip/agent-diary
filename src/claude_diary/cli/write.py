"""Manual diary write — on-demand structured diary generation.

Triggered by `claude-diary write` (typically via `/diary` slash command).
Auto-detects current session's transcript and writes to:
    <manual_diary_dir>/<date>/<project>/<date>.md

Same date + project → append. Otherwise → create.
"""

import os
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

from claude_diary.config import load_config
from claude_diary.log import get_logger, configure_from_config
from claude_diary.lib.parser import parse_transcript
from claude_diary.lib.git_info import collect_git_info
from claude_diary.lib.categorizer import categorize
from claude_diary.lib.secret_scanner import scan_entry_data
from claude_diary.formatter import format_entry, format_daily_header

logger = get_logger("claude_diary.cli.write")


def _encode_cwd(cwd):
    """Encode cwd to Claude Code's project dir name format.

    Replaces every non-alphanumeric char with '-'. Verified consistent
    across Windows/macOS/Linux via Claude Code's transcript storage:
      Linux:   /home/user/myapp   → -home-user-myapp
      macOS:   /Users/foo/proj    → -Users-foo-proj
      Windows: C:\\Users\\foo\\proj → C--Users-foo-proj
    """
    if not cwd:
        return ""
    return re.sub(r"[^A-Za-z0-9]", "-", cwd)


def _candidate_project_dirs(cwd):
    """Return candidate ~/.claude/projects/<encoded>/ paths to probe.

    Tries multiple cwd normalizations because the harness may have
    recorded the path differently than os.getcwd() returns it (case,
    symlinks, abspath vs realpath).
    """
    base = Path(os.path.expanduser("~/.claude/projects"))
    seen = set()
    candidates = []
    for variant in (
        cwd,
        os.path.abspath(cwd) if cwd else None,
        os.path.realpath(cwd) if cwd else None,
    ):
        if not variant:
            continue
        encoded = _encode_cwd(variant)
        if encoded in seen:
            continue
        seen.add(encoded)
        candidates.append(base / encoded)
    return candidates


def _find_latest_transcript(cwd):
    """Locate the most recent transcript .jsonl for the current session.

    Strategy (first hit wins):
      1. $CLAUDE_TRANSCRIPT_PATH env var (if harness ever exposes it)
      2. ~/.claude/projects/<encoded-cwd>/*.jsonl — multiple cwd variants,
         latest by mtime
      3. Fallback: globally most-recently-modified .jsonl across all
         projects, but only if modified within the last hour (likely the
         current live session) — defensive for unexpected encoding edge cases
    """
    env_path = os.environ.get("CLAUDE_TRANSCRIPT_PATH")
    if env_path and os.path.exists(env_path):
        return env_path

    for projects_dir in _candidate_project_dirs(cwd):
        if not projects_dir.is_dir():
            continue
        jsonls = list(projects_dir.glob("*.jsonl"))
        if jsonls:
            return str(max(jsonls, key=lambda p: p.stat().st_mtime))

    # Final fallback: scan all projects, pick latest .jsonl if recent
    base = Path(os.path.expanduser("~/.claude/projects"))
    if base.is_dir():
        all_jsonls = list(base.glob("*/*.jsonl"))
        if all_jsonls:
            latest = max(all_jsonls, key=lambda p: p.stat().st_mtime)
            import time
            if time.time() - latest.stat().st_mtime < 3600:
                return str(latest)
    return None


def _extract_project_name(cwd):
    if not cwd:
        return "unknown"
    cwd = cwd.replace("\\", "/").rstrip("/")
    return os.path.basename(cwd) or "unknown"


def _safe_project_name(name):
    """Sanitize project name for use as directory name."""
    safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip()
    return safe or "unknown"


def _append_or_create(target_path, date_str, entry_text, lang):
    """Append entry to target_path; create with daily header if missing."""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if not target_path.exists():
        with open(target_path, "w", encoding="utf-8") as f:
            f.write(format_daily_header(date_str, lang))
    with open(target_path, "a", encoding="utf-8") as f:
        f.write(entry_text)


def cmd_write(args):
    """Generate manual diary entry for the current session."""
    config = load_config()
    configure_from_config(config)

    lang = config.get("lang", "ko")
    tz_offset = config.get("timezone_offset", 9)
    manual_dir = os.path.expanduser(
        config.get("manual_diary_dir") or "~/working-diary/manual"
    )
    enrichment = config.get("enrichment", {})

    cwd = os.getcwd()
    project = _safe_project_name(_extract_project_name(cwd))

    transcript_path = _find_latest_transcript(cwd)
    if not transcript_path:
        encoded = _encode_cwd(os.path.abspath(cwd))
        print("[claude-diary write] No transcript found for current project.", file=sys.stderr)
        print("  cwd: %s" % cwd, file=sys.stderr)
        print("  searched: ~/.claude/projects/%s/" % encoded, file=sys.stderr)
        print("  hint: run /diary inside a Claude Code session that has at least", file=sys.stderr)
        print("        one user message — transcripts are written by Claude Code,", file=sys.stderr)
        print("        not by claude-diary.", file=sys.stderr)
        sys.exit(1)

    local_tz = timezone(timedelta(hours=tz_offset))
    now = datetime.now(local_tz)
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M:%S")

    parsed = parse_transcript(transcript_path, max_lines=config.get("max_transcript_lines"))

    has_content = bool(
        parsed.get("user_prompts") or parsed.get("files_modified") or
        parsed.get("files_created") or parsed.get("commands_run")
    )
    if not has_content:
        print("[claude-diary write] Transcript has no diary-worthy content yet.", file=sys.stderr)
        sys.exit(1)

    entry_data = {
        "session_id": "manual",
        "date": date_str,
        "time": time_str,
        "project": project,
        "cwd": cwd,
        "user_prompts": parsed.get("user_prompts", []),
        "files_created": parsed.get("files_created", []),
        "files_modified": parsed.get("files_modified", []),
        "commands_run": parsed.get("commands_run", []),
        "summary_hints": parsed.get("summary_hints", []),
        "errors_encountered": parsed.get("errors_encountered", []),
        "categories": [],
        "git_info": None,
        "code_stats": None,
        "secrets_masked": 0,
    }

    if enrichment.get("git_info", True):
        try:
            git_info = collect_git_info(cwd, parsed.get("session_start"))
            if git_info:
                entry_data["git_info"] = git_info
                if enrichment.get("code_stats", True):
                    entry_data["code_stats"] = git_info.get("diff_stat")
        except Exception as e:
            logger.warning("Git enrichment failed: %s", e)

    if enrichment.get("auto_category", True):
        try:
            entry_data["categories"] = categorize(
                entry_data, config.get("custom_categories") or None
            )
        except Exception as e:
            logger.warning("Auto-categorization failed: %s", e)

    try:
        scan_entry_data(
            entry_data,
            config.get("security", {}).get("additional_secret_patterns") or None,
        )
    except Exception as e:
        logger.warning("Secret scan failed: %s", e)

    entry_text = format_entry(entry_data, lang)
    target = Path(manual_dir) / date_str / project / ("%s.md" % date_str)

    existed = target.exists()
    try:
        _append_or_create(target, date_str, entry_text, lang)
    except OSError as e:
        print("[claude-diary write] Failed to write diary file.", file=sys.stderr)
        print("  target: %s" % target, file=sys.stderr)
        print("  error: %s" % e, file=sys.stderr)
        print("  hint: check CLAUDE_DIARY_MANUAL_DIR or `claude-diary config --set manual_diary_dir=<path>`", file=sys.stderr)
        sys.exit(1)

    action = "appended to" if existed else "created"
    print("[claude-diary write] %s %s" % (action, target))
