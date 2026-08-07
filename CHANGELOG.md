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
- **`claude-diary diary-notion init`**: 대화형 셋업 (token + 페이지 URL/ID + 권한 검증)
- **`claude-diary diary-notion push --input <file>` `--force`**: 임시 JSON 파일 받아 Notion에 push
- **Codex 표준 지원**: `$diary`, `$diary-notion` skills + `.codex-plugin/plugin.json`
- **중립 CLI alias**: `working-diary` 명령을 `claude-diary`와 동일하게 제공
- **DB 자동 생성 스키마**: Name, Date, Work Period, Project, Purpose, Branch, Status, Task Group, Parent Task, Sub-items, Depends On, Priority, Next Action, Blocked, Block Reason, Carryover, Review Status, Last Reviewed, Categories, Files, Commits, Lines, Session ID, Task Index
- **Notion native 하위항목 연결**: push가 부모-자식을 Notion **native sub-item 관계**(UI에서 1회 활성화, locale 이름 예 `상위 항목`/`하위 항목`)에 기록해 실제 접기/펼치기 nesting을 구동. 코드가 native 관계를 이름 하드코딩 없이 자동 탐지(소거법 + locale 토큰). `ensure`가 `작업 계층` view를 native 관계로 연결하고 기존 `Parent Task` 데이터를 native로 이전(멱등). native 미활성 시 작업 기록은 진행하고 활성화 안내 출력. 기존 영문 `Parent Task`/`Sub-items` 관계는 legacy로 유지·숨김, `Depends On`은 선행 관계로 유지
- **접힌 근거 중심 Notion 본문**: page body를 핵심 callout 1개, 결과 체크리스트, 작업 한눈에 표, 영향 bullet, 검증 checklist, 리스크/다음 액션, 접힌 부록 구조로 압축
- **Working Diary OS 비전 문서**: Structure → Views → Operations → Intelligence → Multi-project OS로 확장하는 최고모델 설계, 최소 명령 원칙, 전날 todo 기반 `today-plan`, schema/view conflict drift 관리 방향 추가
- **2차 View 설계 문서**: `working-diary diary-notion ensure`, `--year`, `--dry-run`과 Core Views 5개, operating views 5개, `Work Period`와 `Sub-items` 기반 schema v7 방향, 하위 항목 데이터 구조, sub-item UI best-effort/fallback, partial failure/exit code 정책 정리
- **`working-diary diary-notion ensure` 구현**: schema v7 `Work Period`, native sub-item relation, Priority/Blocked/Review 운영 컬럼 보장, Core Views 5개와 Operating Views 5개 생성/검증/update, `--year`, `--dry-run`, required setting repair 지원
- **`working-diary diary-notion ops` 구현**: Notion Entries DB를 읽기 전용으로 조회해 blocked/review/next action/stale/work days/today-plan 후보/task group/project/parent progress/부모 상태 제안 운영 신호를 요약
- **Phase 3 ensure diagnostics**: schema/view conflict reason을 `missing_filter`, `missing_property`, `subitem_missing`, `permission_or_auth`, `api_failure`로 분류하고 repair plan/action/apply 가능 여부를 출력
- **`claude-diary write --input <file>`**: Codex skill이 생성한 JSON으로 수동 Markdown 일지 작성
- **`lib/notion_cache.py`**: 연도 페이지/DB/행 ID 캐시 (root_page_id 변경 시 자동 무효화)
- **`lib/git_info.py` 확장**: `get_branch_for_commit`, `get_head_branch`, `get_commit_info`, `get_diff_stat_for_commits`
- **테스트 보강**: Notion Purpose, Codex plugin/skills, Codex JSON input 경로 검증 (전체 583 통과)

- **`working-diary diary-notion review`**: 검토 대기 row를 읽기 전용으로 나열하고, `--apply`로 `Reviewed` + `Last Reviewed=오늘` 기록. 검토 상태를 사람 소유로 전환 — push는 항상 `Needs Review`로 기록하고 에이전트는 이 필드를 작성하지 않음
- **작업 그룹 차수**: 같은 `Task Group`에 이미 기록된 세션 수를 세어 제목에 `(N차)` 부여 (컬럼 추가 없음). 세션 단위로 집계하고 자기 세션은 제외하므로 재push해도 밀리지 않음

### Changed
- `cli/setup.py` 일반화: `SLASH_COMMANDS` dict로 다중 슬래시 커맨드 관리
- **Notion 뷰 10개 → 5개**: `작업 계층` / `오늘 작업` / `Blocked` / `전날 미완료` / `작업 그룹별`. 각 뷰 컬럼은 최대 5개. `_property_config`가 property map 전체를 순회해 spec에 없는 컬럼을 전부 숨기므로, 스키마가 늘어도 테이블이 넓어지지 않음. 더 이상 관리하지 않는 뷰는 `ensure`가 목록으로 보고 (자동 삭제하지 않음)
- **Notion 본문**: 배경/범위/접근/상태 서술 표를 부록 토글로 접고 결과·검증 섹션을 확대 (성과 2→4, 검증 1→3, 상한 4→7)
- **`Work Period`를 명령 실행일에 고정**: 단일 날짜는 실행일로 수렴, 범위는 실행일을 넘지 못하게 clamp. 에이전트가 넣은 세션 날짜나 예시 날짜가 Notion에 들어가지 않음
- **에이전트 계약**: 근거 없는 선택 필드는 생략하도록 변경 (`priority`, `work_period`). 예시 JSON의 하드코딩 날짜 제거
- ruff 룰 확대: `E9,F63,F7,F82` → `E4,E7,E9,E501,F,B`
- CI가 모든 브랜치에서 실행되고 `[notion]` extra까지 설치

### Fixed
- Notion native 하위항목이 비활성일 때 계층 연결을 조용히 건너뛰던 문제 — 실패로 집계하고 입력 JSON을 보존해 재실행 가능
- `formatter.py`: Notion API blocks 빌더 (`build_notion_blocks`) 추가 및 compact executive body 렌더링 보강
- 설계 문서: [`docs/02-design/features/diary-notion-hierarchical.design.md`](docs/02-design/features/diary-notion-hierarchical.design.md)

## [4.2.0] - 2026-04-29

### Added
- **`/diary` 슬래시 커맨드**: 세션 중 수동으로 Markdown 작업일지 작성
- **`claude-diary install` / `uninstall`**: pip 설치 후 Claude Code Stop Hook과 슬래시 커맨드를 등록/해제
- 오프라인 HTML 대시보드 (외부 CDN 의존 제거)
- 구조적 로깅 (`log.py`)
- 크로스플랫폼 경로/인코딩 fallback

### Changed
- `cli.py` 단일 파일(823줄)을 `cli/` 서브패키지로 분리
- README 리뉴얼 + 데모 SVG + FAQ

### Fixed
- `stats`의 프로젝트별 세션 카운트 오류와 막대 정렬

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
