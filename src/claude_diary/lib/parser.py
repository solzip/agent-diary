"""Transcript JSONL parser — extracts work content from Claude Code sessions."""

import json
import os
import re

MAX_TRANSCRIPT_LINES = 2000


def parse_transcript(transcript_path, max_lines=MAX_TRANSCRIPT_LINES):
    """Parse JSONL transcript and extract key work content.

    Returns dict with:
        user_prompts, files_created, files_modified, commands_run,
        tools_used, summary_hints, errors_encountered,
        session_start, session_end (ISO timestamps)
    """
    result = {
        "user_prompts": [],
        "files_modified": set(),
        "files_created": set(),
        "commands_run": [],
        "tools_used": set(),
        "errors_encountered": [],
        "summary_hints": [],
        "session_start": None,
        "session_end": None,
    }

    if not transcript_path or not os.path.exists(transcript_path):
        return _finalize(result)

    try:
        line_count = 0
        with open(transcript_path, "r", encoding="utf-8") as f:
            for line in f:
                line_count += 1
                if line_count > max_lines:
                    break

                line = line.strip()
                if not line:
                    continue

                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                # Track timestamps
                ts = entry.get("timestamp")
                if ts:
                    if result["session_start"] is None:
                        result["session_start"] = ts
                    result["session_end"] = ts

                entry_type = entry.get("type", "")
                message = entry.get("message") or entry.get("data") or {}
                content = message.get("content", "")

                # User messages
                if entry_type in ("user", "human"):
                    text = _extract_text(content)
                    if text and len(text) > 5:
                        result["user_prompts"].append(text[:200])

                # Assistant messages (tool_use blocks + text)
                elif entry_type == "assistant":
                    if isinstance(content, list):
                        for block in content:
                            if not isinstance(block, dict):
                                continue
                            block_type = block.get("type", "")

                            if block_type == "tool_use":
                                _process_tool_use(block, result)

                            elif block_type == "text":
                                text = block.get("text", "")
                                if text:
                                    _extract_summary_hints(text, result["summary_hints"])

                    elif isinstance(content, str) and content:
                        _extract_summary_hints(content, result["summary_hints"])

    except Exception as e:
        result["errors_encountered"].append("Transcript parse error: %s" % str(e))

    return _finalize(result)


def get_session_time_range(transcript_path):
    """Extract first and last timestamps from transcript.
    Returns (start_iso, end_iso) or (None, None).
    """
    start = None
    end = None

    if not transcript_path or not os.path.exists(transcript_path):
        return (None, None)

    try:
        with open(transcript_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts = entry.get("timestamp")
                if ts:
                    if start is None:
                        start = ts
                    end = ts
    except Exception:
        pass

    return (start, end)


def _process_tool_use(block, result):
    """Process a tool_use block from assistant message."""
    tool_name = block.get("name", "")
    tool_input = block.get("input", {})

    if tool_name:
        result["tools_used"].add(tool_name)

    if tool_name in ("Write", "write_to_file", "file_write"):
        fp = tool_input.get("file_path") or tool_input.get("path", "")
        if fp:
            result["files_created"].add(_shorten_path(fp))

    elif tool_name in ("Edit", "MultiEdit", "edit_file", "str_replace_editor"):
        fp = tool_input.get("file_path") or tool_input.get("path", "")
        if fp:
            result["files_modified"].add(_shorten_path(fp))

    elif tool_name in ("Bash", "execute_command", "bash"):
        command = tool_input.get("command", "")
        if command and not _is_noise_command(command):
            result["commands_run"].append(command[:150])


def _extract_text(content):
    """Extract text from message content (string or block array)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                texts.append(block.get("text", ""))
            elif isinstance(block, str):
                texts.append(block)
        return " ".join(texts)
    return ""


def _extract_summary_hints(text, hints_list):
    """Extract work summary hints from text using keyword matching."""
    keywords = [
        "완료", "구현", "수정", "추가", "삭제", "생성",
        "설정", "배포", "테스트", "리팩토링",
        "fixed", "implemented", "created", "updated", "added",
        "configured", "deployed", "tested", "refactored",
        "completed", "resolved", "installed", "removed",
    ]
    for keyword in keywords:
        if keyword in text.lower():
            sentences = re.split(r'[.!?\n]', text)
            for sent in sentences:
                if keyword in sent.lower() and 10 < len(sent.strip()) < 200:
                    hints_list.append(sent.strip())
            break


def _shorten_path(file_path):
    """Shorten file path for display (Windows/Unix compatible)."""
    file_path = file_path.replace("\\", "/")
    home = os.path.expanduser("~").replace("\\", "/")
    if file_path.startswith(home):
        file_path = "~" + file_path[len(home):]
    parts = file_path.split("/")
    if len(parts) > 4:
        file_path = ".../" + "/".join(parts[-3:])
    return file_path


def _is_noise_command(command):
    """Filter out trivial/noisy commands."""
    noise_patterns = [
        r"^(cat|ls|pwd|echo|cd|which|type|file)\s",
        r"^(cat|ls|pwd)$",
        r"^head\s", r"^tail\s", r"^wc\s",
        r"^find .* -name", r"^grep -r",
    ]
    for pattern in noise_patterns:
        if re.match(pattern, command.strip()):
            return True
    return False


def _finalize(result):
    """Convert sets to sorted lists and deduplicate."""
    result["files_modified"] = sorted(result["files_modified"])
    result["files_created"] = sorted(result["files_created"])
    result["tools_used"] = sorted(result["tools_used"])
    result["summary_hints"] = list(dict.fromkeys(result["summary_hints"]))[:10]
    result["commands_run"] = result["commands_run"][:30]
    return result
