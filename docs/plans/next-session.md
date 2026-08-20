# Next session

> Written 2026-08-13, at v4.10.0. Kept in the repository rather than in
> assistant memory because that memory is per-machine and this work is
> continuing somewhere else. Updated 2026-08-14 after a full-project audit and
> the four releases that followed it, two of them fixing things the audit had
> passed — and again later that day, after the README was brought back in line
> with the code and 4.12.0 went out. Updated 2026-08-20 after a sentence-level
> README-vs-code audit found two more code defects and 4.13.0 shipped the
> fixes — the day's full record is in
> [`docs/tasks/2026-08-20.md`](../tasks/2026-08-20.md).

## Where things stand

```
main        clean, nothing unpushed
released    v4.13.0 (PyPI confirmed; 24 tags = 24 releases = 24 CHANGELOG sections)
CHANGELOG   [Unreleased] empty
tests       1,210 passing
CI          green on 30 combinations
```

## What 4.13.0 changed (2026-08-20)

The README was checked claim-by-claim against the code, every sentence to a
file:line. Most of it held. What did not is in the CHANGELOG; the two worth
remembering here:

- **The 4.12.0 ordinal fix was incomplete.** The counting function was right
  and its tests passed — but `core.py` added 1 to a count that still included
  the session being written, so the first session on a branch stamped `(#2)`
  from its second turn. The off-by-one lived at the *call site*, the same
  boundary-shape 4.12.0's own release note warned about. Fixed with
  `count_branch_sessions(..., exclude_session_id=)`. As before, numbers
  already stamped are not corrected retroactively.
- **The README is also the PyPI long description, and PyPI does not rewrite
  relative URLs.** Twelve links — including the Architecture/postmortem links
  the introduction points code readers at — and the demo image were dead on
  pypi.org, silently, since the beginning. All absolute now; verified with
  `readme_renderer[md]` (the renderer PyPI uses) before merging, and against
  the live PyPI JSON after 4.13.0 published: zero relative links remain.

Also: `team monthly --month` accepted the flag and returned the current
*week* — no monthly report existed. One does now (`monthly/team-YYYY-MM.md`).
Two follow-up questions were deliberately left as discussion, not code:
whether `/diary` should gain a summary-input path, and whether
`diary-notion push` should run the secret scanner over agent-authored JSON
(today it does not — the README now says so precisely). Both are argued in
PR #93's body.

**The working rules now live in [`CLAUDE.md`](../../CLAUDE.md), not in one
machine's assistant memory.** Read it first. It holds the rule that a
user-visible change updates both READMEs in the same PR, the table of which
document is authoritative for what, and the two ways a check here silently
measures the wrong thing (`PYTHONPATH=src`, and the three variables an
isolated run needs).

v4.11.0 was the first tag to publish its own release notes, and four releases
have gone out that way since. The workflow runs all eight steps green and the
published body is byte-identical to the CHANGELOG section it came from —
checked, not assumed.

**Anyone whose index has ever been rebuilt should run `agent-diary reindex`
once on 4.11.3 or later.** The category defect made `reindex` write a thin
index; the diary files were never wrong, so a rebuild on the fixed code
recovers all of it. Measured below: `search feature` went from 2,287 hits to
4,949. This is in the README now, which it was not when this paragraph was
written — a user had no way to know the command was worth running.

The published 4.11.3 was installed from PyPI into a clean virtualenv and run:
`stats`, `weekly`, `doctor` and `search` all complete on a cp949 console with
zero `?` in the output. 4.12.0 was installed the same way and `doctor` reports
8 ok, 0 warnings, 0 failures; its release body is byte-identical to the
CHANGELOG section (2,274 characters, compared rather than assumed).

Nothing is half-finished. Every branch is merged and deleted.

## The README had drifted 65 commits behind the code

Worth recording because nothing failed while it happened. Between 4.9.0 and
4.11.3 the README was not touched once, and its opening description of how the
tool works became false: it said one finished session appends one entry, and
its sample entry showed a `📝 Work Summary` block the hook stopped writing
while omitting the `💬 Response` block it started writing. Four PRs (#81–#83,
#85) brought it back.

Two things came out of that worth keeping:

- **The rule is now in the repository** (`CLAUDE.md`), because the failure mode
  was a rule that lived nowhere. Documentation drift here looks exactly like
  the code defects this project keeps finding — nothing raises, and a plausible
  wrong answer is served.
- **Documenting a number is a way of checking it.** Writing down what the
  branch line's `(#N)` meant is what found that it did not mean that.

## What 4.12.0 changed

- **`(#N)` on the branch line counted rows, not sessions.** Correct until
  4.9.0 made an entry a turn. Measured on the real index: one branch held
  1,292 rows from 24 sessions, and a branch worked on in a single sitting held
  15 — the next entry would have called itself the sixteenth session on it.
  Now counts distinct `session_id`, which `reindex_all` recovers from the
  entry text, so it survives a rebuild.
  **Entries already written keep the number they were stamped with.** Anything
  written between 4.9.0 and 4.12.0 has a turn count in it; it is not
  retroactively corrected and should be read as one.
- **`Parent Task` / `Sub-items` are out of the Notion schema.** `ensure` no
  longer creates them. Existing databases keep their columns and values; the
  migration that folds them into native sub-items stays.

The test that should have caught the ordinal gave its three entries three
different session ids, so rows and sessions were the same number in the
fixture. That is the third time this pattern has appeared here — see the
4.11.3 note below on `test_reindex_fidelity`. **When a fixture could
distinguish two readings of a value, make it distinguish them.**

## Waiting on Sol, not on code

1. **PyPI: yank `claude-diary` 4.2.0.** The retired package name still serves
   April's code — checked 2026-08-14: one version, 4.2.0, uploaded 2026-04-29,
   not yanked, while `agent-diary` is at 4.12.0. So `pip install claude-diary`
   today installs code from before turn-scoped entries, before the console
   encoding fixes, and before the category fix, and it installs *quietly*.

   **"Leaves a warning either way" was wrong**, which is why this now says what
   it does. Read out of pip 24.0
   (`_internal/resolution/resolvelib/factory.py:302-334`): a yanked candidate
   is skipped unless `all_yanked and pinned`, where pinned means `==` without a
   wildcard, or `===`. Since 4.2.0 is the only version:

   - `pip install claude-diary` → **fails.** No candidate survives the filter.
   - `pip install claude-diary==4.2.0` → still installs, with the yank reason
     shown.

   That is the shape worth having: someone who pinned it keeps working, and
   someone typing the old name by mistake is stopped rather than quietly given
   April. Yank is reversible and deletes nothing.

   Measured earlier: 91% of its 324 downloads had no Python version or platform
   in the user agent, so there is no evidence of real users either way. Needs
   PyPI credentials, so it is a click Sol has to make.
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

`docs/02-design/features/records-and-work-items.design.md` holds the
measurements; do not re-measure them. What has changed is that **the design's
six open questions are no longer all open.** Three decisions were taken on
2026-08-14 and are in `docs/decisions/`:

- [x] Second database, or per-project databases
  - 📄 [DB를 나누지 않고 링크드 뷰로](../decisions/0001-project-pages-via-linked-views.md) — 2026-08-14
- [x] Whether cross-session linking works at all
  - 📄 [2계층으로 간다 — 세션 넘는 연결 확인](../decisions/0002-two-layer-records-and-work-items.md) — 2026-08-14
- [x] Whether this database tracks state at all
  - 📄 [구조를 가진 일지다 — 상태를 관리하지 않는다](../decisions/0003-a-structured-journal-not-a-tracker.md) — 2026-08-14
- [x] Which relation pair carries the hierarchy — native. The legacy
      `Parent Task`/`Sub-items` pair is gone from the schema and from the live
      2026 database
- [x] Unlinked records — dissolved by ADR-0003. With no state, a record with no
      parent is simply a record

**What the database is now:** a journal with structure. It records what
happened and links related records into a hierarchy. It does not track status.
Deployment is the one exception — it is an event, not a state — and it attaches
only to *the unit that shipped together*, which the hierarchy already expresses.

### Still open

- **The shape of the deployment marker** — checkbox, date, or release
  identifier (`v4.11.3`). This repository deploys by tag so an identifier
  answers all three questions, but how projects like `project-a`
  deploy has not been checked.
- **The lookup key for a parent in an earlier session.** Cross-session linking
  works; what is missing is how a push finds the parent row. This is the same
  question as the identifier scheme, so answering one answers both.
- **Year boundaries.** The database is per year and a hierarchy spanning New
  Year has no defined home.

### The dangerous part: what order to remove things in

ADR-0003 removes `Status`, `Priority`, `Blocked`, `Block Reason`,
`Review Status` and `Carryover`. **The cost is not the six fields. It is
everything that reads them**, and the order matters:

```
1. ops           완료율·stale·needs review 계산을 먼저 제거하거나 다시 정의
2. 뷰            Blocked / 전날 미완료 / 리뷰 필요 3개
3. 스킬 계약      태스크마다 status·priority를 정하라는 지시
4. review 명령    존재 이유가 사라진다
5. 그 다음에      스키마에서 필드 제거
```

**Fields first is the mistake.** Remove a property and the readers do not
fail — they receive an empty value and report a plausible wrong answer. That
is the failure mode this project hit repeatedly on 2026-08-14: an unreadable
input looking exactly like an empty one. `Parent Task`/`Sub-items` were safe to
remove in the other order only because nothing read them.

Existing rows keep their values. Nothing is deleted from the 566 rows; they are
simply no longer read.

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
- **A second `diary-notion push` in the same session writes nothing.** The row
  key is `session_id:task_index` (`notion_cache._row_key`) and `task_index` is
  the position in the `tasks` array, so pushing 6 new tasks after an 11-task
  push collides on indices 0-5 and every one comes back `already exists`.
  Measured 2026-08-14: `Pushed 0, skipped 6`.

  `--force` is not the fix — `archive_rows_for_session` archives **every** row
  of that session, so it would have destroyed the 11 already there to write 6.

  The workaround is to re-send the whole array: previous tasks first (they skip)
  and the new ones after, which lands them on fresh indices. The previous input
  is preserved at `.codefleet/runs/<timestamp>-<session>/input.json`, and
  `parent_index` / `depends_on_indices` in the appended tasks have to be shifted
  by the offset. Doing that gave `Pushed 6, skipped 11` with nothing archived.

  It is the shape this project keeps finding: nothing fails, and the command
  reports success while doing nothing.

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
