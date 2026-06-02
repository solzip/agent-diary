# 📓 Claude Code Working Diary

**Claude Code 작업 내용, 자동으로 기록됩니다.**

[![CI](https://github.com/solzip/claude-code-hooks-diary/actions/workflows/ci.yml/badge.svg)](https://github.com/solzip/claude-code-hooks-diary/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Zero Dependencies](https://img.shields.io/badge/dependencies-0-brightgreen)](https://github.com/solzip/claude-code-hooks-diary)

> **[English](README.en.md)** | 한국어

> ⚠️ This is a community project, not officially affiliated with Anthropic.

Claude Code 세션마다 수많은 작업이 이뤄집니다 — 기능 구현, 파일 수정, 버그 수정. 하지만 세션이 끝나면 그 맥락은 사라집니다. **claude-diary**가 이 모든 것을 자동으로 기록합니다.

```bash
pip install claude-diary && claude-diary init  # 이게 끝입니다.
```

<p align="center">
  <img src="docs/demo.svg" alt="claude-diary 데모" width="680">
</p>

## 어떻게 동작하나요?

```
Claude Code 세션 종료
        │
        ▼
  Stop Hook 자동 실행
        │
        ▼
  트랜스크립트 분석 → 작업 내용, 파일, 명령어, Git 정보 추출
        │
        ▼
  ~/working-diary/2026-03-24.md  ← 일지 자동 생성
```

설정 없이 바로 동작합니다. 세션이 끝날 때마다 Hook이 자동 실행되어 구조화된 마크다운 일지를 생성합니다.

## 지원 환경

| 플랫폼 | Python | 자동 일지 | 주간 요약 | Cron |
|--------|--------|-----------|-----------|------|
| macOS | python3 | ✅ | ✅ | ✅ |
| Linux | python3 | ✅ | ✅ | ✅ |
| Windows (Git Bash) | python | ✅ | ✅ | ❌ (Task Scheduler 사용) |

## 기록되는 내용

| 항목 | 설명 |
|------|------|
| 📋 작업 요청 | 사용자가 Claude에게 요청한 내용 |
| 📄 생성된 파일 | 새로 만들어진 파일 목록 |
| ✏️ 수정된 파일 | 편집된 파일 목록 |
| ⚡ 주요 명령어 | 실행된 중요 shell 명령어 |
| 📝 작업 요약 | AI가 수행한 작업의 요약 |
| ⚠️ 이슈 | 발생한 오류나 문제 |

## 설치

### 방법 1: pip (권장)

```bash
pip install claude-diary
claude-diary init
```

### 방법 2: Claude Code 플러그인

```bash
# Claude Code 안에서
/plugin marketplace add https://github.com/solzip/claude-code-hooks-diary
/plugin install working-diary
```

### 방법 3: 수동 설치

```bash
git clone https://github.com/solzip/claude-code-hooks-diary.git
cd claude-code-hooks-diary/working-diary-system
./install.sh
```

설치 후 자동으로:
- Stop Hook 등록 (세션 종료마다 자동 실행)
- `~/working-diary/` 디렉토리 생성
- 설정 파일 생성

## 디렉토리 구조

```
~/working-diary/
├── 2026-03-15.md          ← 일일 작업일지
├── 2026-03-16.md
├── 2026-03-17.md
├── .session_counts.json    ← 내부 카운트 (자동)
├── .gitignore
└── weekly/
    ├── W11_2026-03-09.md   ← 주간 요약 리포트
    └── W12_2026-03-16.md
```

## 수동 일지 — `/diary` 슬래시 커맨드

세션 종료를 기다리지 않고 작업 도중 즉시 일지를 남기고 싶을 때 사용합니다. 자동 일지(Stop Hook)와 **공존**하며, 별도 경로에 프로젝트별로 정리됩니다.

```
~/working-diary/manual/
└── 2026-04-29/
    └── claude-code-hooks-diary/
        └── 2026-04-29.md      ← 같은 날 같은 프로젝트면 append
```

**사용법:**
- Claude Code 세션에서 `/diary` 입력 → 현재 cwd의 transcript를 읽고 기록
- Codex 세션에서 `$diary` 입력 → 현재 대화/도구 사용 내역을 JSON으로 정리해 같은 경로에 기록
- 또는 터미널에서 `claude-diary write`

`claude-diary install` 시 `~/.claude/commands/diary.md`가 함께 설치되어 모든 프로젝트에서 `/diary` 사용 가능. 이미 설치한 적 있다면 한 번 더 실행해서 슬래시 커맨드만 추가하세요 (멱등). `claude-diary uninstall` 시 함께 제거됩니다 (사용자가 수정한 파일은 보존).
Codex skill은 repo의 Codex plugin으로 설치하거나 `claude-diary install --codex`로 `~/.codex/skills`에 설치할 수 있습니다.

## Notion 업무일지 — `/diary-notion` / `$diary-notion`

현재 세션을 **작업 단위로 분리**해 Notion DB에 push합니다. Claude Code에서는 `/diary-notion`, Codex에서는 `$diary-notion`을 사용합니다. 별도 LLM API 키 없이 현재 에이전트 세션 컨텍스트로 동작하며, Notion 무료 플랜에서도 동작.

```
[Notion 루트 페이지: "Working Diary"]
 └── 📄 2026 (자동 생성)
     └── 🗄️ Entries (인라인 DB, 자동 생성)
         ├── "Notion DB 컬럼 스키마 결정"   | Project: claude-diary | Branch: feat/notion
         ├── "git_info.py 리팩토링"          | Project: claude-diary | Purpose: Refactor
         └── ...
```

한 세션의 의논/구현이 의미 단위로 N개 행으로 분리되어 들어갑니다. branch가 바뀌면 무조건 새 task로 분리. `Project`, `Purpose`, `Task Group`, `Parent Task`, `Sub-items`, `Depends On`, `Work Period`, `Priority`, `Blocked`, `Next Action` 컬럼으로 Notion에서 필터/그룹/관계/운영 상태 조회가 가능합니다.
`$diary-notion`과 `/diary-notion`은 작업 row push에 집중하고, `working-diary diary-notion ensure`는 schema v7, native sub-items, core views 5개, operating views 5개 보장에 집중합니다.
`Parent Task`와 `Sub-items`는 Notion 하위항목/sub-item을 위한 양방향 포함 관계이고, `Depends On`은 큰 메인 작업끼리의 선행 연결성만 나타냅니다. 하위 작업을 종속성으로 연결하지 않습니다. `Project`가 task JSON에서 누락되거나 `unknown`으로 들어오면 CLI가 명령 실행 cwd의 폴더명으로 보정합니다.
각 Notion 페이지 본문은 `body_intro` 핵심 callout 1개, `결과` 체크리스트, `작업 한눈에` 표, `영향` bullet, `검증` 체크리스트, `리스크 / 다음 액션`, `부록` 순서로 생성됩니다. 코드 변경·파일·명령어·Git·원문 요청은 접힌 부록(toggle)에 기록합니다. 코드 변경은 full diff가 아니라 동작/스키마/CLI/사용자 흐름/검증 범위를 바꾼 주요 변경만 남깁니다.
제목과 설명형 본문은 한국어로 기록하고, 파일 경로/명령어/branch/commit hash/코드 식별자 및 `Purpose`, `Status` enum 값은 원문 또는 영어 값을 유지합니다.

### 5분 셋업

1. **Notion Integration 토큰 발급** — https://www.notion.so/my-integrations → "New integration" → 토큰 복사 (`secret_...`)
2. **Notion에 루트 페이지 생성** — 이름 자유 (예: "Working Diary")
3. **그 페이지를 Integration에 공유** — 페이지 우상단 ⋯ → "Connections" → 만든 Integration 추가
4. **셋업 명령 실행**:
   ```bash
   claude-diary diary-notion init
   ```
   대화형으로 token과 root page URL(또는 ID)을 입력하면 권한 검증 후 config에 저장됩니다.
5. **DB schema와 core/operating views 보장**:
   ```bash
   working-diary diary-notion ensure
   ```
6. **Codex에서 쓸 경우 skill 설치 또는 갱신**:
   ```bash
   claude-diary install --force --codex
   ```
7. **세션에서 `/diary-notion` 또는 `$diary-notion` 입력** — 작업 분리 + Notion push 자동 실행

### 사용법

```bash
# 처음 한 번
claude-diary diary-notion init
working-diary diary-notion ensure --dry-run  # 변경 없이 schema/view 상태 확인
working-diary diary-notion ensure            # schema v7, native sub-items, core/operating views 보장
working-diary diary-notion ensure --year 2026

# 매 세션
/diary-notion       # Claude Code 세션 안에서
$diary-notion       # Codex 세션 안에서

# 같은 세션 다시 push (실수 등):
#   기본은 skip (Session ID + Task Index로 멱등성)
#   --force 로 기존 행 archive 후 재push
```

다른 Codex 세션에서 최신 `$diary-notion` 지시문을 쓰려면 repo를 최신화한 뒤 `claude-diary install --force --codex`를 다시 실행하고 새 Codex 세션을 여는 것을 권장합니다.

### Core Views

`working-diary diary-notion ensure`는 현재 연도 또는 `--year`로 지정한 연도 `Entries` DB에 다음 5개 core view를 보장합니다. 기존 작업 row는 생성, 수정, 삭제하지 않습니다.

| View | 용도 | 기준 |
|------|------|------|
| 작업 계층 | 메인 작업과 하위 작업 관계 확인 | `Parent Task` 표시, `Sub-items` 기반 native 하위항목/sub-item, `Work Period` 표시, `Date desc` |
| 오늘 작업 | 오늘 기록된 수행분 확인 | `Date = today`, `Date desc`, `Work Period` 표시 |
| 상태별 | 진행 단계별 작업 확인 | `Status` group_by, `Work Period` 표시 |
| 목적별 | 작업 성격별 확인 | `Purpose` group_by, `Work Period` 표시 |
| 프로젝트별 | 프로젝트별 작업 확인 | `Project` group_by, `Work Period` 표시 |

같은 이름의 view가 이미 있고 required 설정을 만족하면 `verified`로 처리합니다. required 설정이 다르면 `working-diary diary-notion ensure`가 보장 view 기본 설정을 업데이트하고, `--dry-run`에서는 `update planned`로만 표시합니다. `작업 계층`의 sub-item UI와 `오늘 작업`의 relative today filter는 Notion API 제약에 따라 best-effort fallback을 사용합니다.

### Operating Views

최고모델 기준에서는 core view 5개를 유지하면서, 오늘 실행과 막힘 관리를 위한 operating view 5개도 같은 `ensure` 명령으로 보장합니다.

| View | 용도 | 기준 |
|------|------|------|
| 오늘 우선순위 | 오늘 처리할 작업을 우선순위대로 확인 | `Date = today`, `Blocked = false`, `Priority asc`, `Date desc` |
| 전날 미완료 | 이전 기록일에서 완료되지 않은 작업 확인 | `Date before today`, `Status != Deployed`, `Priority asc` |
| Blocked | 외부 결정/권한/정보 때문에 막힌 작업 확인 | `Blocked = true`, `Block Reason` 표시 |
| 리뷰 필요 | 검토가 필요한 작업 확인 | `Review Status = Needs Review` |
| 작업 그룹별 | 여러 날/세션에 걸친 큰 작업 흐름 확인 | `Task Group` group_by |

### DB 컬럼

| 컬럼 | 타입 | 비고 |
|------|------|------|
| Name | title | Claude가 뽑은 task 제목 (명사구) |
| Date | date | |
| Work Period | date | 실제 작업 기간. 프로젝트/작업 그룹 기간 계산 재료 |
| Project | select | cwd 폴더명. group/filter용. task JSON에서 누락되거나 `unknown`이면 CLI가 명령 실행 cwd로 보정 |
| Purpose | select | Feature/Bugfix/Refactor/Docs/Test/Infra/Planning/Research/Review/Release/Support/Maintenance/General |
| Branch | select | task별 branch (group/filter용) |
| Status | select | Discussion/Design/Implementation/Testing/Deployed |
| Task Group | select | 며칠/여러 세션에 걸치는 큰 작업 묶음 |
| Parent Task | relation | 같은 DB의 상위 작업. `Sub-items`와 양방향으로 연결되는 하위항목/sub-item 부모 관계 |
| Sub-items | relation | 같은 DB의 하위 작업 목록. `작업 계층` view의 native sub-item toggle 기준 |
| Depends On | relation | 같은 DB의 선행 작업. 하위 작업이 아니라 큰 메인 작업끼리의 연결성에만 사용 |
| Priority | select | P0/P1/P2/P3. `오늘 우선순위`, `전날 미완료`, `Blocked` view 정렬 기준 |
| Next Action | rich_text | 다음에 바로 실행할 수 있는 구체적 행동 |
| Blocked | checkbox | 외부 결정/권한/정보 없이는 진행할 수 없는 작업 표시 |
| Block Reason | rich_text | 막힌 원인 |
| Carryover | checkbox | 전날 또는 이전 세션 미완료 작업을 오늘 이어서 처리한 row 표시 |
| Review Status | select | Needs Review/Reviewed/Deferred |
| Last Reviewed | date | 실제 검토일 |
| Categories | multi_select | design/refactor/bugfix/... 자유 라벨 |
| Files | number | 수정+생성 파일 수 |
| Commits | number | task별 commit 수 |
| Lines | number | 추가+삭제 합 |
| Session ID, Task Index | (hidden 권장) | 멱등성 키 |

자세한 설계는 [`docs/02-design/features/diary-notion-hierarchical.design.md`](docs/02-design/features/diary-notion-hierarchical.design.md).

### 주의

- `config.json`은 절대 git에 커밋/공유하지 마세요 (token이 평문 저장됨)
- 사용자 프로젝트 `.gitignore`에 `.diary-notion-*.json` 추가 권장 (임시 파일 보호망)

## 일지 예시

```markdown
# 📓 작업일지 — 2026-03-17 (화요일)

> 이 파일은 Claude Code Stop Hook에 의해 자동 생성됩니다.
> 각 세션이 종료될 때마다 작업 내용이 자동으로 기록됩니다.

---

### ⏰ 09:32:15 | 📁 `ai-chatbot`

**📋 작업 요청:**
  1. WebSocket 핸들러에 circuit breaker 패턴 구현해줘
  2. 에러 코드 정의서 업데이트

**📄 생성된 파일:**
  - `.../handler/CircuitBreakerHandler.java`

**✏️ 수정된 파일:**
  - `.../config/WebSocketConfig.java`
  - `.../constant/ErrorCode.java`

**⚡ 주요 명령어:**
  - `./gradlew test`
  - `./gradlew bootRun`

**📝 작업 요약:**
  - Circuit breaker 패턴이 WebSocket 핸들러에 구현 완료
  - 3단계 상태 전환(CLOSED→OPEN→HALF_OPEN) 로직 추가
```

## 환경변수 설정

| 환경변수 | 설명 | 기본값 |
|----------|------|--------|
| `CLAUDE_DIARY_LANG` | 일지 언어 (`ko` 또는 `en`) | `ko` |
| `CLAUDE_DIARY_DIR` | 자동 일지 저장 경로 | `~/working-diary` |
| `CLAUDE_DIARY_MANUAL_DIR` | 수동 일지(`/diary`) 저장 경로 | `~/working-diary/manual` |
| `CLAUDE_DIARY_TZ_OFFSET` | UTC 오프셋 | `9` (KST) |

```bash
# ~/.bashrc 또는 ~/.zshrc에 추가
export CLAUDE_DIARY_LANG="ko"
export CLAUDE_DIARY_DIR="$HOME/working-diary"
export CLAUDE_DIARY_TZ_OFFSET="9"
```

**Windows 환경변수 설정:**
```powershell
# PowerShell (영구 설정)
[Environment]::SetEnvironmentVariable("CLAUDE_DIARY_LANG", "ko", "User")
[Environment]::SetEnvironmentVariable("CLAUDE_DIARY_DIR", "$env:USERPROFILE\working-diary", "User")
```

## CLI 명령어

```bash
claude-diary write                        # 현재 세션 작업일지를 즉시 기록 (`/diary` 슬래시 커맨드로도 호출)
working-diary write                       # 동일한 CLI의 중립 alias
claude-diary search "키워드"              # 키워드 검색
claude-diary filter --project my-app      # 프로젝트 필터
claude-diary trace src/main.py            # 파일 변경 이력
claude-diary stats                        # 터미널 대시보드
claude-diary weekly                       # 주간 요약 생성
claude-diary dashboard                    # HTML 대시보드
claude-diary audit                        # 보안 감사 로그
claude-diary audit --verify               # 소스 코드 무결성 검증
claude-diary config                       # 설정 확인
claude-diary team stats                   # 팀 통계
claude-diary team weekly                  # 팀 주간 리포트
```

## 주요 기능

| 기능 | 설명 |
|------|------|
| 자동 카테고리 | feature/bugfix/refactor/docs/test/config/style 자동 분류 |
| Git 연동 | 브랜치, 커밋, 변경량 (+/- lines) 자동 기록 |
| 시크릿 스캔 | 패스워드, API 키, 토큰 자동 마스킹 (11+ 패턴) |
| 검색 인덱스 | 수개월 일지에서도 빠른 검색 |
| 5개 Exporter | Notion, Slack, Discord, Obsidian, GitHub 연동 |
| HTML 대시보드 | GitHub 잔디 히트맵, 오프라인 차트 (CDN 없음) |
| 보안 감사 | audit 로그, SHA-256 checksum 변조 감지 |
| 팀 모드 | 접근 제어, Git 중앙 repo, 팀 리포트 |

## 요구사항

- Python 3.8+ (`python3` or `python`)
- Claude Code (hooks 지원 버전)
- 외부 의존성 없음 (코어), API 토큰 불필요

## 팁

**CLAUDE.md에 추가하면 더 좋은 일지가 생성됩니다:**

```markdown
## 작업일지
- 세션 종료 시 작업 내용이 자동 기록됩니다
- 작업 완료/구현/수정 시 명확한 요약을 출력해주세요
```

## FAQ

**"git log로 충분하지 않나요?"**

git log는 *커밋한 것*을 기록합니다. claude-diary는 *시도한 것, 요청한 것, 디버깅한 것*을 기록합니다 — 커밋 없이 끝난 세션도 포함해서요. "JWT 인증 구현해줘" 같은 원래 요청, 실행한 명령어, 발생한 에러, 소요 시간까지. 커밋 이력과 실제 하루 사이의 빈 공간을 채워줍니다.

**"Cursor / Windsurf / Copilot에서도 되나요?"**

아직은 Claude Code 전용입니다 (Stop Hook 기반). 하지만 핵심 파이프라인은 `session_id + transcript + cwd`만 있으면 되기 때문에, 다른 AI IDE 지원은 구조적으로 어렵지 않습니다. 아래 로드맵을 참고하세요.

**"JSON 인덱스 말고 SQLite는요?"**

현재 JSON 인덱스는 단순하고 의존성이 없습니다. SQLite는 Python 표준 라이브러리에 포함되어 있어 여전히 의존성 0을 유지하면서, 전문 검색과 수개월 데이터 쿼리 성능을 개선할 수 있습니다. v5.0에서 계획 중입니다.

## 로드맵

| Phase | 목표 | 버전 | 상태 |
|-------|------|------|------|
| **A** | 개인 생산성 도구 (카테고리, Git, CLI, 플러그인, 대시보드) | v2.0.0 | ✅ 완료 |
| **B** | 오픈소스 커뮤니티 (보안, 테스트 420+개, CI/CD) | v3.0.0 | ✅ 완료 |
| **C** | 팀/회사 도구 (접근 제어, Git 중앙 repo, 팀 리포트) | v4.0.0 | ✅ 완료 |
| **D** | 배포 (플러그인, PyPI, 마켓플레이스) | v4.1.0 | ✅ 완료 |
| **E** | 멀티 IDE 지원 (Cursor, Windsurf, VS Code 확장) | v5.0.0 | 📋 예정 |
| **F** | SQLite 인덱스 + 전문 검색 + 분석 API | v5.1.0 | 📋 예정 |

자세한 내용은 [`docs/plans/`](docs/plans/) 디렉토리를 참고하세요.

## 라이선스

MIT License — [LICENSE](LICENSE)
