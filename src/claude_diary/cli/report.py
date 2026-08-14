"""`agent-diary report` — one document for a period, for someone else to read.

The existing commands answer questions. `search` finds an entry, `stats`
counts things, `weekly` summarises the current week and takes no arguments.
None of them produce the thing people actually need on a recurring basis: a
document covering a chosen period and project, for a standup, a monthly
report, an invoice, or evidence of what a stretch of work consisted of.

Two sources, joined on session id:

- the search index carries one record per session — date, project,
  categories, files, line counts — and is the authority on *which* sessions
  fall in range
- the day files carry the narrative, and are split per entry so a report
  filtered to one project does not inherit another project's prose

`parse_daily_file` is deliberately not reused here: it aggregates a whole
day at once, so on a day spanning three projects it cannot say which
sentence belongs to which.
"""

from __future__ import annotations

import json
import os
import re
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from claude_diary.config import load_config, resolve_diary_dir
from claude_diary.log import configure_from_config, get_logger

logger = get_logger("claude_diary.cli.report")

# Entries begin with the time/project heading the formatter writes.
_ENTRY_SPLIT = re.compile(r"^### ", re.M)
_SESSION_ID = re.compile(r"^<code>([0-9A-Za-z][0-9A-Za-z._-]{7,})</code>\s*$", re.M)
_TASK_REQUESTS = re.compile(
    r"(?:작업 요청|Task Requests).*?\n((?:\s+\d+\. .+\n?)+)"
)
_WORK_SUMMARY = re.compile(
    r"(?:작업 요약|Work Summary).*?\n((?:\s+- .+\n?)+)"
)


def cmd_report(args) -> None:
    config = load_config()
    configure_from_config(config)
    lang = config.get("lang", "ko")
    diary_dir = resolve_diary_dir(config)

    try:
        start, end = _resolve_period(args)
    except ValueError as e:
        print("[agent-diary report] %s" % e)
        raise SystemExit(2) from None

    entries = _load_entries(diary_dir, start, end, getattr(args, "project", None))
    if not entries:
        print("[agent-diary report] No sessions between %s and %s%s." % (
            start.isoformat(), end.isoformat(),
            " for project %s" % args.project if getattr(args, "project", None) else "",
        ))
        return

    narrative = _load_narrative(diary_dir, start, end)
    for e in entries:
        e["narrative"] = narrative.get(e.get("session_id"), {})

    if getattr(args, "json", False):
        payload = _as_payload(entries, start, end)
        text = json.dumps(payload, ensure_ascii=False, indent=2)
    else:
        text = _render(entries, start, end, lang, getattr(args, "detail", False))

    out = getattr(args, "output", None)
    if out:
        path = Path(os.path.expanduser(out))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        print("[agent-diary report] %d session(s) -> %s" % (len(entries), path))
    else:
        print(text)


def _resolve_period(args):
    """Work out the window. Exactly one selector, defaulting to the last 7 days."""
    month = getattr(args, "month", None)
    days = getattr(args, "days", None)
    date_from = getattr(args, "date_from", None)
    date_to = getattr(args, "date_to", None)

    chosen = [bool(month), bool(days), bool(date_from or date_to)]
    if sum(chosen) > 1:
        raise ValueError("choose one of --month, --days, or --from/--to")

    if month:
        try:
            first = datetime.strptime(str(month).strip(), "%Y-%m").date()
        except ValueError:
            raise ValueError("--month must be YYYY-MM") from None
        nxt = date(first.year + (first.month == 12), (first.month % 12) + 1, 1)
        return first, nxt - timedelta(days=1)

    if days:
        try:
            n = int(days)
        except (TypeError, ValueError):
            raise ValueError("--days must be a number") from None
        if n < 1:
            raise ValueError("--days must be at least 1")
        today = date.today()
        return today - timedelta(days=n - 1), today

    if date_from or date_to:
        start = _parse_date(date_from) if date_from else date(1970, 1, 1)
        end = _parse_date(date_to) if date_to else date.today()
        if start > end:
            raise ValueError("--from is after --to")
        return start, end

    today = date.today()
    return today - timedelta(days=6), today


def _parse_date(raw):
    try:
        return datetime.strptime(str(raw).strip(), "%Y-%m-%d").date()
    except ValueError:
        raise ValueError("dates must be YYYY-MM-DD") from None


def _load_entries(diary_dir: str, start: date, end: date,
                  project: Optional[str]) -> List[dict]:
    """Sessions in range, from the search index."""
    index_path = os.path.join(diary_dir, ".diary_index.json")
    if not os.path.exists(index_path):
        return []
    try:
        with open(index_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        logger.warning("Search index unreadable: %s", index_path)
        return []

    records = data.get("entries", data) if isinstance(data, dict) else data
    if not isinstance(records, list):
        return []

    out = []
    for rec in records:
        if not isinstance(rec, dict):
            continue
        raw = rec.get("date")
        try:
            when = datetime.strptime(str(raw), "%Y-%m-%d").date()
        except (TypeError, ValueError):
            continue
        if when < start or when > end:
            continue
        if project and rec.get("project") != project:
            continue
        out.append(dict(rec))
    out.sort(key=lambda r: (r.get("date", ""), r.get("time", "")))
    return out


def _load_narrative(diary_dir: str, start: date, end: date) -> Dict[str, dict]:
    """Task requests and work summary per session id.

    Day files are split per entry so a report filtered to one project does
    not pick up another project's sentences from the same day.
    """
    found: Dict[str, dict] = {}
    if not os.path.isdir(diary_dir):
        return found
    for path in sorted(Path(diary_dir).glob("*.md")):
        try:
            when = datetime.strptime(path.stem, "%Y-%m-%d").date()
        except ValueError:
            continue
        if when < start or when > end:
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for chunk in _ENTRY_SPLIT.split(content):
            match = _SESSION_ID.search(chunk)
            if not match:
                continue
            found[match.group(1)] = {
                "requests": _bullets(_TASK_REQUESTS, chunk, r"\d+\. (.+)"),
                "summary": _bullets(_WORK_SUMMARY, chunk, r"- (.+)"),
            }
    return found


def _bullets(block_re, text, item_pattern) -> List[str]:
    out: List[str] = []
    for block in block_re.findall(text):
        out.extend(re.findall(item_pattern, block))
    return [s.strip() for s in out if s.strip()]


# Harness bookkeeping that ends up in a prompt but is not something anyone
# did. Dropping it is safe; it never carries content.
_NOISE = (
    "[Request interrupted",
    "<local-command-caveat>",
    "<command-name>",
    "<command-message>",
    "Caveat: The messages below were generated",
)

# Below this a line is an instruction to the agent rather than a description
# of work — "2번으로 가자", "ㄱㄱ".
_MIN_USEFUL_CHARS = 12

# Per day, so one busy day cannot bury the rest of the period.
_ITEMS_PER_DAY = 8


def _is_reportable(line: str) -> bool:
    text = (line or "").strip()
    if len(text) < _MIN_USEFUL_CHARS:
        return False
    return not any(text.startswith(n) or n in text for n in _NOISE)


def _totals(entries: List[dict]) -> dict:
    days = {e.get("date") for e in entries if e.get("date")}
    projects = Counter(e.get("project") or "unknown" for e in entries)
    categories: Counter = Counter()
    files = 0
    added = deleted = 0
    commits = 0
    for e in entries:
        categories.update(e.get("categories") or [])
        files += len(e.get("files") or [])
        added += int(e.get("lines_added") or 0)
        deleted += int(e.get("lines_deleted") or 0)
        commits += len(e.get("git_commits") or [])
    return {
        "sessions": len(entries),
        "days": len(days),
        "projects": projects,
        "categories": categories,
        "files": files,
        "added": added,
        "deleted": deleted,
        "commits": commits,
    }


def _render(entries: List[dict], start: date, end: date, lang: str,
            detail: bool = False) -> str:
    t = _totals(entries)
    lines: List[str] = []
    title = "작업 보고" if lang == "ko" else "Work report"
    lines.append("# %s — %s ~ %s" % (title, start.isoformat(), end.isoformat()))
    lines.append("")
    lines.append("%d session(s) · %d day(s) · %d project(s) · +%d / -%d lines · %d file(s) · %d commit(s)"
                 % (t["sessions"], t["days"], len(t["projects"]),
                    t["added"], t["deleted"], t["files"], t["commits"]))
    if t["categories"]:
        lines.append("")
        lines.append(" · ".join("`%s` %d" % (name, n)
                                for name, n in t["categories"].most_common()))

    by_project: Dict[str, List[dict]] = defaultdict(list)
    for e in entries:
        by_project[e.get("project") or "unknown"].append(e)

    for project, items in sorted(by_project.items(),
                                 key=lambda kv: (-len(kv[1]), kv[0])):
        lines.append("")
        lines.append("## %s — %d session(s)" % (project, len(items)))
        by_day: Dict[str, List[dict]] = defaultdict(list)
        for e in items:
            by_day[e.get("date") or "?"].append(e)

        wrote_any = False
        for day, day_items in sorted(by_day.items()):
            said, source = _day_lines(day_items, detail)
            if not said:
                continue
            wrote_any = True
            lines.append("")
            lines.append("### %s" % day)
            shown = said[:_ITEMS_PER_DAY]
            for item in shown:
                lines.append("- %s" % item)
            if len(said) > len(shown):
                lines.append("- _… %d more, see the diary for %s_"
                             % (len(said) - len(shown), day))
            if source == "requests":
                lines.append("")
                lines.append("_No work summary was recorded for this day; "
                             "the lines above are the requests as typed._")
        if not wrote_any:
            lines.append("")
            lines.append("_Sessions recorded, but no summaries or requests were "
                         "captured for them._")
    lines.append("")
    return "\n".join(lines)


def _day_lines(day_items: List[dict], detail: bool):
    """Lines for one day, and which source they came from.

    The work summary is the synthesised record and is what a report wants.
    Raw requests are the unedited input — long, sometimes truncated, and
    occasionally just "2번으로 가자". They are the fallback when nothing was
    summarised, and are included alongside only with `--detail`.
    """
    summaries: List[str] = []
    requests: List[str] = []
    for e in day_items:
        narrative = e.get("narrative") or {}
        summaries.extend(x for x in (narrative.get("summary") or [])
                         if _is_reportable(x))
        requests.extend(x for x in (narrative.get("requests") or [])
                        if _is_reportable(x))

    if summaries and detail:
        return _dedupe(summaries + requests), "summary"
    if summaries:
        return _dedupe(summaries), "summary"
    return _dedupe(requests), "requests"


def _dedupe(items: List[str]) -> List[str]:
    seen = set()
    out = []
    for item in items:
        key = item.strip().lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(item.strip())
    return out


def _as_payload(entries: List[dict], start: date, end: date) -> dict:
    t = _totals(entries)
    return {
        "from": start.isoformat(),
        "to": end.isoformat(),
        "sessions": t["sessions"],
        "days": t["days"],
        "lines_added": t["added"],
        "lines_deleted": t["deleted"],
        "files": t["files"],
        "commits": t["commits"],
        "projects": dict(t["projects"]),
        "categories": dict(t["categories"]),
        "entries": entries,
    }


__all__ = ["cmd_report"]
