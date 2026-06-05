# Security Policy

## What This Tool Does

- Reads Claude Code transcript files (read-only)
- Writes diary entries to `~/working-diary/` directory
- Registers or refreshes Claude Code hook/slash command settings when you run `working-diary init` or `working-diary install`
- Codex-only setup does not modify Claude Code settings when you use `working-diary init --codex-only` and `working-diary install --codex-only`
- Stores exporter credentials such as API tokens and webhook URLs in local config
- Scans for secrets before writing (auto-masking)
- Logs all operations to `.audit.jsonl`

## What This Tool Does NOT Do

- Does NOT send data to external servers unless you explicitly enable an exporter such as Notion, Slack, Discord, or GitHub
- Does NOT modify your source code
- Does NOT access files outside the diary directory (except reading transcripts)
- Does NOT transmit stored exporter credentials except when the corresponding exporter is explicitly enabled

## Supported Versions

| Version | Supported |
|---------|-----------|
| 4.x     | Yes       |
| 3.x     | Yes       |
| 2.x     | Deprecated |
| 1.x     | No        |

## Security Features

- **Secret scanning**: Auto-masks passwords, API keys, tokens before writing
- **Audit log**: Every Hook execution is logged with checksums
- **Checksum verification**: `claude-diary audit --verify` detects source tampering
- **Exporter isolation**: Exporters receive processed data only (no transcript access)
- **Config protection**: File permissions 600 on Unix, tokens masked in CLI output
- **Exporter trust levels**: Official / Community / Custom classification

## Reporting a Vulnerability

- **Email**: solzip@users.noreply.github.com
- **Do NOT** open a public issue for security vulnerabilities
- Expected response time: within 48 hours
- We will coordinate disclosure after a fix is available

## Verifying Integrity

```bash
# Verify source code hasn't been tampered with
claude-diary audit --verify

# Review recent Hook executions
claude-diary audit --days 7
```
