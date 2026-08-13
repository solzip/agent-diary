# Two layers: work items have state, records do not

> **Status**: design, not implemented
> **Date**: 2026-08-13
> **Project**: agent-diary

## What is wrong

The Notion database holds one row per task per session, and attaches to each
row a set of fields that only make sense for something with a lifecycle:
`Status`, `Review Status`, `Blocked`, `Carryover`.

Rows are records. Records do not change state. Measured on 532 live rows:

```
created and never touched again      471   (89%)
edited within the hour                10   ( 2%)
edited hours later                    27   ( 5%)
edited a day or more later            24   ( 5%)

median time from creation to last edit      0 seconds
```

Every symptom investigated this week follows from that one fact.

| Reading | What it actually is |
|---|---|
| 6% done | 94% of rows are records, which cannot be completed |
| `Testing` 53%, median 44 days old | not dwell time — the state each session was in when it wrote |
| 441 rows stale | not neglect — past records |
| `Review Status`: 232 rows, one distinct value | reviewing is a person's act, not a row's state |
| `solarchive` 0% done | not an undeployed project — a project with only records |

`ops` reporting "441 rows untouched for 7+ days" is a diary being told its
pages are out of date.

## The layer that already exists

Work items are already there. They are written into row titles rather than
into a field.

```
532 rows, 92 (17%) carry an identifier in the title
19 identifiers are shared by more than one row

  라운드 2   17 rows    Testing 13, Design 3, Deployed 1
  R27       10 rows    Testing 9, Implementation 1
  P3         8 rows    Testing 6, Deployed 1, Design 1
  IF-76      4 rows    Testing 3, Design 1
```

`R27` is a work item and those ten rows are its records. Today each of the ten
carries its own status, so "where is R27 now" has to be reconstructed by eye —
and nine of them say `Testing` not because R27 is being tested but because nine
sessions happened to be testing when they wrote.

`Task Group` is the field meant for this. It is filled on 8% of rows while 17%
carry an identifier in the title, which suggests the field is not being skipped
out of laziness so much as bypassed: the title is what Notion shows first.

## The model

```
work item     R27, IF-76, 라운드 2        few, long-lived, HAS STATE
  └─ record   one per session per task    many, immutable, NO STATE
  └─ record
```

- A **record** answers *what happened*. Date, project, what was asked, what the
  assistant said, files, commands, commits, errors. Written once.
- A **work item** answers *where is this*. Status, next action, blocked, owner.
  Updated as the work moves.

## Where the work item lives

**A parent row in the same database, not a second database.**

Reasons, in order of weight:

1. A second database doubles what `ensure` reconciles, and schema reconciliation
   is the most dangerous code in this project — see the 2026-08-07 postmortem
   where one PATCH emptied six properties across 497 rows.
2. Notion's native sub-item relation already drives expand/collapse in the UI,
   and `ensure` already detects it.
3. `ops` has a `parent_progress` calculation — children done vs total per
   parent — and it finds 37 parents today.

The cost of staying in one database: rows are heterogeneous, so every view and
every count has to say which kind it means. That is a real cost and it is
smaller than the alternative.

### How much of this is actually proven

Less than the list above suggests, and the difference matters.

Every hierarchy link in the database today is **within one session**:

```
native   상위 항목 links     77    same session 77   across sessions 0
custom   Parent Task links  13    same session 13   across sessions 0
```

Necessarily so: `_wire_parent_tasks` only pairs indices that are both in
`row_ids`, which holds the rows this push created. Verified in the code rather
than taken from the docstring.

So `parent_progress` runs, but it has never once run on the case this design
exists for. "The reporting half already exists" would be an overstatement — the
code exists and its input never has.

### Two hierarchy relations, not one

The database carries two dual-property relation pairs:

```
Sub-items  <-> Parent Task     custom,  1% / 2% filled
하위 항목   <-> 상위 항목        native,  7% / 14% filled
```

`detect_subitem_relation` picks the native pair, so that is where the tool
writes and where 77 of the 90 existing links are. `Parent Task` is left over
from the schema and holds the other 13.

Which pair the work-item layer uses has to be decided rather than assumed, and
the 13 links in the other pair have to go somewhere. The design does not settle
this; it names it.

## The hard part: linking across sessions

**`parent_index` cannot do this.** It is a zero-based index *into the same
push*, so it expresses "task 3 is a subtask of task 1 in this session" and
nothing else. A record written today cannot point at a work item created three
weeks ago through it.

What can: `Task Group` is a string that already crosses sessions, and the push
already queries by it — `get_task_group_session_ids(db_id, task_group)` exists
and is how continuation ordinals are numbered.

So the join is:

```
push writes a record with Task Group = "R27"
  -> look up the work-item row for "R27" in this year's database
  -> not found: create it
  -> wire the record as its sub-item
```

This makes `Task Group` the identifier of the work item rather than a loose
label, which is what it was already trying to be.

### Getting the group filled

8% today. Three measures, in increasing order of intrusion:

1. **Already shipped**: `push` warns when a task has no `task_group` and prints
   the names already in use for that project.
2. **Propose from the title.** 17% of rows carry an identifier the agent
   already wrote — `R27`, `IF-76`, `라운드 2`. Offer those as candidates rather
   than requiring a new naming discipline. The schemes differ per project and
   forcing one would mean changing how Sol works to suit the tool.
3. **Not** rejecting a push without one. An unlinked record still beats no
   record; that trade has been made every time it came up in this project.

Open: whether an unlinked record should get an implicit work item of its own,
or hang loose. Hanging loose is simpler and honest; an implicit one keeps every
record reachable from the work-item layer at the cost of many one-record items.

## Status, after the split

Only work items have it. The question the database exists to answer, per the
vision, is *what did I do / what is blocked / what is next*, and after the
split each lands somewhere:

| Question | Answered by |
|---|---|
| what did I do | records — date, name, content |
| what is next | work item — `Next Action` |
| what is blocked | work item — status |

Minimum viable set on the work item:

```
진행 중  /  막힘  /  완료
```

Two values would drop `막힘`, and that is one of the three questions. Sol has
said 작업완료 and 배포 are different things; if 배포 must be tracked, it is a
fourth value or a separate checkbox on the work item — that decision is not
made here.

`Review Status`, `Blocked`, `Carryover` come off the record. `Review Status`
loses nothing: 232 rows, one distinct value, never moved. `Block Reason` stays,
on the work item.

## What breaks

Everything below reads status off records today.

| Thing | Today | After |
|---|---|---|
| `ops` done ratio, stale | counts records | must count work items only |
| `ops` blocked, needs review | reads record fields | reads work items |
| view `Blocked` | `Blocked` checkbox on records | work items with status 막힘 |
| view `전날 미완료` | unfinished records before today | work items, no date filter |
| view `오늘 작업` | unchanged — records with today's date | unchanged |
| view `작업 그룹별` | group records by Task Group | becomes the work-item list |
| `DONE_STATUSES` etc. | five literals in six places | see below |
| skill | tells the agent to set a status per task | sets it on the work item |

### The six places

The status vocabulary is written out separately in six locations that do not
reference each other:

```
properties.py:21      VALID_STATUSES        (push validation)
notion_ops.py:26      DONE_STATUSES         (completion)
notion_ops.py:27      ACTIVE_STATUSES       (open work)
notion_ops.py:296-298 "Testing", "Implementation" inline
skills/diary-notion/SKILL.md:75
setup.py:122, 326     (embedded skill copy, ko + en)
```

Plus the Notion `select` property's own option list, which is a seventh and
accepts values the code has never heard of.

Adding a value today means editing six places, and missing one makes that value
neither done nor active — it disappears from every count silently. **Merging
these into one definition is a prerequisite**, the same way normalising the
project name had to land before turn-scoped entries.

## The 532 rows already there

They stay as records, and they keep whatever status they were written with.

They are **not** migrated automatically. Which of the 283 `Testing` rows are
actually finished is not something the tool can know, and guessing would put
wrong answers into the one place Sol reads daily. `Review Status` and the
`Testing` pile are evidence of what happens when a field is filled by machine
and expected to be corrected by hand.

The practical consequence: counts spanning the change are not comparable, the
same caveat 4.9.0 carries for entry counts.

## Order of work

1. **Merge the status vocabulary into one definition.** No behaviour change,
   and a prerequisite: with six copies, adding a value and missing one makes it
   neither done nor active, and it vanishes from every count in silence.
2. **Decide which relation pair carries the hierarchy**, and deal with the 13
   links in the other one. Nothing else can be built on an ambiguous answer.
3. **Link one record to a work item across sessions, by hand, and read it
   back.** One row, not a feature. This path has never executed: every existing
   link is intra-session, so "Notion accepts it and `parent_progress` reports
   it correctly" is an assumption until a single case says otherwise. Today's
   work turned up three separate places where code existed and its path did
   not.
4. Work-item rows for real: look up or create by `Task Group`, wire records as
   children. Records keep every field they have; nothing is removed yet.
5. Move status to the work item; stop writing it on records.
6. Repoint `ops` and the two views that filter on status.
7. Retire `Review Status` and `Carryover` from records.

Steps 1 to 3 are small, and 3 is the one that decides whether the rest is worth
starting. Steps 1 and 4 are useful even if the rest never happens.

## Open questions

- **The 배포 distinction.** Fourth status value, separate checkbox, or out of
  scope.
- **Unlinked records.** Implicit one-record work item, or hanging loose.
- **Identifier scheme.** Whether the tool proposes from titles (`R27`, `IF-76`)
  or expects `Task Group` to be authored directly. Proposing is friendlier and
  guesses; expecting is precise and has been 8% effective so far.
- **Year boundaries.** The database is per-year. A work item spanning New Year
  has no defined home, and today nothing does either.
- **Which relation pair**, and what happens to the 13 links in the loser.
- **Whether cross-session linking works at all.** Unknown, not assumed — see
  step 3. Every one of the 90 links that exists today is intra-session.
