# Agent Diary

**Remember what you did with an AI.** Automatically when a Claude Code session ends, or on one command in Codex, Agent Diary records what you asked for and what changed.

[![CI](https://github.com/solzip/agent-diary/actions/workflows/ci.yml/badge.svg)](https://github.com/solzip/agent-diary/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Core Dependencies: 0](https://img.shields.io/badge/core%20dependencies-0-brightgreen)](https://github.com/solzip/agent-diary)

> English | [한국어](README.ko.md)
>
> This is a community project. It is not an official Anthropic or OpenAI project.

![Agent Diary demo](docs/demo.svg)

> **Here to read the code?** [Architecture](docs/ARCHITECTURE.md) covers the idempotency key and its cache invalidation, a retry policy that branches on cause, schema versioning, and what partial failure means. The [postmortem](docs/postmortem/2026-08-07-ensure-wipe.md) is how one schema PATCH emptied six properties across 497 rows.

## 1. Why

Work done with an AI lives in a chat window, and chat windows close. Two days later there is no way back to why a file was changed the way it was, and when a weekly review or a status report comes due you are working from memory. A commit log keeps the result; it does not keep what you asked for or what was tried on the way there.

Agent Diary captures that context at the moment a session ends. There is no habit to build.

One finished session appends an entry like this.

```markdown
### ⏰ 14:30:15 | 📁 `my-app`

**🏷️ Categories:** `feature` `test`

**📋 Task Requests:**
  1. Add JWT authentication to login
  2. Write the tests as well

**📄 Files Created:**
  - `src/auth/jwt_handler.py`
  - `tests/test_auth.py`

**✏️ Files Modified:**
  - `src/api/routes.py`

**🔀 Git:**
  - 🌿 Branch: `feat/jwt-auth`
  - Commit: `a1b2c3d` feat: verify tokens and cover login

**📊 Code Stats:** +145 / -12 lines (5 files)

**⚡ Key Commands:**
  - `export API_KEY=****`
  - `pytest -q`

**📝 Work Summary:**
  - Added JWT verification middleware and covered the login failure path

**🔒 1 secrets masked**
```

Categories are inferred from the work. Branch, commits and diff stats are read from the repository. Anything that looks like a secret — the `API_KEY` above — is masked **before** the file is written.

### What makes it different

- **It is automatic.** In Claude Code a Stop Hook picks up the end of a session. You never have to decide to record something.
- **Zero core dependencies.** Standard library only. `requests` is added only if you use the Notion integration.
- **Local files.** Plain Markdown, so it greps, it opens in Obsidian, and it outlives any service.
- **It scales to a team.** Push to a Notion work-log database when you need to, or export to Slack, Discord and GitHub.

```bash
pip install agent-diary
agent-diary init
agent-diary backfill      # optional: import the sessions you already have
```

Nothing else is required. Every Claude Code session from then on lands in `~/working-diary/YYYY-MM-DD.md`.

Claude Code has been keeping transcripts on disk all along, so `backfill` gives you a diary of work you already did rather than an empty directory. On the machine this was built on it turned 79 past sessions into 21 days of entries. Running it twice changes nothing — sessions already in the diary are skipped.

> This project was `claude-diary`, then `working-diary`, and is now `agent-diary`. If you installed it under an older name, the `working-diary` and `claude-diary` commands still work.
>
> The internal Python package is still `claude_diary`. `install` writes `python -m claude_diary.hook` into the user's `settings.json`, so renaming it would stop an existing Stop Hook silently. A distribution name that differs from the import name is ordinary in Python.

### Supported Agents

| Agent | Auto diary | Manual Markdown | Notion work log | Apply/refresh |
|-------|------------|-----------------|-----------------|---------------|
| Claude Code | Stop Hook | `/diary` | `/diary-notion` | `agent-diary install --force` |
| Codex | None | `$diary` | `$diary-notion` | `agent-diary install --force --codex-only` |

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
| Claude Code Markdown auto/manual diary | `pip install agent-diary` -> `agent-diary init` -> `agent-diary install --force` |
| Claude Code with Notion work log | `pip install "agent-diary[notion]"` -> `agent-diary init` -> `agent-diary install --force` -> `agent-diary diary-notion init` -> `agent-diary diary-notion ensure` |
| Codex Markdown manual diary | `pip install agent-diary` -> `agent-diary init --codex-only` -> `agent-diary install --force --codex-only` -> open a new Codex session |
| Codex with Notion work log | `pip install "agent-diary[notion]"` -> `agent-diary init --codex-only` -> `agent-diary install --force --codex-only` -> `agent-diary diary-notion init` -> `agent-diary diary-notion ensure` -> open a new Codex session |

### 2-1. Package Install And Basic Setup

pip install:

```bash
pip install agent-diary
agent-diary init
```

With Notion support:

```bash
pip install "agent-diary[notion]"
agent-diary init
```

Claude Code plugin installation is a separate distribution path for Claude Code plugin marketplace users.

```bash
# Run inside Claude Code
/plugin marketplace add https://github.com/solzip/agent-diary
/plugin install agent-diary
```

The plugin distributes Claude Code hook settings. The `agent-diary` CLI comes from the Python package, so Python package installation and `agent-diary init` are still required.

Install from source:

```bash
git clone https://github.com/solzip/agent-diary.git
cd agent-diary
pip install -e .
agent-diary init
```

Install from source with Notion support:

```bash
pip install -e ".[notion]"
```

`agent-diary init` creates the config file and diary directory, and it also registers the Claude Code Stop Hook. If you only use Codex, run `agent-diary init --codex-only` to avoid modifying Claude Code settings.

Run the agent-specific apply command below to refresh Claude Code slash commands or Codex skills.

### 2-2. Claude Code Usage

Claude Code supports automatic diaries when sessions end and manual diaries during a session.

Apply or refresh Claude Code setup:

```bash
agent-diary install --force
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

`/diary` finds the Claude Code transcript for the current project and records it through the `agent-diary write` core. `/diary-notion` creates task-row JSON from the session and passes it to `agent-diary diary-notion push`.

### 2-3. Codex Usage

Codex does not use an automatic hook. It records only when the user invokes a skill.

Apply or refresh Codex setup:

```bash
agent-diary install --force --codex-only
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
pip install "agent-diary[notion]"
```

For source installs:

```bash
pip install -e ".[notion]"
```

Setup steps:

1. Create a Notion integration at https://www.notion.so/my-integrations and copy the token.
2. Create a Notion root page, for example `Agent Diary`.
3. Share the root page with the integration.
4. Save the configuration.

```bash
agent-diary diary-notion init
```

`diary-notion init` stores the Notion token and root page ID you enter in local config. If you later set `CLAUDE_DIARY_NOTION_TOKEN` or `CLAUDE_DIARY_NOTION_ROOT_PAGE_ID`, those environment variables override the saved config values.

5. Ensure the yearly `Entries` database, schema, and views.

```bash
agent-diary diary-notion ensure
```

6. Run `/diary-notion` or `$diary-notion` from an agent session.

### 2-5. Notion Push Behavior

```bash
agent-diary diary-notion push --input .diary-notion-<id>.json
agent-diary diary-notion push --input .diary-notion-<id>.json --force
agent-diary diary-notion push --input .diary-notion-<id>.json --dry-run
```

- Default push skips rows already recorded with the same `Session ID + Task Index`.
- `--force` archives prior rows for the session and pushes again.
- `--dry-run` prints the rows and page bodies that would be created without writing to Notion. Add `--preview-file <path>` to save the same rendering as Markdown.
- If a `Task Group` already has recorded sessions, the title gets an `(N차)` ordinal. The first session of a group is left alone.
- `--dry-run` **reads** from Notion to resolve that ordinal — a query, nothing more. Without credentials, or before that year's database exists, it renders without the ordinal and says so at the top of the output. A preview never creates a page or a database.
- If any task fails, the command exits with code `1` and preserves the input JSON.
- Fully successful pushes and already-skipped pushes exit with code `0`.

### 2-6. What A Push Leaves On Disk (Run Artifacts)

Every push writes a record of the run under the current working directory, **by default**. `--dry-run` writes it too.

```text
<cwd>/.agent-diary/runs/<YYYYMMDD-HHMMSS-session>/
  input.json        the original task JSON
  git-diff.patch    the working tree diff at push time
  preview.md        the rendered Notion body
  manifest.json     the files above with sha256, plus a push result summary
```

Notion is the destination, not the record. If a push half-fails, or a row is later edited by hand, this local copy is the only way back to what was actually submitted.

**`git-diff.patch` contains your uncommitted code.** Keep it out of your repository:

```gitignore
.agent-diary/runs/
```

To relocate or disable it:

```bash
agent-diary diary-notion push --input <json> --artifact-dir build/diary-runs
agent-diary diary-notion push --input <json> --no-artifacts
```

### 2-7. Review Queue

Review is a judgement a person makes after the fact, so no stage of the recording pipeline declares work reviewed on its own. Push files every new row as `Needs Review`, and only this command's `--apply` promotes a row to `Reviewed`.

```bash
agent-diary diary-notion review              # list rows awaiting review (read-only)
agent-diary diary-notion review --apply      # set Reviewed + Last Reviewed=today
agent-diary diary-notion review --year 2026
```

Without `--apply` nothing is written, matching the `ensure --dry-run` / `ensure` pattern.

### 2-8. Notion Sub-Items

Expandable task hierarchy uses Notion native Sub-items. Enable it once in the Notion UI.

1. Open the yearly `Entries` database.
2. Open the top-right `...` menu and enable `Sub-items`.
3. Run `agent-diary diary-notion ensure` again.

Rows are still recorded if Sub-items are not enabled. Only visual nesting is missing, and push prints a hint.

## 3. Logic

This section covers **what flows where, in what order**. Why it is built that way — the idempotency key, the retry policy, schema versioning, partial-failure handling — is in [Architecture](docs/ARCHITECTURE.md).

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
| CLI entry | `src/claude_diary/cli/__init__.py` | Routes the `agent-diary` command and its `working-diary` / `claude-diary` aliases |
| Automatic diary core | `src/claude_diary/core.py` | Claude Code Stop Hook diary pipeline |
| Manual diary core | `src/claude_diary/cli/write.py` | Handles `/diary`, `$diary`, and `agent-diary write` |
| Notion push | `src/claude_diary/cli/notion_push/` | Pushes task JSON as Notion rows (split into validate/properties/relations/artifacts) |
| Notion schema/view | `src/claude_diary/cli/notion_ensure.py` | Ensures schema v8, 5 core views and 5 operating views |
| Notion review queue | `src/claude_diary/cli/notion_review.py` | Lists `Needs Review` rows; `--apply` records `Reviewed` |
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
  -> agent-diary write
  -> find Claude transcript for the current cwd
  -> append to manual diary path

/diary-notion
  -> agent creates task JSON
  -> agent-diary diary-notion push --input <json>
  -> push rows to Notion Entries DB
```

`agent-diary install --force` refreshes:

- `~/.claude/settings.json` Stop Hook
- `~/.claude/commands/diary.md`
- `~/.claude/commands/diary-notion.md`

### 3-3. Codex Logic

Codex has no Stop Hook. Global skills call the core CLI.

```text
$diary
  -> Codex writes current session content to .diary-<id>.json
  -> agent-diary write --input .diary-<id>.json
  -> append to manual diary path

$diary-notion
  -> Codex splits the session into tasks
  -> writes .diary-notion-<id>.json
  -> agent-diary diary-notion push --input .diary-notion-<id>.json
  -> push rows to Notion Entries DB
```

`agent-diary install --force --codex-only` refreshes:

- `~/.codex/skills/diary/SKILL.md`
- `~/.codex/skills/diary-notion/SKILL.md`

## 4. CLI

Core commands:

```bash
agent-diary init
agent-diary init --codex-only
agent-diary install --force
agent-diary install --force --codex
agent-diary install --force --codex-only
agent-diary uninstall
agent-diary uninstall --codex
agent-diary uninstall --codex-only

agent-diary write
agent-diary write --input .diary-<id>.json

agent-diary backfill
agent-diary backfill --dry-run
agent-diary backfill --since 2026-07-01
agent-diary backfill --limit 20
agent-diary backfill --transcripts /path/to/projects

agent-diary doctor
agent-diary doctor --notion

agent-diary diary-notion init
agent-diary diary-notion ensure
agent-diary diary-notion ensure --dry-run
agent-diary diary-notion ensure --year 2026

agent-diary diary-notion push --input .diary-notion-<id>.json
agent-diary diary-notion push --input .diary-notion-<id>.json --force
agent-diary diary-notion push --input .diary-notion-<id>.json --dry-run
agent-diary diary-notion push --input .diary-notion-<id>.json --preview-file preview.md
agent-diary diary-notion push --input .diary-notion-<id>.json --artifact-dir build/diary-runs
agent-diary diary-notion push --input .diary-notion-<id>.json --no-artifacts

agent-diary diary-notion ops
agent-diary diary-notion ops --stale-days 14
agent-diary diary-notion ops --json

agent-diary diary-notion review
agent-diary diary-notion review --apply

agent-diary notion push --input .diary-notion-<id>.json
```

Search and maintenance commands:

```bash
agent-diary search "keyword"
agent-diary filter --project my-app
agent-diary trace src/main.py
agent-diary stats
agent-diary weekly
agent-diary audit
agent-diary audit --verify
agent-diary config
agent-diary config --set lang=en
agent-diary migrate
agent-diary reindex
agent-diary delete --last
```

Extension commands:

```bash
agent-diary config --add-exporter slack
agent-diary config --add-exporter discord
agent-diary config --add-exporter obsidian
agent-diary config --add-exporter github
agent-diary dashboard
agent-diary dashboard --serve --port 8787
agent-diary team stats
agent-diary team weekly
agent-diary team monthly --month 2026-06
agent-diary team init --repo <url> --name <name>
agent-diary team add-member --name <name> --role member
```

The legacy CLI remains supported.

```bash
agent-diary write
agent-diary diary-notion ensure
```

## 5. Configuration

The config file is stored at the OS-specific user config path under `claude-diary/config.json`. If you configure exporters such as Notion, Slack, or Discord, API tokens, webhook URLs, and root page IDs are stored in this local config. CLI output masks long token and webhook values.

These variables fall into **two groups whose precedence runs in opposite directions**. Read the last column first.

| Environment variable | Description | Default | Precedence |
|----------------------|-------------|---------|------------|
| `CLAUDE_DIARY_LANG` | Diary language, `ko` or `en` | `ko` | config.json wins |
| `CLAUDE_DIARY_DIR` | Automatic diary path | `~/working-diary` | config.json wins |
| `CLAUDE_DIARY_MANUAL_DIR` | Manual diary path | `~/working-diary/manual` | config.json wins |
| `CLAUDE_DIARY_TZ_OFFSET` | UTC offset | `9` | config.json wins |
| `CLAUDE_DIARY_NOTION_TOKEN` | Notion token | - | **env wins** |
| `CLAUDE_DIARY_NOTION_ROOT_PAGE_ID` | Notion root page ID | - | **env wins** |
| `CLAUDE_DIARY_SKIP` | `1`, `true`, or `yes` skips Claude Code Stop Hook auto diary | - | env only |

The first four merge as `config.json > environment > defaults`. So if you have ever run `init`, the key is already written to the config and **setting the environment variable has no effect.** To move the diary path, edit `config.json` rather than exporting a variable.

### Gitmoji on commit lines

Off by default. Turn it on in `config.json` and each commit line gains the [gitmoji](https://gitmoji.dev) for its Conventional Commit type:

```json
{ "formatting": { "gitmoji": true } }
```

```diff
-  - Commit: `a1b2c3d` feat: verify tokens and cover login
+  - Commit: `a1b2c3d` ✨ feat: verify tokens and cover login
```

A commit with no recognised type is left as it is, and one that already starts with an emoji is not given a second.

It applies to commit lines only, not to the category tags. Three gitmoji — 📝, ⚡ and 🔒 — already mean Work Summary, Key Commands and secrets-masked in an entry, and decorating categories would give the same glyph two meanings on one screen.

The two Notion credentials are the exception and override the config, so a token need not be written to a file in CI or when moving between workspaces.

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
- Notion work log: `agent-diary diary-notion init` -> `agent-diary diary-notion ensure`
- Notion operations report: `agent-diary diary-notion ops` for blocked/review/next action/stale/work days/today-plan candidates/parent status signals
- Review queue: `agent-diary diary-notion review`. Push always files as `Needs Review`; only `--apply` promotes a row to `Reviewed`
- Run artifacts: every push preserves `input.json`, `git-diff.patch`, `preview.md` and `manifest.json` locally, each sha256-stamped
- Automatic `(N차)` ordinals for sessions continuing the same `Task Group`, with no extra column
- A day's rows read in the order the work was done (`Date` ties broken by `Task Index`)
- Slack, Discord, Obsidian, GitHub exporters: `agent-diary config --add-exporter <name>`
- HTML dashboard: `agent-diary dashboard` or `agent-diary dashboard --serve --port 8787`
- Audit log and source checksum verification
- Team mode: `agent-diary team init --repo <url> --name <name>`

## 7. Troubleshooting

| Symptom | Check |
|---------|-------|
| `/diary` or `/diary-notion` does not use the latest instructions | Run `agent-diary install --force` to refresh the hook and slash commands |
| `$diary` or `$diary-notion` does not use the latest instructions | Run `agent-diary install --force --codex-only`, then open a new Codex session |
| Notion push reports an auth error | Check the integration token, root page ID, and page sharing |
| Notion task hierarchy is not nested | Enable Sub-items once in the Notion `Entries` database UI |
| Re-push might duplicate rows | Default push skips the same `Session ID + Task Index`; use `--force` to rewrite |
| A `.agent-diary/` directory appeared in my project | That is the push run record. Add `.agent-diary/runs/` to `.gitignore`, or disable it with `--no-artifacts` (see [2-6](#2-6-what-a-push-leaves-on-disk-run-artifacts)) |
| Entries stopped appearing and I do not know why | Run `agent-diary doctor`. It checks that the hook is registered, that the module it names still resolves, and how long it has been since the last entry |
| I used to get `.codefleet/runs/` | That was the old default, named after a separate project. New projects use `.agent-diary/runs/`; an existing `.codefleet/runs/` keeps being used so your history does not split |
| I want to drop the `(N차)` suffix from titles | It counts prior sessions of the same `Task Group`. Leave `task_group` empty and no suffix is added |
| PowerShell text is garbled | Apply the UTF-8 output setting above |

## 8. Development

```bash
pip install -e ".[dev,notion]"
python -m pytest -q
python -m ruff check .
python -m mypy
```

Run bare, `mypy` checks only the modules listed in `pyproject.toml`. That list is the annotated core, and CI keeps it green. Annotating a new module means adding it to the list — being on the list is a commitment to stay clean.

CI runs it on the Python 3.12 job only, because current mypy will not run under this project's 3.8 floor. The annotations themselves are written for 3.8.

## 9. Roadmap

This README focuses on currently usable functionality. Detailed design and planning artifacts live under `docs/`.

| Area | Status |
|------|--------|
| Available | Claude Code Stop Hook, Codex skills, Markdown diaries, Notion task row push, schema v8 / view ensure, `ops` operations report, `review` queue, push run artifacts |
| In progress | Notion schema reduction ([#12](https://github.com/solzip/agent-diary/issues/12)), dry-run ordinals ([#10](https://github.com/solzip/agent-diary/issues/10)), `Schema Version` string fix ([#11](https://github.com/solzip/agent-diary/issues/11)) |
| Next | Windows install/output experience, Notion sub-item guidance |
| Under review | SQLite search index, Cursor/Windsurf/VS Code integration |

## 10. Documentation

If you are deciding whether the code is worth reading, start with these two.

- **[Architecture](docs/ARCHITECTURE.md)** — the idempotency model, the retry and error-taxonomy policy, cache invalidation, schema versioning, what partial failure means, and why the core has no dependencies
- **[Postmortem: `ensure` emptied six properties across 497 rows](docs/postmortem/2026-08-07-ensure-wipe.md)** — symptom, measurement against production, root cause, fix, regression tests, and why it went unseen for two months

Detailed design notes:

- [Notion hierarchical design](docs/02-design/features/diary-notion-hierarchical.design.md)
- [Notion views design](docs/02-design/features/diary-notion-views.design.md)
- [Distribution plan](docs/plans/phase-d-distribution.md)
- [Contributing](CONTRIBUTING.md)
- [Security](SECURITY.md)

## 11. License

MIT
