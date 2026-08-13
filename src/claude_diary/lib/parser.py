"""Transcript JSONL parser — extracts work content from Claude Code sessions."""

import json
import os
import re

# No cap by default. There was one of 2,000 lines, and on this machine it read
# 67% of the transcript corpus: 20 of 91 files were longer than that, and the
# longest had 21% of it recorded. What the cap dropped was always the end of
# the session — the part where the work concluded — and it dropped it in
# silence, which is the opposite of a tool whose purpose is to record what was
# done. One session's entry claimed it ended on 2026-07-02 while the transcript
# ran to 07-08.
#
# The cap was there for cost that turns out not to exist: parsing is line by
# line, so peak memory tracks the longest line rather than the file, and a
# 300MB transcript parses in under a second. `max_transcript_lines` in config
# still sets one for anyone who wants it, and hitting it is now recorded in the
# entry rather than passed over.
DEFAULT_MAX_TRANSCRIPT_LINES = None


def parse_transcript(transcript_path, max_lines=None, start_line=0):
    """Parse JSONL transcript and extract key work content.

    `start_line` skips that many lines before collecting anything. The Stop
    Hook fires once per assistant turn, and without this it re-read the whole
    transcript every time — which is how 85% of the entries in one real diary
    came to be copies of an earlier entry in the same session. Transcripts are
    append-only (verified by hashing a live one's prefix across a turn), so a
    line count is a durable place to resume from.

    Returns dict with:
        user_prompts, files_created, files_modified, commands_run,
        tools_used, summary_hints, errors_encountered,
        session_start, session_end (ISO timestamps), lines_read
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
        # Absolute position in the file, including anything skipped. This is
        # what the next turn resumes from, so it counts lines seen rather than
        # lines used.
        "lines_read": 0,
    }

    if max_lines is None:
        max_lines = DEFAULT_MAX_TRANSCRIPT_LINES

    if not transcript_path or not os.path.exists(transcript_path):
        return _finalize(result)

    truncated_at = None

    try:
        line_count = 0
        # `errors="replace"`, because one bad byte used to cost the whole
        # session. Text IO decodes in chunks, so the error surfaced before any
        # line was yielded and the parse returned nothing at all — not even
        # the lines that came before it. With nothing parsed, `has_content` is
        # false, and the session left no diary entry and no audit line: the
        # one failure mode indistinguishable from a quiet day.
        with open(transcript_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line_count += 1
                if line_count <= start_line:
                    # Already recorded by an earlier turn. Counted, not read.
                    continue
                if max_lines and line_count - start_line > max_lines:
                    # Say so in the entry. A partial record that looks complete
                    # is the failure this whole tool exists to avoid.
                    truncated_at = max_lines
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
                    _collect_tool_errors(content, result)
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

        result["lines_read"] = line_count
    except Exception as e:
        result["errors_encountered"].append("Transcript parse error: %s" % str(e))

    if truncated_at:
        result["truncated_at"] = truncated_at
        result["errors_encountered"].append(
            "Transcript read stopped at %d lines (max_transcript_lines); "
            "this entry covers the start of the session only." % truncated_at
        )

    return _finalize(result)


ERROR_LIMIT = 10
ERROR_TEXT_LIMIT = 200


def _collect_tool_errors(content, result):
    """Record the failures a session actually hit.

    The diary has had an `Issues Encountered` section since the beginning and
    it was filled in 20 of 6,921 entries — and those twenty were not failures
    during the work, they were this parser failing to read the transcript. A
    section named for the problems you ran into that only ever reported the
    diary's own problems.

    The material was there the whole time: every failed tool call carries
    `is_error` on its result block. Sampling twenty real transcripts, all
    twenty had some, 244 in total.

    Capped and deduplicated because that average is twelve per session, and an
    entry that is mostly error text is not a work log. What survives is the
    distinct failures, which is the part worth reading later.
    """
    if not isinstance(content, list):
        return
    for block in content:
        if not isinstance(block, dict) or block.get("type") != "tool_result":
            continue
        if not block.get("is_error"):
            continue
        text = _tool_result_text(block.get("content"))
        if not text:
            continue
        # One line: a traceback's first line names the failure, and the rest
        # is a path listing that says nothing a reader wants six weeks later.
        text = _error_headline(text)
        if not text or text in result["errors_encountered"]:
            continue
        # Capped here rather than in `_finalize`, so the note about a truncated
        # transcript appended afterwards cannot be pushed out by error text.
        if len(result["errors_encountered"]) >= ERROR_LIMIT:
            continue
        result["errors_encountered"].append(text)


_EXIT_CODE_ONLY = re.compile(r"^exit code \d+\.?$", re.I)


def _error_headline(text):
    """The first line that says something.

    A failed shell call starts with `Exit code 1` and puts the reason on the
    next line, so taking the first line literally recorded "Exit code 1" nine
    times in one session — true, and useless to read six weeks later. The exit
    code is kept as a prefix when there is a reason to attach it to.
    """
    lines = [line.strip() for line in (text or "").strip().splitlines()]
    lines = [line for line in lines if line]
    if not lines:
        return ""
    if not _EXIT_CODE_ONLY.match(lines[0]):
        return lines[0][:ERROR_TEXT_LIMIT]
    if len(lines) == 1:
        return lines[0][:ERROR_TEXT_LIMIT]
    return ("%s: %s" % (lines[0].rstrip("."), lines[1]))[:ERROR_TEXT_LIMIT]


def _tool_result_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
            elif isinstance(block, str):
                parts.append(block)
        return " ".join(parts)
    return ""


def get_session_time_range(transcript_path):
    """Extract first and last timestamps from transcript.
    Returns (start_iso, end_iso) or (None, None).
    """
    start = None
    end = None

    if not transcript_path or not os.path.exists(transcript_path):
        return (None, None)

    try:
        with open(transcript_path, "r", encoding="utf-8", errors="replace") as f:
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
