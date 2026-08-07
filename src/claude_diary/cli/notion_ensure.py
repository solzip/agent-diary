"""`claude-diary diary-notion ensure` -- ensure Notion DB schema and core views."""

import sys

from claude_diary.config import load_config
from claude_diary.log import configure_from_config
from claude_diary.cli.notion_common import resolve_year_and_today as _resolve_year_and_today
from claude_diary.cli.notion_push import _resolve_credentials, _print_setup_hint
from claude_diary.exporters.notion_hierarchical import (
    NotionHierarchicalExporter,
    NotionAuthError,
    NotionBadRequest,
    NotionNotFound,
    SCHEMA_VERSION,
)
from claude_diary.exporters.notion_views import (
    CORE_VIEW_NAMES,
    OPERATION_VIEW_NAMES,
    CoreViewsEnsurer,
    NotionViewsClient,
)


def cmd_notion_ensure(args):
    """Ensure the current year's hierarchical Notion DB and guaranteed views."""
    config = load_config()
    configure_from_config(config)

    token, root_page_id = _resolve_credentials(config)
    if not token or not root_page_id:
        _print_setup_hint()
        sys.exit(1)

    year, today = _resolve_year_and_today(config, getattr(args, "year", None))
    dry_run = getattr(args, "dry_run", False) is True

    exporter = NotionHierarchicalExporter({
        "api_token": token,
        "root_page_id": root_page_id,
    })
    exporter.load_cache()

    try:
        if dry_run:
            db_id = exporter.resolve_existing_database(year)
            if not db_id:
                _print_missing_database_plan(root_page_id, year)
                return
            schema_status = "%s would be verified" % SCHEMA_VERSION
        else:
            db_id = exporter.ensure_database(year, force_schema=True)
            exporter.save_cache()
            schema_status = "%s ensured" % SCHEMA_VERSION

        client = NotionViewsClient({"api_token": token})
        result = CoreViewsEnsurer(client).ensure(db_id, today, dry_run=dry_run)
    except NotionAuthError as e:
        print("[working-diary diary-notion ensure] Auth error: %s" % e, file=sys.stderr)
        print("  Check: claude-diary config or run `claude-diary diary-notion init`", file=sys.stderr)
        sys.exit(1)
    except NotionNotFound as e:
        print("[working-diary diary-notion ensure] Not found: %s" % e, file=sys.stderr)
        print("  Check that the root page/database is shared with the integration.", file=sys.stderr)
        sys.exit(1)
    except NotionBadRequest as e:
        print("[working-diary diary-notion ensure] Bad request: %s" % e, file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print("[working-diary diary-notion ensure] Failed: %s" % e, file=sys.stderr)
        sys.exit(1)

    _print_ensure_report(root_page_id, year, db_id, schema_status, result, dry_run)
    if not result.ok():
        sys.exit(1)


def _print_missing_database_plan(root_page_id, year):
    print("[working-diary diary-notion ensure --dry-run]")
    print("Root page: %s" % root_page_id)
    print("Year: %s" % year)
    print("Database: missing")
    print("Plan:")
    print("  + create year page if missing")
    print("  + create Entries DB")
    print("  + ensure schema %s" % SCHEMA_VERSION)
    print("  + create %d core views" % len(CORE_VIEW_NAMES))
    print("  + create %d operating views" % len(OPERATION_VIEW_NAMES))


def _print_ensure_report(root_page_id, year, db_id, schema_status, result, dry_run):
    suffix = " --dry-run" if dry_run else ""
    print("[working-diary diary-notion ensure%s]" % suffix)
    print("Root page: %s" % root_page_id)
    print("Year: %s" % year)
    print("Database: %s" % db_id)
    print("Schema: %s" % schema_status)
    print("Views:")
    for name in result.created:
        print("  + %s" % name)
    for name in result.updated:
        print("  ~ %s (updated)" % name)
    for name in result.planned:
        print("  + %s (planned)" % name)
    for name in result.updates_planned:
        print("  ~ %s (update planned)" % name)
    for name in result.verified:
        print("  = %s (verified)" % name)
    for conflict in result.conflicts:
        plan = build_conflict_plan(conflict.name, conflict.reason)
        print("  x %s -- conflict[%s]: %s" % (
            conflict.name,
            plan["category"],
            conflict.reason,
        ))
        print("    action: %s" % plan["action"])
        print("    apply: %s" % ("yes" if plan["apply_supported"] else "manual"))
    for failure in result.failed:
        plan = build_conflict_plan(failure.name, failure.reason)
        print("  ! %s -- %s [%s]" % (
            failure.name,
            failure.reason,
            plan["category"],
        ))
        print("    action: %s" % plan["action"])
        print("    apply: %s" % ("yes" if plan["apply_supported"] else "manual"))
    if result.repaired:
        print("Sub-item sync:")
        for entry in result.repaired:
            print("  ~ %s" % entry)
    if result.warnings:
        print("Warnings:")
        for warning in result.warnings:
            plan = build_conflict_plan("warning", warning)
            print("  ! %s [%s]" % (warning, plan["category"]))
            print("    action: %s" % plan["action"])
            print("    apply: %s" % ("yes" if plan["apply_supported"] else "manual"))


def build_conflict_plan(name, reason):
    """Return a structured read-only repair plan for an ensure problem."""
    category = classify_conflict_reason(reason)
    if category == "missing_filter":
        return _plan(name, reason, category,
                     "rerun `working-diary diary-notion ensure` to repair the view filter", True)
    if category == "missing_property":
        return _plan(name, reason, category,
                     "rerun `working-diary diary-notion ensure` to add the missing schema property", True)
    if category == "subitem_missing":
        return _plan(name, reason, category, "enable Notion Sub-items in the Entries DB UI, then rerun ensure", False)
    if category == "permission_or_auth":
        return _plan(name, reason, category,
                     "share the root page/database with the integration or refresh the token", False)
    if category == "api_failure":
        return _plan(name, reason, category,
                     "inspect the Notion API error, then rerun ensure after fixing the payload"
                     " or permission issue", False)
    return _plan(name, reason, category, "inspect the reported issue, then rerun ensure", False)


def _plan(name, reason, category, action, apply_supported):
    return {
        "name": name,
        "reason": reason,
        "category": category,
        "action": action,
        "apply_supported": apply_supported,
    }


def classify_conflict_reason(reason):
    """Return a stable Phase 3 conflict category for ensure diagnostics."""
    text = (reason or "").lower()
    if "native sub-items not enabled" in text or "sub-items" in text or "subitem" in text:
        return "subitem_missing"
    if "missing" in text and "filter" in text:
        return "missing_filter"
    if "missing" in text and ("property" in text or "column" in text):
        return "missing_property"
    if "permission" in text or "403" in text or "unauthorized" in text or "auth" in text:
        return "permission_or_auth"
    if "api" in text or "400" in text or "failed" in text:
        return "api_failure"
    return "unknown"
