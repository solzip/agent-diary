# Working Diary

Working Diary records Claude Code and Codex work sessions as Markdown diaries or task-based Notion work logs.

[![CI](https://github.com/solzip/working-diary/actions/workflows/ci.yml/badge.svg)](https://github.com/solzip/working-diary/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Core Dependencies: 0](https://img.shields.io/badge/core%20dependencies-0-brightgreen)](https://github.com/solzip/working-diary)

> English | [한국어](README.md)
>
> This is a community project. It is not an official Anthropic or OpenAI project.

## 1. Overview

Working Diary preserves the context that usually disappears when an AI coding session ends.

- User requests
- Created and modified files
- Important commands
- Git branch, commit, and diff statistics
- Work summaries and errors
- Task rows for a Notion work database

The package name remains `claude-diary` for compatibility. User-facing docs prefer the neutral `working-diary` CLI alias.

```bash
pip install claude-diary
working-diary init
```

### Supported Agents

| Agent | Auto diary | Manual Markdown | Notion work log | Apply/refresh |
|-------|------------|-----------------|-----------------|---------------|
| Claude Code | Stop Hook | `/diary` | `/diary-notion` | `working-diary install --force` |
| Codex | None | `$diary` | `$diary-notion` | `working-diary install --force --codex-only` |

Package installation is shared, but agent setup is different. Use `--codex-only` for Codex-only setup without modifying Claude Code settings. `--codex` remains as a compatibility option that also refreshes the Claude Code hook and slash commands.

### Storage Paths

Automatic diaries are appended to daily files.

```text
~/working-diary/
  2026-03-15.md
  2026-03-16.md
  .session_counts.json
  weekly/
    W11_2026-03-09.md
```

Manual diaries are stored separately by date and project.

```text
~/working-diary/manual/
  2026-04-29/
    my-project/
      2026-04-29.md
```

## 2. Usage

Follow the sequence for the target workflow.

| Goal | Command sequence |
|------|------------------|
| Claude Code Markdown auto/manual diary | `pip install claude-diary` -> `working-diary init` -> `working-diary install --force` |
| Claude Code with Notion work log | `pip install "claude-diary[notion]"` -> `working-diary init` -> `working-diary install --force` -> `working-diary diary-notion init` -> `working-diary diary-notion ensure` |
| Codex Markdown manual diary | `pip install claude-diary` -> `working-diary init --codex-only` -> `working-diary install --force --codex-only` -> open a new Codex session |
| Codex with Notion work log | `pip install "claude-diary[notion]"` -> `working-diary init --codex-only` -> `working-diary install --force --codex-only` -> `working-diary diary-notion init` -> `working-diary diary-notion ensure` -> open a new Codex session |

### 2-1. Package Install And Basic Setup

pip install:

```bash
pip install claude-diary
working-diary init
```

With Notion support:

```bash
pip install "claude-diary[notion]"
working-diary init
```

Claude Code plugin installation is a separate distribution path for Claude Code plugin marketplace users.

```bash
# Run inside Claude Code
/plugin marketplace add https://github.com/solzip/working-diary
/plugin install working-diary
```

The plugin distributes Claude Code hook settings. The `working-diary` CLI comes from the Python package, so Python package installation and `working-diary init` are still required.

Install from source:

```bash
git clone https://github.com/solzip/working-diary.git
cd working-diary
pip install -e .
working-diary init
```

Install from source with Notion support:

```bash
pip install -e ".[notion]"
```

`working-diary init` creates the config file and diary directory, and it also registers the Claude Code Stop Hook. If you only use Codex, run `working-diary init --codex-only` to avoid modifying Claude Code settings.

Run the agent-specific apply command below to refresh Claude Code slash commands or Codex skills.

### 2-2. Claude Code Usage

Claude Code supports automatic diaries when sessions end and manual diaries during a session.

Apply or refresh Claude Code setup:

```bash
working-diary install --force
```

Automatic diary flow:

```text
Claude Code session ends
  -> Stop Hook runs
  -> transcript is parsed
  -> ~/working-diary/YYYY-MM-DD.md
```

Manual Markdown diary:

```text
/diary
```

Notion work log:

```text
/diary-notion
```

`/diary` finds the Claude Code transcript for the current project and records it through the `working-diary write` core. `/diary-notion` creates task-row JSON from the session and passes it to `working-diary diary-notion push`.

### 2-3. Codex Usage

Codex does not use an automatic hook. It records only when the user invokes a skill.

Apply or refresh Codex setup:

```bash
working-diary install --force --codex-only
```

`--codex-only` installs only the Codex skills under `~/.codex/skills` and does not modify Claude Code hooks or slash commands. `--codex` remains as a compatibility option that also refreshes the Claude Code setup.

Manual Markdown diary:

```text
$diary
```

Notion work log:

```text
$diary-notion
```

`$diary` and `$diary-notion` create JSON from the current Codex conversation and tool activity, then call the same core CLI. Already-running Codex sessions keep the skills loaded at startup. Refreshed skills are applied in a new Codex session.

### 2-4. First Notion Setup

Notion work logs require the optional `requests` dependency.

```bash
pip install "claude-diary[notion]"
```

For source installs:

```bash
pip install -e ".[notion]"
```

Setup steps:

1. Create a Notion integration at https://www.notion.so/my-integrations and copy the token.
2. Create a Notion root page, for example `Working Diary`.
3. Share the root page with the integration.
4. Save the configuration.

```bash
working-diary diary-notion init
```

`diary-notion init` stores the Notion token and root page ID you enter in local config. If you later set `CLAUDE_DIARY_NOTION_TOKEN` or `CLAUDE_DIARY_NOTION_ROOT_PAGE_ID`, those environment variables override the saved config values.

5. Ensure the yearly `Entries` database, schema, and views.

```bash
working-diary diary-notion ensure
```

6. Run `/diary-notion` or `$diary-notion` from an agent session.

### 2-5. Notion Push Behavior

```bash
working-diary diary-notion push --input .diary-notion-<id>.json
working-diary diary-notion push --input .diary-notion-<id>.json --force
```

- Default push skips rows already recorded with the same `Session ID + Task Index`.
- `--force` archives prior rows for the session and pushes again.
- If any task fails, the command exits with code `1` and preserves the input JSON.
- Fully successful pushes and already-skipped pushes exit with code `0`.

### 2-6. Notion Sub-Items

Expandable task hierarchy uses Notion native Sub-items. Enable it once in the Notion UI.

1. Open the yearly `Entries` database.
2. Open the top-right `...` menu and enable `Sub-items`.
3. Run `working-diary diary-notion ensure` again.

Rows are still recorded if Sub-items are not enabled. Only visual nesting is missing, and push prints a hint.

## 3. Logic

### 3-1. Core Logic

The core handles actual recording independently of the agent.

```text
input
  -> transcript or agent-authored JSON
  -> cwd, session_id, task metadata

core processing
  -> parser
  -> Git enrichment
  -> category inference
  -> secret scan
  -> formatter
  -> writer or Notion exporter
  -> audit/index/export retry
```

Key modules:

| Area | File | Role |
|------|------|------|
| CLI entry | `src/claude_diary/cli/__init__.py` | Routes `working-diary` and `claude-diary` commands |
| Automatic diary core | `src/claude_diary/core.py` | Claude Code Stop Hook diary pipeline |
| Manual diary core | `src/claude_diary/cli/write.py` | Handles `/diary`, `$diary`, and `working-diary write` |
| Notion push | `src/claude_diary/cli/notion_push.py` | Pushes task JSON as Notion rows |
| Notion schema/view | `src/claude_diary/cli/notion_ensure.py` | Ensures schema v7 and core/operating views |
| Formatter | `src/claude_diary/formatter.py` | Creates Markdown entries and Notion page bodies |

### 3-2. Claude Code Logic

Automatic diary:

```text
Claude Code Stop Hook
  -> src/claude_diary/hook.py
  -> core.process_session(session_id, transcript_path, cwd)
  -> ~/working-diary/YYYY-MM-DD.md
```

Manual diary:

```text
/diary
  -> claude-diary write
  -> find Claude transcript for the current cwd
  -> append to manual diary path

/diary-notion
  -> agent creates task JSON
  -> claude-diary diary-notion push --input <json>
  -> push rows to Notion Entries DB
```

`working-diary install --force` refreshes:

- `~/.claude/settings.json` Stop Hook
- `~/.claude/commands/diary.md`
- `~/.claude/commands/diary-notion.md`

### 3-3. Codex Logic

Codex has no Stop Hook. Global skills call the core CLI.

```text
$diary
  -> Codex writes current session content to .diary-<id>.json
  -> working-diary write --input .diary-<id>.json
  -> append to manual diary path

$diary-notion
  -> Codex splits the session into tasks
  -> writes .diary-notion-<id>.json
  -> working-diary diary-notion push --input .diary-notion-<id>.json
  -> push rows to Notion Entries DB
```

`working-diary install --force --codex-only` refreshes:

- `~/.codex/skills/diary/SKILL.md`
- `~/.codex/skills/diary-notion/SKILL.md`

## 4. CLI

Core commands:

```bash
working-diary init
working-diary init --codex-only
working-diary install --force
working-diary install --force --codex
working-diary install --force --codex-only
working-diary uninstall
working-diary uninstall --codex
working-diary uninstall --codex-only

working-diary write
working-diary diary-notion init
working-diary diary-notion ensure
working-diary diary-notion ensure --dry-run
working-diary diary-notion ops
working-diary diary-notion push --input .diary-notion-<id>.json
working-diary notion push --input .diary-notion-<id>.json
```

Search and maintenance commands:

```bash
working-diary search "keyword"
working-diary filter --project my-app
working-diary trace src/main.py
working-diary stats
working-diary weekly
working-diary audit
working-diary audit --verify
working-diary config
working-diary config --set lang=en
working-diary migrate
working-diary reindex
working-diary delete --last
```

Extension commands:

```bash
working-diary config --add-exporter slack
working-diary config --add-exporter discord
working-diary config --add-exporter obsidian
working-diary config --add-exporter github
working-diary dashboard
working-diary dashboard --serve --port 8787
working-diary team stats
working-diary team weekly
working-diary team monthly --month 2026-06
working-diary team init --repo <url> --name <name>
working-diary team add-member --name <name> --role member
```

The legacy CLI remains supported.

```bash
claude-diary write
claude-diary diary-notion ensure
```

## 5. Configuration

The config file is stored at the OS-specific user config path under `claude-diary/config.json`. If you configure exporters such as Notion, Slack, or Discord, API tokens, webhook URLs, and root page IDs are stored in this local config. CLI output masks long token and webhook values.

| Environment variable | Description | Default |
|----------------------|-------------|---------|
| `CLAUDE_DIARY_LANG` | Diary language, `ko` or `en` | `ko` |
| `CLAUDE_DIARY_DIR` | Automatic diary path | `~/working-diary` |
| `CLAUDE_DIARY_MANUAL_DIR` | Manual diary path | `~/working-diary/manual` |
| `CLAUDE_DIARY_TZ_OFFSET` | UTC offset | `9` |
| `CLAUDE_DIARY_NOTION_TOKEN` | Notion token, overrides config | - |
| `CLAUDE_DIARY_NOTION_ROOT_PAGE_ID` | Notion root page ID, overrides config | - |
| `CLAUDE_DIARY_SKIP` | `1`, `true`, or `yes` skips Claude Code Stop Hook auto diary | - |

If PowerShell output shows broken Korean or emoji characters, switch the current session output encoding to UTF-8.

```powershell
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$OutputEncoding = [System.Text.UTF8Encoding]::new()
```

## 6. Features

- Automatic category inference
- Git branch, commit, and diff stat recording
- Secret scanning and masking
- Search index
- Notion work log: `working-diary diary-notion init` -> `working-diary diary-notion ensure`
- Notion operations report: `working-diary diary-notion ops` for blocked/review/next action/stale/work days/today-plan candidates/parent status signals
- Slack, Discord, Obsidian, GitHub exporters: `working-diary config --add-exporter <name>`
- HTML dashboard: `working-diary dashboard` or `working-diary dashboard --serve --port 8787`
- Audit log and source checksum verification
- Team mode: `working-diary team init --repo <url> --name <name>`

## 7. Troubleshooting

| Symptom | Check |
|---------|-------|
| `/diary` or `/diary-notion` does not use the latest instructions | Run `working-diary install --force` to refresh the hook and slash commands |
| `$diary` or `$diary-notion` does not use the latest instructions | Run `working-diary install --force --codex-only`, then open a new Codex session |
| Notion push reports an auth error | Check the integration token, root page ID, and page sharing |
| Notion task hierarchy is not nested | Enable Sub-items once in the Notion `Entries` database UI |
| Re-push might duplicate rows | Default push skips the same `Session ID + Task Index`; use `--force` to rewrite |
| PowerShell text is garbled | Apply the UTF-8 output setting above |

## 8. Development

```bash
pip install -e ".[dev,notion]"
python -m pytest -q
python -m ruff check .
```

## 9. Roadmap

This README focuses on currently usable functionality. Detailed design and planning artifacts live under `docs/`.

| Area | Status |
|------|--------|
| Stable now | Claude Code Stop Hook, Codex skills, Markdown diaries, Notion task row push, schema/view ensure |
| Phase 3 started | `working-diary diary-notion ops` read-only operations report, parent/task group progress, ensure conflict classification and repair plans |
| Next | Windows install/output experience, Notion sub-item guidance, incremental CI/lint expansion |
| Under review | SQLite search index, Cursor/Windsurf/VS Code integration |

## 10. Documentation

- [Notion hierarchical design](docs/02-design/features/diary-notion-hierarchical.design.md)
- [Notion views design](docs/02-design/features/diary-notion-views.design.md)
- [Distribution plan](docs/plans/phase-d-distribution.md)
- [Contributing](CONTRIBUTING.md)
- [Security](SECURITY.md)

## 11. License

MIT
