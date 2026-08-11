"""`agent-diary diary-notion review` -- the human review queue.

Review is a judgement a person makes after the fact, so nothing in the record
pipeline may declare work reviewed: `push` files every new row as
`Needs Review`, and only this command — with an explicit `--apply` — moves a
row to `Reviewed` and stamps `Last Reviewed`. Without `--apply` it is
read-only, matching the `ensure --dry-run` / `ensure` pattern.
"""

import sys

from claude_diary.config import load_config
from claude_diary.log import configure_from_config
from claude_diary.cli.notion_common import (
    date_start_value,
    resolve_year_and_today,
    select_value,
    title_value,
)
from claude_diary.cli.notion_push import _resolve_credentials, _print_setup_hint
from claude_diary.exporters.notion_hierarchical import (
    NotionHierarchicalExporter,
    NotionAuthError,
    NotionBadRequest,
    NotionNotFound,
)


NEEDS_REVIEW = "Needs Review"
REVIEWED = "Reviewed"


def cmd_notion_review(args):
    """List rows awaiting review, and with --apply mark them reviewed."""
    config = load_config()
    configure_from_config(config)

    token, root_page_id = _resolve_credentials(config)
    if not token or not root_page_id:
        _print_setup_hint()
        sys.exit(1)

    year, today = resolve_year_and_today(config, getattr(args, "year", None))
    apply_changes = getattr(args, "apply", False) is True

    exporter = NotionHierarchicalExporter({
        "api_token": token,
        "root_page_id": root_page_id,
    })
    exporter.load_cache()

    try:
        db_id = exporter.resolve_existing_database(year)
        if not db_id:
            print("[agent-diary diary-notion review] No Entries database for %d." % year)
            print("  Run `agent-diary diary-notion ensure` first.")
            sys.exit(1)
        rows = exporter.query_database_rows(db_id)
    except NotionAuthError as e:
        print("[agent-diary diary-notion review] Auth error: %s" % e, file=sys.stderr)
        print("  Check: agent-diary config or run `agent-diary diary-notion init`", file=sys.stderr)
        sys.exit(1)
    except NotionNotFound as e:
        print("[agent-diary diary-notion review] Not found: %s" % e, file=sys.stderr)
        print("  Check that the root page/database is shared with the integration.", file=sys.stderr)
        sys.exit(1)
    except NotionBadRequest as e:
        print("[agent-diary diary-notion review] Bad request: %s" % e, file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print("[agent-diary diary-notion review] Failed: %s" % e, file=sys.stderr)
        sys.exit(1)

    queue = build_review_queue(rows)
    _print_review_queue(year, queue, apply_changes)

    if not apply_changes or not queue:
        return

    failures = _mark_reviewed(exporter, queue, today)
    _print_apply_result(queue, failures, today)
    sys.exit(1 if failures else 0)


def build_review_queue(rows):
    """Return the rows still waiting on review, newest work first.

    Only an explicit `Needs Review` counts. A row with no review state at all
    predates this workflow, and silently sweeping it into a bulk `--apply`
    would mark work reviewed that nobody looked at.
    """
    queue = []
    for row in rows:
        if row.get("archived"):
            continue
        props = row.get("properties") or {}
        if select_value(props.get("Review Status")) != NEEDS_REVIEW:
            continue
        queue.append({
            "id": row.get("id"),
            "title": title_value(props.get("Name")),
            "date": date_start_value(props.get("Date")),
            "project": select_value(props.get("Project")),
            "status": select_value(props.get("Status")),
            "task_group": select_value(props.get("Task Group")),
        })
    queue.sort(key=lambda item: item["date"], reverse=True)
    return queue


def _mark_reviewed(exporter, queue, today):
    """Mark each queued row reviewed. Returns [(title, reason)] for failures."""
    failures = []
    for item in queue:
        try:
            exporter.update_row_review(item["id"], REVIEWED, today)
        except Exception as e:
            failures.append((item["title"], str(e)))
    return failures


def _print_review_queue(year, queue, apply_changes):
    header = "[agent-diary diary-notion review%s]" % (" --apply" if apply_changes else "")
    print(header)
    print("Year: %d" % year)
    if not queue:
        print("Nothing awaiting review.")
        return
    print("Awaiting review: %d" % len(queue))
    for item in queue:
        detail = [item["date"] or "-", item["status"] or "-"]
        if item["project"]:
            detail.append(item["project"])
        if item["task_group"]:
            detail.append(item["task_group"])
        print("  - %s (%s)" % (item["title"], " | ".join(detail)))
    if not apply_changes:
        print("")
        print("Run `agent-diary diary-notion review --apply` to mark these reviewed.")


def _print_apply_result(queue, failures, today):
    marked = len(queue) - len(failures)
    print("")
    print("Marked reviewed: %d (Last Reviewed = %s)" % (marked, today))
    for title, reason in failures:
        print("  ! %s: %s" % (title, reason), file=sys.stderr)
