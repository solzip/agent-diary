"""Facts about the Notion API that more than one module needs.

`RICH_TEXT_LIMIT` is why this file exists. It was defined in
`exporters/notion_hierarchical.py` and referenced by nothing: eight literal
`[:2000]` did the truncating, spread across `exporters/notion.py`,
`cli/notion_push/properties.py` and `formatter.py`, and `formatter`'s own
docstring told the reader that truncation happened "to RICH_TEXT_LIMIT" while
that module could not have imported it — `notion_hierarchical` imports
`formatter`, so the arrow only points one way.

Hence a leaf module that imports nothing. The API version and base URL come
along because they had started down the same road: the version string was in
two places, one of them named and one of them typed out again.
"""

#: Every request goes here. Versioned in the path by Notion's own convention.
API_BASE = "https://api.notion.com/v1"

#: Sent as `Notion-Version` on every request. Notion pins behaviour to this
#: date, so changing it is an API migration, not an upgrade.
API_VERSION = "2022-06-28"

#: Notion rejects a rich_text value longer than this. Truncating is the
#: caller's job; every path that builds rich_text has to do it, which is
#: exactly why the number should not be typed out at each of them.
RICH_TEXT_LIMIT = 2000
