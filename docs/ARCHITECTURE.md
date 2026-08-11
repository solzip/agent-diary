# Architecture

Agent Diary writes a record of AI coding sessions to two places: local Markdown files, and rows in a Notion database. The Markdown side is a file append. The Notion side is where the interesting problems are, because it is a write path against a third-party API that can fail halfway, be called twice, and change shape underneath you.

This document covers the decisions behind that write path. It is written for someone deciding whether the code is worth reading.

---

## 1. Writes must be safe to repeat

A push can fail partway through. The agent that produced the input can be asked to run again. The user can retry by hand. So every write has to be safe to repeat.

Each row carries two hidden columns that together form a natural key:

```
Session ID   the agent session that produced the record
Task Index   the task's position within that session
```

Before creating a row, `find_existing_row` looks for that pair. If it exists, the push reports `skipped` rather than writing a duplicate. Re-running a push that half-succeeded therefore completes it instead of doubling it.

`--force` is the deliberate escape hatch: it archives the session's prior rows first, then re-pushes everything. Archiving before, rather than deleting after, means a mistake leaves the old rows recoverable in Notion's trash.

### The lookup is cache-aside, and the cache is not trusted

```python
cached = notion_cache.get_row(cache, session_id, task_index)
if cached:
    try:
        self._request("GET", "/pages/%s" % cached)   # confirm it still exists
        return cached
    except NotionNotFound:
        notion_cache.invalidate_row(cache, session_id, task_index)
# fall through to a filtered query
```

A cached page id is a claim about a remote system, and the user may have deleted the row in the Notion UI. The cache is checked, then verified, then dropped when the verification fails. A stale hit costs one GET; trusting it blindly would mean writing into a page that no longer exists.

The whole cache is discarded when `root_page_id` changes, because every id under it is then meaningless.

---

## 2. Not every failure deserves a retry

`_request` wraps the Notion API with a retry policy that distinguishes causes rather than counting attempts:

| status | behaviour | why |
|---|---|---|
| 200 | return | |
| 401, 403 | raise `NotionAuthError`, no retry | a bad token will not become good |
| 400 | raise `NotionBadRequest`, no retry | the request is wrong; repeating it wastes quota |
| 404 | raise `NotionNotFound`, no retry | callers use this to invalidate caches |
| 429 | sleep `Retry-After`, capped at 30s, retry | the server said when; the cap stops a hostile header stalling the run |
| 5xx | exponential backoff `2 ** attempt`, retry | transient by definition |
| network error | exponential backoff, retry, then wrap | same |

`MAX_RETRIES = 3`, every request carries a 15 second timeout.

The typed exceptions are the point. Callers act on the category, not on a string: the push loop stops the whole run on `NotionAuthError` because every later task would fail the same way, records a per-task failure on `NotionBadRequest`, and the task-group ordinal lookup treats `NotionBadRequest` as "no prior session" because that is exactly what Notion returns when you filter on a select option that does not exist yet.

Error messages are truncated to 200 characters by `short_error`. Notion's select errors enumerate every existing option, which runs to thousands of characters and buries the actual message.

---

## 3. The schema has a version, and patching it is dangerous

The database gains columns as the tool grows. Existing databases have to catch up without the user recreating anything, so `ensure_database` reconciles the schema on the way through.

That reconciliation is the most dangerous code in the project. `{"select": {}}` sent to an existing property does not mean "leave it alone" — it replaces the option list with an empty one, and Notion then clears that property on **every row that referenced a removed option**. Patching the full extension set on each run silently emptied six properties across a live database. See [the postmortem](postmortem/2026-08-07-ensure-wipe.md).

Two guards now stand in front of it:

1. **Read before write.** The current property map is fetched and only genuinely missing properties are sent. An existing property is never re-patched.
2. **A version cache.** `schema_v[db_id]` records the schema version last reconciled. When it matches, the function returns without a request at all.

The same reasoning is why `--dry-run` does not call `ensure_database`. Despite the name it creates the year page and the database when they are missing, so a preview reads the database id from the local cache and gives up when the cache is empty. A preview must not bring anything into existence.

---

## 4. Partial failure is a defined outcome, not an accident

A push is a sequence of independent API calls, so "it half worked" is a normal state and has defined semantics:

- Each task's outcome is recorded as `pushed`, `skipped`, or `failed`, with a reason.
- Relation wiring happens in a second pass, once every row id is known — a row cannot link to a row that does not exist yet.
- **Exit code 1 if anything failed, 0 otherwise**, so a caller can branch on it.
- **The input JSON is preserved on failure** and deleted only on full success. The record of what was meant to happen outlives the attempt.

### Every run leaves a local record

Notion is the destination, not the archive. If a push half-fails, or a row is later edited by hand, the only way back to what was actually submitted is a local copy. Each run writes:

```
<cwd>/.codefleet/runs/<YYYYMMDD-HHMMSS-session>/
  input.json        the original task JSON
  git-diff.patch    the working tree at push time
  preview.md        the rendered page body
  manifest.json     the above, each with a sha256, plus the push result
```

The checksums mean a reference can be verified against the file it names rather than assumed.

---

## 5. Zero dependencies in the core

`dependencies = []`. The core runs on the standard library; `requests` arrives only with the `[notion]` extra.

This is a deliberate constraint, not an accident of scope. The tool installs into whatever environment the user already codes in, and runs from a Stop Hook on every session end. A dependency tree there is a permanent tax on someone else's project and a permanent supply-chain surface, for a tool that mostly parses JSON and writes Markdown.

The same reasoning applies to release: publishing uses PyPI trusted publishing over OIDC, so there is no long-lived API token stored in the repository at all.

---

## 6. Layout

```
src/claude_diary/
  core.py            Stop Hook pipeline: transcript -> entry -> file
  formatter.py       entry -> Markdown, and entry -> Notion block payload
  hook.py            the Stop Hook entry point
  indexer.py         search index over the Markdown diaries
  cli/
    notion_push/     the Notion write path, below
    notion_ensure.py schema and view reconciliation
    notion_ops.py    read-only operational report
    notion_review.py the human review queue
    setup.py         installs hooks, slash commands, and Codex skills
  exporters/
    notion_hierarchical.py  the API client: retries, error taxonomy, schema
    notion_views.py         view definitions
    slack.py discord.py obsidian.py github.py
  lib/
    notion_cache.py  page/database/row id cache with invalidation
    secret_scanner.py  masks credentials before anything is written
    audit.py         append-only log with source checksums
```

`cli/notion_push/` is a package rather than a module because it had grown past a thousand lines:

| module | responsibility |
|---|---|
| `__init__.py` | the command, plus the two functions that reach outside it |
| `tasks.py` | reading fields off a task dict |
| `properties.py` | task dict → Notion row properties |
| `validate.py` | rejecting bad input before anything is written |
| `relations.py` | pass 2, linking rows once every row id is known |
| `ordinals.py` | numbering sessions that continue a task group |
| `preview.py` | Notion block payload → readable text |
| `artifacts.py` | the local record of what a run submitted |

The command and `_gather_git_info` / `_push_task` stay in `__init__` on purpose. Tests patch `claude_diary.cli.notion_push.load_config` and the `git_info` helpers, and a patch only reaches the module that resolves the name — moving those callers would not have failed the tests, it would have silently stopped the mocking from applying.

---

## 7. Two things that look wrong and are not

**`Schema Version` reads `vlegacy`.** It began as a bug: a function returned `"legacy"` and a normalizer prefixed a `v`. It stays because it is a live select option carrying 350 of 509 rows in a real database. Changing it creates a third option and splits the column, so renaming it is a migration rather than an edit. It is now a named constant with a test pinning it.

**The import package is `claude_diary` while the distribution is `agent-diary`.** `install` writes `python -m claude_diary.hook` into the user's `settings.json`. Renaming the package would stop an existing Stop Hook — and stop it silently, since a diary that is not being written looks exactly like a quiet day. A distribution name that differs from its import name is ordinary in Python (`pillow`/`PIL`, `beautifulsoup4`/`bs4`).

Both are cases where the tidier-looking option costs a user something and the untidy one costs a paragraph of explanation.

---

## 8. Verification

- **741 tests**, 88.78% line coverage, with the CI gate at 85%
- **15 combinations** per run: Python 3.8–3.12 across Linux, macOS and Windows
- `ruff` with correctness rules, and per-file exemptions that each carry a written reason
- Every release publishes over OIDC from a tag, with no stored credentials
