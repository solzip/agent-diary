# Agent Diary

**AI와 한 작업을 기억해두는 도구.** Claude Code가 답할 때마다 자동으로, Codex에서는 명령 한 번으로 그날 무엇을 시켰고 무엇이 바뀌었는지 기록합니다.

[![CI](https://github.com/solzip/agent-diary/actions/workflows/ci.yml/badge.svg)](https://github.com/solzip/agent-diary/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Core Dependencies: 0](https://img.shields.io/badge/core%20dependencies-0-brightgreen)](https://github.com/solzip/agent-diary)

> [English](README.md) | 한국어
>
> 커뮤니티 프로젝트입니다. Anthropic 또는 OpenAI의 공식 프로젝트가 아닙니다.

![Agent Diary 데모](docs/demo.svg)

> **코드를 보러 오셨다면** — [Architecture](docs/ARCHITECTURE.md)에 멱등성 키와 캐시 무효화, 원인별로 갈리는 재시도 정책, 스키마 버전 관리, 부분 실패의 의미를 정리해뒀습니다. [Postmortem](docs/postmortem/2026-08-07-ensure-wipe.md)은 스키마 PATCH 하나가 497 row에서 6개 속성을 지운 사고의 전말입니다.

## 1. 왜 필요한가

AI와 한 작업은 대화창에 남고, 대화창은 닫힙니다. 이틀 뒤 "이 파일 왜 이렇게 고쳤더라"를 되짚을 방법이 없고, 주간 회고나 업무일지를 쓸 때가 되면 기억에 의존하게 됩니다. 커밋 로그는 결과만 남기지 무엇을 요청했고 무엇을 시도했는지는 남기지 않습니다.

Agent Diary는 그 맥락을 작업이 진행되는 동안 자동으로 붙잡습니다. 별도로 기록하는 습관을 만들 필요가 없습니다.

턴 하나가 끝날 때마다 이런 항목이 파일에 append됩니다 — 주고받은 한 번이지, 세션 전체의 요약이 아닙니다.

```markdown
### ⏰ 14:30:15 | 📁 `my-app`

**🏷️ 카테고리:** `feature` `test`

**📋 작업 요청:**
  1. 로그인에 JWT 인증을 붙여줘
  2. 테스트도 같이 작성해줘

**📄 생성된 파일:**
  - `src/auth/jwt_handler.py`
  - `tests/test_auth.py`

**✏️ 수정된 파일:**
  - `src/api/routes.py`

**🔀 Git:**
  - 🌿 브랜치: `feat/jwt-auth`
  - 커밋: `a1b2c3d` feat: verify tokens and cover login

**📊 변경 통계:** +145 / -12 lines (5 files)

**⚡ 주요 명령어:**
  - `export API_KEY=****`
  - `pytest -q`

**💬 응답:**

> `verify_token()`을 추가해 로그인 라우트에 연결했습니다. 만료된 토큰 경로가
> 안 덮여 있어서 `test_auth.py`에 401을 확인하는 케이스도 넣었습니다.

**🔒 1 시크릿 마스킹됨**
```

카테고리는 작업 내용에서 추론하고, 브랜치·커밋·diff 통계는 저장소에서 직접 읽습니다. 답변은 키워드가 든 문장 조각으로 자르지 않고 원문 그대로 남깁니다. 위 `API_KEY`처럼 시크릿으로 보이는 값은 **파일에 쓰기 전에** 마스킹합니다.

**항목 하나는 턴 하나지 세션 하나가 아닙니다.** Stop Hook은 Claude Code가 답을 마칠 때마다 돌고, 항목에는 직전 항목 이후에 일어난 것만 들어갑니다. 그래서 긴 세션은 그날 파일에 항목 여러 개를 남깁니다. 4.9.0 이전에 쓰인 일지는 모양이 다릅니다 — 그때는 항목마다 세션 앞부분의 요청을 다시 적어서, 같은 요청이 파일 아래로 계속 반복됩니다.

위 예시에 `📝 작업 요약`이 없는 건 훅이 그 항목을 쓰지 않기 때문입니다. 이건 에이전트가 항목을 직접 작성할 때 — `$diary`, `agent-diary write --input` — `summary_hints`를 넣어주면 나옵니다. `/diary`는 항목을 직접 작성하지 않고 transcript를 읽어 기록하므로 이 블록을 만들지 않습니다.

**브랜치 줄에는 차수가 붙습니다.** ``🌿 브랜치: `feat/jwt-auth` (#3)``은 이 프로젝트가 그 브랜치에서 기록한 **세 번째 세션**이라는 뜻입니다. 항목 자체가 "이 작업의 어디쯤인지"를 말해주니 세어볼 필요가 없습니다. **항목이 아니라 세션을 셉니다** — 오래 붙잡고 있던 날은 항목이 여러 개여도 숫자는 하나입니다. 브랜치의 첫 세션에는 번호를 붙이지 않습니다. 뒤에 가리킬 흐름이 없기 때문입니다.

### 이런 점이 다릅니다

- **자동입니다.** Claude Code에서는 Stop Hook이 Claude가 답을 마칠 때마다 돌면서 기록합니다. 기록하겠다고 결심할 필요가 없습니다.
- **코어 의존성이 0개입니다.** 표준 라이브러리만 씁니다. Notion 연동을 쓸 때만 `requests`가 추가됩니다.
- **로컬 파일입니다.** 평범한 Markdown이라 grep도 되고 Obsidian에도 들어가고, 서비스가 사라져도 남습니다.
- **팀 도구로도 씁니다.** 필요하면 Notion 업무일지 DB로 push하고, Slack·Discord·GitHub으로도 내보냅니다.

```bash
pip install agent-diary
agent-diary init
agent-diary backfill      # 선택: 이미 쌓여 있는 세션 가져오기
```

이후로는 따로 할 일이 없습니다. Claude Code에서 하는 작업이 `~/working-diary/YYYY-MM-DD.md`에 쌓입니다.

Claude Code는 그동안 transcript를 디스크에 남겨왔습니다. `backfill`은 그걸 읽어서 **이미 한 일**로 채워진 일지를 만들어줍니다 — 빈 디렉터리가 아니라요. 이 도구를 만든 PC에서는 과거 세션 79개가 21일치 기록이 됐습니다. 두 번 실행해도 아무것도 달라지지 않습니다. 이미 들어 있는 세션은 건너뜁니다.

> 이 프로젝트는 `claude-diary` → `working-diary`를 거쳐 `agent-diary`가 되었습니다. 옛 이름으로 설치했더라도 `working-diary`와 `claude-diary` 명령이 그대로 동작합니다.
>
> 내부 Python 패키지는 `claude_diary`로 남아 있습니다. `install`이 사용자의 `settings.json`에 `python -m claude_diary.hook`을 기록해두기 때문에, 이름을 바꾸면 기존 사용자의 Stop Hook이 조용히 멈춥니다. 설치 경로(`pip install agent-diary`)와 import 이름이 다른 건 파이썬에서 흔한 구성입니다.

### 지원 에이전트

| 에이전트 | 자동 기록 | 수동 Markdown | Notion 업무일지 | 적용/갱신 |
|----------|-----------|---------------|-----------------|-----------|
| Claude Code | Stop Hook | `/diary` | `/diary-notion` | `agent-diary install --force` |
| Codex | 없음 | `$diary` | `$diary-notion` | `agent-diary install --force --codex-only` |

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
| Claude Code에서 Markdown 자동/수동 기록 | `pip install agent-diary` -> `agent-diary init` -> `agent-diary install --force` |
| Claude Code에서 Notion 업무일지까지 사용 | `pip install "agent-diary[notion]"` -> `agent-diary init` -> `agent-diary install --force` -> `agent-diary diary-notion init` -> `agent-diary diary-notion ensure` |
| Codex에서 Markdown 수동 기록 | `pip install agent-diary` -> `agent-diary init --codex-only` -> `agent-diary install --force --codex-only` -> 새 Codex 세션 |
| Codex에서 Notion 업무일지까지 사용 | `pip install "agent-diary[notion]"` -> `agent-diary init --codex-only` -> `agent-diary install --force --codex-only` -> `agent-diary diary-notion init` -> `agent-diary diary-notion ensure` -> 새 Codex 세션 |

### 2-1. 패키지 설치와 기본 설정

pip 설치:

```bash
pip install agent-diary
agent-diary init
```

Notion 연동까지 사용할 경우:

```bash
pip install "agent-diary[notion]"
agent-diary init
```

Claude Code 플러그인 설치는 별도 배포 경로입니다. Claude Code의 plugin marketplace에서 이 프로젝트를 설치할 때 사용합니다.

```bash
# Claude Code 안에서 실행
/plugin marketplace add solzip/agent-diary
/plugin install agent-diary@solzip
```

이 플러그인은 Claude Code 쪽 hook 설정을 배포합니다. `agent-diary` CLI는 Python 패키지에서 제공되므로, 플러그인 경로를 쓰더라도 Python 패키지 설치와 `agent-diary init`이 준비되어 있어야 합니다.

소스에서 설치:

```bash
git clone https://github.com/solzip/agent-diary.git
cd agent-diary
pip install -e .
agent-diary init
```

소스 설치에서 Notion 연동까지 사용할 경우:

```bash
pip install -e ".[notion]"
```

`agent-diary init`은 설정 파일과 일지 디렉터리를 만들고 Claude Code Stop Hook도 함께 등록합니다. Codex만 쓰는 경우에는 `agent-diary init --codex-only`를 실행하면 Claude Code 설정을 수정하지 않습니다.

Claude Code나 Codex에서 slash command 또는 skill을 최신 상태로 쓰려면 아래 에이전트별 적용 명령을 추가로 실행합니다.

### 2-2. Claude Code 사용법

Claude Code는 세션 종료 시 자동 기록할 수 있고, 세션 중 수동 기록도 할 수 있습니다.

Claude Code 적용 또는 갱신:

```bash
agent-diary install --force
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

`/diary`는 현재 프로젝트의 Claude Code transcript를 찾아 `agent-diary write` core로 기록합니다. `/diary-notion`은 세션 내용을 task row로 정리한 JSON을 만든 뒤 `agent-diary diary-notion push` core로 전달합니다.

### 2-3. Codex 사용법

Codex는 자동 hook을 사용하지 않습니다. 사용자가 skill을 호출할 때만 기록합니다.

Codex 적용 또는 갱신:

```bash
agent-diary install --force --codex-only
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
pip install "agent-diary[notion]"
```

소스 설치에서 Notion까지 사용할 경우:

```bash
pip install -e ".[notion]"
```

설정 절차:

1. https://www.notion.so/my-integrations 에서 Integration을 만들고 토큰을 복사합니다.
2. Notion에 루트 페이지를 만듭니다. 예: `Agent Diary`
3. 루트 페이지를 Integration에 공유합니다.
4. 설정을 저장합니다.

```bash
agent-diary diary-notion init
```

`diary-notion init`은 입력한 Notion token과 root page ID를 로컬 config에 저장합니다. 이후 `CLAUDE_DIARY_NOTION_TOKEN` 또는 `CLAUDE_DIARY_NOTION_ROOT_PAGE_ID` 환경변수를 지정하면 저장된 config 값보다 환경변수가 우선합니다.

5. 연도별 `Entries` DB와 schema/view를 보장합니다.

```bash
agent-diary diary-notion ensure
```

6. 세션에서 `/diary-notion` 또는 `$diary-notion`을 실행합니다.

### 2-5. Notion push 동작

```bash
agent-diary diary-notion push --input .diary-notion-<id>.json
agent-diary diary-notion push --input .diary-notion-<id>.json --force
agent-diary diary-notion push --input .diary-notion-<id>.json --dry-run
```

- 기본 push는 `Session ID + Task Index`로 이미 기록된 row를 skip합니다.
- `--force`는 같은 세션의 기존 row를 archive한 뒤 다시 push합니다.
- `--dry-run`은 Notion에 쓰지 않고 만들어질 row와 page 본문을 출력합니다. `--preview-file <path>`를 함께 주면 같은 내용을 Markdown 파일로 저장합니다.
- 같은 `Task Group`에 이미 기록된 세션이 있으면 제목에 `(N차)`가 붙습니다. 첫 세션에는 붙지 않습니다.
- `--dry-run`도 차수를 반영하려고 Notion을 **읽습니다**(조회만). 자격증명이 없거나 아직 해당 연도 DB를 만든 적이 없으면 차수 없이 렌더링하고 그 사실을 출력 상단에 밝힙니다. 미리보기가 데이터베이스나 페이지를 새로 만드는 일은 없습니다.
- 실패한 task가 하나라도 있으면 exit code `1`로 종료하고 입력 JSON을 보존합니다.
- 전체 성공 또는 이미 push된 task만 skip된 경우 exit code `0`으로 종료합니다.

### 2-6. push가 남기는 로컬 기록 (run artifacts)

push는 **기본적으로** 실행할 때마다 현재 작업 디렉터리 아래에 실행 기록을 남깁니다. `--dry-run`에서도 남깁니다.

```text
<cwd>/.agent-diary/runs/<YYYYMMDD-HHMMSS-session>/
  input.json        원본 task JSON
  git-diff.patch    push 시점의 작업 트리 diff
  preview.md        Notion 본문 렌더링 결과
  manifest.json     위 파일들의 목록과 sha256. 실제 push였다면 결과 요약까지
```

Notion은 기록의 목적지이지 사본이 아닙니다. push가 중간에 실패하거나 row를 나중에 손으로 고치면, 실제로 무엇을 보냈는지 되짚을 방법은 이 로컬 기록뿐입니다.

**`git-diff.patch`에는 커밋하지 않은 코드가 그대로 들어갑니다.** 저장소에 딸려 올라가지 않도록 `.gitignore`에 추가하세요.

```gitignore
.agent-diary/runs/
```

저장 위치를 바꾸거나 아예 끄려면:

```bash
agent-diary diary-notion push --input <json> --artifact-dir build/diary-runs
agent-diary diary-notion push --input <json> --no-artifacts
```

### 2-7. 검토 큐

검토는 일이 끝난 뒤 사람이 내리는 판단이므로, 기록 파이프라인의 어느 단계도 스스로 "검토됨"을 선언하지 않습니다. push는 모든 새 row를 `Needs Review`로 기록하고, `Reviewed`로 올릴 수 있는 것은 이 명령의 `--apply`뿐입니다.

```bash
agent-diary diary-notion review              # 검토 대기 row 나열 (읽기 전용)
agent-diary diary-notion review --apply      # Reviewed + Last Reviewed=오늘 기록
agent-diary diary-notion review --year 2026
```

`--apply` 없이 실행하면 아무것도 쓰지 않습니다. `ensure --dry-run` / `ensure`와 같은 방식입니다.

### 2-8. Notion sub-item

작업 계층 접기/펼치기는 Notion의 native Sub-items 기능을 사용합니다. 이 기능은 Notion UI에서 한 번 켜야 합니다.

1. 해당 연도의 `Entries` DB를 엽니다.
2. 우상단 `...` 메뉴에서 `Sub-items`를 활성화합니다.
3. 다시 `agent-diary diary-notion ensure`를 실행합니다.

Sub-items가 아직 없어도 row 자체는 만들어집니다. 다만 부모를 지정한 task는 실패로 집계됩니다 — push가 위 안내를 출력하고, 입력 JSON을 보존한 채 종료 코드 `1`로 끝나므로, Sub-items를 켠 뒤 같은 push를 다시 실행하면 됩니다.

## 3. 로직

이 절은 **무엇이 어떤 순서로 흐르는가**를 다룹니다. 왜 그렇게 설계했는지 — 멱등성 키, 재시도 정책, 스키마 버전 관리, 부분 실패 처리 — 는 [Architecture](docs/ARCHITECTURE.md)에 있습니다.

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
| CLI entry | `src/claude_diary/cli/__init__.py` | `agent-diary` 명령과 `working-diary` / `claude-diary` alias 라우팅 |
| 자동 기록 core | `src/claude_diary/core.py` | Claude Code Stop Hook 자동 일지 pipeline |
| 수동 기록 core | `src/claude_diary/cli/write.py` | `/diary`, `$diary`, `agent-diary write` 처리 |
| Notion push | `src/claude_diary/cli/notion_push/` | task JSON을 Notion row로 push (validate/properties/relations/artifacts로 분리) |
| Notion schema/view | `src/claude_diary/cli/notion_ensure.py` | schema v8, core view 3개와 operating view 2개 보장 |
| Notion 검토 큐 | `src/claude_diary/cli/notion_review.py` | `Needs Review` row 나열, `--apply` 시 `Reviewed` 기록 |
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
  -> agent-diary write
  -> 현재 cwd에 맞는 Claude transcript 탐색
  -> manual diary 경로에 append

/diary-notion
  -> agent가 task JSON 생성
  -> agent-diary diary-notion push --input <json>
  -> Notion Entries DB에 row push
```

설치 명령 `agent-diary install --force`는 다음을 갱신합니다.

- `~/.claude/settings.json` Stop Hook
- `~/.claude/commands/diary.md`
- `~/.claude/commands/diary-notion.md`

### 3-3. Codex 로직

Codex는 Stop Hook이 없습니다. 전역 skill을 통해 core CLI를 호출합니다.

```text
$diary
  -> Codex가 현재 세션 내용을 .diary-<id>.json으로 작성
  -> agent-diary write --input .diary-<id>.json
  -> manual diary 경로에 append

$diary-notion
  -> Codex가 현재 세션을 task 단위로 분리
  -> .diary-notion-<id>.json 작성
  -> agent-diary diary-notion push --input .diary-notion-<id>.json
  -> Notion Entries DB에 row push
```

설치 명령 `agent-diary install --force --codex-only`는 다음을 갱신합니다.

- `~/.codex/skills/diary/SKILL.md`
- `~/.codex/skills/diary-notion/SKILL.md`

## 4. CLI

핵심 명령:

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

agent-diary try
agent-diary try path/to/transcript.jsonl
agent-diary try --cwd /path/to/project

agent-diary report
agent-diary report --days 14
agent-diary report --month 2026-07
agent-diary report --from 2026-07-01 --to 2026-07-15
agent-diary report --project my-app --output july.md
agent-diary report --month 2026-07 --detail
agent-diary report --month 2026-07 --json

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

조회와 관리 명령:

```bash
agent-diary search "키워드"
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

<a id="reindex-once-on-4-11-3"></a>
**4.11.3으로 올린 뒤 `agent-diary reindex`를 한 번 돌리세요.** 그 이전 버전의 `reindex`는 일지 본문에서 인덱스를 다시 만들면서 항목마다 **첫 번째 카테고리만** 담았습니다. 그래서 카테고리로 하는 검색이 매치의 일부만 답했습니다 — 실제 일지 73개 파일 기준 `refactor`가 1,183건 중 35건만 돌려줬습니다. 일지 파일 자체는 처음부터 정확했고, 얇았던 건 거기서 만들어진 인덱스뿐이며, 그것도 **한 번이라도 rebuild한 경우에만** 그렇습니다. 훅이 쓰는 증분 경로는 영향을 받은 적이 없습니다. 그래서 4.11.3 이상에서 다시 만들면 전부 복구됩니다.

확장 기능 명령:

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

기존 명령 이름도 계속 지원합니다. `working-diary`·`claude-diary` 바이너리는 같은 CLI이고, `notion`은 `diary-notion`의 별칭으로 남아 있습니다.

```bash
working-diary write
claude-diary diary-notion ensure
agent-diary notion push --input .diary-notion-<id>.json
```

## 5. 설정

설정 파일은 OS별 사용자 config 경로의 `claude-diary/config.json`에 저장됩니다. Notion 같은 exporter를 설정하면 API token, webhook URL, root page ID도 이 로컬 config에 저장됩니다. CLI 출력에서는 긴 token과 webhook 값을 masking해서 보여줍니다.

환경변수는 **두 부류로 우선순위가 반대**입니다. 아래 표의 "우선순위" 열을 먼저 보세요.

| 환경변수 | 설명 | 기본값 | 우선순위 |
|----------|------|--------|----------|
| `CLAUDE_DIARY_LANG` | 일지 언어. `ko` 또는 `en` | `ko` | config.json이 이김 |
| `CLAUDE_DIARY_DIR` | 자동 일지 저장 경로 | `~/working-diary` | config.json이 이김 |
| `CLAUDE_DIARY_MANUAL_DIR` | 수동 일지 저장 경로 | `~/working-diary/manual` | config.json이 이김 |
| `CLAUDE_DIARY_TZ_OFFSET` | UTC offset | `9` | config.json이 이김 |
| `CLAUDE_DIARY_NOTION_TOKEN` | Notion token | - | **환경변수가 이김** |
| `CLAUDE_DIARY_NOTION_ROOT_PAGE_ID` | Notion root page ID | - | **환경변수가 이김** |
| `CLAUDE_DIARY_SKIP` | `1`, `true`, `yes`이면 Claude Code Stop Hook 자동 기록 skip | - | 환경변수 전용 |

앞의 네 개는 `config.json > 환경변수 > 기본값` 순서로 병합됩니다. 즉 `init`을 한 번이라도 실행했다면 해당 키가 config에 기록돼 있어서 **환경변수를 지정해도 무시됩니다.** 저장 경로를 임시로 바꾸려면 환경변수가 아니라 `config.json`을 고쳐야 합니다.

### 기간 단위 보고서

`search`는 항목을 찾고 `stats`는 개수를 셉니다. `report`는 **한 덩어리의 작업을 문서 하나로** 만듭니다 — 스탠드업, 월간 보고, 청구 근거, 또는 그 기간에 무엇을 했는지에 대한 증빙용으로요.

```bash
agent-diary report                                  # 최근 7일
agent-diary report --month 2026-07 --project my-app
agent-diary report --from 2026-07-01 --to 2026-07-15 --output july.md
```

```markdown
# 작업 보고 — 2026-07-01 ~ 2026-07-31

640 session(s) · 16 day(s) · 1 project(s) · +21871 / -11431 lines · 11272 file(s) · 2305 commit(s)

`docs` 197 · `bugfix` 177 · `test` 169 · `feature` 88

## my-app — 640 session(s)

### 2026-07-01
- JWT 검증 미들웨어를 추가하고 로그인 실패 경로를 테스트로 덮음
- …
```

세션 목록은 검색 인덱스에서, 서술은 일지에서 가져와 **session id로 조인**합니다. 그래서 한 프로젝트로 필터링하면 같은 날 다른 프로젝트의 문장이 섞이지 않습니다.

작업 요약을 우선하고 입력한 요청은 뒤로 뺍니다 — 요약은 정리된 기록이고 요청은 날것이니까요. `--detail`을 주면 둘 다 넣습니다. 요약이 없는 날은 요청을 쓰고, 그 사실을 문서에 밝힙니다.

### 무엇이 기록되고, 어떻게 제한하는가

**입력한 프롬프트는 쓴 그대로 저장됩니다.** 그게 이 도구의 목적이지만, 회사에서 돌리기 전에 한 번 생각해볼 지점이기도 합니다. 프롬프트에는 고객사명, 내부 URL, 사업 맥락이 예사로 들어갑니다.

제어 수단이 세 개 있고 전부 기본 꺼짐입니다.

**세션 하나만 건너뛰기** — 아무것도 기록되지 않고 설정도 안 건드립니다.

```bash
CLAUDE_DIARY_SKIP=1 claude
```

**프로젝트를 영구 제외.** 이름만 쓰면 디렉터리명과 비교하고, 구분자가 들어가면 경로로 취급해 그 아래 전부를 덮습니다.

```json
{
  "skip_projects": [
    "personal-notes",        // 이 이름을 가진 디렉터리
    "~/clients",             // 이 디렉터리와 그 아래 전부
    "C:\\work\\acme"
  ]
}
```

경로 형태가 필요한 이유는 이름만으로는 `~/work/acme`와 `~/personal/acme`를 구분할 수 없기 때문이고, 고객사 저장소를 하나씩 열거하는 일은 **정작 빼고 싶었던 세션 직전까지 미뤄지기** 때문입니다.

**기본 패턴 외에 더 가리기.** 시크릿은 기록 전에 마스킹됩니다 (API 키·토큰·개인키 등 기본 패턴 12종). 시크릿은 아니지만 남기고 싶지 않은 이름은 직접 정규식으로 추가합니다.

```json
{
  "security": {
    "additional_secret_patterns": [
      "acme-corp",
      "internal\\.example\\.com",
      "PROJ-\\d{4}"
    ]
  }
}
```

마스킹은 항목을 포맷하기 전에 일어나므로, 일지와 거기서 이어지는 모든 exporter — Notion exporter 포함 — 에서 똑같이 `****`가 됩니다. 덮이지 않는 경로가 하나 있습니다: 에이전트가 `diary-notion push`용으로 직접 작성한 task JSON은 작성된 그대로 push되고, push 명령 자체는 스캔하지 않습니다.

`agent-diary doctor`가 각 규칙이 몇 개 걸려 있는지 알려줍니다. "지금 뭘 기록하고 있더라"를 기억이 아니라 확인으로 답할 수 있게요.

### 커밋 줄의 Gitmoji

기본은 꺼짐입니다. `config.json`에서 켜면 커밋 줄에 Conventional Commit 타입에 해당하는 [gitmoji](https://gitmoji.dev)가 붙습니다.

```json
{ "formatting": { "gitmoji": true } }
```

```diff
-  - 커밋: `a1b2c3d` feat: verify tokens and cover login
+  - 커밋: `a1b2c3d` ✨ feat: verify tokens and cover login
```

타입을 알아볼 수 없는 커밋은 그대로 두고, 이미 이모지로 시작하는 메시지에는 덧붙이지 않습니다.

**커밋 줄에만** 적용되고 카테고리 태그에는 붙이지 않습니다. 📝·⚡·🔒 세 개가 일지에서 이미 작업 요약·주요 명령어·시크릿 마스킹을 뜻해서, 카테고리까지 장식하면 한 화면에서 같은 글자가 두 가지 의미를 갖게 됩니다.

Notion 자격증명 두 개만 반대로, 환경변수가 config를 덮어씁니다. CI나 여러 워크스페이스를 오갈 때 토큰을 파일에 남기지 않기 위한 예외입니다.

<a id="consoles-that-cannot-draw-every-character"></a>
### 콘솔이 못 그리는 문자가 있을 때

4.11.1부터, 콘솔이 인코딩하지 못하는 문자가 있어도 **명령이 죽지 않습니다.** 레거시 코드페이지에는 이 도구가 쓰는 문장부호와 이모지가 들어갈 자리가 없습니다 — cp949는 한글과 `→`는 담지만 `—`·`✓`, 그리고 모든 항목 헤더를 이루는 `⏰`/`📁`는 담지 못합니다. 그래서 `stats`·`weekly`·`report`·`doctor`가 자기 출력에 걸려 죽곤 했습니다.

출력 스트림은 UTF-8로 강제하지 않고 **콘솔이 쓰던 인코딩을 그대로 둡니다.** 레거시 콘솔에서 그 인코딩이 곧 그 터미널이 실제로 그려낼 수 있는 것이고, UTF-8로 바꾸면 em dash 하나 살리자고 **멀쩡하던 한글을 깨뜨리게** 되기 때문입니다. 대신 인코딩할 수 없는 문자는 가장 가까운 ASCII로 그립니다 — `█`은 `#`, `╔═╗`는 `+=+`, em dash는 `-`가 됩니다. 살아남지 못한 글자나 숫자는 `?`가 되는데, 내용이 사라진 건 사라진 것처럼 보여야 하기 때문입니다. 그 외 기호는 `*`가 됩니다.

즉 차트에 `#`가 보이거나 단어 중간에 `?`가 보이면 설치가 깨진 게 아니라 이 대체가 동작한 것입니다. 전부 원래 문자로 보고 싶으면 UTF-8 콘솔을 쓰면 됩니다.

```powershell
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$OutputEncoding = [System.Text.UTF8Encoding]::new()
```

한 번만 필요하면 `PYTHONIOENCODING=utf-8`로도 같습니다.

## 6. 주요 기능

- 자동 카테고리 분류
- Git branch, commit, diff stat 기록
- secret scan과 masking
- 검색 인덱스
- Notion 업무일지: `agent-diary diary-notion init` -> `agent-diary diary-notion ensure`
- Notion 운영 진단: `agent-diary diary-notion ops`로 blocked/review/next action/stale/work days/today-plan 후보/부모 상태 제안 확인
- 검토 큐: `agent-diary diary-notion review`. push는 항상 `Needs Review`로 기록하고 `--apply`만 `Reviewed`로 승격
- push 실행 기록: 매 push마다 `input.json`, `git-diff.patch`, `preview.md`, `manifest.json`을 로컬에 sha256과 함께 보존
- 같은 `Task Group`을 이어가는 세션에 `(N차)` 자동 부여 (컬럼 추가 없음)
- 하루치 row는 작업한 순서대로 정렬 (`Date` 동률을 `Task Index`로 tie-break)
- Slack, Discord, Obsidian, GitHub exporter: `agent-diary config --add-exporter <name>`
- HTML dashboard: `agent-diary dashboard` 또는 `agent-diary dashboard --serve --port 8787`
- audit log와 source checksum 검증
- team mode: `agent-diary team init --repo <url> --name <name>`

## 7. 문제 해결

| 증상 | 확인할 것 |
|------|-----------|
| `/diary` 또는 `/diary-notion`이 최신 지시문을 쓰지 않음 | `agent-diary install --force`로 hook과 slash command를 갱신 |
| `$diary` 또는 `$diary-notion`이 최신 지시문을 쓰지 않음 | `agent-diary install --force --codex-only`로 skill을 갱신한 뒤 새 Codex 세션 시작 |
| Notion push가 인증 오류를 냄 | Integration token, root page ID, page 공유 상태 확인 |
| Notion 하위항목 nesting이 안 보임 | `Entries` DB에서 Notion UI의 Sub-items를 한 번 활성화 |
| push 재시도 시 중복이 걱정됨 | 기본 push는 같은 `Session ID + Task Index`를 skip. 다시 쓰려면 `--force` 사용 |
| 프로젝트에 `.agent-diary/` 디렉터리가 생김 | push가 남기는 실행 기록입니다. `.gitignore`에 `.agent-diary/runs/`를 추가하거나 `--no-artifacts`로 끕니다 ([2-6](#2-6-push가-남기는-로컬-기록-run-artifacts)) |
| 어느 순간부터 일지가 안 쌓이는데 이유를 모르겠음 | `agent-diary doctor`를 실행하세요. hook 등록 여부, 그 hook이 가리키는 모듈이 아직 존재하는지, 마지막 기록이 며칠 전인지를 확인합니다 |
| 예전엔 `.codefleet/runs/` 였는데 | 별개 프로젝트 이름을 빌려 쓰던 옛 기본값입니다. 새 프로젝트는 `.agent-diary/runs/`를 쓰고, 이미 `.codefleet/runs/`가 있으면 기록이 갈라지지 않도록 그대로 씁니다 |
| 제목에 붙은 `(N차)`를 없애고 싶음 | 같은 `Task Group`의 이전 세션 수로 매겨집니다. `task_group`을 비우면 붙지 않습니다 |
| 출력에 `#`·`+`·`?`·`*`가 보임 | 콘솔이 그 문자를 인코딩하지 못해 가장 가까운 ASCII로 그린 것입니다. [콘솔이 못 그리는 문자가 있을 때](#consoles-that-cannot-draw-every-character) 참고 |
| 카테고리로 하는 `search` 결과가 일지보다 적음 | 4.11.3 이전에 만든 인덱스는 항목당 카테고리를 하나만 담았습니다. [`agent-diary reindex`](#reindex-once-on-4-11-3)를 한 번 돌리세요 |

## 8. 개발

```bash
pip install -e ".[dev,notion]"
python -m pytest -q
python -m ruff check .
python -m mypy
```

`mypy`는 인자 없이 실행하면 `pyproject.toml`에 나열된 모듈만 검사합니다. 타입을 붙인 코어가 그 목록이고, CI가 초록으로 유지합니다. 모듈을 새로 주석 처리하면 목록에 추가하세요 — 목록에 올린다는 건 앞으로 계속 통과시키겠다는 약속입니다.

CI에서는 Python 3.12 작업에서만 돕니다. 현재 mypy가 이 프로젝트의 하한인 3.8에서 실행되지 않기 때문이고, 어노테이션 자체는 3.8 기준으로 작성돼 있습니다.

## 9. 로드맵

현재 README는 사용 가능한 기능을 중심으로 유지하고, 상세 설계와 진행 기록은 `docs/`에 둡니다.

| 구분 | 내용 |
|------|------|
| 사용 가능 | Claude Code Stop Hook, Codex skill, Markdown 일지, Notion task row push, schema v8 / view ensure, 운영 진단 `ops`, 검토 큐 `review`, push 실행 기록 |
| 진행 중 | Notion 스키마 축소 ([#12](https://github.com/solzip/agent-diary/issues/12)) |
| 다음 개선 | Windows 설치/출력 경험 정리, Notion sub-item 안내 개선 |
| 검토 중 | SQLite 기반 검색 인덱스, Cursor/Windsurf/VS Code 같은 다른 AI IDE 연동 |

## 10. 문서

코드를 읽을지 판단하려는 분이라면 이 둘을 먼저 보세요.

- **[Architecture](docs/ARCHITECTURE.md)** — 멱등성 모델, 재시도·에러 분류 정책, 캐시 무효화, 스키마 버전 관리, 부분 실패의 의미, 의존성 0개를 택한 이유
- **[Postmortem: `ensure`가 497 row의 6개 속성을 지운 사고](docs/postmortem/2026-08-07-ensure-wipe.md)** — 증상, 프로덕션 대조 측정, 근본 원인, 수정, 회귀 테스트, 그리고 두 달간 못 본 이유

세부 설계 문서:

- [결정 문서 (ADR)](docs/decisions/README.md) — 비교한 선택지와 탈락한 쪽을 버린 이유
- [Notion hierarchical design](docs/02-design/features/diary-notion-hierarchical.design.md)
- [Notion views design](docs/02-design/features/diary-notion-views.design.md)
- [Distribution plan](docs/plans/phase-d-distribution.md)
- [Contributing](CONTRIBUTING.md)
- [Security](SECURITY.md)

## 11. 라이선스

MIT
