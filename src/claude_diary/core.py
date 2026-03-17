"""Core pipeline orchestrator — processes a session into a diary entry."""

import os
import sys
from datetime import datetime, timezone, timedelta

from claude_diary.config import load_config
from claude_diary.lib.parser import parse_transcript, get_session_time_range
from claude_diary.lib.git_info import collect_git_info
from claude_diary.lib.categorizer import categorize
from claude_diary.lib.secret_scanner import scan_entry_data
from claude_diary.formatter import format_entry
from claude_diary.writer import append_entry, update_session_count, ensure_diary_dir
from claude_diary.indexer import update_index


def process_session(session_id, transcript_path, cwd):
    """Main pipeline: transcript → enrichment → write → export.

    Args:
        session_id: Claude Code session ID
        transcript_path: Path to transcript.jsonl
        cwd: Working directory path

    Returns:
        True if entry was written, False if skipped (no content).
    """
    config = load_config()
    lang = config.get("lang", "ko")
    tz_offset = config.get("timezone_offset", 9)
    diary_dir = os.path.expanduser(config.get("diary_dir", "~/working-diary"))
    enrichment = config.get("enrichment", {})

    local_tz = timezone(timedelta(hours=tz_offset))
    now = datetime.now(local_tz)
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M:%S")

    # 1. Parse transcript
    parsed = parse_transcript(transcript_path)

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
    entry_data = {
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
        except Exception:
            pass

    # 4. Enrichment: Auto-categorization
    if enrichment.get("auto_category", True):
        try:
            custom_rules = config.get("custom_categories", {})
            categories = categorize(entry_data, custom_rules or None)
            entry_data["categories"] = categories
        except Exception:
            pass

    # 5. Secret scan (always runs)
    try:
        scan_entry_data(entry_data)
    except Exception:
        pass

    # 6. Format and write
    entry_text = format_entry(entry_data, lang)
    ensure_diary_dir(diary_dir)
    append_entry(diary_dir, date_str, entry_text, lang)
    count = update_session_count(diary_dir, date_str)

    # 7. Update search index (non-critical)
    try:
        update_index(diary_dir, entry_data)
    except Exception:
        pass

    # 8. Run exporters (non-critical)
    try:
        _run_exporters(config, entry_data)
    except Exception:
        pass

    # 9. Log success
    sys.stderr.write(
        "[diary] Session #%d for %s | project: %s | categories: %s\n"
        % (count, date_str, project, ",".join(entry_data["categories"]) or "none")
    )

    return True


def _extract_project_name(cwd):
    """Extract project name from working directory (Windows/Unix)."""
    if not cwd:
        return "unknown"
    cwd = cwd.replace("\\", "/").rstrip("/")
    return os.path.basename(cwd)


def _supplement_from_git(entry_data, git_info):
    """Supplement file lists from git when transcript may be incomplete."""
    # If git has commits but transcript has no files, git diff is more reliable
    if git_info.get("diff_stat", {}).get("files", 0) > 0:
        if not entry_data["files_created"] and not entry_data["files_modified"]:
            # transcript was empty — trust git
            pass  # git diff --stat doesn't give individual filenames easily
            # This will be enhanced when we parse `git diff --name-status`


def _run_exporters(config, entry_data):
    """Load and run enabled exporters."""
    exporters_config = config.get("exporters", {})
    if not exporters_config:
        return

    for name, exp_config in exporters_config.items():
        if not exp_config.get("enabled", False):
            continue
        try:
            _run_single_exporter(name, exp_config, entry_data)
        except Exception as e:
            sys.stderr.write("[diary] Exporter '%s' failed: %s\n" % (name, str(e)))


def _run_single_exporter(name, exp_config, entry_data):
    """Dynamically load and run a single exporter."""
    import importlib
    try:
        module = importlib.import_module("claude_diary.exporters.%s" % name)
        exporter_class = getattr(module, "%sExporter" % name.capitalize(), None)
        if exporter_class is None:
            return
        exporter = exporter_class(exp_config)
        if exporter.validate_config():
            exporter.export(entry_data)
    except ImportError:
        sys.stderr.write("[diary] Exporter '%s' not found\n" % name)
