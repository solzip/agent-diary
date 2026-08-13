"""`agent-diary try` — run the real Stop Hook against a transcript, safely.

Seeing what this tool would record used to mean letting it record. The obvious
approach, exporting `CLAUDE_DIARY_DIR` and running the hook, does not work:
`config.json` wins over the environment by design, so the diary path stays
whatever `init` wrote and the trial run lands in the real diary. Doing that by
accident is not hypothetical — it happened twice while building this, once
into a diary with five months of history in it.

So this spawns `python -m claude_diary.hook`, the exact entry point Claude Code
calls, with three variables pointed at a temporary directory:

    APPDATA / XDG_CONFIG_HOME   so no config.json is found
    CLAUDE_DIARY_DIR            so the diary lands in the sandbox

With no config there are no exporters, which is the part that matters most: a
trial run must not push a row to somebody's Notion database.

The entry is printed and the directory removed. Nothing outside it is written.
"""

import io
import json
import os
import shutil
import subprocess
import sys
import tempfile


def cmd_try(args):
    """Show what the hook would record for a transcript, writing nothing."""
    transcript = _resolve_transcript(args)
    if not transcript:
        return 1

    print("[agent-diary try] transcript: %s" % transcript)
    print("[agent-diary try] %d line(s), %.1f MB" % (
        _line_count(transcript), os.path.getsize(transcript) / 1e6,
    ))

    sandbox = tempfile.mkdtemp(prefix="agent-diary-try-")
    try:
        entry = _run_hook(sandbox, transcript, args)
        if entry is None:
            print("[agent-diary try] The hook recorded nothing for this transcript.")
            print("  A session with no prompts, files, or commands is skipped by design.")
            return 0
        print()
        print(entry.rstrip())
        print()
        print("[agent-diary try] Nothing was written outside the sandbox.")
        return 0
    finally:
        shutil.rmtree(sandbox, ignore_errors=True)


def _run_hook(sandbox, transcript, args):
    config_home = os.path.join(sandbox, "config-home")
    diary = os.path.join(sandbox, "diary")
    os.makedirs(config_home)
    os.makedirs(diary)

    env = dict(os.environ)
    env["APPDATA"] = config_home           # Windows
    env["XDG_CONFIG_HOME"] = config_home   # Linux, macOS
    env["CLAUDE_DIARY_DIR"] = diary
    env["CLAUDE_DIARY_MANUAL_DIR"] = os.path.join(diary, "manual")
    env["PYTHONIOENCODING"] = "utf-8"

    payload = json.dumps({
        "session_id": getattr(args, "session_id", None) or "try-run",
        "transcript_path": os.path.abspath(transcript),
        "cwd": os.path.abspath(getattr(args, "cwd", None) or os.getcwd()),
    })

    result = subprocess.run(
        [sys.executable, "-m", "claude_diary.hook"],
        input=payload, env=env, cwd=os.getcwd(),
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    stderr = (result.stderr or "").strip()
    if stderr:
        for line in stderr.splitlines():
            print("  %s" % line)

    return _read_entry(diary)


def _read_entry(diary):
    for name in sorted(os.listdir(diary)):
        if not name.endswith(".md"):
            continue
        text = io.open(os.path.join(diary, name), encoding="utf-8", errors="replace").read()
        marker = text.find("### ")
        if marker >= 0:
            return text[marker:]
    return None


def _resolve_transcript(args):
    given = getattr(args, "transcript", None)
    if given:
        if os.path.isfile(given):
            return given
        print("[agent-diary try] No such transcript: %s" % given, file=sys.stderr)
        return None

    # Default to this project's most recent transcript, which is almost always
    # the one someone wants to look at.
    latest = _latest_transcript_for_cwd()
    if latest:
        return latest
    print("[agent-diary try] No transcript found for this directory.", file=sys.stderr)
    print("  Pass one: agent-diary try <path to .jsonl>", file=sys.stderr)
    return None


def _latest_transcript_for_cwd():
    """The newest transcript whose own `cwd` is this directory.

    Not by directory name. Claude Code encodes the project path into the folder
    name by replacing separators, and every character outside ASCII collapses
    to a dash as well — `C:\\Users\\윤솔\\Desktop\\개인\\sol\\working-diary`
    becomes `C--Users----Desktop----sol-working-diary`, which cannot be matched
    back to the path it came from. The transcript records its `cwd` in the
    first few lines, so that is what gets compared.
    """
    root = os.path.expanduser(os.path.join("~", ".claude", "projects"))
    if not os.path.isdir(root):
        return None

    here = os.path.normcase(os.path.abspath(os.getcwd()))
    candidates = []
    for directory, _dirs, files in os.walk(root):
        for name in files:
            if name.endswith(".jsonl"):
                candidates.append(os.path.join(directory, name))

    # Newest first, so the usual case stops after one file.
    for path in sorted(candidates, key=os.path.getmtime, reverse=True):
        if _transcript_cwd(path) == here:
            return path
    return None


def _transcript_cwd(path, scan_lines=40):
    try:
        with io.open(path, encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f):
                if i >= scan_lines:
                    return None
                if '"cwd"' not in line:
                    continue
                try:
                    value = json.loads(line).get("cwd")
                except ValueError:
                    continue
                if value:
                    return os.path.normcase(os.path.abspath(value))
    except OSError:
        return None
    return None


def _line_count(path):
    with io.open(path, encoding="utf-8", errors="replace") as f:
        return sum(1 for _ in f)
