---
name: diary-notion
description: Push the current Codex work session to the hierarchical Notion working diary DB. Use when the user invokes $diary-notion or asks Codex to record the current session in Notion by project, purpose, task group, branch, status, categories, files, commands, commits, and dependencies.
---

# Diary Notion

Split the current Codex session into task-sized entries and push them to Notion.

## Workflow

1. Review the current conversation, tool calls, git branch, and relevant git commits.
2. Split work into task-sized database rows. Branch changes are hard task boundaries; within a branch, split by semantic work unit.
   - Create a row for work that has its own status, evidence, code/test output, or can block another task
   - Keep tiny check items, raw notes, long SQL/JS snippets, and reference links inside the page body evidence instead of making them separate rows
   - Use `parent_index` for containment hierarchy and `depends_on_indices` for prerequisite order; do not mix the two
3. For each task, produce:
   - Language policy:
     - Write `title`, `body_intro`, `summary_hints`, `key_changes`, `work_context`, `work_scope`, `approach`, `outcome`, `impact`, `decisions`, `implementation_notes`, `verification`, `risks`, `next_steps`, and `support_needed` in Korean
     - Keep `status` and `purpose` as the exact English enum values below
     - Preserve file paths, commands, branches, commit hashes, code identifiers, function names, and class names as written
     - Preserve `user_prompts` in the user's original wording as evidence
   - `title`: concise Korean noun phrase, no prefix or period
   - `body_intro`: 1-3 factual Korean sentences based only on observed work
   - Write it like a Notion task database record: compact top summary, structured relations in DB properties, and raw evidence hidden in the page body appendix
   - `summary_hints`: up to 3 outcome-focused bullets that explain what changed and why it matters
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
   - `task_group`: stable kebab-case/snake-case group for multi-session work
   - `parent_index`: zero-based index of the parent task in this push, or `null`; use it for "part of" hierarchy
   - `depends_on_indices`: zero-based indices in this push, or `[]`
     - Use this only when the current task cannot proceed before another task is done
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
