"""`agent-diary diary-notion ops` -- read-only Notion operations report."""

import json
import sys
from datetime import datetime

from claude_diary.config import load_config
from claude_diary.lib import statuses
from claude_diary.log import configure_from_config
from claude_diary.cli.notion_common import (
    date_start_value as _date_start,
    plain_text as _plain_text,
    resolve_year_and_today as _resolve_year_and_today,
    select_value as _select,
    title_value as _title,
)
from claude_diary.cli.notion_push import _resolve_credentials, _print_setup_hint
from claude_diary.exporters.notion_hierarchical import (
    NotionHierarchicalExporter,
    NotionAuthError,
    NotionBadRequest,
    NotionNotFound,
    detect_subitem_relation,
)


DONE_STATUSES = statuses.DONE
PRIORITY_RANK = {"P0": 0, "P1": 1, "P2": 2, "P3": 3, "": 9}


def cmd_notion_ops(args):
    """Print a read-only operations report for the yearly Entries database."""
    config = load_config()
    configure_from_config(config)

    token, root_page_id = _resolve_credentials(config)
    if not token or not root_page_id:
        _print_setup_hint()
        sys.exit(1)

    year, today = _resolve_year_and_today(config, getattr(args, "year", None))
    stale_days = getattr(args, "stale_days", None)
    if stale_days is None:
        stale_days = 7
    json_output = getattr(args, "json_output", False) is True

    exporter = NotionHierarchicalExporter({
        "api_token": token,
        "root_page_id": root_page_id,
    })
    exporter.load_cache()

    try:
        db_id = exporter.resolve_existing_database(year)
        if not db_id:
            _print_missing_database(year, json_output)
            sys.exit(1)
        rows = exporter.query_database_rows(db_id)
        prop_map = exporter.get_database_property_map(db_id)
    except NotionAuthError as e:
        print("[agent-diary diary-notion ops] Auth error: %s" % e, file=sys.stderr)
        print("  Check: agent-diary config or run `agent-diary diary-notion init`", file=sys.stderr)
        sys.exit(1)
    except NotionNotFound as e:
        print("[agent-diary diary-notion ops] Not found: %s" % e, file=sys.stderr)
        print("  Check that the root page/database is shared with the integration.", file=sys.stderr)
        sys.exit(1)
    except NotionBadRequest as e:
        print("[agent-diary diary-notion ops] Bad request: %s" % e, file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print("[agent-diary diary-notion ops] Failed: %s" % e, file=sys.stderr)
        sys.exit(1)

    native = detect_subitem_relation(prop_map)
    parent_property_name = native["parent_name"] if native else "Parent Task"
    report = build_ops_report(rows, today, stale_days, parent_property_name)
    if json_output:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_ops_report(year, db_id, report)


def build_ops_report(rows, today, stale_days=7, parent_property_name="Parent Task"):
    """Build a read-only operations report from Notion page rows."""
    items = [_row_to_item(row, parent_property_name) for row in rows if not row.get("archived")]
    active = [item for item in items if not _is_done(item)]

    blocked = [item for item in active if item["blocked"]]
    needs_review = [item for item in active if item["review_status"] == "Needs Review"]
    missing_next_action = [
        item for item in active
        if item["status"] in statuses.IN_PROGRESS and not item["next_action"]
    ]
    stale = [
        item for item in active
        if _days_since(item["work_period_start"] or item["date"], today) is not None
        and _days_since(item["work_period_start"] or item["date"], today) >= stale_days
    ]
    verification_candidates = _verification_candidates(active)
    today_plan_candidates = _today_plan_candidates(active, today)

    parent_status_suggestions = _parent_status_suggestions(items)
    parent_progress = _parent_progress(items)
    task_groups = {}
    projects = {}
    for item in items:
        _accumulate_group(task_groups, item["task_group"] or "(no task group)", item)
        _accumulate_group(projects, item["project"] or "(no project)", item)

    task_groups = _finalize_groups(task_groups)
    projects = _finalize_groups(projects)

    return {
        "today": today,
        "stale_days": stale_days,
        "counts": {
            "total": len(items),
            "active": len(active),
            "blocked": len(blocked),
            "needs_review": len(needs_review),
            "missing_next_action": len(missing_next_action),
            "stale": len(stale),
            "verification_candidates": len(verification_candidates),
            "today_plan_candidates": len(today_plan_candidates),
            "parent_status_suggestions": len(parent_status_suggestions),
        },
        "blocked": _compact_items(blocked),
        "needs_review": _compact_items(needs_review),
        "missing_next_action": _compact_items(missing_next_action),
        "stale": _compact_items(stale),
        "verification_candidates": _compact_items(verification_candidates, include_reason=True),
        "today_plan_candidates": _compact_items(today_plan_candidates),
        "parent_status_suggestions": parent_status_suggestions,
        "parent_progress": parent_progress,
        "task_groups": task_groups,
        "projects": projects,
    }


def _row_to_item(row, parent_property_name="Parent Task"):
    props = row.get("properties") or {}
    return {
        "id": row.get("id", ""),
        "title": _title(props.get("Name")),
        "project": _select(props.get("Project")),
        "purpose": _select(props.get("Purpose")),
        "status": _select(props.get("Status")),
        "priority": _select(props.get("Priority")),
        "task_group": _select(props.get("Task Group")),
        "review_status": _select(props.get("Review Status")),
        "next_action": _rich_text(props.get("Next Action")),
        "blocked": _checkbox(props.get("Blocked")),
        "block_reason": _rich_text(props.get("Block Reason")),
        "date": _date_start(props.get("Date")),
        "work_period_start": _date_start(props.get("Work Period")),
        "parent_ids": _relation_ids(props.get(parent_property_name)),
        "url": row.get("url", ""),
    }


def _compact_items(items, limit=10, include_reason=False):
    result = []
    for item in items[:limit]:
        compact = {
            "title": item["title"],
            "project": item["project"],
            "task_group": item["task_group"],
            "status": item["status"],
            "priority": item["priority"],
            "next_action": item["next_action"],
            "block_reason": item["block_reason"],
            "work_period_start": item["work_period_start"],
            "url": item["url"],
        }
        if include_reason:
            compact["reason"] = item.get("reason", "")
        result.append(compact)
    return result


def _is_done(item):
    return item["status"] in DONE_STATUSES


def _accumulate_group(groups, name, item):
    entry = groups.setdefault(name, {
        "total": 0,
        "active": 0,
        "blocked": 0,
        "needs_review": 0,
        "done": 0,
        "first_worked_on": "",
        "last_worked_on": "",
        "_work_days": set(),
    })
    entry["total"] += 1
    if _is_done(item):
        entry["done"] += 1
    else:
        entry["active"] += 1
    if item["blocked"]:
        entry["blocked"] += 1
    if item["review_status"] == "Needs Review":
        entry["needs_review"] += 1
    work_day = (item["work_period_start"] or item["date"])[:10]
    if work_day:
        entry["_work_days"].add(work_day)
        if not entry["first_worked_on"] or work_day < entry["first_worked_on"]:
            entry["first_worked_on"] = work_day
        if not entry["last_worked_on"] or work_day > entry["last_worked_on"]:
            entry["last_worked_on"] = work_day


def _finalize_groups(groups):
    result = {}
    for name, entry in groups.items():
        finalized = dict(entry)
        work_days = finalized.pop("_work_days", set())
        finalized["work_days"] = len(work_days)
        finalized["done_ratio"] = _ratio(finalized["done"], finalized["total"])
        result[name] = finalized
    return result


def _parent_progress(items):
    by_id = {
        item["id"]: item
        for item in items
        if item["id"]
    }
    children_by_parent = {}
    for item in items:
        for parent_id in item["parent_ids"]:
            children_by_parent.setdefault(parent_id, []).append(item)

    progress = []
    for parent_id, children in children_by_parent.items():
        parent = by_id.get(parent_id)
        if not parent or not children:
            continue
        done = sum(1 for child in children if _is_done(child))
        blocked = sum(1 for child in children if child["blocked"])
        progress.append({
            "title": parent["title"],
            "project": parent["project"],
            "task_group": parent["task_group"],
            "status": parent["status"],
            "children": len(children),
            "done": done,
            "active": len(children) - done,
            "blocked": blocked,
            "done_ratio": _ratio(done, len(children)),
            "url": parent["url"],
        })
    return sorted(
        progress,
        key=lambda item: (
            item["done_ratio"],
            item["title"],
        ),
    )


def _parent_status_suggestions(items):
    by_id = {
        item["id"]: item
        for item in items
        if item["id"]
    }
    children_by_parent = {}
    for item in items:
        for parent_id in item["parent_ids"]:
            children_by_parent.setdefault(parent_id, []).append(item)

    suggestions = []
    for parent_id, children in children_by_parent.items():
        parent = by_id.get(parent_id)
        if not parent or not children:
            continue
        suggestion = _suggest_parent_status(parent, children)
        if suggestion:
            suggestions.append(suggestion)
    return suggestions


def _suggest_parent_status(parent, children):
    child_statuses = {child["status"] for child in children}
    if all(_is_done(child) for child in children):
        return _parent_suggestion(parent, "Deployed", "all child tasks are Deployed", children)
    if any(child["blocked"] for child in children):
        if parent["blocked"]:
            return None
        return _parent_suggestion(parent, parent["status"] or "Implementation",
                                  "at least one child task is blocked", children)
    if "Testing" in child_statuses and parent["status"] not in ("Testing", "Deployed"):
        return _parent_suggestion(parent, "Testing", "at least one child task is in Testing", children)
    if "Implementation" in child_statuses and (
            not parent["status"] or parent["status"] in statuses.EARLY):
        return _parent_suggestion(parent, "Implementation", "at least one child task is in Implementation", children)
    return None


def _parent_suggestion(parent, suggested_status, reason, children):
    return {
        "title": parent["title"],
        "project": parent["project"],
        "task_group": parent["task_group"],
        "status": parent["status"],
        "suggested_status": suggested_status,
        "reason": reason,
        "child_count": len(children),
        "url": parent["url"],
    }


def _ratio(part, total):
    if not total:
        return 0.0
    return round(float(part) / float(total), 4)


def _today_plan_candidates(items, today):
    candidates = []
    for item in items:
        if item["blocked"] or not item["next_action"]:
            continue
        age = _days_since(item["work_period_start"] or item["date"], today)
        if age is None or age <= 0:
            continue
        candidate = dict(item)
        candidate["age_days"] = age
        candidates.append(candidate)
    return sorted(
        candidates,
        key=lambda item: (
            PRIORITY_RANK.get(item["priority"], 9),
            -item["age_days"],
            item["title"],
        ),
    )


def _verification_candidates(items):
    candidates = []
    for item in items:
        if item["blocked"] or item["status"] not in statuses.IN_PROGRESS:
            continue
        reasons = []
        if item["review_status"] != "Reviewed":
            reasons.append("review_status_not_reviewed")
        if item["status"] == "Testing" and not item["next_action"]:
            reasons.append("testing_without_next_action")
        if item["status"] == "Implementation" and item["review_status"] in ("", "Deferred"):
            reasons.append("implementation_review_deferred")
        if not reasons:
            continue
        candidate = dict(item)
        candidate["reason"] = ", ".join(reasons)
        candidates.append(candidate)
    return sorted(
        candidates,
        key=lambda item: (
            item["status"] != "Testing",
            PRIORITY_RANK.get(item["priority"], 9),
            item["title"],
        ),
    )


def _days_since(date_str, today):
    if not date_str:
        return None
    try:
        start = datetime.strptime(date_str[:10], "%Y-%m-%d").date()
        end = datetime.strptime(today[:10], "%Y-%m-%d").date()
    except ValueError:
        return None
    return (end - start).days


def _rich_text(prop):
    values = (prop or {}).get("rich_text") or []
    return "".join(_plain_text(item) for item in values).strip()


def _checkbox(prop):
    return bool((prop or {}).get("checkbox"))


def _relation_ids(prop):
    return [
        item.get("id")
        for item in (prop or {}).get("relation") or []
        if item.get("id")
    ]


def _print_missing_database(year, json_output):
    if json_output:
        print(json.dumps({
            "year": year,
            "error": "database_missing",
        }, ensure_ascii=False, indent=2))
        return
    print("[agent-diary diary-notion ops]")
    print("Year: %s" % year)
    print("Database: missing")
    print("Run `agent-diary diary-notion ensure --year %s` first." % year)


def _print_ops_report(year, db_id, report):
    counts = report["counts"]
    print("[agent-diary diary-notion ops]")
    print("Year: %s" % year)
    print("Database: %s" % db_id)
    print("Rows: %d total, %d active" % (counts["total"], counts["active"]))
    print("Signals:")
    print("  Blocked: %d" % counts["blocked"])
    print("  Needs review: %d" % counts["needs_review"])
    print("  Missing next action: %d" % counts["missing_next_action"])
    print("  Stale >= %d day(s): %d" % (report["stale_days"], counts["stale"]))
    print("  Verification candidates: %d" % counts["verification_candidates"])
    print("  Today-plan candidates: %d" % counts["today_plan_candidates"])
    print("  Parent status suggestions: %d" % counts["parent_status_suggestions"])
    _print_section("Blocked", report["blocked"])
    _print_section("Needs Review", report["needs_review"])
    _print_section("Missing Next Action", report["missing_next_action"])
    _print_section("Stale Work", report["stale"])
    _print_section("Today Plan Candidates", report["today_plan_candidates"])
    _print_parent_progress(report["parent_progress"])
    _print_parent_status_suggestions(report["parent_status_suggestions"])
    _print_group_summary(report["task_groups"])
    _print_project_summary(report["projects"])


def _print_section(name, items):
    if not items:
        return
    print("%s:" % name)
    for item in items:
        suffix = []
        if item["project"]:
            suffix.append(item["project"])
        if item["task_group"]:
            suffix.append(item["task_group"])
        if item["status"]:
            suffix.append(item["status"])
        detail = " | ".join(suffix)
        print("  - %s%s" % (item["title"], " (%s)" % detail if detail else ""))
        if item.get("reason"):
            print("    reason: %s" % item["reason"])
        if item["next_action"]:
            print("    next: %s" % item["next_action"])
        if item["block_reason"]:
            print("    blocked: %s" % item["block_reason"])


def _print_group_summary(groups):
    if not groups:
        return
    print("Task Groups:")
    for name in sorted(groups):
        data = groups[name]
        print(
            "  - %s: %d total, %d active, %d done, %d blocked, %d review, %d work day(s)%s" %
            (
                name,
                data["total"],
                data["active"],
                data["done"],
                data["blocked"],
                data["needs_review"],
                data["work_days"],
                _period_suffix(data),
            )
        )


def _print_project_summary(projects):
    if not projects:
        return
    print("Projects:")
    for name in sorted(projects):
        data = projects[name]
        print(
            "  - %s: %d total, %d active, %d done, %d work day(s)%s" %
            (
                name,
                data["total"],
                data["active"],
                data["done"],
                data["work_days"],
                _period_suffix(data),
            )
        )


def _print_parent_status_suggestions(items):
    if not items:
        return
    print("Parent Status Suggestions:")
    for item in items:
        detail = []
        if item["project"]:
            detail.append(item["project"])
        if item["task_group"]:
            detail.append(item["task_group"])
        suffix = " (%s)" % " | ".join(detail) if detail else ""
        print(
            "  - %s%s: %s -> %s (%s, %d child task(s))" %
            (
                item["title"],
                suffix,
                item["status"] or "(unset)",
                item["suggested_status"],
                item["reason"],
                item["child_count"],
            )
        )


def _print_parent_progress(items):
    if not items:
        return
    print("Parent Progress:")
    for item in items:
        detail = []
        if item["project"]:
            detail.append(item["project"])
        if item["task_group"]:
            detail.append(item["task_group"])
        suffix = " (%s)" % " | ".join(detail) if detail else ""
        percent = int(round(item["done_ratio"] * 100))
        print(
            "  - %s%s: %d/%d done, %d active, %d blocked (%d%%)" %
            (
                item["title"],
                suffix,
                item["done"],
                item["children"],
                item["active"],
                item["blocked"],
                percent,
            )
        )


def _period_suffix(data):
    if not data.get("first_worked_on"):
        return ""
    if data.get("first_worked_on") == data.get("last_worked_on"):
        return ", %s" % data["first_worked_on"]
    return ", %s..%s" % (data["first_worked_on"], data["last_worked_on"])
