# Next session

> Written 2026-08-13, at v4.10.0. Kept in the repository rather than in
> assistant memory because that memory is per-machine and this work is
> continuing somewhere else. Updated 2026-08-14 after a full-project audit and
> the four releases that followed it, two of them fixing things the audit had
> passed.

## Where things stand

```
main        clean, nothing unpushed
released    v4.11.3 (PyPI confirmed; 22 tags = 22 releases = 22 CHANGELOG sections)
CHANGELOG   [Unreleased] empty
tests       1,197 passing
CI          green on 30 combinations
```

v4.11.0 was the first tag to publish its own release notes, and four releases
have gone out that way since. The workflow runs all eight steps green and the
published body is byte-identical to the CHANGELOG section it came from —
checked, not assumed.

**Anyone whose index has ever been rebuilt should run `agent-diary reindex`
once on 4.11.3.** The category defect made `reindex` write a thin index; the
diary files were never wrong, so a rebuild on the fixed code recovers all of
it. Measured below: `search feature` went from 2,287 hits to 4,949.

The published 4.11.3 was installed from PyPI into a clean virtualenv and run:
`stats`, `weekly`, `doctor` and `search` all complete on a cp949 console with
zero `?` in the output.

Nothing is half-finished. Every branch is merged and deleted.

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

## The 2026-08-14 audit, and what it left open

Everything the project can check was run against the whole of it: the suite
with the coverage gate, ruff, mypy, a package build with `twine check`, the
version string in all five files, CHANGELOG against tags against GitHub
releases, `claude plugin validate --strict`, every relative link in the 28
tracked Markdown files, every subcommand's `--help` (22 plus 5 nested), the
project's own secret scanner over all 158 tracked files, and a replay of the
release workflow's shell steps. All clean. Coverage 89.91%; the floor is
`notion_views.py` at 75%, still the module yesterday named as code whose paths
had never run.

Three things were found and fixed — the home-directory leak, the sdist that
could not run its own tests, and four handlers whose failure value was
indistinguishable from an empty success. They are in the CHANGELOG.

**"All clean" was premature.** Two more defects turned up within hours, both
in paths this audit had signed off on. See the next section for what it was
not looking at.

**What the audit found in the constants, and what was done about it.** Three
were defined and read by nothing — `RICH_TEXT_LIMIT`, `ACTIVE_STATUSES`,
`DEFAULT_VERIFICATION_LIMIT` — and in each case the value they named was typed
out by hand nearby: eight `[:2000]` across three modules, the status strings
compared inline six times in the file below them. They now live in
`lib/notion_api.py` and `lib/statuses.py`, the diary defaults behind
`resolve_diary_dir()`, the transcript root behind `resolve_transcript_root()`.
A test fails if a constant goes unread again or a consolidated value reappears
as a literal.

Two things came out of doing it that are worth keeping:

- **The three spellings of the transcript root were not equivalent.**
  `expanduser("~/.claude/projects")` mixes separators on Windows;
  `os.path.join("~", ".claude", "projects")` does not. Both open the directory
  and only one compares equal to a path built any other way. An existing test
  caught it the moment they were merged, which is why there is a
  `CLAUDE_TRANSCRIPT_ROOT` *string* for display and a
  `resolve_transcript_root()` *function* for code.
- **Consolidating the statuses is step 1 of the records/work-items work**, and
  it is done. It moved definitions only: whether `Deployed` means shipped or
  merely finished is still the open question, and `lib/statuses.py` states the
  current meaning without answering it.

**Clean, and worth not re-checking:** no absolute machine paths, no `/tmp` or
`/var`, no Notion IDs, no e-mail addresses, no credential-shaped values (the
only match is the scanner's own pattern list), the version literal appears in
`__init__.py` alone, and every environment variable read is either namespaced
`CLAUDE_DIARY_*` or an OS standard.

## What the audit missed, and how it was found

Two defects arrived after the audit had declared everything clean, and both
were found the same way: by **running a command and looking at the output**,
which the audit never did. It ran `--help` on all 27 paths and captured every
one through a UTF-8 pipe.

- **A Korean console could not print this tool's output at all** (4.11.1).
  cp949 has no em dash and no emoji, so `stats` died on `╔` — its first
  character — along with `weekly`, `report` and `doctor`. Four of the eleven
  commands that run without credentials. Reported by a user of another
  project, not by any check here. `hook.py` had guarded its own streams since
  it was written; the CLI never got it.
- **Every category after the first was dropped** (4.11.3). `indexer.py` and
  `lib/stats.py` each held a copy of a regex that looks like it collects all
  of them and collects one. On a real 73-file diary: **20,424 categories in
  the files, 7,048 reaching `stats`**, and 96.1% of entries affected. It also
  invented categories out of prose — `reindex`, `search`, `([^` were being
  counted as categories.

Three things worth keeping from how those went:

- **Test data written by hand is not evidence.** A first pass with an invented
  diary format "found" that Korean search was broken and that session ids were
  not indexed. Both were artifacts of the fixture. Regenerating the diary with
  the tool's own hook made one disappear and the real one appear.
- **A fixture can carry the bug and still pass.** `test_reindex_fidelity`'s
  entry has had two categories since the day it was written, and nothing
  asserted on them — so reverting the broken regex left all 28 tests green.
  The suite existed specifically to catch thin indexes.
- **Check a fix against more than the case that produced it.** The console fix
  looked right on cp949 and turned `주간 작업 리포트` into `** ** ***` on an
  ASCII locale, and a `·` that cp949 happens to have became 31 asterisks. Five
  encodings now, not one.

## What the category fix actually changed

Measured on a copy of the real diary — the live one was not touched. The index
on disk held 7,195 categories against 20,443 in the files, with 6,966 of 7,152
entries carrying exactly one. After `reindex` on 4.11.3 it holds 20,443, and
6,531 entries carry three.

What `search` answers, before and after that rebuild:

| keyword | before | after |
|---|---|---|
| `feature` | 2,287 | **4,949** |
| `bugfix` | 912 | **3,150** |
| `test` | 3,239 | **4,613** |
| `refactor` | 243 | **1,301** |
| `style` | 236 | **1,079** |
| `docs` | 5,183 | **5,941** |
| `config` | 1,131 | **1,640** |

`feature` more than doubled. These counts are higher than the category totals
because `search` also matches keywords in the prompts; the difference between
the columns is the categories that were missing.

**The incremental path was never broken** — the hook writes `categories`
straight from the entry data. Only `reindex` rebuilt from the text, so only a
diary that has been reindexed at some point is thin. This one was.

## Not verified

- `mypy` still covers 15% of the code (6 of 62 files, 1,932 of 12,882 lines),
  and `notion_views.py` is still the coverage floor at 75%. Both are
  deliberate, neither has changed.
- The five console encodings are exercised through `PYTHONIOENCODING`, which
  is not the same thing as a real Windows console with that code page active.
  The original report came from a real one; the regression tests do not run on
  one.

## The one large piece of work left

`docs/02-design/features/records-and-work-items.design.md` — **design, not
implemented**. Every measurement is already in it; do not re-measure.

The finding it rests on: of 532 live Notion rows, **89% were never edited after
creation**, median time from creation to last edit 0 seconds. Rows are records,
records do not change state, and the database attaches `Status`, `Review
Status`, `Blocked` and `Carryover` to them anyway. Completion 6%, `Testing` 53%
at a median 44 days, 441 stale — all of it follows from that one fact.

Six decisions in the doc's "Open questions" block the work, and they are Sol's,
not the tool's. The order of work is in the doc. **Step 1, consolidating the
status definitions, is done** — they are in `src/claude_diary/lib/statuses.py`,
with the current meanings unchanged and a test that fails if the enumeration is
written out anywhere else.

**Step 3 is the one that matters now**: link one record to a work item across
sessions by hand and read it back. Not a feature — one row. Every one of the 90
hierarchy links that exists today is intra-session, so cross-session linking is
unverified, and that single row decides whether steps 4-7 are worth starting.

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
- **New `print` calls need no wrapping.** `make_output_unbreakable()` runs at
  the CLI entry point and installs an encoding error handler on stdout and
  stderr, so a console that cannot draw `█` gets `#` and one that cannot draw
  a word gets `?`. Write the real character. What must *not* pass through it
  is file content — `weekly` writes its report and then prints it, and the
  diary headers this repo's own parser matches on (`### ⏰ … 📁`) are parsed,
  not decorated.
- **The category line has one parser**, `CATEGORY_LINE` in `lib/stats.py`,
  used by both the indexer and the stats. It is anchored to the bold label
  line on purpose: a loose match also finds the word in ordinary prose, which
  is how `reindex` and `search` ended up counted as categories.
- **Count broad handlers with an AST, and read the `except` type properly.**
  A scan that treats `except json.JSONDecodeError` as a bare `except` — the
  type is an `ast.Attribute`, not an `ast.Name` — reported 85 handlers and 42
  silent ones where there were 82 and 39. Two separate measurements that day
  disagreed for this reason before the classifier was fixed.
- **A handler with no `logger` or `print` in it is not necessarily silent.**
  Of the 39 untraced handlers, most hand the failure back as a return value or
  append it to a `failures` list the command prints later. The ones worth
  fixing are narrower: where the failure value is *indistinguishable from a
  real, empty, successful answer*. `tests/test_silent_failures.py` holds the
  reviewed list, so the next scan starts from a decision rather than a count.
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
