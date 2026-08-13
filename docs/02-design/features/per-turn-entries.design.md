# One entry per turn, not one copy of the session per turn

> **Status**: design, not yet implemented
> **Date**: 2026-08-13
> **Project**: agent-diary

## The defect

The Stop Hook fires at the end of every assistant turn, not at the end of a
session. It has always done this. On each firing it parses the transcript
**from line 1** and writes the **first five** user prompts it finds.

```python
parsed = parse_transcript(transcript_path)   # always from the start
...
user_prompts[:5]                             # always the first five
```

Turn 1 records requests 1–5. Turn 2 records requests 1–5. Turn 400 records
requests 1–5. The sixth request of a session is never written down, and the
first five are copied once per turn.

Measured over the whole diary:

```
entries                          6,971
copies of an earlier entry       5,904   (85%)
entries with distinct content    1,067   (15%)
sessions containing copies         255 / 337
worst session          400 entries, 395 copies (99%)
```

A tool whose purpose is to record everything done with an AI is recording the
opening of each session several hundred times and discarding the rest.

### What this has been distorting

Every count derived from the diary inherits the duplication. Numbers used in
decisions this week, all inflated:

| Reading | What it actually was |
|---|---|
| 132 "sessions" in a day | turns, not sessions |
| project line churn of -1,547,143 | one working tree counted once per turn |
| `_verification` 3.3% done | one task duplicated 20–400 times, all open |
| `docs` 6,916 commits | the same commits recounted every turn |
| 441 of 476 Notion rows stale | many are copies of one piece of work |

Proportions mostly survive — everything is inflated by roughly the same
factor — but no absolute figure from the diary can be trusted until this is
fixed.

## What an entry should be

One prompt, and what came of it.

```
### ⏰ 13:40:53 | 📁 `working-diary`

**📋 작업 요청:**
  1. 이게 말이 안되잖아 내가 계속 똑같은 말을 보낸게 아닌데

**💬 응답:**
  전체로 재보니 85%가 복사본입니다. 원인은 훅이 턴마다 transcript를
  처음부터 다시 읽고 앞 5개만 쓰는 것입니다. …

**✏️ 수정된 파일:** …
**⚠️ 발생한 이슈:** …
```

That also delivers the thing that prompted this — the assistant's answer kept
alongside the request — without any new duplication, because each turn's text
is written exactly once.

## Design

### Read from where the last turn stopped

Transcripts are append-only JSONL. Claude Code appends records and never
rewrites earlier lines; verified by watching one file grow across turns while
its earlier content stayed byte-identical.

So the state needed is one number per session: how many lines have been
recorded already.

```
parse_transcript(path, start_line=N)   # skip the first N lines
```

`start_line` is new. `max_lines` stays as it is — a separate concern, and now
unset by default.

### Where the position lives

A new file beside the diary:

```
~/working-diary/.session_progress.json

{
  "81ee7f34-...": {"lines": 2457, "updated": "2026-08-13T13:40:53+09:00"},
  "1b1a3b22-...": {"lines": 812,  "updated": "2026-08-13T12:02:11+09:00"}
}
```

Rejected alternatives:

- **The audit log.** Append-only JSONL, one record per write, no line count.
  Deriving a position would mean scanning a 3.4MB file on every turn and
  trusting a derived value — the same mistake as reading session ids out of
  the search index, which `backfill` deliberately does not do.
- **The search index.** Already 14.7MB; it is a derived artifact that
  `reindex` rebuilds, and a rebuild must not be able to lose the position.
- **The transcript itself.** Not ours to write to.

The file is small, one entry per session, and read-modify-write — so it takes
the same `FileLock` as the counter, for the same reason: two sessions ending
in the same second are ordinary here.

Pruning: entries whose transcript no longer exists are dropped when the file is
next written. Claude Code deletes old transcripts — 65% of the sessions in this
diary no longer have one — so without pruning the file grows forever.

### Guarding against a transcript that is not what we last saw

Two checks before trusting a stored position:

1. **The file is shorter than the position.** It was replaced or truncated.
   Reset to 0 and record from the start.
2. **The file is missing.** Drop the entry.

A stronger fingerprint (hashing the first N lines) was considered and left
out: the failure it protects against — a transcript rewritten in place with
the same length — has not been observed, and the cost is reading the head of
the file on every turn.

### First contact with a session that already has entries

On upgrade there will be sessions mid-flight with no stored position. Reading
from 0 would write one final giant duplicate of everything already recorded.

So: when there is no stored position **and** the diary already contains an
entry for this session id, seed the position to the transcript's current
length and record nothing for this turn. The backlog stays as it is — it is
already written, badly — and everything from the next turn on is correct.

When there is no stored position and no existing entry, the session is new:
read from 0, which is right.

### Assistant responses

With turn-scoped parsing, the assistant text in the new lines is this turn's
answer. Recorded in full rather than mined for keyword fragments.

The current `_extract_summary_hints` splits on every `.`, which breaks
`run-local.sh` into `run-local` and `sh`; 17.6% of the 32,887 summary lines in
the diary are damaged that way. Turn-scoped recording removes the reason that
function exists — there is no longer a session's worth of text to summarise,
only one answer to keep.

Whether it is dropped or kept alongside is decided when this is built, not
here; the split-on-period bug is fixed either way.

### What does not change

- The hook still fires per turn. That was never the problem.
- Existing entries are left alone. 6,971 of them, 85% redundant, and the
  transcripts that would be needed to rebuild them are 65% gone.
- `session_id` still identifies the session, so entries from one session
  remain groupable.
- `backfill` still imports a whole transcript as one entry. It is importing
  history, not following a live session, and it skips sessions already in the
  diary by reading the Markdown.

## Consequences to expect

- **Entry counts stop being comparable across the change.** Before: turns,
  mostly duplicated. After: turns, distinct. The daily counter counts entries
  either way, and its historical values stay inflated.
- **Per-entry line churn becomes meaningful**, since a turn's commits are its
  own. Historical values remain wrong and cannot be recomputed for the 65% of
  sessions whose transcripts are gone.
- **Notion pushes become finer-grained.** A session that pushed one row for
  its first five prompts will now have material for several. Whether that
  changes how `diary-notion` groups tasks is a separate question, deliberately
  not answered here.

## How it gets verified

The existing bar: reverting each piece must turn a test red, and the numbers
must be measured rather than asserted.

1. A synthetic transcript grown turn by turn, asserting each entry contains
   only that turn's prompts — the direct regression for the 85%.
2. Position survives a process restart; a shortened transcript resets it.
3. Concurrent sessions writing the progress file lose nothing, in separate
   processes rather than threads.
4. A session already in the diary with no stored position records nothing and
   seeds its position.
5. Re-run the duplication measurement above against a sandbox diary built from
   a real transcript replayed turn by turn: copies must be 0.
