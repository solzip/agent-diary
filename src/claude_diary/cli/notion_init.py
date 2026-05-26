"""`claude-diary notion init` — interactive Notion setup.

Walks the user through:
  1. Pasting their integration token (https://www.notion.so/my-integrations)
  2. Pasting the root page URL or ID
  3. Verifying token + read access via the Notion API
  4. Saving credentials to <config_dir>/config.json under
     exporters.notion_hierarchical

Write permission is NOT verified at init time — it follows from read access
when the user shares the page with their integration. If the first push 404s,
the error message points them back to the share dialog.
"""

import getpass
import re
import sys

from claude_diary.config import load_config, save_config, get_config_path
from claude_diary.exporters.notion_hierarchical import (
    NotionHierarchicalExporter,
    NotionAuthError,
    NotionNotFound,
)


PAGE_ID_RE = re.compile(
    r"([0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{12})"
)


def cmd_notion_init(args):
    """Run the interactive setup. Returns 0 on success, non-zero on failure."""
    print("─" * 56)
    print("Notion hierarchical export setup")
    print("─" * 56)

    token = _prompt_token()
    if not token:
        print("\nAborted (no token).", file=sys.stderr)
        sys.exit(1)

    page_input = _prompt_page()
    if not page_input:
        print("\nAborted (no page URL/ID).", file=sys.stderr)
        sys.exit(1)

    page_id = parse_page_id(page_input)
    if not page_id:
        print(
            "\n[claude-diary] Could not parse a page ID from input.\n"
            "  Expected: a Notion URL or a 32-character page ID.",
            file=sys.stderr,
        )
        sys.exit(1)
    print("  Parsed page_id: %s" % page_id)

    print("\nStep 3/3: Verifying access...")
    ok, error = _verify_access(token, page_id)
    if not ok:
        print("  %s" % error, file=sys.stderr)
        sys.exit(1)

    _save_credentials(token, page_id)
    print("\nSaved to: %s" % get_config_path())
    print("  exporters.notion_hierarchical.api_token = secret_***")
    print("  exporters.notion_hierarchical.root_page_id = %s" % page_id)
    print("\nTry it: type /diary-notion in any Claude Code session.")


def parse_page_id(input_str):
    """Extract a Notion page ID from a URL or raw ID string.

    Accepts the 8-4-4-4-12 UUID form (with or without dashes). Returns the
    canonical undashed 32-char hex, or None on parse failure.
    """
    if not input_str:
        return None
    m = PAGE_ID_RE.search(input_str.strip())
    if not m:
        return None
    return m.group(1).replace("-", "").lower()


def _prompt_token():
    print("\nStep 1/3: Integration token")
    print("  Get it from: https://www.notion.so/my-integrations")
    try:
        return getpass.getpass("  Token (secret_...): ").strip()
    except (EOFError, KeyboardInterrupt):
        return ""


def _prompt_page():
    print("\nStep 2/3: Root page URL or ID")
    print("  Paste a Notion URL or page ID:")
    try:
        return input("  > ").strip()
    except (EOFError, KeyboardInterrupt):
        return ""


def _verify_access(token, page_id):
    """Verify token is valid and the integration can read the root page.

    Returns (ok: bool, error_message: str).
    """
    exporter = NotionHierarchicalExporter({
        "api_token": token,
        "root_page_id": page_id,
    })
    try:
        exporter._request("GET", "/users/me")
    except NotionAuthError:
        return False, (
            "✗ Token invalid (401/403).\n"
            "  Get a new token at https://www.notion.so/my-integrations"
        )
    except Exception as e:
        return False, "✗ Could not verify token: %s" % e
    print("  ✓ Token valid")

    try:
        exporter._request("GET", "/blocks/%s" % page_id)
    except NotionNotFound:
        return False, (
            "✗ Page not found, or not shared with the integration.\n"
            "  In Notion: open the page → top-right ⋯ → Connections → add your integration."
        )
    except NotionAuthError:
        return False, (
            "✗ Page exists but the integration has no access.\n"
            "  In Notion: open the page → top-right ⋯ → Connections → add your integration."
        )
    except Exception as e:
        return False, "✗ Could not verify page access: %s" % e
    print("  ✓ Integration can read root page")
    return True, ""


def _save_credentials(token, page_id):
    """Merge token + root_page_id into config.json under notion_hierarchical."""
    config = load_config()
    exporters = config.setdefault("exporters", {})
    nh = exporters.setdefault("notion_hierarchical", {})
    nh["api_token"] = token
    nh["root_page_id"] = page_id
    save_config(config)
