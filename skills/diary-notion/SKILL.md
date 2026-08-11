---
name: diary-notion
description: Push the current Codex work session to the hierarchical Notion working diary DB. Use when the user invokes $diary-notion or asks Codex to record the current session in Notion by project, purpose, task group, status, priority, sub-items, dependencies, blockers, next actions, files, commands, and commits.
---

# Diary Notion

Split the current Codex session into task-sized entries and push them to Notion.

## Current Implementation Contract

- `$diary-notion` is a row push workflow only. Do not run schema/view ensure unless the user explicitly asks for it.
- `agent-diary diary-notion ensure` is the separate maintenance command that guarantees schema v8, native sub-items, 5 core views, and 5 operating views.
- Use Notion native sub-items for containment by setting `parent_index`. If the native relation is not enabled in Notion, still push the rows and report that sub-item activation is needed.
- Treat legacy `Parent Task` / `Sub-items` as compatibility data only. Do not target them directly in JSON.
- Use `Depends On` only for prerequisite links between large top-level main tasks. Never use dependencies for child tasks.
- Never write `"unknown"` as `project`; omit it or leave it blank so the CLI falls back to the command cwd folder name.
- Page bodies render as compact work reports: summary, results, work table, decisions, issues/risks, next actions/support, and appendix toggles.
- Notion is the report surface; raw logs, long diffs, and bulky evidence belong in local artifact files and should be referenced by path/hash instead of pasted.
- `diary-notion push` writes local run artifacts under `.codefleet/runs` by default: `input.json`, `git-diff.patch`, `preview.md`, and `manifest.json`. Use `--preview-file` for an extra Markdown preview path or `--no-artifacts` to disable local artifact writes.
- For testing, QA, review, validation, or verification sessions, create a row even without code changes; keep `verification` short and place the meaningful prompt-result document in `prompt_outputs` or `verification_artifacts` so it renders inside a toggle.

## Workflow

1. Review the current conversation, tool calls, git branch, and relevant git commits.
2. Split work into task-sized database rows. Branch changes are hard task boundaries; within a branch, split by semantic work unit.
   - Create a row for work that has its own status, evidence, code/test output, or can block another task
   - Create a row for verification-only work even when the session produced no file changes or commits
   - Keep tiny check items, raw notes, long SQL/JS snippets, and reference links inside the page body evidence instead of making them separate rows
   - Create a separate row only when the work has an independent status, verification/evidence, code change, commit, blocker, or follow-up owner
   - For tester/verification sessions, summarize the final state in `verification` and put each meaningful pass, fail, blocker, skipped check, regression, defect, and follow-up in the prompt-output artifact fields
   - Use `parent_index` for containment hierarchy and Notion sub-items; do not model subtasks with dependencies
   - Use `depends_on_indices` only for prerequisite links between large top-level tasks
   - Mark continued work from an earlier day/session as a new row with the same `task_group` and `carryover=true` when it is still unfinished
3. For each task, produce:
   - Prefer schema v2 normalized fields: `summary`, `work`, `decisions`, `risks`, `next_actions`, `support_needed`, and `appendix`.
   - Legacy flat fields are still accepted by the CLI, but new agent output should use v2 unless compatibility with an older installed version is required.
   - Language policy:
     - Write `title`, `summary`, `work`, `decisions`, `risks`, `next_actions`, `support_needed`, `appendix`, `next_action`, and `block_reason` narrative values in Korean
     - Keep `status` and `purpose` as the exact English enum values below
     - Preserve file paths, commands, branches, commit hashes, code identifiers, function names, and class names as written
     - Preserve `user_prompts` in the user's original wording as evidence
   - `title`: concise Korean noun phrase, no prefix or period
   - `body_intro`: 1-3 factual Korean sentences based only on observed work
   - Write it like a Notion task database record: compact top summary, structured relations in DB properties, and raw evidence hidden in the page body appendix
   - Body rendering policy:
     - Use `summary.intro` as the only top summary callout
     - Treat `summary.outcomes`, `summary.verification`, and `summary.remaining` as the compact results checklist
     - Keep `work.context`, `work.scope`, `work.approach`, and `work.state` short because they render as a compact work table
     - Put settled choices in `decisions`; put unresolved external asks in `support_needed`
     - Keep `risks` concise as issue/risk bullets, not raw logs
     - Put developer evidence, prompt outputs, original requests, and command/file/commit evidence in `appendix` toggles
     - For tester/verification sessions, keep `summary.verification` to 1-3 summary items and put the meaningful prompt-result document in `appendix.prompt_outputs` or `appendix.verification_artifacts`; summarize long raw logs instead of pasting them
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
   - `verification`: 0-3 summary tests/checks run, final results, or explicit reasons checks were not run
   - `prompt_outputs`: 0-15 meaningful prompt-result items for tester/verification sessions; include distinct pass/fail/blocker/skipped/regression/defect/follow-up results, not raw logs
   - `verification_artifacts`: 0-15 structured verification artifact items when the prompt output is better grouped as a generated test report or review document
   - `appendix.artifacts`: 0-5 local artifact references with `path`, `kind`, `summary`, and optional `sha256`; use this for stdout/stderr/diff/raw-log evidence
   - `risks`: 0-2 cautions, remaining risks, or usage/operation notes
   - `next_steps`: 0-2 remaining follow-ups
   - `support_needed`: 0-1 decisions or support needed from others
   - `status`: `Discussion`, `Design`, `Implementation`, `Testing`, or `Deployed`
   - `purpose`: `Feature`, `Bugfix`, `Refactor`, `Docs`, `Test`, `Infra`, `Planning`, `Research`, `Review`, `Release`, `Support`, `Maintenance`, or `General`
     - Use `Test` for tester, QA, validation, and verification-only sessions unless another enum is clearly more accurate
   - Omit any optional field you cannot ground in what actually happened this session. A guessed value is worse than a blank one: it reads as a real signal in Notion and in `agent-diary diary-notion ops`
   - `work_period`: only for work that genuinely spans several days, as `{"start":"YYYY-MM-DD","end":"YYYY-MM-DD"}`. Omit it for single-day work — the CLI records the date the command ran
   - `priority`: `P0`, `P1`, `P2`, or `P3`, only when the session gives a real reason to rank it — `P0` when it blocks other work, `P1` when the user asked for it next. Omit it rather than defaulting everything to `P2`
   - `next_action`: 0-1 concrete Korean action that can be started next
   - `blocked`: `true` only when the task cannot continue without external decision, permission, or information
   - `block_reason`: Korean reason when `blocked` is `true`
   - `carryover`: `true` when this row continues unfinished work from a previous day/session
   - Do not author review state. Every row is filed as `Needs Review`; only a human running `agent-diary diary-notion review --apply` moves it to `Reviewed`
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
  "schema_version": 2,
  "tasks": [
    {
      "title": "...",
      "summary": {
        "intro": "...",
        "outcomes": ["..."],
        "verification": ["..."],
        "remaining": ["..."]
      },
      "work": {
        "context": "...",
        "scope": "...",
        "approach": "...",
        "state": "..."
      },
      "decisions": ["..."],
      "risks": ["..."],
      "next_actions": ["..."],
      "support_needed": ["..."],
      "appendix": {
        "key_changes": ["..."],
        "implementation_notes": ["..."],
        "prompt_outputs": ["..."],
        "verification_artifacts": ["..."],
        "user_prompts": ["..."],
        "files_modified": ["..."],
        "files_created": ["..."],
        "commands_run": ["..."],
        "commit_hashes": ["..."],
        "errors": ["..."],
        "artifacts": [
          {
            "kind": "stdout",
            "path": ".codefleet/runs/<run-id>/stdout.log",
            "summary": "raw command output",
            "sha256": "..."
          }
        ]
      },
      "status": "Implementation",
      "purpose": "Feature",
      "priority": "P1",
      "next_action": "...",
      "blocked": false,
      "block_reason": "",
      "carryover": false,
      "task_group": "agent-diary-notion",
      "parent_index": null,
      "depends_on_indices": [],
      "categories": ["feature"],
      "project": "<cwd folder name>"
    }
  ]
}
```

5. Run `agent-diary diary-notion push --input .diary-notion-<8-random>.json --dry-run` to validate v2 input, write local artifacts, and preview the compact report body and appendix toggles without writing to Notion.
6. If the preview is structurally wrong, fix the JSON before pushing.
7. Run `agent-diary diary-notion push --input .diary-notion-<8-random>.json`.
8. If `agent-diary` is not available, run `working-diary diary-notion push --input .diary-notion-<8-random>.json`.
9. Report pushed/skipped/failed tasks from the CLI output.

If there are no task-worthy changes, explain that and do not call the CLI.
