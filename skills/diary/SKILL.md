---
name: diary
description: Write the current Codex work session to the manual working diary. Use when the user invokes $diary or asks Codex to record the current work session as a Markdown diary entry, including prompts, files, commands, summaries, errors, categories, and git metadata.
---

# Diary

Record the current Codex session as a manual Markdown work diary entry.

## Workflow

1. Summarize the current conversation and tool activity into one diary entry.
2. Use the current cwd folder name as `project`.
3. Create `.diary-<8-random>.json` in cwd with this shape:

```json
{
  "session_id": "<current session id or manual-codex>",
  "project": "<cwd folder name>",
  "user_prompts": ["..."],
  "files_modified": ["..."],
  "files_created": ["..."],
  "commands_run": ["..."],
  "summary_hints": ["..."],
  "errors": ["..."],
  "categories": ["feature"]
}
```

4. Run `working-diary write --input .diary-<8-random>.json`.
5. If `working-diary` is not available, run `claude-diary write --input .diary-<8-random>.json`.
6. Report the CLI result. The CLI removes the temp file after a successful write.

Only include content visible in the current conversation or tool history. Do not invent work.
