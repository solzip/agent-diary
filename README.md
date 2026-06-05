# Working Diary

Claude Code와 Codex 작업 세션을 Markdown 일지 또는 Notion 업무일지로 기록하는 CLI 도구입니다.

[![CI](https://github.com/solzip/working-diary/actions/workflows/ci.yml/badge.svg)](https://github.com/solzip/working-diary/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Core Dependencies: 0](https://img.shields.io/badge/core%20dependencies-0-brightgreen)](https://github.com/solzip/working-diary)

> [English](README.en.md) | 한국어
>
> 커뮤니티 프로젝트입니다. Anthropic 또는 OpenAI의 공식 프로젝트가 아닙니다.

## 1. 설명

Working Diary는 AI 코딩 세션에서 사라지기 쉬운 작업 맥락을 남깁니다.

- 사용자가 요청한 작업
- 생성/수정된 파일
- 실행한 주요 명령
- Git branch, commit, diff 통계
- 작업 요약과 오류
- Notion 업무 DB용 task row

패키지 이름은 호환성을 위해 `claude-diary`를 유지합니다. 사용자 문서에서는 중립 alias인 `working-diary`를 우선 사용합니다.

```bash
pip install claude-diary
working-diary init
```

### 지원 에이전트

| 에이전트 | 자동 기록 | 수동 Markdown | Notion 업무일지 | 적용/갱신 |
|----------|-----------|---------------|-----------------|-----------|
| Claude Code | Stop Hook | `/diary` | `/diary-notion` | `working-diary install --force` |
| Codex | 없음 | `$diary` | `$diary-notion` | `working-diary install --force --codex-only` |

패키지 설치는 공통이지만 에이전트에 적용하는 명령은 다릅니다. Codex만 쓰는 경우에는 `--codex-only`를 사용하면 Claude Code 설정을 수정하지 않습니다. `--codex`는 Claude Code hook/slash command도 함께 갱신하는 호환 옵션입니다.

### 저장 위치

자동 일지는 날짜별 파일에 append됩니다.

```text
~/working-diary/
  2026-03-15.md
  2026-03-16.md
  .session_counts.json
  weekly/
    W11_2026-03-09.md
```

수동 일지는 자동 일지와 분리되어 프로젝트별로 저장됩니다.

```text
~/working-diary/manual/
  2026-04-29/
    my-project/
      2026-04-29.md
```

## 2. 사용법

처음 쓰는 경우에는 목표에 맞는 실행 순서를 그대로 진행합니다.

| 목표 | 실행 순서 |
|------|----------------|
| Claude Code에서 Markdown 자동/수동 기록 | `pip install claude-diary` -> `working-diary init` -> `working-diary install --force` |
| Claude Code에서 Notion 업무일지까지 사용 | `pip install "claude-diary[notion]"` -> `working-diary init` -> `working-diary install --force` -> `working-diary diary-notion init` -> `working-diary diary-notion ensure` |
| Codex에서 Markdown 수동 기록 | `pip install claude-diary` -> `working-diary init --codex-only` -> `working-diary install --force --codex-only` -> 새 Codex 세션 |
| Codex에서 Notion 업무일지까지 사용 | `pip install "claude-diary[notion]"` -> `working-diary init --codex-only` -> `working-diary install --force --codex-only` -> `working-diary diary-notion init` -> `working-diary diary-notion ensure` -> 새 Codex 세션 |

### 2-1. 패키지 설치와 기본 설정

pip 설치:

```bash
pip install claude-diary
working-diary init
```

Notion 연동까지 사용할 경우:

```bash
pip install "claude-diary[notion]"
working-diary init
```

Claude Code 플러그인 설치는 별도 배포 경로입니다. Claude Code의 plugin marketplace에서 이 프로젝트를 설치할 때 사용합니다.

```bash
# Claude Code 안에서 실행
/plugin marketplace add https://github.com/solzip/working-diary
/plugin install working-diary
```

이 플러그인은 Claude Code 쪽 hook 설정을 배포합니다. `working-diary` CLI는 Python 패키지에서 제공되므로, 플러그인 경로를 쓰더라도 Python 패키지 설치와 `working-diary init`이 준비되어 있어야 합니다.

소스에서 설치:

```bash
git clone https://github.com/solzip/working-diary.git
cd working-diary
pip install -e .
working-diary init
```

소스 설치에서 Notion 연동까지 사용할 경우:

```bash
pip install -e ".[notion]"
```

`working-diary init`은 설정 파일과 일지 디렉터리를 만들고 Claude Code Stop Hook도 함께 등록합니다. Codex만 쓰는 경우에는 `working-diary init --codex-only`를 실행하면 Claude Code 설정을 수정하지 않습니다.

Claude Code나 Codex에서 slash command 또는 skill을 최신 상태로 쓰려면 아래 에이전트별 적용 명령을 추가로 실행합니다.

### 2-2. Claude Code 사용법

Claude Code는 세션 종료 시 자동 기록할 수 있고, 세션 중 수동 기록도 할 수 있습니다.

Claude Code 적용 또는 갱신:

```bash
working-diary install --force
```

자동 기록:

```text
Claude Code 세션 종료
  -> Stop Hook 실행
  -> transcript 분석
  -> ~/working-diary/YYYY-MM-DD.md
```

수동 Markdown 일지:

```text
/diary
```

Notion 업무일지:

```text
/diary-notion
```

`/diary`는 현재 프로젝트의 Claude Code transcript를 찾아 `working-diary write` core로 기록합니다. `/diary-notion`은 세션 내용을 task row로 정리한 JSON을 만든 뒤 `working-diary diary-notion push` core로 전달합니다.

### 2-3. Codex 사용법

Codex는 자동 hook을 사용하지 않습니다. 사용자가 skill을 호출할 때만 기록합니다.

Codex 적용 또는 갱신:

```bash
working-diary install --force --codex-only
```

`--codex-only`는 Codex skill만 `~/.codex/skills` 아래에 설치하고 Claude Code hook/slash command는 수정하지 않습니다. `--codex`는 기존 호환 옵션으로 Claude Code hook/slash command를 함께 갱신합니다.

수동 Markdown 일지:

```text
$diary
```

Notion 업무일지:

```text
$diary-notion
```

`$diary`와 `$diary-notion`은 현재 Codex 대화와 도구 사용 내역을 바탕으로 JSON을 만든 뒤 같은 core CLI를 호출합니다.

이미 실행 중인 Codex 세션은 시작 시점에 로드한 skill을 유지합니다. 갱신된 skill은 새 Codex 세션에서 반영됩니다.

### 2-4. Notion 처음 설정

Notion 업무일지를 쓰려면 Notion API용 `requests`가 필요합니다.

```bash
pip install "claude-diary[notion]"
```

소스 설치에서 Notion까지 사용할 경우:

```bash
pip install -e ".[notion]"
```

설정 절차:

1. https://www.notion.so/my-integrations 에서 Integration을 만들고 토큰을 복사합니다.
2. Notion에 루트 페이지를 만듭니다. 예: `Working Diary`
3. 루트 페이지를 Integration에 공유합니다.
4. 설정을 저장합니다.

```bash
working-diary diary-notion init
```

`diary-notion init`은 입력한 Notion token과 root page ID를 로컬 config에 저장합니다. 이후 `CLAUDE_DIARY_NOTION_TOKEN` 또는 `CLAUDE_DIARY_NOTION_ROOT_PAGE_ID` 환경변수를 지정하면 저장된 config 값보다 환경변수가 우선합니다.

5. 연도별 `Entries` DB와 schema/view를 보장합니다.

```bash
working-diary diary-notion ensure
```

6. 세션에서 `/diary-notion` 또는 `$diary-notion`을 실행합니다.

### 2-5. Notion push 동작

```bash
working-diary diary-notion push --input .diary-notion-<id>.json
working-diary diary-notion push --input .diary-notion-<id>.json --force
```

- 기본 push는 `Session ID + Task Index`로 이미 기록된 row를 skip합니다.
- `--force`는 같은 세션의 기존 row를 archive한 뒤 다시 push합니다.
- 실패한 task가 하나라도 있으면 exit code `1`로 종료하고 입력 JSON을 보존합니다.
- 전체 성공 또는 이미 push된 task만 skip된 경우 exit code `0`으로 종료합니다.

### 2-6. Notion sub-item

작업 계층 접기/펼치기는 Notion의 native Sub-items 기능을 사용합니다. 이 기능은 Notion UI에서 한 번 켜야 합니다.

1. 해당 연도의 `Entries` DB를 엽니다.
2. 우상단 `...` 메뉴에서 `Sub-items`를 활성화합니다.
3. 다시 `working-diary diary-notion ensure`를 실행합니다.

Sub-items가 아직 없어도 row 기록은 정상 동작합니다. 다만 계층 nesting만 표시되지 않고, push 명령이 안내를 출력합니다.

## 3. 로직

### 3-1. Core 로직

Core는 에이전트와 무관하게 실제 기록 처리를 담당합니다.

```text
입력
  -> transcript 또는 agent-authored JSON
  -> cwd, session_id, task metadata

core 처리
  -> parser
  -> Git 정보 보강
  -> category 추론
  -> secret scan
  -> formatter
  -> writer 또는 Notion exporter
  -> audit/index/export retry
```

주요 모듈:

| 영역 | 파일 | 역할 |
|------|------|------|
| CLI entry | `src/claude_diary/cli/__init__.py` | `working-diary`, `claude-diary` 명령 라우팅 |
| 자동 기록 core | `src/claude_diary/core.py` | Claude Code Stop Hook 자동 일지 pipeline |
| 수동 기록 core | `src/claude_diary/cli/write.py` | `/diary`, `$diary`, `working-diary write` 처리 |
| Notion push | `src/claude_diary/cli/notion_push.py` | task JSON을 Notion row로 push |
| Notion schema/view | `src/claude_diary/cli/notion_ensure.py` | schema v7, core/operating views 보장 |
| Formatter | `src/claude_diary/formatter.py` | Markdown entry와 Notion page body 생성 |

### 3-2. Claude Code 로직

Claude Code에는 두 경로가 있습니다.

자동 기록:

```text
Claude Code Stop Hook
  -> src/claude_diary/hook.py
  -> core.process_session(session_id, transcript_path, cwd)
  -> ~/working-diary/YYYY-MM-DD.md
```

수동 기록:

```text
/diary
  -> claude-diary write
  -> 현재 cwd에 맞는 Claude transcript 탐색
  -> manual diary 경로에 append

/diary-notion
  -> agent가 task JSON 생성
  -> claude-diary diary-notion push --input <json>
  -> Notion Entries DB에 row push
```

설치 명령 `working-diary install --force`는 다음을 갱신합니다.

- `~/.claude/settings.json` Stop Hook
- `~/.claude/commands/diary.md`
- `~/.claude/commands/diary-notion.md`

### 3-3. Codex 로직

Codex는 Stop Hook이 없습니다. 전역 skill을 통해 core CLI를 호출합니다.

```text
$diary
  -> Codex가 현재 세션 내용을 .diary-<id>.json으로 작성
  -> working-diary write --input .diary-<id>.json
  -> manual diary 경로에 append

$diary-notion
  -> Codex가 현재 세션을 task 단위로 분리
  -> .diary-notion-<id>.json 작성
  -> working-diary diary-notion push --input .diary-notion-<id>.json
  -> Notion Entries DB에 row push
```

설치 명령 `working-diary install --force --codex-only`는 다음을 갱신합니다.

- `~/.codex/skills/diary/SKILL.md`
- `~/.codex/skills/diary-notion/SKILL.md`

## 4. CLI

핵심 명령:

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
working-diary diary-notion push --input .diary-notion-<id>.json
working-diary notion push --input .diary-notion-<id>.json
```

조회와 관리 명령:

```bash
working-diary search "키워드"
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

확장 기능 명령:

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

기존 CLI도 계속 지원합니다.

```bash
claude-diary write
claude-diary diary-notion ensure
```

## 5. 설정

설정 파일은 OS별 사용자 config 경로의 `claude-diary/config.json`에 저장됩니다. Notion 같은 exporter를 설정하면 API token, webhook URL, root page ID도 이 로컬 config에 저장됩니다. CLI 출력에서는 긴 token과 webhook 값을 masking해서 보여줍니다.

| 환경변수 | 설명 | 기본값 |
|----------|------|--------|
| `CLAUDE_DIARY_LANG` | 일지 언어. `ko` 또는 `en` | `ko` |
| `CLAUDE_DIARY_DIR` | 자동 일지 저장 경로 | `~/working-diary` |
| `CLAUDE_DIARY_MANUAL_DIR` | 수동 일지 저장 경로 | `~/working-diary/manual` |
| `CLAUDE_DIARY_TZ_OFFSET` | UTC offset | `9` |
| `CLAUDE_DIARY_NOTION_TOKEN` | Notion token. config보다 우선 | - |
| `CLAUDE_DIARY_NOTION_ROOT_PAGE_ID` | Notion root page ID. config보다 우선 | - |
| `CLAUDE_DIARY_SKIP` | `1`, `true`, `yes`이면 Claude Code Stop Hook 자동 기록 skip | - |

PowerShell에서 한글이나 이모지가 깨져 보이면 현재 세션 출력 인코딩을 UTF-8로 바꿉니다.

```powershell
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$OutputEncoding = [System.Text.UTF8Encoding]::new()
```

## 6. 주요 기능

- 자동 카테고리 분류
- Git branch, commit, diff stat 기록
- secret scan과 masking
- 검색 인덱스
- Notion 업무일지: `working-diary diary-notion init` -> `working-diary diary-notion ensure`
- Slack, Discord, Obsidian, GitHub exporter: `working-diary config --add-exporter <name>`
- HTML dashboard: `working-diary dashboard` 또는 `working-diary dashboard --serve --port 8787`
- audit log와 source checksum 검증
- team mode: `working-diary team init --repo <url> --name <name>`

## 7. 문제 해결

| 증상 | 확인할 것 |
|------|-----------|
| `/diary` 또는 `/diary-notion`이 최신 지시문을 쓰지 않음 | `working-diary install --force`로 hook과 slash command를 갱신 |
| `$diary` 또는 `$diary-notion`이 최신 지시문을 쓰지 않음 | `working-diary install --force --codex-only`로 skill을 갱신한 뒤 새 Codex 세션 시작 |
| Notion push가 인증 오류를 냄 | Integration token, root page ID, page 공유 상태 확인 |
| Notion 하위항목 nesting이 안 보임 | `Entries` DB에서 Notion UI의 Sub-items를 한 번 활성화 |
| push 재시도 시 중복이 걱정됨 | 기본 push는 같은 `Session ID + Task Index`를 skip. 다시 쓰려면 `--force` 사용 |
| PowerShell에서 글자가 깨짐 | 위 UTF-8 출력 설정 적용 |

## 8. 개발

```bash
pip install -e ".[dev,notion]"
python -m pytest -q
python -m ruff check .
```

## 9. 로드맵

현재 README는 사용 가능한 기능을 중심으로 유지하고, 상세 설계와 진행 기록은 `docs/`에 둡니다.

| 구분 | 내용 |
|------|------|
| 현재 안정화 | Claude Code Stop Hook, Codex skill, Markdown 일지, Notion task row push, schema/view ensure |
| 다음 개선 | Windows 설치/출력 경험 정리, Notion sub-item 안내 개선, CI/lint 범위 점진 확대 |
| 검토 중 | SQLite 기반 검색 인덱스, Cursor/Windsurf/VS Code 같은 다른 AI IDE 연동 |

## 10. 문서

- [Notion hierarchical design](docs/02-design/features/diary-notion-hierarchical.design.md)
- [Notion views design](docs/02-design/features/diary-notion-views.design.md)
- [Distribution plan](docs/plans/phase-d-distribution.md)
- [Contributing](CONTRIBUTING.md)
- [Security](SECURITY.md)

## 11. 라이선스

MIT
