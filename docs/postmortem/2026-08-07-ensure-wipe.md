# Postmortem — `ensure` emptied six properties across a live database

**Date of incident:** 2026-08-07
**Detected by:** the operator, noticing a Notion view had gone blank
**Data destroyed:** 6 select properties across 497 rows
**Data recovered by the tool:** none — the fix stops the bleeding, it does not restore
**Released to users:** no. See [Exposure](#exposure).

---

## What happened

`agent-diary diary-notion ensure` reconciles the Notion database schema so that databases created by older versions gain the columns newer versions expect. It is meant to be safe to run at any time, and the operator ran it as part of normal use.

Each run silently emptied `Status`, `Purpose`, `Task Group`, `Priority`, `Review Status` and `Schema Version` on every row in the database.

Nothing errored. `ensure` reported success. The loss was only visible by opening the database and noticing that columns which had held values now held nothing.

## Root cause

`_ensure_db_schema_extensions` patched the **full** extension property set on every run. Its docstring asserted that re-patching an existing property is a no-op.

It is not.

```python
# what was sent, for every extension property, on every run
{"properties": {"Status": {"select": {}}, ...}}
```

To Notion, `{"select": {}}` on an existing property is not "leave this alone". It is a **replacement of the option list with an empty one**. And when an option disappears from a select property, Notion clears that property on every row that referenced it.

So the sequence was:

1. `ensure` patches `Status` with an empty option list
2. Notion drops every `Status` option
3. Notion clears `Status` on all 497 rows, because every one of them referenced an option that no longer exists
4. Repeat for the other five properties

The docstring was the actual defect. The code did exactly what it said; what it said was wrong about the remote system's semantics.

## How it was confirmed

The hypothesis was checked against the live 2026 database rather than reasoned about:

| property | options after | rows with a value |
|---|---|---|
| `Status` | 0 | 0 |
| `Purpose` | 0 | 0 |
| `Task Group` | 0 | 0 |
| `Priority` | 0 | 0 |
| `Review Status` | 0 | 0 |
| `Schema Version` | 0 | 0 |
| `Project` | 16 | intact |
| `Branch` | 21 | intact |

`Project` and `Branch` are the control that made the diagnosis certain. They are select properties on the same rows, holding the same kind of data, and they were untouched — because they live in the **base** schema and are created once, never re-patched. The blast radius matched the re-patched set exactly, and nothing else.

## Timeline

| when | what |
|---|---|
| 2026-05-27 | `83e56fc` adds `_ensure_db_schema_extensions` to backfill columns on older databases. The re-patch is introduced here, along with the docstring claiming it is a no-op. |
| 2026-05-27 → 08-07 | Every `ensure` run empties the properties again. Unnoticed: rows keep being pushed, and each push re-creates the option it needs, so the columns look populated for recent work while history quietly blanks. |
| 2026-08-07 | Operator notices a view is empty. Measured against the live database; `Project`/`Branch` intact isolates the cause. |
| 2026-08-07 | `049e97f` fixes it, with two regression tests. |
| 2026-08-11 | Fix reaches `main` and ships in 4.3.0. |

The gap between cause and detection — over two months — is the part worth sitting with. See [What made it hard to see](#what-made-it-hard-to-see).

## The fix

`049e97f` — 2 files, +73/−21.

Read the current state before writing, and send only what is genuinely absent:

```python
existing = set(self.get_database_property_map(db_id))
missing = {
    name: spec
    for name, spec in _current_schema_extensions(db_id).items()
    if name not in existing
}
if missing:
    self._request("PATCH", "/databases/%s" % db_id, {"properties": missing})
```

An existing property is now never rewritten, so there is no path by which an option list can be replaced.

A second guard was added for cost rather than safety: `schema_v[db_id]` caches the schema version last reconciled, and the function returns without a request when it matches.

### Regression tests

The two tests encode the invariant rather than the symptom:

```python
def test_existing_select_properties_are_never_patched(self):
    # every property already exists -> nothing may be sent at all
    exp._ensure_db_schema_extensions("db1", force=True)
    exp._request.assert_not_called()

def test_only_the_missing_property_is_sent(self):
    # one property absent -> exactly that one is sent
    exp._ensure_db_schema_extensions("db1", force=True)
    payload = exp._request.call_args.args[2]
    assert list(payload["properties"]) == ["Priority"]
```

`assert_not_called` is the important one. A test that checked the payload's *shape* would still pass if the code went back to sending everything. This one fails the moment a write appears where there should be none.

## Exposure

Users were not affected.

- **PyPI**: the released 4.2.0 predates `_ensure_db_schema_extensions` entirely. Anyone who installed from PyPI never had the code.
- **`main`**: had the bug. The README's plugin route (`/plugin marketplace add`) installs from the repository, so that path served it.
- **Actual installs via that route**: none known. The repository had no stars or forks at the time.

The blast radius was one database: the author's own.

## What made it hard to see

Three properties of the failure conspired:

1. **The write reported success.** `ensure` returned normally. Nothing in its output hinted that 497 rows had changed.
2. **New work looked fine.** Each push writes a value, and Notion auto-creates the select option it needs. So the columns repopulated for recent rows immediately after being emptied. Only history went blank — and history is exactly what nobody scrolls back to.
3. **The docstring was reassuring and wrong.** Anyone reading the function, including its author months later, was told the operation was idempotent. The comment inoculated the code against review.

The lesson generalises past this bug: **a claim about a remote system's semantics is not documentation, it is an untested assumption.** `{"select": {}}` being a no-op was never verified against Notion; it was asserted in prose and then relied on in a loop.

## Follow-through

Done:

- Read-before-write in the schema reconciler, with tests asserting no write occurs when nothing is missing
- The docstring rewritten to state the real semantics, so the next reader is warned rather than reassured
- `--dry-run` audited for the same class of problem, and fixed: it reached the database through `ensure_database`, which creates the year page and database when absent and then calls the schema reconciler. A preview now reads the database id from the local cache and gives up when it is empty, with a test asserting `ensure_database`, `ensure_year_page`, `create_row`, `archive_rows_for_session` and `save_cache` are all untouched on that path.

Outstanding:

- **Recovery of the 497 rows.** The fix prevents recurrence; it restores nothing. Notion's page history is the only route and its window is bounded by plan. As of 2026-08-11 the affected properties have partially repopulated for recent rows through normal pushes — `Status` 2 options, `Purpose` 4, `Task Group` 2, `Priority` 2, `Review Status` 1, `Schema Version` 2 — while older rows remain blank. A read-only count on 2026-08-11 found 96 of 509 rows with no `Schema Version`.
- **A pre-flight for destructive schema operations.** The reconciler is safe now by construction, but nothing in the codebase distinguishes "this call can modify existing rows" from "this call cannot". A future schema change re-introduces the risk unless that distinction is made explicit.
