# Notion views to create by hand

The Notion API cannot create database views, so these are set up once in the
Notion UI. Everything they need is already on the rows — this is configuration,
not a schema change.

Why these five: measured on the live database (532 rows, 476 active), the
numbers that matter are not visible in the default table.

```
untouched 7+ days     441   (93% of active)
awaiting review       218
no next action        125
no task group         ~62% of rows
blocked                 8
```

The `push` summary now prints the same signals for the project just pushed.
These views are where you go to act on them.

---

## 1. This week, by project

The one to open daily. Answers "what did I touch this week, and where does it
stand".

| | |
|---|---|
| Layout | Table |
| Filter | `Work Period` — **This week** |
| Group by | `Project` |
| Sort | `Priority` ascending, then `Date` descending |
| Shown | Name, Status, Priority, Task Group, Next Action |

`Work Period` is populated on every row, so this filter never silently drops
anything. `Date` is the day the row was written; `Work Period` is the span the
work covers, which is the one you want for a weekly view.

> Notion's week starts on Sunday or Monday according to your account's
> language/region setting. There is no per-view override, so if the boundary
> matters, use **Past 7 days** instead — it is relative to today and needs no
> setting.

## 2. Stale

The 441. Open work nobody has touched in a week.

| | |
|---|---|
| Layout | Table |
| Filter | `Status` **is not** `Deployed` **AND** `Work Period` **is before** — *1 week ago* |
| Group by | `Project` |
| Sort | `Work Period` ascending (oldest first) |
| Shown | Name, Status, Work Period, Next Action, Blocked |

Read the top of each group first: those are the oldest open items.

**Before concluding anything from this view**, note that `Deployed` is the only
status counted as done. A row whose work is finished but still sitting in
`Testing` shows up here. Some of the 441 is genuinely abandoned and some of it
is just a status never moved — this view is where you tell the two apart.

## 3. Needs review

The 218. Rows filed by the agent and not yet checked by you.

| | |
|---|---|
| Layout | Table |
| Filter | `Review Status` **is** `Needs Review` |
| Sort | `Date` descending |
| Shown | Name, Project, Status, Date, Task Group |

Every row is filed as `Needs Review` by design — the agent never writes review
state. `agent-diary diary-notion review --apply` moves them to `Reviewed` in
bulk; this view is for reading them before you do.

## 4. Blocked

Only 8 rows, and the highest value per row in the database: each one is work
that has stopped and is waiting on something.

| | |
|---|---|
| Layout | Table |
| Filter | `Blocked` **is** checked **AND** `Status` **is not** `Deployed` |
| Sort | `Work Period` ascending |
| Shown | Name, Project, Block Reason, Next Action |

`Blocked` is a checkbox; the text is in `Block Reason`.

## 5. No task group

The connectivity gap — roughly 62% of rows. `Task Group` is the only thing
joining work done on different days into one thread, so a row without one
cannot be linked to its own follow-up.

| | |
|---|---|
| Layout | Table |
| Filter | `Task Group` **is empty** **AND** `Status` **is not** `Deployed` |
| Group by | `Project` |
| Sort | `Date` descending |
| Shown | Name, Project, Date, Status |

This is a backfill queue. Assign groups from the top down; within a project,
adjacent rows on the same theme usually belong to the same group. New rows
should stop arriving here — the skill now instructs the agent to always set
one, and `push` warns when it does not.

---

## What is not worth a view

**Per-week browsing beyond view 1.** `Work Period` supports any date filter, so
a second "last week" view is a copy of the first with one dropdown changed.
Change the filter instead of keeping two.

**A terminal equivalent.** This was considered and dropped: arrow-key
navigation needs a TTY, and commands here often run inside an agent session
where stdout is not one. `curses` is not available on Windows, and the
alternative — `termios` on Unix plus `msvcrt` on Windows — is the split this
project already refused once when building the file lock. Notion is the
browser; these views are the configuration it was missing.
