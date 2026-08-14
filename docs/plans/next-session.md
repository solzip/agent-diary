# Next session

> Written 2026-08-13, at v4.10.0. Kept in the repository rather than in
> assistant memory because that memory is per-machine and this work is
> continuing somewhere else.

## Where things stand

```
main        clean, nothing unpushed
released    v4.10.0 (PyPI 4.10.0 confirmed)
CHANGELOG   [Unreleased] empty
tests       1,109 passing, CI green on 30 combinations
```

Nothing is half-finished. Every branch opened today is merged and deleted.

## Waiting on Sol, not on code

1. **PyPI: yank `claude-diary` 4.2.0.** The retired package name still serves
   April's code. Measured: 91% of its 324 downloads had no Python version or
   platform in the user agent, so there is no evidence of real users — but the
   yank is one click and leaves a warning either way. Needs PyPI credentials.
2. ~~**GitHub Releases: 18 tags, 0 release notes.**~~ **Done 2026-08-14.** All
   18 tags now have a release; each body is its CHANGELOG section verbatim,
   verified by round-tripping every published body against the source (18/18
   identical). Titles carry the CHANGELOG date (`v4.10.0 — 2026-08-13`) because
   GitHub stamps all eighteen with today's creation date and the real release
   dates would otherwise be lost. v4.10.0 is marked latest.
   **It stays current on its own now.** `release.yml` reads the version's
   CHANGELOG section, publishes to PyPI, then creates the release from that
   section verbatim. The extraction runs *before* the build on purpose: a tag
   whose version the CHANGELOG never mentioned fails while it is still
   fixable, because a PyPI version cannot be unpublished. So the only rule
   left is the one that was always there — **write the CHANGELOG section
   before tagging**, and a test on `pyproject.toml`'s version now enforces it
   at PR time rather than at tag time.

## The one large piece of work left

`docs/02-design/features/records-and-work-items.design.md` — **design, not
implemented**. Every measurement is already in it; do not re-measure.

The finding it rests on: of 532 live Notion rows, **89% were never edited after
creation**, median time from creation to last edit 0 seconds. Rows are records,
records do not change state, and the database attaches `Status`, `Review
Status`, `Blocked` and `Carryover` to them anyway. Completion 6%, `Testing` 53%
at a median 44 days, 441 stale — all of it follows from that one fact.

Six decisions in the doc's "Open questions" block the work, and they are Sol's,
not the tool's. The order of work is in the doc and **step 3 is the one that
matters**: link one record to a work item across sessions by hand and read it
back. Not a feature — one row. Every one of the 90 hierarchy links that exists
today is intra-session, so cross-session linking is unverified, and that single
row decides whether steps 4-7 are worth starting.

## Things that are true and are not written in the code

- **`agent-diary diary-notion ops` completion and stale numbers are
  meaningless until the split above.** They count records as though records
  could be finished. Do not read them as signals.
- **Diary data written before v4.10.0 is not comparable to data after it.**
  85% of the 6,971 entries are duplicates of an earlier entry in the same
  session, and `변경 통계` line counts measured the uncommitted working tree
  rather than the session's commits. Neither is repairable: 65% of the source
  transcripts are already gone. Never present a before/after count spanning
  the change.
- **The version string lives in five files** — `pyproject.toml`,
  `src/claude_diary/__init__.py`, `.claude-plugin/plugin.json`,
  `.claude-plugin/marketplace.json`, `.codex-plugin/plugin.json`. Two
  consecutive releases missed the fifth one, and both times
  `test_distribution_versions_match_package_version` caught it. Trust the test,
  not a grep.
- **Publishing to PyPI is automatic.** `.github/workflows/release.yml` fires on
  a `v*` tag and authenticates with OIDC. There are no credentials on any
  developer machine and there should not be.
- **Experiments that could touch the real diary go through `agent-diary try`.**
  Setting `CLAUDE_DIARY_DIR` alone is not enough: `config.json` deliberately
  wins over the environment, so an isolated run needs `APPDATA`,
  `XDG_CONFIG_HOME` and `CLAUDE_DIARY_DIR` all redirected. A test that got this
  wrong wrote five entries into the real diary.
- **Concurrency regressions must be tested with separate processes.** Threads
  share a file object and pass tests that the real thing fails.
- **`non_fatal` is not for every `except Exception`.** It reports `NameError`,
  which in a short body that runs on every entry dies in CI on the first run.
  The 4.9.0 defect survived a day because its *call site* was untested, not its
  body. Apply it where rarely-executed code sits inside a broad handler. Eleven
  broad handlers are deliberately left alone for this reason.

## How today went, in case the pattern repeats

Every defect found today came from running something, never from reading or
reasoning about it. Three shapes came up repeatedly and are worth checking for
directly:

- **The place that was only half fixed.** A lock on two of three writers;
  `errors="replace"` on two of six read paths; `.export_queue.json` left out of
  the four state files that got hardened. When fixing something, count every
  other place with the same shape.
- **Code that exists and whose path has never run.** `notion_views.py`,
  `get_diff_stat_for_commits`, `parent_progress`, and the drift summary — four
  in one day. Code existing is not evidence that it executes.
- **A signal in a place nobody opens.** `diary-notion push` ran 2,286 times
  against roughly 18 for `ops`, and `stats`, `weekly`, `report` and `search`
  zero. New signals belong on paths that already run.

Claims made without running something were wrong six times out of six today.
Check first.
