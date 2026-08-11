"""`agent-diary doctor` — check that the thing is actually still recording.

This exists because of a specific failure this project has already had, twice
over, in two different forms.

The 2026-08-07 incident went unnoticed for two months partly because the
write reported success and only history went quiet — and, as the postmortem
puts it, a diary that is not being written looks exactly like a quiet day.
Then during the rename to `agent-diary` the import package was very nearly
renamed too, which would have left `python -m claude_diary.hook` in every
user's settings.json pointing at nothing: the Stop Hook would have stopped
without an error, and the only symptom would have been an empty diary.

Same class of failure both times, and until now nothing looked for it. Every
check here answers one question: *would I find out if this quietly stopped?*

Exit code is 1 if anything failed, so it can be wired into a cron or a
pre-flight without parsing the output.
"""

from __future__ import annotations

import importlib.util
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, NamedTuple

from claude_diary.config import get_config_path, load_config
from claude_diary.log import configure_from_config, get_logger

logger = get_logger("claude_diary.cli.doctor")

OK = "ok"
WARN = "warn"
FAIL = "fail"

_MARK = {OK: "[ ok ]", WARN: "[warn]", FAIL: "[fail]"}

# How long a gap in the diary is worth mentioning. Long enough that a weekend
# or a holiday does not cry wolf, short enough that a dead hook surfaces
# before two months of history is missing.
STALE_AFTER_DAYS = 7


class Check(NamedTuple):
    status: str
    title: str
    detail: str
    fix: str = ""


def cmd_doctor(args) -> None:
    config = load_config()
    configure_from_config(config)

    checks: List[Check] = []
    checks.append(_check_config())
    checks.append(_check_module_importable())
    checks.append(_check_hook_registered())
    checks.append(_check_diary_dir(config))
    checks.append(_check_recent_activity(config))
    checks.extend(_check_notion(config, verbose=getattr(args, "notion", False)))

    print("[agent-diary doctor]")
    for c in checks:
        print("%s %-34s %s" % (_MARK[c.status], c.title, c.detail))
        if c.fix and c.status != OK:
            print("       -> %s" % c.fix)

    failed = [c for c in checks if c.status == FAIL]
    warned = [c for c in checks if c.status == WARN]
    print()
    print("  %d ok, %d warning(s), %d failure(s)" % (
        len(checks) - len(failed) - len(warned), len(warned), len(failed)))

    if failed:
        raise SystemExit(1)


def _check_config() -> Check:
    path = get_config_path()
    if not os.path.exists(path):
        return Check(FAIL, "config", "not found at %s" % path,
                     "run: agent-diary init")
    if not os.access(path, os.R_OK):
        return Check(FAIL, "config", "not readable: %s" % path,
                     "check file permissions")
    return Check(OK, "config", path)


def _check_module_importable() -> Check:
    """The hook command names a module by string. Confirm it resolves.

    A package rename, a moved virtualenv, or an uninstall all break this
    while leaving the hook entry in settings.json intact and silent.
    """
    try:
        spec = importlib.util.find_spec("claude_diary.hook")
    except Exception as e:
        return Check(FAIL, "hook module", "import failed: %s" % e,
                     "reinstall: pip install --upgrade agent-diary")
    if spec is None:
        return Check(FAIL, "hook module", "claude_diary.hook not importable",
                     "reinstall: pip install --upgrade agent-diary")
    return Check(OK, "hook module", "claude_diary.hook")


def _check_hook_registered() -> Check:
    from claude_diary.cli.setup import (
        HOOK_COMMAND,
        _find_existing_hook,
        _get_claude_settings_path,
        _load_claude_settings,
    )

    path = _get_claude_settings_path()
    if not os.path.exists(path):
        return Check(WARN, "stop hook", "no Claude Code settings at %s" % path,
                     "Codex-only setups can ignore this")
    settings = _load_claude_settings(path)
    existing = _find_existing_hook(settings)
    if not existing:
        return Check(FAIL, "stop hook", "not registered in settings.json",
                     "run: agent-diary install --force")
    command = existing.get("command", "") if isinstance(existing, dict) else str(existing)
    if command.strip() != HOOK_COMMAND:
        return Check(WARN, "stop hook", "registered, but the command differs: %s" % command,
                     "run: agent-diary install --force to refresh it")
    return Check(OK, "stop hook", HOOK_COMMAND)


def _check_diary_dir(config) -> Check:
    diary_dir = os.path.expanduser(config.get("diary_dir", "~/working-diary"))
    if not os.path.isdir(diary_dir):
        return Check(WARN, "diary directory", "does not exist yet: %s" % diary_dir,
                     "it is created on the first entry")
    if not os.access(diary_dir, os.W_OK):
        return Check(FAIL, "diary directory", "not writable: %s" % diary_dir,
                     "check permissions; entries are being dropped")
    count = len(list(Path(diary_dir).glob("*.md")))
    return Check(OK, "diary directory", "%s (%d day file(s))" % (diary_dir, count))


def _check_recent_activity(config) -> Check:
    """The check this command exists for.

    Everything else can pass while the diary quietly stops filling in. The
    only way to notice that is to look at how long it has been.
    """
    diary_dir = os.path.expanduser(config.get("diary_dir", "~/working-diary"))
    latest = _latest_entry_date(diary_dir)
    if latest is None:
        return Check(WARN, "recent activity", "no entries yet",
                     "end a Claude Code session, or run: agent-diary backfill")

    tz_offset = config.get("timezone_offset", 9)
    today = datetime.now(timezone(timedelta(hours=tz_offset))).date()
    age = (today - latest).days
    if age > STALE_AFTER_DAYS:
        return Check(
            WARN, "recent activity",
            "last entry %s, %d days ago" % (latest.isoformat(), age),
            "if you have been working, the hook may have stopped: "
            "agent-diary install --force",
        )
    return Check(OK, "recent activity", "last entry %s" % latest.isoformat())


def _latest_entry_date(diary_dir: str):
    """Newest YYYY-MM-DD.md in the diary, by filename rather than mtime.

    mtime moves when a file is touched for any reason; the name is what the
    entry actually claims about itself.
    """
    if not os.path.isdir(diary_dir):
        return None
    newest = None
    for path in Path(diary_dir).glob("*.md"):
        try:
            parsed = datetime.strptime(path.stem, "%Y-%m-%d").date()
        except ValueError:
            continue
        if newest is None or parsed > newest:
            newest = parsed
    return newest


def _check_notion(config, verbose: bool = False) -> List[Check]:
    from claude_diary.cli.notion_push import _resolve_credentials

    token, root_page_id = _resolve_credentials(config)
    if not token or not root_page_id:
        return [Check(OK, "notion", "not configured (optional)")]

    checks = [Check(OK, "notion credentials", "token and root page id present")]
    if not verbose:
        checks.append(Check(
            OK, "notion reachability", "not checked",
            "pass --notion to make a read-only request",
        ))
        return checks

    # Imported before the try: `except NotionAuthError` would raise NameError
    # if the import itself were the thing that failed.
    from claude_diary.exporters.notion_hierarchical import (
        NotionAuthError,
        NotionHierarchicalExporter,
    )
    from claude_diary.lib import notion_cache

    try:
        exporter = NotionHierarchicalExporter({
            "api_token": token,
            "root_page_id": root_page_id,
        })
        exporter.load_cache()
        # Read-only, and never through ensure_database — that creates the
        # year page and the database when they are missing, which a health
        # check has no business doing.
        year = datetime.now().year
        db_id = notion_cache.get_database(exporter._cache, year)
        if not db_id:
            checks.append(Check(
                WARN, "notion database", "no cached database for %d" % year,
                "run: agent-diary diary-notion ensure",
            ))
            return checks
        exporter._request("GET", "/databases/%s" % db_id)
        checks.append(Check(OK, "notion database", "%d reachable" % year))
    except NotionAuthError as e:
        checks.append(Check(FAIL, "notion", "auth rejected: %s" % e,
                            "the integration token may have been revoked"))
    except Exception as e:
        checks.append(Check(FAIL, "notion", "unreachable: %s" % e,
                            "check the network and the integration's page access"))
    return checks


__all__ = ["cmd_doctor"]
