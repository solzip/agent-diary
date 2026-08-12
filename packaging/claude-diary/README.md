# claude-diary has been renamed to agent-diary

This distribution is retired. It contains no code — installing it installs
[`agent-diary`](https://pypi.org/project/agent-diary/), which is the same
project under its current name.

```bash
pip install agent-diary          # what you want
pip install "agent-diary[notion]"
```

Nothing needs to change in your code. The import package is `claude_diary` in
both, so `import claude_diary` keeps working and now resolves to the
maintained version.

## Why you are reading this

The project was published as `claude-diary` up to 4.2.0 (April 2026) and
renamed to `agent-diary` when it grew past Claude Code to cover Codex sessions
as well. The old name kept receiving installs after the rename, and each one
got 4.2.0 — which predates, among other things, the fix for diary entries
disappearing when two sessions ended at the same moment, and the fix for a
write that stopped halfway making a whole day unreadable to every command that
reads the diary.

The details are in the [changelog](https://github.com/solzip/agent-diary/blob/main/CHANGELOG.md).

- **Source**: https://github.com/solzip/agent-diary
- **Issues**: https://github.com/solzip/agent-diary/issues
