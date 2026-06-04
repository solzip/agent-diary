# Working Diary

Claude Code와 Codex 작업 세션을 Markdown 일지 또는 Notion 업무일지로 기록하는 CLI 도구입니다.

[![CI](https://github.com/solzip/working-diary/actions/workflows/ci.yml/badge.svg)](https://github.com/solzip/working-diary/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Core Dependencies: 0](https://img.shields.io/badge/core%20dependencies-0-brightgreen)](https://github.com/solzip/working-diary)

> [English](README.en.md) | 한국어
>
> 커뮤니티 프로젝트입니다. Anthropic 또는 OpenAI의 공식 프로젝트가 아닙니다.

## 한눈에 보기

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

## 에이전트별 사용 방식

| 에이전트 | 자동 기록 | 수동 Markdown | Notion 업무일지 | 설치/갱신 |
|----------|-----------|---------------|-----------------|-----------|
| Claude Code | Stop Hook | `/diary` | `/diary-notion` | `working-diary install --force` |
| Codex | 없음 | `$diary` | `$diary-notion` | `working-diary install --force --codex` |

### Claude Code

Claude Code는 세션 종료 시 자동 기록할 수 있습니다.

```text
Claude Code 세션 종료
  -> Stop Hook 실행
  -> transcript 분석
  -> 작업, 파일, 명령, Git 정보 추출
  -> ~/working-diary/YYYY-MM-DD.md
```

세션 중 바로 기록할 수도 있습니다.

```text
/diary         -> Markdown 수동 일지
/diary-notion  -> Notion 업무 DB에 task row push
```

설치 또는 갱신:

```bash
working-diary install --force
```

이 명령은 Claude Code Stop Hook과 `/diary`, `/diary-notion` slash command를 설치하거나 갱신합니다.

### Codex

Codex는 자동 hook을 사용하지 않습니다. 사용자가 skill을 호출할 때만 기록합니다.

```text
$diary         -> 현재 대화/도구 사용 내역을 Markdown 수동 일지로 기록
$diary-notion  -> 현재 세션을 task row로 나누어 Notion에 push
```

설치 또는 갱신:

```bash
working-diary install --force --codex
```

실행 중인 Codex 세션은 이미 로드한 skill을 유지합니다. 갱신 후에는 새 Codex 세션을 여는 것을 권장합니다.

## 설치

### pip 설치

```bash
pip install claude-diary
working-diary init
```

Notion 연동까지 사용할 경우:

```bash
pip install "claude-diary[notion]"
working-diary init
```

### Claude Code 플러그인 설치

Claude Code 안에서 실행합니다.

```bash
/plugin marketplace add https://github.com/solzip/working-diary
/plugin install working-diary
```

### 소스에서 설치

```bash
git clone https://github.com/solzip/working-diary.git
cd working-diary
pip install -e .
working-diary init
working-diary install --force
```

## 저장 위치

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

## Markdown 일지

Claude Code:

```text
/diary
```

Codex:

```text
$diary
```

터미널:

```bash
working-diary write
```

Claude Code의 `/diary`는 현재 프로젝트의 transcript를 찾아 `working-diary write` core로 기록합니다. Codex의 `$diary`는 현재 대화/도구 사용 내역을 JSON으로 정리한 뒤 같은 core를 호출합니다.

## Notion 업무일지

`/diary-notion`과 `$diary-notion`은 현재 세션을 task 단위로 나누어 Notion DB에 push합니다.

```text
Notion root page
  2026
    Entries
      "Notion DB 스키마 정리" | Project: working-diary | Purpose: Planning
      "push 멱등성 보강"      | Project: working-diary | Purpose: Refactor
```

Notion page body는 짧게 유지합니다. 결과, 작업 한눈에, 영향, 검증, 리스크/다음 액션을 먼저 보여주고, 파일/명령/Git/원문 요청은 접힌 부록에 넣습니다.

### Notion 처음 설정

1. https://www.notion.so/my-integrations 에서 Integration을 만들고 토큰을 복사합니다.
2. Notion에 루트 페이지를 만듭니다. 예: `Working Diary`
3. 루트 페이지를 Integration에 공유합니다.
4. 설정을 저장합니다.

```bash
working-diary diary-notion init
```

5. 연도별 `Entries` DB와 schema/view를 보장합니다.

```bash
working-diary diary-notion ensure
```

6. 세션에서 기록합니다.

```text
/diary-notion   # Claude Code
$diary-notion   # Codex
```

### Notion sub-item

작업 계층 접기/펼치기는 Notion의 native Sub-items 기능을 사용합니다. 이 기능은 Notion UI에서 한 번 켜야 합니다.

1. 해당 연도의 `Entries` DB를 엽니다.
2. 우상단 `...` 메뉴에서 `Sub-items`를 활성화합니다.
3. 다시 `working-diary diary-notion ensure`를 실행합니다.

Sub-items가 아직 없어도 row 기록은 정상 동작합니다. 다만 계층 nesting만 표시되지 않고, push 명령이 안내를 출력합니다.

### Notion push 동작

```bash
working-diary diary-notion push --input .diary-notion-<id>.json
working-diary diary-notion push --input .diary-notion-<id>.json --force
```

- 기본 push는 `Session ID + Task Index`로 이미 기록된 row를 skip합니다.
- `--force`는 같은 세션의 기존 row를 archive한 뒤 다시 push합니다.
- 실패한 task가 하나라도 있으면 exit code `1`로 종료하고 입력 JSON을 보존합니다.
- 전체 성공 또는 이미 push된 task만 skip된 경우 exit code `0`으로 종료합니다.

## CLI

```bash
working-diary init
working-diary install --force
working-diary install --force --codex
working-diary uninstall
working-diary uninstall --codex

working-diary write
working-diary diary-notion init
working-diary diary-notion ensure
working-diary diary-notion ensure --dry-run
working-diary diary-notion push --input .diary-notion-<id>.json
working-diary notion push --input .diary-notion-<id>.json

working-diary search "키워드"
working-diary filter --project my-app
working-diary trace src/main.py
working-diary stats
working-diary weekly
working-diary dashboard
working-diary dashboard --serve --port 8787
working-diary audit
working-diary audit --verify
working-diary config
working-diary config --set lang=en
working-diary migrate
working-diary reindex
working-diary delete --last

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

## 설정

| 환경변수 | 설명 | 기본값 |
|----------|------|--------|
| `CLAUDE_DIARY_LANG` | 일지 언어. `ko` 또는 `en` | `ko` |
| `CLAUDE_DIARY_DIR` | 자동 일지 저장 경로 | `~/working-diary` |
| `CLAUDE_DIARY_MANUAL_DIR` | 수동 일지 저장 경로 | `~/working-diary/manual` |
| `CLAUDE_DIARY_TZ_OFFSET` | UTC offset | `9` |
| `CLAUDE_DIARY_NOTION_TOKEN` | Notion token. config보다 우선 | - |
| `CLAUDE_DIARY_NOTION_ROOT_PAGE_ID` | Notion root page ID. config보다 우선 | - |
| `CLAUDE_DIARY_SKIP` | `1`, `true`, `yes`이면 현재 세션 기록 skip | - |

PowerShell에서 한글이나 이모지가 깨져 보이면 현재 세션 출력 인코딩을 UTF-8로 바꿉니다.

```powershell
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$OutputEncoding = [System.Text.UTF8Encoding]::new()
```

## 주요 기능

- 자동 카테고리 분류
- Git branch, commit, diff stat 기록
- secret scan과 masking
- 검색 인덱스
- Notion, Slack, Discord, Obsidian, GitHub exporter
- HTML dashboard
- audit log와 source checksum 검증
- team mode

## 문제 해결

| 증상 | 확인할 것 |
|------|-----------|
| `/diary` 또는 `/diary-notion`이 최신 지시문을 쓰지 않음 | `working-diary install --force`로 slash command를 갱신 |
| `$diary` 또는 `$diary-notion`이 최신 지시문을 쓰지 않음 | `working-diary install --force --codex` 후 새 Codex 세션 시작 |
| Notion push가 인증 오류를 냄 | Integration token, root page ID, page 공유 상태 확인 |
| Notion 하위항목 nesting이 안 보임 | `Entries` DB에서 Notion UI의 Sub-items를 한 번 활성화 |
| push 재시도 시 중복이 걱정됨 | 기본 push는 같은 `Session ID + Task Index`를 skip. 다시 쓰려면 `--force` 사용 |
| PowerShell에서 글자가 깨짐 | 위 UTF-8 출력 설정 적용 |

## 개발

```bash
pip install -e ".[dev,notion]"
python -m pytest -q
python -m ruff check .
```

## 로드맵

현재 README는 사용 가능한 기능을 중심으로 유지하고, 상세 설계와 진행 기록은 `docs/`에 둡니다.

| 구분 | 내용 |
|------|------|
| 현재 안정화 | Claude Code Stop Hook, Codex skill, Markdown 일지, Notion task row push, schema/view ensure |
| 다음 개선 | Windows 설치/출력 경험 정리, Notion sub-item 안내 개선, CI/lint 범위 점진 확대 |
| 검토 중 | SQLite 기반 검색 인덱스, Cursor/Windsurf/VS Code 같은 다른 AI IDE 연동 |

## 문서

- [Notion hierarchical design](docs/02-design/features/diary-notion-hierarchical.design.md)
- [Notion views design](docs/02-design/features/diary-notion-views.design.md)
- [Distribution plan](docs/plans/phase-d-distribution.md)
- [Contributing](CONTRIBUTING.md)
- [Security](SECURITY.md)

## 라이선스

MIT
