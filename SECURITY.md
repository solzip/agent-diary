# Security Policy

## What This Tool Does

- Reads Claude Code transcript files (read-only)
- Writes diary entries to `~/working-diary/` directory
- Scans for secrets before writing (auto-masking)
- Logs all operations to `.audit.jsonl`

## What This Tool Does NOT Do

- Does NOT send data to external servers (core has zero network access)
- Does NOT modify your source code or Claude Code configuration
- Does NOT access files outside the diary directory (except reading transcripts)
- Does NOT store or transmit API tokens (exporter configs are local-only)

## Supported Versions

| Version | Supported |
|---------|-----------|
| 3.x     | Yes       |
| 2.x     | Yes       |
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
