# Community Post Templates

Use these templates to share claude-diary across platforms.

---

## Reddit (r/ClaudeAI)

**Title:** I built an auto-diary for Claude Code — every session gets documented automatically

**Body:**

I've been using Claude Code daily and realized I had no record of what I actually did each session. So I built **claude-diary** — a Stop Hook that automatically generates structured Markdown diaries from your Claude Code sessions.

**What it does:**
- Captures every session: tasks requested, files created/modified, commands run, git changes
- Auto-categorizes work (feature, bugfix, refactor, docs, test...)
- Masks secrets automatically (API keys, tokens, passwords — 11+ patterns)
- Generates weekly summaries, HTML dashboards, and search indexes
- Zero external dependencies, works offline

**Setup is 2 lines:**
```bash
pip install claude-diary
claude-diary init
```

That's it. Every Claude Code session now auto-generates entries like this:

```
### ⏰ 14:30:15 | 📁 `my-app`
**🏷️ Categories:** `feature` `test`
**📋 Task Requests:**
  1. Add user authentication with JWT
  2. Write integration tests
**📊 Code Stats:** +145 / -12 lines (5 files)
**🔒 2 secrets masked
```

**Extras:**
- `claude-diary stats` — terminal dashboard
- `claude-diary dashboard` — HTML dashboard with GitHub-style heatmap
- `claude-diary search "keyword"` — search across months of work
- Team mode with access control and central repo

GitHub: https://github.com/solzip/claude-code-hooks-diary

MIT licensed, Python 3.8+, zero dependencies. Feedback welcome!

---

## X (Twitter)

**Post:**

I built an auto-diary for Claude Code 📓

Every session → structured Markdown diary. Automatically.

- Tasks, files, git changes captured
- Secrets auto-masked
- HTML dashboard with heatmap
- Zero dependencies, 2-line setup

```
pip install claude-diary && claude-diary init
```

GitHub: https://github.com/solzip/claude-code-hooks-diary

#ClaudeCode #DevTools #Productivity

---

## Hacker News (Show HN)

**Title:** Show HN: Auto-generate work diaries from Claude Code sessions

**Body:**

I built claude-diary, a Python tool that hooks into Claude Code's session lifecycle and automatically generates structured Markdown work diaries.

When a Claude Code session ends, the Stop Hook parses the transcript and extracts: user prompts, files created/modified, commands run, git branch/commits/diff stats. It then formats this into a daily Markdown diary entry with auto-categorization (feature/bugfix/refactor/etc.) and secret scanning (masks API keys, tokens, passwords).

Key design decisions:
- Zero external dependencies for the core (stdlib only)
- XDG-compliant config, works on Linux/macOS/Windows
- Plugin architecture for exporters (Notion, Slack, Discord, Obsidian, GitHub)
- 420+ tests, 94% coverage, CI across 3 OS × 5 Python versions
- Never blocks Claude Code exit (hook always exits 0)

CLI includes search, filter, file trace, stats dashboard, weekly summaries, and team mode with RBAC.

https://github.com/solzip/claude-code-hooks-diary

---

## Anthropic Discord (#claude-code)

**Post:**

Hey all! I made a tool that auto-generates work diaries from your Claude Code sessions.

**claude-diary** uses the Stop Hook to capture what you did each session — tasks, files, git changes, commands — and writes it to daily Markdown files.

Quick start:
```
pip install claude-diary
claude-diary init
```

Features: auto-categorization, secret masking, HTML dashboard, weekly summaries, Notion/Slack/Discord export, team mode.

Zero dependencies, MIT licensed: https://github.com/solzip/claude-code-hooks-diary

Would love to hear if this is useful for anyone else!
