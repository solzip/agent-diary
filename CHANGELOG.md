# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- **`/diary-notion` 슬래시 커맨드**: 현재 세션을 작업 단위로 분리해 Notion 업무일지 DB에 push
  - 계층 구조: 루트 페이지 → 연도 페이지 → 단일 Entries DB (자동 생성)
  - 작업 분리: branch 경계 → 의미 단위 (semantic-first)
  - LLM은 슬래시 커맨드 안의 Claude가 처리 — 별도 Anthropic API 키 불필요
  - 멱등성: Session ID + Task Index 컬럼으로 skip, `--force` 시 archive&recreate
  - 에러 분기: 401/403 fail fast, 400 skip, 429/5xx retry, 404 자동 재생성
- **`claude-diary notion init`**: 대화형 셋업 (token + 페이지 URL/ID + 권한 검증)
- **`claude-diary notion push --input <file>` `--force`**: 임시 JSON 파일 받아 Notion에 push
- **DB 자동 생성 스키마**: Name, Date, Project, Branch, Categories, Files, Commits, Lines, Session ID, Task Index
- **`lib/notion_cache.py`**: 연도 페이지/DB/행 ID 캐시 (root_page_id 변경 시 자동 무효화)
- **`lib/git_info.py` 확장**: `get_branch_for_commit`, `get_head_branch`, `get_commit_info`, `get_diff_stat_for_commits`
- **새 테스트 90개** (전체 553 통과)

### Changed
- `cli/setup.py` 일반화: `SLASH_COMMANDS` dict로 다중 슬래시 커맨드 관리
- `formatter.py`: Notion API blocks 빌더 (`build_notion_blocks`) 추가
- 설계 문서: [`docs/02-design/features/diary-notion-hierarchical.design.md`](docs/02-design/features/diary-notion-hierarchical.design.md)

## [4.1.0] - 2026-03-17 (Phase D)

### Added
- **Plugin**: `.claude-plugin/` directory for Claude Code marketplace
- **Install**: 3 installation methods (pip / plugin / manual)
- **GitHub**: Topics, badges, description optimization

### Changed
- Version sync across pyproject.toml, __init__.py, cli.py, plugin.json

## [4.0.0] - 2026-03-17 (Phase C)

### Added
- **Team Security**: Path masking (glob patterns), content filtering (redact/skip), session opt-out
- **Team Access**: member/lead/admin 3-tier role-based access control
- **Team Repo**: Git central repo with `init --team`, `.team-config.json`
- **Team CLI**: `team stats`, `team weekly`, `team init`, `team add-member`
- **Team Notion**: Author column auto-set for shared Notion DB
- **CLI**: `delete --last` / `delete --session` for session removal

## [3.0.0] - 2026-03-17 (Phase B)

### Added
- **Security**: Audit log system (`.audit.jsonl`) — every Hook execution recorded
- **Security**: SHA-256 checksum verification (`claude-diary audit --verify`)
- **Security**: SECURITY.md with transparency documentation
- **Testing**: 40 unit tests (parser, categorizer, secret_scanner, config, audit)
- **CI/CD**: GitHub Actions (Python 3.8~3.12 × 3 OS)
- **CI/CD**: PyPI auto-release on tag push
- **Community**: LICENSE (MIT), CONTRIBUTING.md, Issue/PR templates
- **Community**: CHANGELOG.md

### Changed
- Audit log integrated into core pipeline

## [2.0.0] - 2026-03-17 (Phase A)

### Added
- **Core**: Modular pip package structure (`src/claude_diary/`)
- **Core**: Auto-categorization (7 categories, KO/EN keywords)
- **Core**: Git integration (branch, commits, diff stats)
- **Core**: Secret scanner (11+ patterns auto-masked)
- **Core**: Search index (`.diary_index.json`) for fast CLI queries
- **CLI**: 11 subcommands (search, filter, trace, stats, weekly, config, init, migrate, reindex, audit, dashboard)
- **Exporters**: Plugin architecture with 5 official exporters (Notion, Slack, Discord, Obsidian, GitHub)
- **Dashboard**: HTML dashboard with Chart.js (heatmap, charts, dark theme)
- **Config**: XDG standard paths, environment variable fallback

### Changed
- Refactored from single script to modular package
- Config priority: `config.json > env vars > defaults`

## [1.0.0] - 2026-03-17

### Added
- Initial release
- Stop Hook auto-diary (transcript parsing)
- Weekly summary generator
- Korean/English bilingual support
- Windows/macOS/Linux cross-platform
- `install.sh` auto-installer
