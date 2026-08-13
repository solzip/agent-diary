"""Core pipeline orchestrator — processes a session into a diary entry."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone, timedelta
from typing import Optional

from claude_diary.types import Config, EntryData, GitInfo
from claude_diary.config import load_config
from claude_diary.log import get_logger, configure_from_config
from claude_diary.lib.parser import parse_transcript
from claude_diary.lib.git_info import collect_git_info
from claude_diary.lib.categorizer import categorize
from claude_diary.lib.nonfatal import non_fatal
from claude_diary.lib.secret_scanner import scan_entry_data
from claude_diary.formatter import format_entry
from claude_diary.lib.audit import log_entry as audit_log
from claude_diary.writer import append_entry, update_session_count, ensure_diary_dir
from claude_diary.indexer import update_index

logger = get_logger("claude_diary.core")


def process_session(session_id: str, transcript_path: str, cwd: str,
                    when: Optional[datetime] = None) -> bool:
    """Main pipeline: transcript → enrichment → write → export.

    Args:
        session_id: Claude Code session ID
        transcript_path: Path to transcript.jsonl
        cwd: Working directory path
        when: The moment the session happened. Defaults to now, which is
            correct for the Stop Hook — it runs as the session ends. `backfill`
            passes the transcript's own start time so an imported session is
            filed under the day it was worked, not the day it was imported.

    Returns:
        True if entry was written, False if skipped (no content).
    """
    config = load_config()
    configure_from_config(config)
    lang = config.get("lang", "ko")
    tz_offset = config.get("timezone_offset", 9)
    diary_dir = os.path.expanduser(config.get("diary_dir", "~/working-diary"))
    enrichment = config.get("enrichment", {})

    # 0. Session opt-out check
    from claude_diary.lib.team_security import should_skip_session
    if should_skip_session(cwd, config):
        logger.info("Session skipped (opt-out)")
        return False

    local_tz = timezone(timedelta(hours=tz_offset))
    now = datetime.now(local_tz) if when is None else when.astimezone(local_tz)
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M:%S")

    # 1. Parse transcript, from where the previous turn stopped.
    #
    # The hook runs once per assistant turn. Reading from the beginning every
    # time is what made 85% of the entries in one diary copies of an earlier
    # entry in the same session.
    max_lines = config.get("max_transcript_lines")
    start_line = _resume_point(diary_dir, session_id, transcript_path)
    if start_line is None:
        return False
    parsed = parse_transcript(transcript_path, max_lines=max_lines,
                              start_line=start_line)

    # Check if session has meaningful content
    has_content = (
        len(parsed.get("user_prompts", [])) > 0 or
        len(parsed.get("files_modified", [])) > 0 or
        len(parsed.get("files_created", [])) > 0 or
        len(parsed.get("commands_run", [])) > 0
    )
    if not has_content:
        return False

    # 2. Build entry_data
    project = _extract_project_name(cwd)
    entry_data: EntryData = {
        "session_id": session_id,
        "date": date_str,
        "time": time_str,
        "project": project,
        "cwd": cwd,
        "user_prompts": parsed.get("user_prompts", []),
        "files_created": parsed.get("files_created", []),
        "files_modified": parsed.get("files_modified", []),
        "commands_run": parsed.get("commands_run", []),
        "summary_hints": parsed.get("summary_hints", []),
        "assistant_responses": parsed.get("assistant_responses", []),
        "errors_encountered": parsed.get("errors_encountered", []),
        "categories": [],
        "git_info": None,
        "code_stats": None,
        "secrets_masked": 0,
    }

    # 3. Enrichment: Git info
    if enrichment.get("git_info", True):
        try:
            session_start = parsed.get("session_start")
            git_info = collect_git_info(cwd, session_start)
            if git_info:
                entry_data["git_info"] = git_info
                # Use git diff stat as code_stats
                if enrichment.get("code_stats", True):
                    entry_data["code_stats"] = git_info.get("diff_stat")

                # Supplement files from git if transcript was incomplete
                _supplement_from_git(entry_data, git_info)
        except Exception as e:
            logger.warning("Git enrichment failed: %s", e)

    # 3.5 Where this session sits in the branch's thread. Read before the entry
    # is formatted, so the record itself carries the position rather than
    # requiring a separate command to go and work it out.
    try:
        branch = (entry_data.get("git_info") or {}).get("branch", "")
        if branch:
            from claude_diary.indexer import count_branch_sessions
            entry_data["branch_session_ordinal"] = (
                count_branch_sessions(diary_dir, project, branch) + 1
            )
    except Exception as e:
        logger.warning("Branch thread lookup failed: %s", e)

    # 4. Enrichment: Auto-categorization
    if enrichment.get("auto_category", True):
        try:
            custom_rules = config.get("custom_categories", {})
            categories = categorize(entry_data, custom_rules or None)
            entry_data["categories"] = categories
        except Exception as e:
            logger.warning("Auto-categorization failed: %s", e)

    # 5. Secret scan (always runs)
    try:
        additional = config.get("security", {}).get("additional_secret_patterns", [])
        scan_entry_data(entry_data, additional or None)
    except Exception as e:
        logger.warning("Secret scan failed: %s", e)

    # 5.5 Team security filters (path masking + content filter)
    try:
        from claude_diary.lib.team_security import mask_paths, filter_entry_data
        security = config.get("security", {})
        mask_patterns = security.get("mask_paths", [])
        if mask_patterns:
            entry_data["files_created"] = mask_paths(entry_data["files_created"], mask_patterns)
            entry_data["files_modified"] = mask_paths(entry_data["files_modified"], mask_patterns)

        content_filters = security.get("content_filters", [])
        filter_mode = security.get("filter_mode", "redact")
        if content_filters:
            should_record = filter_entry_data(entry_data, content_filters, filter_mode)
            if not should_record:
                logger.info("Session skipped (content filter)")
                return False
    except Exception as e:
        logger.warning("Team security filter failed: %s", e)

    # 6. Format and write (CRITICAL — exit 1 on failure)
    try:
        entry_text = format_entry(entry_data, lang, gitmoji=_gitmoji_enabled(config))
        ensure_diary_dir(diary_dir)
        append_entry(diary_dir, date_str, entry_text, lang)
        count = update_session_count(diary_dir, date_str)
    except Exception as e:
        logger.error("FATAL: Failed to write diary: %s", e)
        sys.exit(1)

    # 6.5 Advance the read position, but only now that the entry is on disk.
    # A failed write leaves the position where it was, so the next turn covers
    # this turn's work as well rather than dropping it.
    try:
        from claude_diary.lib.progress import record_position
        record_position(diary_dir, session_id, transcript_path,
                        parsed.get("lines_read", 0))
    except Exception as e:
        logger.warning("Could not record read position: %s", e)

    # 7. Update search index (non-critical)
    try:
        update_index(diary_dir, entry_data)
    except Exception as e:
        logger.warning("Index update failed: %s", e)

    # 8. Retry previously failed exports (non-critical)
    try:
        from claude_diary.exporters.loader import retry_queued
        retry_queued(config, diary_dir)
    except Exception as e:
        logger.warning("Export retry failed: %s", e)

    # 9. Run exporters (non-critical)
    try:
        _run_exporters(config, entry_data)
    except Exception as e:
        logger.warning("Exporter execution failed: %s", e)

    # 10. Audit log (non-critical)
    try:
        diary_file = os.path.join(diary_dir, "%s.md" % date_str)
        audit_log(
            diary_dir=diary_dir,
            session_id=session_id,
            transcript_path=transcript_path,
            files_written=[diary_file],
            secrets_masked=entry_data.get("secrets_masked", 0),
            tz_offset=tz_offset,
        )
    except Exception as e:
        logger.warning("Audit log failed: %s", e)

    # 11. Log success
    logger.info(
        "Session #%d for %s | project: %s | categories: %s",
        count, date_str, project, ",".join(entry_data["categories"]) or "none",
    )

    return True


def _resume_point(diary_dir: str, session_id: str, transcript_path: str):
    """Where this turn should start reading, or None to record nothing.

    Three cases:

    - A position is stored: resume there.
    - Nothing stored and the diary has no entry for this session: it is new,
      so read from the beginning.
    - Nothing stored but the diary already holds entries for it: this is the
      first turn after upgrading, mid-session. Reading from 0 would write one
      final copy of everything already recorded — the exact defect being
      fixed, one last time. Seed the position to the file's current length and
      record nothing for this turn.
    """
    from claude_diary.lib.progress import read_position, record_position

    try:
        stored = read_position(diary_dir, session_id, transcript_path)
    except Exception as e:
        logger.warning("Could not read resume point: %s", e)
        return 0

    if stored is not None:
        return stored

    if not _session_already_recorded(diary_dir, session_id):
        return 0

    lines = _count_lines(transcript_path)
    logger.info(
        "First run for a session already in the diary; "
        "recording from line %d onward.", lines,
    )
    record_position(diary_dir, session_id, transcript_path, lines)
    return None


def _session_already_recorded(diary_dir: str, session_id: str) -> bool:
    """Whether the diary Markdown already mentions this session.

    The Markdown, not the index or the audit log — `backfill` reads the same
    source for the same reason: a derived artifact that has fallen behind would
    answer this wrongly.
    """
    if not session_id or not os.path.isdir(diary_dir):
        return False
    from pathlib import Path
    for path in Path(diary_dir).glob("*.md"):
        try:
            if session_id in path.read_text(encoding="utf-8", errors="replace"):
                return True
        except OSError:
            continue
    return False


def _count_lines(path: str) -> int:
    if not path or not os.path.exists(path):
        return 0
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return sum(1 for _ in f)
    except OSError:
        return 0


def _gitmoji_enabled(config: Config) -> bool:
    return bool((config.get("formatting") or {}).get("gitmoji", False))


def _extract_project_name(cwd: str) -> str:
    """Name the project after its repository, not after the current folder.

    The last path segment is what the hook used to record, and it is the
    repository only when the session happened to be sitting at the root. See
    `get_repo_root` for what that cost.

    Falls back to the folder name outside a repository, which is the best
    available answer there.
    """
    if not cwd:
        return "unknown"
    from claude_diary.lib.git_info import get_repo_root
    root = get_repo_root(cwd)
    return _basename(root or cwd)


def _basename(path: str) -> str:
    return os.path.basename(path.replace("\\", "/").rstrip("/"))


def _supplement_from_git(entry_data: EntryData, git_info: GitInfo) -> None:
    """Supplement file lists from git when transcript may be incomplete."""
    diff_stat = git_info.get("diff_stat", {})
    if diff_stat.get("files", 0) > 0 and not entry_data["files_modified"] and not entry_data["files_created"]:
        # Transcript was empty/incomplete — get filenames from git
        cwd = entry_data.get("cwd", "")
        if cwd:
            # A fallback only runs when the thing it backs up came up empty,
            # so it is exercised rarely and a defect in it would sit here
            # unnoticed for as long as the normal path keeps working.
            with non_fatal("git file-list fallback"):
                import subprocess
                result = subprocess.run(
                    ["git", "diff", "--name-only", "HEAD"],
                    cwd=cwd, capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    from claude_diary.lib.parser import _shorten_path
                    for line in result.stdout.strip().split("\n"):
                        line = line.strip()
                        if line:
                            entry_data["files_modified"].append(_shorten_path(line))


def _run_exporters(config: Config, entry_data: EntryData) -> None:
    """Load and run enabled exporters via plugin loader."""
    from claude_diary.exporters.loader import load_exporters, run_exporters
    diary_dir = os.path.expanduser(config.get("diary_dir", "~/working-diary"))

    exporters = load_exporters(config)
    if exporters:
        result = run_exporters(exporters, entry_data, diary_dir)
        if result["failed"]:
            logger.warning("Failed exporters: %s", ", ".join(result["failed"]))
