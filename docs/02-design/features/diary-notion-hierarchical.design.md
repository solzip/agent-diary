# /diary-notion — Hierarchical Notion Export

> **Summary**: 슬래시 커맨드로 현재 세션을 작업 단위로 분리하여 Notion DB에 push (업무일지 자동화)
>
> **Project**: claude-code-hooks-diary
> **Date**: 2026-05-26
> **Status**: Draft (설계 의논 중)

## Executive Summary

| 관점 | 내용 |
|------|------|
| **Problem** | 기존 NotionExporter는 단순 flat DB push만 가능. 세션 1개 = 행 1개. 업무일지로 보기에 부적합 |
| **Solution** | `/diary-notion` 슬래시 커맨드 — Claude가 세션을 작업 단위로 분리 → 연도별 페이지/단일 DB로 push |
| **Core Value** | 별도 API 키 없이 (Claude Code 구독만으로) 업무일지 자동화 |

---

## 1. Overview

### 1.1 Design Goals

- 한 세션의 작업을 **의미 단위로 N개 행**으로 분리
- **연도별 페이지 → 단일 통합 DB** 구조 (단순)
- Claude Code 구독만으로 동작 (별도 Anthropic API 키 불필요)
- Notion 무료 플랜에서도 동작
- 기존 `exporters.notion` config 재사용

### 1.2 Design Principles

- **Claude는 의미 분석만, CLI는 기계 처리만** — 역할 분리
- **무료 path 우선** — 외부 의존성 최소화
- **소프트 멱등** — 실수로 두 번 눌러도 데이터 깨지지 않음

### 1.3 Non-Goals

- 자동 push (Stop Hook 통합) — 별도 단순 flat 모드(`exporters.notion`)가 담당
- Notion 페이지를 다시 markdown으로 sync — 단방향 export only
- 과거 markdown 일지 일괄 Notion 마이그레이션 — 별도 명령(`sync-notion`)으로 분리

---

## 2. Notion Structure

```
[루트 페이지]                          ← 사용자가 미리 만들고 page_id를 config에 등록
 ├─ 📄 2026                            ← 자동 생성 (연도)
 │   └─ 🗄️ Entries (인라인 DB)         ← 자동 생성 (연도당 1개)
 │       ├─ 행: 2026-05-26 / Project: claude-diary / ...
 │       ├─ 행: 2026-05-26 / Project: other-project / ...
 │       └─ 행: 2026-05-27 / ...
 ├─ 📄 2027                            ← 다음 해 첫 push 시 자동 생성
 │   └─ 🗄️ Entries
 │       └─ ...
```

### 2.1 왜 단일 DB + Project select?

**대안 — 프로젝트별 인라인 DB**:
- 새 프로젝트 시작할 때마다 DB 추가 생성 필요 (API 호출 ↑)
- DB가 늘어나면 캐시 키 복잡

**채택 — 단일 DB + Project (select)**:
- DB는 연도당 1개만 (한 번 만들면 끝)
- Notion에서 Project로 group/filter view 자유롭게 생성 가능
- 새 프로젝트 = select 옵션만 자동 추가 (Notion API가 처리)
- "오늘 여러 프로젝트 만진 거" 한눈에 보기 자연스러움

---

## 3. DB Schema

### 3.1 Layer 1 — Properties (DB 뷰에서 보이는 컬럼)

| 컬럼 | 타입 | 표시 | 값 예시 | 용도 |
|------|------|------|---------|------|
| Name | title | ✅ | "DB 컬럼 스키마 의논" | Claude가 뽑은 task 제목 |
| Date | date | ✅ | 2026-05-26 | 정렬/필터/캘린더 뷰 |
| Project | select | ✅ | claude-diary | group/filter |
| Branch | select | ✅ | feat/diary-notion | group/filter. CLI가 자동 채움 |
| Status | select | ✅ | Implementation | 5단계: Discussion/Design/Implementation/Testing/Deployed |
| Task Group | select | ✅ | diary-notion-impl | 큰 작업 단위 묶음. Claude가 추출 |
| Categories | multi_select | ✅ | design, notion | 작업 성격 |
| Files | number | ✅ | 7 | 수정+생성 파일 수 |
| Commits | number | ✅ | 3 | 커밋 개수 |
| Lines | number | ✅ | 142 | 추가+삭제 합 |
| Depends On | relation (self) | ✅ | → 다른 행 | 선행 작업 참조 (단방향) |
| Session ID | rich_text | 🔒 hidden | "abc-123-def" | 멱등성 키 |
| Task Index | number | 🔒 hidden | 0, 1, 2 | 멱등성 키 |

→ 표시 11개 + hidden 2개 = 총 13개. 의미 요약은 컬럼이 아닌 본문(`body_intro`)으로만 노출.

**Status 5단계 (select)**:
- `Discussion`: 의논만, 결정 미완 (드물게)
- `Design`: 결정/문서화 완료
- `Implementation`: 코드 작성 (commit 있음)
- `Testing`: 테스트 작성/검증 완료
- `Deployed`: 머지/배포까지 완료

한 task에 여러 단계가 섞이면 **가장 진행된 단계로**. Claude가 transcript 보고 판단.

**Task Group (select)**: 며칠/여러 세션에 걸치는 큰 작업 단위 묶음. Claude가 첫 task 시점에 새 그룹명 생성, 이전 작업의 연속이면 같은 그룹명 사용. 일관성 보장은 어렵지만 group view로 묶어 보는 편의가 핵심 가치.

**Depends On (self-relation, 단방향)**: 같은 DB 안의 다른 행 참조. JSON 스키마의 `depends_on_indices` 가 같은 push의 task index를 가리킴. CLI가 push 순서대로 row_id 누적 → 인덱스를 실제 row ID로 변환해서 relation 채움. Notion이 자동 reverse view 제공해 단방향 정의로 양방향 효과.

**Branch 컬럼 데이터 소스** (CLI 자동):
- task의 `commit_hashes` 있으면 → 첫 commit의 branch (`git branch --contains`)
- `commit_hashes` 없으면 → 현재 HEAD branch (`git rev-parse --abbrev-ref HEAD`)
- HEAD detached면 → fallback으로 commit hash 단편 또는 빈 값

### 3.2 Layer 2 — Page Body (행 클릭 시 보이는 markdown)

```markdown
[body_intro - Claude가 작성한 1~3문장 의미 요약]

## 사용자 요청
- "..."
- "..."

## 작업 요약
- ...
- ...

## 수정/생성 파일
- src/...
- src/...

## 실행한 명령
- git log --oneline
- ...

## Git 변경사항
**Branch**: main
- `abc1234` feat: ...
- `def5678` test: ...
- (lines: +142 / -38)

## 발생한 에러
(있을 때만 표시)
```

**조립**: Claude가 만든 `body_intro` 1~3문장 + CLI가 raw 데이터로 조립한 기계 섹션들.

---

## 4. JSON Schema (Slash Command → CLI)

```json
{
  "session_id": "abc-123-def",
  "tasks": [
    {
      "title": "Notion DB 컬럼 스키마 결정",
      "body_intro": "DB 컬럼을 Layer 1/2로 분리. 단일 통합 DB + Project select 채택. summary 컬럼은 본문 첫 문단(body_intro)으로 통합.",
      "status": "Design",
      "task_group": "diary-notion-impl",
      "depends_on_indices": [],
      "categories": ["design", "notion"],
      "project": "claude-code-hooks-diary",
      "user_prompts": ["DB 구조 의논하자", "name에는 날짜 말고..."],
      "files_modified": ["src/claude_diary/exporters/notion.py"],
      "files_created": [],
      "commands_run": ["git log --oneline -20"],
      "commit_hashes": ["abc1234"],
      "errors": []
    }
  ]
}
```

### 4.1 Claude의 책임 (슬래시 커맨드 instructions)

- transcript를 작업 단위로 분리
- 각 task의 `title` (30~50자 명사구), `body_intro` (1~3문장 평어체, 결과 중심)
- `categories` 추출
- `user_prompts`, `files_modified`, `files_created`, `commands_run`, `errors` 추출
- `commit_hashes`를 task에 매핑

### 4.2 CLI의 책임

- `commit_hashes`로 git 메타 수집 (message, lines, branch) — `git_info.py` 재사용
- task별 Branch 자동 결정 (commit 있으면 첫 commit의 branch, 없으면 HEAD branch)
- Layer 2 body markdown 조립 (`body_intro` + raw 섹션) — `formatter.py` 확장
- 연도 페이지/DB 자동 생성 (없으면)
- 행 추가 (멱등성 처리 포함)
- 캐시 갱신

### 4.3 JSON 전달 방식 — 임시 파일 via cwd

**선택**: Claude가 cwd에 임시 JSON 파일을 작성 → CLI에 `--input` 으로 경로 전달.

```
1. Claude: Write 도구로 cwd에 `.diary-notion-<short-id>.json` 작성
2. !`claude-diary notion-push --input .diary-notion-<short-id>.json`
3. CLI: 파일 read → push → try/finally로 파일 삭제 (성공/실패 무관)
4. (보험) 슬래시 커맨드 마지막에서 한 번 더 삭제 시도
```

**stdin 방식을 안 쓴 이유**: PowerShell은 `<<<` here-string 미지원. heredoc 문법도 bash와 다름 (`@'...'@`). cross-platform 호환을 위해 임시 파일이 안전.

**보안**:
- JSON에 token 등 secret 없음 (token은 CLI가 config에서 직접 read)
- transcript 데이터 자체는 `secret_scanner.py` 가 push 전에 마스킹
- 파일명에 `session_id` 단편 박아 충돌/추측 방지
- 사용자 프로젝트 `.gitignore`에 `.diary-notion-*.json` 패턴 추가 권장 (README에 안내)

---

## 5. Flow

```
[사용자]
  /diary-notion 입력
       │
       ▼
[Claude (현재 세션)]                              ── Claude Code 구독으로 동작
  ├─ transcript 분석
  ├─ 작업 단위 N개 분리
  ├─ 각 task: title / body_intro / summary / categories / prompts / files / commands / commit_hashes
  └─ JSON 생성
       │
       ▼  !`claude-diary notion-push --stdin`
[CLI: notion-push 명령]
  ├─ JSON 파싱
  ├─ commit_hashes → git_info.py로 메타+lines 수집
  ├─ Notion API 호출:
  │   ├─ 캐시 확인: 연도 페이지 / DB ID
  │   ├─ 없으면 생성:
  │   │   ├─ 연도 페이지: POST /pages (parent=root_page_id)
  │   │   └─ DB: POST /databases (parent=year_page_id, schema=10 columns)
  │   ├─ 각 task:
  │   │   ├─ 쿼리: Session ID + Task Index 매치 행 있나?
  │   │   ├─ 있으면 skip (--force면 archive 후 재생성)
  │   │   └─ 없으면 POST /pages (parent=db_id, properties+body)
  │   └─ 캐시 갱신
  └─ 결과 출력
```

---

## 6. Configuration

### 6.1 기존 config 확장

```json
{
  "exporters": {
    "notion": {
      "enabled": false,                ← Stop Hook 자동 push (별도)
      "api_token": "secret_xxx",
      "database_id": "...",            ← 기존 flat 모드용 (legacy)
      "root_page_id": "abc-123",       ← 신규: hierarchical용
      "mode": "hierarchical"           ← 신규: "flat" | "hierarchical"
    }
  }
}
```

- `enabled` flag는 자동 hook용. **`/diary-notion`은 enabled 무관하게 동작** (api_token + root_page_id만 있으면)
- 한 사용자가 두 모드 다 쓸 일은 거의 없지만, 기존 사용자 호환성 위해 둘 다 둠

### 6.2 환경변수 fallback

- `CLAUDE_DIARY_NOTION_TOKEN`
- `CLAUDE_DIARY_NOTION_ROOT_PAGE_ID`

### 6.3 Setup Command — `claude-diary notion init`

대화형 셋업 명령. 처음 사용자가 한 번만 실행.

**흐름**:
```
$ claude-diary notion init

Step 1/3: Integration token
  Get it from: https://www.notion.so/my-integrations
  Token (secret_...): █

Step 2/3: Root page URL or ID
  Paste full Notion URL or page ID:
  > https://www.notion.so/Working-Diary-abc123def456...
  ✓ Parsed page_id: abc123def456

Step 3/3: Verifying access...
  ✓ Token valid (GET /v1/users/me)
  ✓ Integration can read root page (GET /v1/blocks/{id})

Saved to: <config_dir>/config.json
  exporters.notion.api_token = secret_***
  exporters.notion.root_page_id = abc123def456
  exporters.notion.mode = hierarchical
```

**URL 파싱**: Notion URL 끝의 32자 hex (대시 유무 모두) 정규식 추출. plain page_id 입력도 그대로 통과.

**Write 권한 검증 정책**: 검증 안 함 (실제로 child page 생성 시도는 부작용. read 권한 OK면 write도 따라옴). 첫 push에서 실패하면 그때 안내.

**실패 시 안내**:
- 401: "Token이 잘못되었어요. https://www.notion.so/my-integrations 에서 다시 확인하세요"
- 404: "페이지에 Integration을 공유했나요? 페이지 우상단 ⋯ → Connections → Integration 추가"

---

## 7. Caching

### 7.1 캐시 파일

`<config_dir>/notion-cache.json`:

```json
{
  "root_page_id": "abc-123",
  "years": {
    "2026": "page_id_2026"
  },
  "databases": {
    "2026": "db_id_xxx"
  },
  "rows": {
    "abc-123-def:0": "row_page_id_1",
    "abc-123-def:1": "row_page_id_2"
  }
}
```

- 키 `rows`의 형식: `<session_id>:<task_index>` → Notion 행 page_id
- 캐시 miss 시 → Notion 검색 → 캐시 갱신
- Notion에서 사용자가 삭제 → 다음 호출 시 API 404 → 캐시 무효화 후 재생성

---

## 8. Idempotency

### 8.1 기본: Soft Idempotency (skip)

- push 직전 `query DB where Session_ID=X and Task_Index=Y`
- 매치되면 skip, 없으면 새 행 추가
- 같은 세션 두 번 push: 첫 push의 행은 그대로, 새로 추가된 task만 push

### 8.2 `--force`: Archive & Recreate

- 같은 `session_id`의 모든 행을 archive (Notion API의 `archived: true`)
- 그 다음 모든 task를 새로 push
- 진짜 upsert (block-level update)는 복잡해서 채택 안 함

---

## 9. Decisions & Trade-offs

| # | 결정 | 채택 | 이유 |
|---|------|------|------|
| 1 | 계층 구조 | A: 연도 → Entries DB → 행 | 연말 회고 자료로 한 페이지에 다 보임 |
| 2 | DB 분리 | 단일 DB + Project select | 새 프로젝트마다 DB 생성 X. Notion view로 분류 |
| 3 | DB 컬럼 | 8개 표시 + 2개 hidden | 답답하지 않으면서 멱등성 키 확보 |
| 4 | 작업 분리 | LLM (옵션 3: 슬래시 커맨드 안의 Claude) | API 키 X, 의미 단위 분리 가능 |
| 5 | LLM 호출 위치 | 슬래시 커맨드 = 현재 세션의 Claude | Claude Code 구독으로 무료. SDK 의존성 X |
| 6 | 본문 markdown | C: Claude의 intro + CLI의 raw 섹션 | 의미 정리 + 일관성 동시 확보 |
| 7 | git 정보 수집 | A: CLI가 자체 수집 | 정확도 ↑, `git_info.py` 재사용 |
| 8 | 멱등성 | B + `--force`: skip 기본, force는 archive&recreate | 실수 방지 + 강제 갱신 옵션 |
| 9 | 셋업 흐름 | B: `notion init` 대화형 명령 + URL 파싱 + token/read 검증 | 첫 인상 비용 ↓, page_id 헷갈림 해결, 권한 디버깅 비용 ↓ |
| 10 | 작업 분리 우선순위 | B: Semantic-first (의미 단위) | 의논 세션도 풍부, 큰 commit 안 묶임, Claude 정리 능력 활용 |
| 11 | Title 형식 | 명사구, 30~50자, 시제/주어/prefix/마침표 없음 | DB 뷰 한 줄에 들어감. 일관성 |
| 12 | Body intro 톤 | 평어체, 1~3문장, 결과 중심, markdown 강조 OK, 추측 금지 | 글로벌 지침과 일관. 회고 시 빠른 회상 |
| 13 | summary 컬럼 | 삭제 — `body_intro` 만 유지 | 사용자가 본문 위주로 보기 때문. 중복 제거 |
| 14 | JSON 전달 방식 | 임시 파일 (cwd, `.diary-notion-<id>.json`) | PowerShell 호환. escape 문제 회피. 디버깅 쉬움 |
| 20 | Status 컬럼 | select, 5단계 (Discussion/Design/Implementation/Testing/Deployed) | 진행도 시각화. 한 task 안에 여러 단계 섞이면 가장 진행된 단계 |
| 21 | Depends On 컬럼 | self-relation, 단방향 | 작업 순서 시각화. Notion이 reverse view 자동 제공 |
| 22 | Task Group 컬럼 | select. Claude가 task별로 추출 | 며칠/여러 세션에 걸치는 큰 작업을 group view로 묶기 |
| 23 | 멱등성 + 새 컬럼 마이그레이션 | 기존 행 archive(`--force`) 후 새 스키마로 재push | Status/Depends On/Task Group 소급 채움 |
| 15 | Branch 컬럼 추가 + 경계 룰 | Branch select 컬럼 + "branch 다르면 task 분리"를 최우선 분리 룰로 | 한 task = 한 branch 보장. select 컬럼이 의미 있어짐. 여러 branch 섞이는 케이스 자동 해결 |
| 16 | Error 종류별 분기 | 401/403 fail fast, 400 skip, 429/5xx retry, 404 자동 재생성 | 의미 없는 retry 방지. 캐시 일관성 자동 복구 |
| 17 | Retry 정책 | 인라인 retry 3회 (exponential backoff) + JSON 파일 보존 | 수동 명령에 동기적 보고. queue 안 씀 |
| 18 | 캐시 무효화 | Lazy (404 응답 시) | 정상 path 빠름 |
| 19 | 부분 실패 | Continue + 종합 보고 (`Pushed N, skipped M, failed K`) | 행 단위 독립 |

---

## 10. Slash Command Instructions (확정)

`~/.claude/commands/diary-notion.md` 본문 초안:

```markdown
---
description: 현재 세션을 작업 단위로 분리해 Notion 업무일지 DB에 push
allowed-tools:
  - Bash
  - Read
  - Write
---

# /diary-notion

현재 세션의 transcript와 git 정보를 분석하여 Notion 업무일지 DB에 push.

## 단계

1. **컨텍스트 수집**
   - 이 세션의 user 메시지, 너의 응답, 호출한 도구 검토
   - `git log` 로 이 세션 중 만든 commit 조회 (시간 추정 OK)

2. **작업 단위 분리 (Branch 경계 → Semantic-first)**
   - **branch 경계 최우선**: 세션 중 `git switch`로 branch가 바뀌면 무조건 새 task로 분리
   - 같은 branch 안에서는 **의미 단위로 분리** (사고 흐름 = task)
   - 한 commit이 여러 의미 단위에 걸치면 양쪽 task에 같은 hash 매핑
   - 큰 commit("fix: 5건 개선" 같은) 한 번에 묶지 말고 의미별로 분리
   - 짧은 follow-up("ㅇㅇ", "맞아")은 직전 task에 흡수
   - **commit이 0개인 의논 세션도 정상** — 의미 단위로 task N개 생성

3. **각 task별 추출**
   - `title`: 30~50자 명사구. 시제/주어/prefix/마침표 없음
     - ✅ "Notion DB 컬럼 스키마 결정", "git_info.py 리팩토링"
     - ❌ "오늘 DB 의논했다", "[설계] DB 컬럼"
   - `body_intro`: 1~3문장, 200~500자, 평어체, 결과 중심
     - transcript에 없는 내용 추가 금지 (추측 X)
     - markdown 강조(`**굵게**`, `` `코드` `` ) 사용 OK
   - `categories`: 1~3개. design/refactor/bugfix/test/docs/infra/discussion 같은 자유 라벨
   - `project`: 현재 cwd의 폴더명
   - `user_prompts`, `files_modified`, `files_created`, `commands_run`, `errors`
   - `commit_hashes`: 이 task에 해당하는 commit (0개도 OK)

4. **JSON 출력 및 CLI 호출**
   - cwd에 `.diary-notion-<8자리>.json` 작성 (Write 도구)
   - `!claude-diary notion-push --input .diary-notion-<8자리>.json` 실행
   - 종료 후 파일 삭제

## JSON 형식

JSON Schema는 design 문서 Section 4 참고.

## 빈 결과 처리

tasks 가 0개라면 (transcript에 의미 있는 작업 없음) 사용자에게 이유 설명하고 CLI 호출 없이 종료.

## 사용자 보고

CLI 결과를 그대로 보여주고 push/skip된 task 요약.
```

---

## 11. Open Questions (TBD)

모든 설계 결정 완료. 다음 단계 = 구현.

---

## 11. Reuse vs New Code

### 11.1 재사용

- `exporters/base.py` `BaseExporter` 인터페이스
- `exporters/notion.py` `NotionExporter` (flat 모드는 그대로, mode 분기 추가)
- `lib/git_info.py` commit 메타 수집
- `lib/secret_scanner.py` 시크릿 마스킹
- `formatter.py` 본문 markdown 조립 (확장)
- `cli/setup.py` 슬래시 커맨드 install/uninstall 패턴

### 11.2 신규

- `cli/notion_push.py` — `claude-diary notion-push --stdin` 명령
- `exporters/notion.py` 안에 `_hierarchical_export()` 추가 (또는 `NotionHierarchicalExporter` 클래스 분리)
- `lib/notion_cache.py` — 캐시 read/write
- `~/.claude/commands/diary-notion.md` — 슬래시 커맨드 instructions
- `tests/test_notion_push.py`
- `tests/test_notion_cache.py`

---

## 12. Compatibility & Migration

- 기존 `exporters.notion` (flat 모드) 사용자는 영향 없음 — `mode` 키 없으면 flat 동작
- 기존 Stop Hook 자동 push는 그대로 동작
- `/diary-notion`은 신규 사용자가 추가 셋업해야 사용 가능 (`root_page_id` 등록)

---

## 13. Security

- `api_token`은 config.json 평문 저장 (기존과 동일)
- 셋업 가이드에 "config.json 공유/커밋 금지" 강조 필요
- secret_scanner가 push 전에 entry_data를 마스킹 (기존 로직 재사용)
