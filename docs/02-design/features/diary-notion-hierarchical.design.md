# /diary-notion — Hierarchical Notion Export

> **Summary**: 슬래시 커맨드로 현재 세션을 작업 단위로 분리하여 Notion DB에 push (업무일지 자동화)
>
> **Project**: claude-code-hooks-diary
> **Date**: 2026-05-26
> **Status**: Draft (설계 의논 중)

> 상위 비전: [`working-diary-os.vision.md`](working-diary-os.vision.md)

## Executive Summary

| 관점 | 내용 |
|------|------|
| **Problem** | 기존 NotionExporter는 단순 flat DB push만 가능. 세션 1개 = 행 1개. 업무일지로 보기에 부적합 |
| **Solution** | `/diary-notion`(Claude) / `$diary-notion`(Codex) — 에이전트가 세션을 작업 단위로 분리 → 연도별 페이지/단일 DB로 push |
| **Core Value** | 별도 LLM API 키 없이 현재 에이전트 세션 컨텍스트로 업무일지 자동화 |

---

## 1. Overview

### 1.1 Design Goals

- 한 세션의 작업을 **의미 단위로 N개 행**으로 분리
- **연도별 페이지 → 단일 통합 DB** 구조 (단순)
- Claude Code/Codex 세션 컨텍스트만으로 동작 (별도 LLM API 키 불필요)
- Notion 무료 플랜에서도 동작
- 기존 `exporters.notion` config 재사용

### 1.2 Design Principles

- **에이전트는 의미 분석만, CLI는 기계 처리만** — 역할 분리
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
| Name | title | ✅ | "DB 컬럼 스키마 의논" | 에이전트가 뽑은 task 제목 |
| Date | date | ✅ | 2026-05-26 | 정렬/필터/캘린더 뷰 |
| Project | select | ✅ | claude-diary | group/filter. task JSON 누락/unknown 시 CLI가 cwd 폴더명으로 보정 |
| Purpose | select | ✅ | Feature | 목적별 group/filter |
| Branch | select | ✅ | feat/diary-notion | group/filter. CLI가 자동 채움 |
| Status | select | ✅ | Implementation | 5단계: Discussion/Design/Implementation/Testing/Deployed |
| Task Group | select | ✅ | diary-notion-impl | 큰 작업 단위 묶음. 에이전트가 추출 |
| Categories | multi_select | ✅ | design, notion | 작업 성격 |
| Files | number | ✅ | 7 | 수정+생성 파일 수 |
| Commits | number | ✅ | 3 | 커밋 개수 |
| Lines | number | ✅ | 142 | 추가+삭제 합 |
| Parent Task | relation (self) | ✅ | → 상위 행 | 포함 관계. 하위항목/sub-item view 자동화의 기반 |
| Depends On | relation (self) | ✅ | → 선행 행 | 선행 작업 참조 (단방향) |
| Session ID | rich_text | 🔒 hidden | "abc-123-def" | 멱등성 키 |
| Task Index | number | 🔒 hidden | 0, 1, 2 | 멱등성 키 |

→ 표시 13개 + hidden 2개 = 총 15개. 의미 요약은 컬럼이 아닌 compact body(`body_intro` + callout/checklist/toggle 부록)로 노출.

2차 View 설계에서는 이 v4 모델을 확장해 `Work Period` date range 컬럼을 추가하는 schema v5를 사용한다. `Date`는 기록일로 유지하고, `Work Period`는 프로젝트/작업 그룹의 실제 작업 기간 계산 재료로 사용한다.

**Purpose (select)**:
- 영어 enum 사용: `Feature`, `Bugfix`, `Refactor`, `Docs`, `Test`, `Infra`, `Planning`, `Research`, `Review`, `Release`, `Support`, `Maintenance`, `General`
- Notion에서 목적별 필터/그룹을 보장하는 1차 분류. 자동 view 생성은 후속 단계로 분리.

**Status 5단계 (select)**:
- `Discussion`: 의논만, 결정 미완 (드물게)
- `Design`: 결정/문서화 완료
- `Implementation`: 코드 작성 (commit 있음)
- `Testing`: 테스트 작성/검증 완료
- `Deployed`: 머지/배포까지 완료

한 task에 여러 단계가 섞이면 **가장 진행된 단계로**. 에이전트가 세션 컨텍스트를 보고 판단.

**Task Group (select)**: 며칠/여러 세션에 걸치는 큰 작업 단위 묶음. 에이전트가 첫 task 시점에 새 그룹명 생성, 이전 작업의 연속이면 같은 그룹명 사용. 일관성 보장은 어렵지만 group view로 묶어 보는 편의가 핵심 가치.

**Parent Task (self-relation)**: 포함 관계. 예: `상품 목록 포커싱`의 Parent Task는 `로컬 테스트 진행`. 같은 push 안에서는 JSON의 `parent_index`를 row ID로 변환해 연결한다. 너무 작은 확인 항목은 별도 row가 아니라 본문 checklist로 남긴다.

**Depends On (self-relation, 단방향)**: 같은 DB 안의 다른 행 참조. JSON 스키마의 `depends_on_indices` 가 같은 push의 task index를 가리킴. CLI가 push 순서대로 row_id 누적 → 인덱스를 실제 row ID로 변환해서 relation 채움. Notion이 자동 reverse view 제공해 단방향 정의로 양방향 효과.

**Branch 컬럼 데이터 소스** (CLI 자동):
- task의 `commit_hashes` 있으면 → 첫 commit의 branch (`git branch --contains`)
- `commit_hashes` 없으면 → 현재 HEAD branch (`git rev-parse --abbrev-ref HEAD`)
- HEAD detached면 → fallback으로 commit hash 단편 또는 빈 값

### 3.2 Layer 2 — Page Body (행 클릭 시 보이는 markdown)

```markdown
[callout] body_intro - 핵심 결과 1개. callout은 여기와 경고성 리스크에만 제한한다.

## 결과
- [x] 최종 결과
- [x] 검증 완료 항목
- [x] 커밋/푸시/배포 등 완료 상태

## 작업 한눈에
| 항목 | 내용 |
| --- | --- |
| 배경 | 왜 시작했는가 |
| 범위 | 무엇을 바꿨는가 |
| 접근 | 어떻게 풀었는가 |
| 결과 | 어떤 상태가 되었는가 |

## 영향
- 사용자/운영/제품/개발 품질 영향

## 검증
- [x] 최종 검증 결과

## 리스크 / 다음 액션
[callout] 필요한 경우에만 남은 리스크
- [ ] 후속 작업

## 부록
[toggle] 개발 근거: 주요 변경, 주요 코드 변경, 파일, 명령어, Git, 이슈
[toggle] 원문 요청: user_prompts 원문
```

문제 해결형 작업은 `결과` 섹션을 다음 형태로 우선 렌더링할 수 있다.

```markdown
## 결과

- 문제: 정상 생성된 view가 required property 누락 conflict로 오인됨
- 원인: data source schema와 view retrieve 응답의 property id encoding 기준이 다름
- 조치: property id를 decode해 비교 기준을 통일
- 결과: core view 5개 verified
```

**조립**: 에이전트가 만든 `body_intro`, `summary_hints`, `key_changes`, `work_context`, `work_scope`, `approach`, `outcome`, `impact`, `decisions`, `implementation_notes`, `verification`, `risks`, `next_steps`, `support_needed` + CLI가 코드/파일/명령/Git raw 데이터를 접힌 부록(toggle)으로 조립한다. 코드 변경은 full diff가 아니라 주요 변경만 기록한다.

**언어 정책**: `title`과 설명형 본문 필드(`body_intro`, `summary_hints`, `key_changes`, `work_context`, `work_scope`, `approach`, `outcome`, `impact`, `decisions`, `implementation_notes`, `verification`, `risks`, `next_steps`, `support_needed`)는 한국어로 작성한다. 파일 경로, 명령어, branch, commit hash, 코드 식별자, 함수/클래스명, `Purpose`/`Status` enum 값은 원문 또는 영어 값을 유지한다.

**본문 보고 원칙**:
- DB relation이 구조를 담당하고, page body는 짧은 상태와 근거를 담당한다.
- `결과`, `작업 한눈에`, `영향`, `검증`, `리스크 / 다음 액션`, `부록` 순서로 배치한다.
- callout을 과하게 쓰지 않는다. 최상단 핵심 요약 1개와 경고성 리스크 정도로 제한한다.
- `작업 한눈에`는 callout 여러 개가 아니라 표로 렌더링한다.
- 검증은 최종 상태를 우선 노출하고, 중간 실행 결과는 부록으로 내린다.
- 사용자-facing 명령은 `$diary-notion` 또는 `working-diary diary-notion ...` 기준으로 노출한다.
- 과거 명령이나 내부 명령은 발생 근거가 필요할 때만 부록에 둔다.
- 주요 코드 변경과 파일/명령/Git/오류는 핵심 메시지가 아니라 근거이므로 접힌 `부록`에 둔다.
- Notion API child block 100개 제한을 넘지 않도록 렌더링 한도를 보수적으로 둔다.

---

## 4. JSON Schema (Slash Command → CLI)

```json
{
  "session_id": "abc-123-def",
  "tasks": [
    {
      "title": "Notion DB 컬럼 스키마 결정",
      "body_intro": "DB 컬럼을 Layer 1/2로 분리. 단일 통합 DB + Project select 채택. summary 컬럼은 본문 첫 문단(body_intro)으로 통합.",
      "summary_hints": ["Project/Purpose/Task Group 기준으로 필터 가능한 DB 구조를 확정"],
      "key_changes": ["Project/Purpose/Task Group 기준 필터와 그룹을 컬럼으로 보장"],
      "work_context": ["프로젝트/목적별로 작업을 찾기 어렵던 기존 flat DB 구조를 개선하기 위해 시작"],
      "work_scope": ["Notion DB 컬럼과 본문 렌더링 정책을 함께 정리"],
      "approach": ["컬럼은 필터/그룹/관계 구조를 담당하고 본문은 compact body로 읽히게 분리"],
      "outcome": ["행 하나만 열어도 작업 배경, 영향, 검증, 후속 조치를 파악할 수 있게 됨"],
      "impact": ["상사 보고와 개발자 회고에 모두 쓸 수 있는 단일 작업 문서가 됨"],
      "code_change_highlights": ["`formatter.py`: Notion page body에 주요 변경/검증/리스크 섹션을 선택 렌더링"],
      "decisions": ["view 자동화는 후속 단계로 분리"],
      "implementation_notes": ["단순 파일 목록보다 개발자가 이어서 볼 수 있는 작업 기록을 우선"],
      "verification": ["formatter 단위 테스트로 섹션 렌더링 검증"],
      "risks": ["기존 설치된 slash command/skill은 force refresh 전까지 예전 지시문을 사용할 수 있음"],
      "next_steps": ["사용자 환경에 최신 Codex skill 설치"],
      "support_needed": [],
      "status": "Design",
      "task_group": "diary-notion-impl",
      "purpose": "Planning",
      "parent_index": null,
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

### 4.1 에이전트의 책임 (Claude slash command / Codex skill instructions)

- transcript를 작업 단위로 분리
- 각 task의 `title` (30~50자 명사구), `body_intro` (1~3문장 평어체, 결과 중심), `summary_hints`/`key_changes`/`code_change_highlights`/`decisions`/`implementation_notes`/`verification`/`risks`/`next_steps`, `parent_index`/`depends_on_indices`
- `categories` 추출
- `user_prompts`, `files_modified`, `files_created`, `commands_run`, `errors` 추출
- `commit_hashes`를 task에 매핑

### 4.2 CLI의 책임

- `commit_hashes`로 git 메타 수집 (message, lines, branch) — `git_info.py` 재사용
- task별 Project 자동 보정 (task `project`가 없거나 `unknown`/placeholder이면 명령 실행 cwd 폴더명 사용)
- task별 Branch 자동 결정 (commit 있으면 첫 commit의 branch, 없으면 HEAD branch)
- Layer 2 body 조립 (`body_intro` + callout/checklist/toggle 부록) — `formatter.py` 확장
- 연도 페이지/DB 자동 생성 (없으면)
- 행 추가 (멱등성 처리 포함)
- 캐시 갱신

### 4.3 JSON 전달 방식 — 임시 파일 via cwd

**선택**: 에이전트가 cwd에 임시 JSON 파일을 작성 → CLI에 `--input` 으로 경로 전달.

```
1. 에이전트: cwd에 `.diary-notion-<short-id>.json` 작성
2. !`claude-diary notion push --input .diary-notion-<short-id>.json`
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
[Agent (현재 세션)]                               ── Claude Code/Codex 세션 컨텍스트로 동작
  ├─ transcript 분석
  ├─ 작업 단위 N개 분리
  ├─ 각 task: title / body_intro / summary_hints / key_changes / work_context / work_scope / approach / outcome / impact / code_change_highlights / decisions / implementation_notes / verification / risks / next_steps / support_needed / parent_index / depends_on_indices / categories / prompts / files / commands / commit_hashes
  └─ JSON 생성
       │
       ▼  !`claude-diary notion push --input .diary-notion-<id>.json`
[CLI: notion push 명령]
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
| 4 | 작업 분리 | 현재 에이전트 세션의 LLM | API 키 X, 의미 단위 분리 가능 |
| 5 | LLM 호출 위치 | Claude slash command 또는 Codex skill | 별도 SDK 의존성 X |
| 6 | 본문 markdown | C: 에이전트의 intro + CLI의 raw 섹션 | 의미 정리 + 일관성 동시 확보 |
| 7 | git 정보 수집 | A: CLI가 자체 수집 | 정확도 ↑, `git_info.py` 재사용 |
| 8 | 멱등성 | B + `--force`: skip 기본, force는 archive&recreate | 실수 방지 + 강제 갱신 옵션 |
| 9 | 셋업 흐름 | B: `notion init` 대화형 명령 + URL 파싱 + token/read 검증 | 첫 인상 비용 ↓, page_id 헷갈림 해결, 권한 디버깅 비용 ↓ |
| 10 | 작업 분리 우선순위 | B: Semantic-first (의미 단위) | 의논 세션도 풍부, 큰 commit 안 묶임, 에이전트 정리 능력 활용 |
| 11 | Title 형식 | 명사구, 30~50자, 시제/주어/prefix/마침표 없음 | DB 뷰 한 줄에 들어감. 일관성 |
| 12 | Body intro 톤 | 평어체, 1~3문장, 결과 중심, markdown 강조 OK, 추측 금지 | 글로벌 지침과 일관. 회고 시 빠른 회상 |
| 13 | summary 컬럼 | 삭제 — 의미 요약은 compact body 섹션으로 유지 | 컬럼 중복 없이 요약/상태/검증/근거를 page body에 남김 |
| 14 | JSON 전달 방식 | 임시 파일 (cwd, `.diary-notion-<id>.json`) | PowerShell 호환. escape 문제 회피. 디버깅 쉬움 |
| 20 | Status 컬럼 | select, 5단계 (Discussion/Design/Implementation/Testing/Deployed) | 진행도 시각화. 한 task 안에 여러 단계 섞이면 가장 진행된 단계 |
| 21 | Depends On 컬럼 | self-relation, 단방향 | 작업 순서 시각화. Notion이 reverse view 자동 제공 |
| 22 | Parent Task 컬럼 | self-relation, 단방향 | 포함 관계를 DB에 보존하고 후속 sub-item view 자동화의 기반으로 사용 |
| 22 | Task Group 컬럼 | select. 에이전트가 task별로 추출 | 며칠/여러 세션에 걸치는 큰 작업을 group view로 묶기 |
| 23 | 멱등성 + 새 컬럼 마이그레이션 | 기존 행 archive(`--force`) 후 새 스키마로 재push | Status/Depends On/Parent Task/Task Group 소급 채움 |
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
   - 언어 정책:
     - `title`, `body_intro`, `summary_hints`, `key_changes`, `decisions`, `implementation_notes`, `verification`, `risks`, `next_steps` 같은 설명형 필드는 반드시 한국어로 작성
     - `status`, `purpose` enum 값은 지정된 영어 값을 그대로 사용
     - 파일 경로, 명령어, branch, commit hash, 코드 식별자, 함수/클래스명은 원문 그대로 유지
     - `user_prompts`는 사용자가 말한 원문을 증거로 보존
   - `title`: 30~50자 명사구. 시제/주어/prefix/마침표 없음
     - ✅ "Notion DB 컬럼 스키마 결정", "git_info.py 리팩토링"
     - ❌ "오늘 DB 의논했다", "[설계] DB 컬럼"
   - `body_intro`: 1~3문장, 200~500자, 평어체, 결과 중심
     - transcript에 없는 내용 추가 금지 (추측 X)
     - markdown 강조(`**굵게**`, `` `코드` `` ) 사용 OK
   - Notion 작업 DB 기록처럼 작성. 구조는 DB relation으로 남기고, 본문은 중복 없이 간결하게 쓸 것
   - `summary_hints`: 작업 결과/의미 요약 최대 4개. 단순 파일 나열이 아니라 무엇이 달라졌는지 기록
   - `key_changes`: 개발자가 이 일지만 봐도 흐름을 이해할 수 있는 주요 변경사항 최대 4개
   - `work_context`: 왜 이 작업을 시작했는지 0~1개
   - `work_scope`: 무엇을 바꿨는지 0~1개
   - `approach`: 어떻게 해결했는지 0~1개
   - `outcome`: 결과가 무엇인지 0~1개
   - `impact`: 사용자/운영/제품/개발 품질 영향 0~4개
   - `code_change_highlights`: 실제 코드 변화 중 중요한 것만 0~5개
     - 파일/함수/명령 단위 + 동작상 의미를 함께 기록
     - full diff, 단순 포맷팅, import 정리, 문구 수정, fixture 보정은 제외
     - 동작/스키마/CLI/사용자 흐름/검증 범위가 바뀐 코드는 포함
   - `decisions`: 사용자가 결정했거나 구현 중 확정한 선택지/트레이드오프 0~3개
   - `implementation_notes`: 코드 변경 요약에 넣기 애매한 제약/호환성/마이그레이션 메모 0~4개
   - `verification`: 실행한 테스트, 검증 결과, 검증하지 못한 이유 0~4개
   - `risks`: 주의사항, 남은 리스크, 운영/사용 시 헷갈릴 수 있는 점 0~3개
   - `next_steps`: 남은 작업이나 후속 단계 0~3개
   - `support_needed`: 필요한 결정/지원이 있으면 0~2개
   - `status`: `Discussion` / `Design` / `Implementation` / `Testing` / `Deployed`
   - `purpose`: `Feature` / `Bugfix` / `Refactor` / `Docs` / `Test` / `Infra` / `Planning` / `Research` / `Review` / `Release` / `Support` / `Maintenance` / `General`
   - `task_group`: 며칠/여러 세션에 걸치는 큰 작업 단위 식별자
   - `depends_on_indices`: 같은 push 안에서 의존하는 선행 task 인덱스 배열
   - `categories`: 1~3개. design/refactor/bugfix/test/docs/infra/discussion 같은 자유 라벨
   - `project`: 현재 cwd의 폴더명
   - `user_prompts`, `files_modified`, `files_created`, `commands_run`, `errors`
   - `commit_hashes`: 이 task에 해당하는 commit (0개도 OK)

4. **JSON 출력 및 CLI 호출**
   - cwd에 `.diary-notion-<8자리>.json` 작성 (Write 도구)
   - `!claude-diary notion push --input .diary-notion-<8자리>.json` 실행
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

- `cli/notion_push.py` — `claude-diary notion push --input` 명령
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
