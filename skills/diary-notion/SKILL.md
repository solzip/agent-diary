---
name: diary-notion
description: Push the current Codex work session to the hierarchical Notion working diary DB. Use when the user invokes $diary-notion or asks Codex to record the current session in Notion by project, purpose, task group, status, priority, sub-items, dependencies, blockers, next actions, files, commands, and commits.
---

# Diary Notion

Split the current Codex session into task-sized entries and push them to Notion.

## Current Implementation Contract

- `$diary-notion` is a row push workflow only. Do not run schema/view ensure unless the user explicitly asks for it.
- `working-diary diary-notion ensure` is the separate maintenance command that guarantees schema v7, native sub-items, 5 core views, and 5 operating views.
- Use Notion native sub-items for containment by setting `parent_index`. If the native relation is not enabled in Notion, still push the rows and report that sub-item activation is needed.
- Treat legacy `Parent Task` / `Sub-items` as compatibility data only. Do not target them directly in JSON.
- Use `Depends On` only for prerequisite links between large top-level main tasks. Never use dependencies for child tasks.
- Never write `"unknown"` as `project`; omit it or leave it blank so the CLI falls back to the command cwd folder name.
- Page bodies render as compact executive bodies: top summary, result checklist, work-at-a-glance table, impact, verification, risks/next action, and appendix.

## Workflow

1. Review the current conversation, tool calls, git branch, and relevant git commits.
2. Split work into task-sized database rows. Branch changes are hard task boundaries; within a branch, split by semantic work unit.
   - Create a row for work that has its own status, evidence, code/test output, or can block another task
   - Keep tiny check items, raw notes, long SQL/JS snippets, and reference links inside the page body evidence instead of making them separate rows
   - Create a separate row only when the work has an independent status, verification/evidence, code change, commit, blocker, or follow-up owner
   - Use `parent_index` for containment hierarchy and Notion sub-items; do not model subtasks with dependencies
   - Use `depends_on_indices` only for prerequisite links between large top-level tasks
   - Mark continued work from an earlier day/session as a new row with the same `task_group` and `carryover=true` when it is still unfinished
3. For each task, produce:
   - Language policy:
     - Write `title`, `body_intro`, `summary_hints`, `key_changes`, `work_context`, `work_scope`, `approach`, `outcome`, `impact`, `decisions`, `implementation_notes`, `verification`, `risks`, `next_steps`, `support_needed`, `next_action`, and `block_reason` in Korean
     - Keep `status` and `purpose` as the exact English enum values below
     - Preserve file paths, commands, branches, commit hashes, code identifiers, function names, and class names as written
     - Preserve `user_prompts` in the user's original wording as evidence
   - `title`: concise Korean noun phrase, no prefix or period
   - `body_intro`: 1-3 factual Korean sentences based only on observed work
   - Write it like a Notion task database record: compact top summary, structured relations in DB properties, and raw evidence hidden in the page body appendix
   - Body rendering policy:
     - Use `body_intro` as the only top summary callout
     - Treat `summary_hints` as checked result items, not repeated callouts
     - Keep `work_context`, `work_scope`, `approach`, and `outcome` short because they render as a compact "work at a glance" table
     - Put final verification state in `verification`; move intermediate command history to appendix evidence
     - Keep risks concise; multiple risks are combined into one warning callout
   - `summary_hints`: up to 3 outcome-focused result items that explain what changed and why it matters
   - `key_changes`: up to 3 major behavior/schema/workflow changes a developer can understand without opening the diff
   - `work_context`: 0-1 bullet explaining why this work started
   - `work_scope`: 0-1 bullet explaining what changed
   - `approach`: 0-1 bullet explaining how it was solved
   - `outcome`: 0-1 bullet explaining the resulting state
   - `impact`: 0-3 user, operations, product, or engineering-quality impacts
   - `code_change_highlights`: 0-3 important code changes only
     - Include file/function/command scope plus runtime or developer-facing meaning
     - Exclude full diffs, formatting-only edits, import cleanup, wording-only edits, and fixture-only noise
     - Include changes to behavior, schema, CLI flow, user workflow, or verification scope
   - `decisions`: 0-3 decisions or tradeoffs made by the user or settled during implementation
   - `implementation_notes`: 0-4 constraints, compatibility notes, migrations, or details that do not fit code highlights
   - `verification`: 0-3 tests/checks run, results, or explicit reasons checks were not run
   - `risks`: 0-2 cautions, remaining risks, or usage/operation notes
   - `next_steps`: 0-2 remaining follow-ups
   - `support_needed`: 0-1 decisions or support needed from others
   - `status`: `Discussion`, `Design`, `Implementation`, `Testing`, or `Deployed`
   - `purpose`: `Feature`, `Bugfix`, `Refactor`, `Docs`, `Test`, `Infra`, `Planning`, `Research`, `Review`, `Release`, `Support`, `Maintenance`, or `General`
   - `work_period`: actual work period; use today's `YYYY-MM-DD` by default, or `{"start":"YYYY-MM-DD","end":"YYYY-MM-DD"}` for a range
   - `priority`: one of `P0`, `P1`, `P2`, `P3`; use `P0` for urgent/blocking work, `P1` for today's highest priority, `P2` for normal follow-up, and `P3` for low priority
   - `next_action`: 0-1 concrete Korean action that can be started next
   - `blocked`: `true` only when the task cannot continue without external decision, permission, or information
   - `block_reason`: Korean reason when `blocked` is `true`
   - `carryover`: `true` when this row continues unfinished work from a previous day/session
   - `review_status`: `Needs Review`, `Reviewed`, or `Deferred`
   - `last_reviewed`: `YYYY-MM-DD` when this work was actually reviewed
   - `task_group`: stable kebab-case/snake-case group for multi-session work
   - `parent_index`: zero-based index of the parent task in this push, or `null`; use it for "part of" hierarchy and Notion sub-items
   - `depends_on_indices`: zero-based indices in this push, or `[]`
     - Use this only when a top-level main task cannot proceed before another top-level main task is done
     - Do not use this for child/subtask rows; use `parent_index` instead
   - `project`: current command cwd folder/repository name. Never write `"unknown"`; if you are not sure, omit the field or leave it empty so the CLI falls back to cwd.
   - `categories`, `user_prompts`, `files_modified`, `files_created`, `commands_run`, `commit_hashes`, `errors`
4. Create `.diary-notion-<8-random>.json` in cwd:

```json
{
  "session_id": "<current session id or codex-manual>",
  "tasks": [
    {
      "title": "...",
      "body_intro": "...",
      "summary_hints": ["..."],
      "key_changes": ["..."],
      "work_context": ["..."],
      "work_scope": ["..."],
      "approach": ["..."],
      "outcome": ["..."],
      "impact": ["..."],
      "code_change_highlights": ["..."],
      "decisions": ["..."],
      "implementation_notes": ["..."],
      "verification": ["..."],
      "risks": ["..."],
      "next_steps": ["..."],
      "support_needed": ["..."],
      "status": "Implementation",
      "purpose": "Feature",
      "work_period": "2026-06-02",
      "priority": "P1",
      "next_action": "...",
      "blocked": false,
      "block_reason": "",
      "carryover": false,
      "review_status": "Needs Review",
      "last_reviewed": "2026-06-02",
      "task_group": "working-diary-notion",
      "parent_index": null,
      "depends_on_indices": [],
      "categories": ["feature"],
      "project": "<cwd folder name>",
      "user_prompts": ["..."],
      "files_modified": ["..."],
      "files_created": ["..."],
      "commands_run": ["..."],
      "commit_hashes": ["..."],
      "errors": ["..."]
    }
  ]
}
```

5. Run `working-diary diary-notion push --input .diary-notion-<8-random>.json`.
6. If `working-diary` is not available, run `claude-diary diary-notion push --input .diary-notion-<8-random>.json`.
7. Report pushed/skipped/failed tasks from the CLI output.

If there are no task-worthy changes, explain that and do not call the CLI.
