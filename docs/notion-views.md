# Notion views

`agent-diary diary-notion ensure` creates and verifies these. They are not
set up by hand, and `ensure` is idempotent — running it again on a database
that already has them reports `verified` and changes nothing.

```bash
agent-diary diary-notion ensure --dry-run   # what it would do
agent-diary diary-notion ensure             # do it
```

## What it manages

Five views, each answering one question the database exists to answer.

| View | Filter | Grouping / sort | Shows |
|---|---|---|---|
| **작업 계층** | none | sub-items, date desc | Name, Status, Project, Task Group, Date |
| **오늘 작업** | today, relative | priority, then date desc | Name, Status, Priority, Next Action, Project |
| **Blocked** | `Blocked` is checked | priority, then date desc | Name, Priority, Block Reason, Next Action, Project |
| **전날 미완료** | unfinished, before today | priority, then date desc | Name, Status, Priority, Next Action, Date |
| **작업 그룹별** | none | grouped by `Task Group` | Name, Status, Project, Date |

`오늘 작업` and `전날 미완료` filter on a date relative to the day `ensure`
ran, so re-running keeps them pointed at the current day.

`Session ID` and `Task Index` are hidden in every view. They are the
idempotency key, not something to read.

## What it will not do

**Delete views.** Earlier versions created five more — 상태별, 목적별,
프로젝트별, 오늘 우선순위, 리뷰 필요 — which were group-by duplicates of each
other. `ensure` now lists them as no longer managed and leaves them alone,
because deleting a Notion view can discard a layout somebody customised. Remove
them by hand if they are not being used.

**Manage views you add yourself.** Anything outside the five names above is
left untouched, so a hand-made view is safe from `ensure`.

## Views worth adding by hand

Two gaps the managed set does not cover, both visible in the numbers on a live
database (532 rows, 476 active):

**Stale** — 441 rows, 93% of active work, untouched for a week or more.
`전날 미완료` covers yesterday; nothing covers the long tail.

> Filter `Status` is not `Deployed` and `Work Period` is before *1 week ago*,
> group by `Project`, sort `Work Period` ascending.

Before drawing conclusions from it: **`Deployed` is the only status counted as
done**. A row whose work is finished but still sitting in `Testing` appears
here, so some of the 441 is abandoned and some is a status never moved. Telling
those two apart is what the view is for.

**No task group** — roughly 62% of rows. `Task Group` is the only thing joining
work done on different days, so a row without one cannot be linked to its own
follow-up. `작업 그룹별` groups by it but does not isolate the ones that are
missing it.

> Filter `Task Group` is empty and `Status` is not `Deployed`, group by
> `Project`, sort `Date` descending.

This is a backfill queue. New rows should stop arriving in it: the skill now
tells the agent to always set a group, and `push` warns when one is missing and
prints the names already in use for that project.

## Why there is no terminal browser

Arrow-key navigation needs a TTY, and these commands often run inside an agent
session where stdout is not one. `curses` is absent on Windows, and the
alternative — `termios` on Unix plus `msvcrt` on Windows — is the split this
project already turned down when it built the file lock. Notion renders these
views already; duplicating that in a terminal buys nothing.
