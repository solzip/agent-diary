# Diary Notion Phase 2 Implementation

> 2차 구현은 Notion 작업 DB를 단순 기록 저장소에서 작업 관리 화면으로 확장하는 단계다. 이 문서는 구현 내용을 단계별로 계속 누적하기 위한 README다.

## 목표

2차의 목표는 `$diary-notion`으로 쌓인 작업 row를 Notion 안에서 바로 탐색할 수 있게 만드는 것이다.

- schema v5로 `Work Period`를 보장한다.
- `working-diary diary-notion ensure` 명령으로 DB schema와 core views를 보장한다.
- 기존 push 경로는 안정성을 유지하고, view 자동화는 별도 명령으로 분리한다.
- 기존 Notion view와 row는 자동으로 덮어쓰지 않는다.
- conflict는 감지하고 보고하되, 사용자가 직접 수정하거나 후속 apply 단계에서 처리한다.

## 현재 구현 상태

| 항목 | 상태 | 내용 |
| --- | --- | --- |
| Schema v5 | 완료 | `Work Period` date 컬럼 추가 |
| Push 보강 | 완료 | 작업 row 생성 시 `Work Period` 기록 |
| Ensure CLI | 완료 | `working-diary diary-notion ensure`, `claude-diary diary-notion ensure` 지원 |
| Core Views | 완료 | 5개 core view 생성/검증 |
| Dry-run | 완료 | 생성/수정 없이 계획 출력 |
| Conflict 보고 | 완료 | 기존 view required 설정 mismatch 시 exit 1 |
| Subtasks fallback | 완료 | `작업 계층` sub-item 설정 실패 시 base table fallback |
| Relative today fallback | 완료 | `오늘 작업` relative today filter 실패 시 fixed date fallback |
| View 자동 수정 | 제외 | 2차 MVP에서는 기존 view를 자동 수정하지 않음 |

## 단계별 구현 기록

### Step 1. Schema v5 보장

`NotionHierarchicalExporter`의 schema 버전을 `v5`로 올리고 `Work Period` date 컬럼을 추가했다.

주요 내용:

- 기존 v4 DB는 `Work Period`만 patch한다.
- v3 DB는 `Parent Task`와 `Work Period`를 patch한다.
- v2 DB는 `Purpose`, `Parent Task`, `Work Period`를 patch한다.
- schema 기록이 없거나 오래된 DB는 현재 extension schema 전체를 patch한다.
- `diary-notion ensure`에서는 cache가 `v5`여도 schema patch를 강제로 한 번 보내 보장성을 높인다.

수정 파일:

- `src/claude_diary/exporters/notion_hierarchical.py`
- `tests/test_notion_hierarchical.py`

### Step 2. Work Period row 기록

`$diary-notion` push가 생성하는 각 작업 row에 `Work Period` 값을 넣도록 보강했다.

입력 규칙:

```json
{
  "work_period": "2026-06-02"
}
```

```json
{
  "work_period": {
    "start": "2026-06-01",
    "end": "2026-06-02"
  }
}
```

지원 형태:

- 값이 없으면 기록일 `Date`와 같은 날짜를 사용한다.
- `YYYY-MM-DD` 문자열을 지원한다.
- `YYYY-MM-DD..YYYY-MM-DD` 문자열 range를 지원한다.
- `{ "start": "...", "end": "..." }` 객체 range를 지원한다.

수정 파일:

- `src/claude_diary/cli/notion_push.py`
- `tests/test_notion_push.py`
- `skills/diary-notion/SKILL.md`
- `src/claude_diary/cli/setup.py`

### Step 3. Ensure CLI 추가

사용자 facing 명령은 하나로 유지한다.

```bash
working-diary diary-notion ensure
working-diary diary-notion ensure --year 2026
working-diary diary-notion ensure --dry-run
claude-diary diary-notion ensure
```

동작:

- 일반 실행은 year page, Entries DB, schema v5, core views를 보장한다.
- `--year`는 대상 연도를 명시한다.
- `--dry-run`은 생성/patch 없이 접근 가능한 현재 상태 기준으로 계획만 출력한다.
- DB가 없는 dry-run은 생성 계획만 출력하고 실제 Notion에는 쓰지 않는다.

수정 파일:

- `src/claude_diary/cli/__init__.py`
- `src/claude_diary/cli/notion_ensure.py`
- `tests/test_cli.py`
- `tests/test_notion_ensure.py`

### Step 4. Views API client 분리

기존 push 경로와 view 자동화 경로를 분리했다.

```text
NotionHierarchicalExporter
  Notion-Version: 2022-06-28
  역할: year page, Entries DB, schema, row, relation

NotionViewsClient
  Notion-Version: 2025-09-03
  역할: data source, property id map, view list/retrieve/create
```

분리 이유:

- push 경로는 이미 안정화된 기록 경로이므로 API version 변경 영향을 최소화해야 한다.
- Views API는 `2025-09-03` 이상이 필요하므로 별도 client가 맞다.
- view 생성 실패가 `$diary-notion` row 기록 실패로 이어지지 않게 한다.

수정 파일:

- `src/claude_diary/exporters/notion_views.py`
- `tests/test_notion_views.py`

### Step 5. Core Views 5개 생성/검증

2차 MVP에서 보장하는 core views:

| View | 목적 | Required 기준 |
| --- | --- | --- |
| 작업 계층 | 상위/하위 작업 탐색 | `Parent Task`, `Work Period` 표시 |
| 오늘 작업 | 오늘 기록한 수행분 확인 | `Date = today`, `Date desc`, `Work Period` 표시 |
| 상태별 | 진행 단계 확인 | `Status` group_by |
| 목적별 | 작업 성격별 확인 | `Purpose` group_by |
| 프로젝트별 | 프로젝트별 작업 확인 | `Project` group_by |

검증 원칙:

- 같은 이름의 view가 없으면 생성한다.
- 같은 이름의 view가 required 설정을 만족하면 verified 처리한다.
- 같은 이름의 view가 required 설정을 만족하지 않으면 자동 수정하지 않고 conflict로 보고한다.
- `Session ID`, `Task Index`는 hidden property로 유지한다.

검증 보정:

- Notion data source schema는 property id를 URL-encoded 형태로 반환할 수 있다.
- Notion view retrieve 응답은 같은 property id를 decoded 형태로 반환한다.
- 따라서 property id map 생성 시 id를 decode해 view 응답과 같은 기준으로 비교한다.
- 이 보정이 없으면 실제 view가 정상 생성되어도 dry-run에서 false conflict가 발생한다.

### Step 6. Best-effort fallback

두 가지는 core 성공 기준이 아니라 best-effort로 처리한다.

`작업 계층` subtasks fallback:

- 우선 `Parent Task` self-relation 기반 `subtasks` 설정을 포함해 생성한다.
- Notion API가 거절하면 `subtasks`를 제거한 base table view로 다시 생성한다.
- base table 생성이 성공하면 warning만 출력하고 exit 0을 유지한다.

`오늘 작업` relative today fallback:

- 우선 `Date equals today` relative filter로 생성한다.
- Notion API validation이 실패하면 실행일 기준 fixed date filter로 다시 생성한다.
- fixed date fallback이 성공하면 warning만 출력한다.

### Step 7. 문서와 설치 지시문 반영

사용자가 새 세션에서도 같은 구조를 만들 수 있도록 README와 skill 지시문을 갱신했다.

반영 내용:

- README에 `working-diary diary-notion ensure` 명령 추가
- README에 `Work Period` 컬럼 설명 추가
- Codex skill JSON 예시에 `work_period` 추가
- 설치용 embedded Codex skill에도 동일 지시문 반영
- CHANGELOG에 구현 항목 추가

수정 파일:

- `README.md`
- `README.en.md`
- `CHANGELOG.md`
- `skills/diary-notion/SKILL.md`
- `src/claude_diary/cli/setup.py`
- `tests/test_setup.py`
- `tests/test_codex_plugin.py`

## 검증

실행한 검증:

```bash
python -m pytest
```

결과:

```text
620 passed
```

컴파일 확인:

```bash
python -m compileall src
```

결과:

```text
passed
```

## 사용 방법

처음 또는 view/schema를 정리하고 싶을 때:

```bash
working-diary diary-notion ensure
```

특정 연도 DB를 보장할 때:

```bash
working-diary diary-notion ensure --year 2026
```

실제 변경 없이 계획만 볼 때:

```bash
working-diary diary-notion ensure --dry-run
```

작업 기록은 기존처럼 유지한다.

```bash
$diary-notion
```

## 운영 원칙

- `$diary-notion`은 작업 row 기록에 집중한다.
- `diary-notion ensure`는 DB schema와 core views 보장에 집중한다.
- view conflict는 자동 수정하지 않는다.
- 기존 row는 생성, 수정, 삭제하지 않는다.
- generated 대체 view를 자동으로 만들지 않는다.
- `--apply`, `--force`, `--plan`은 3차 이후 운영/지능화 단계에서 다룬다.

## 남은 작업

2차 이후 후보:

- 실제 Notion workspace에서 `working-diary diary-notion ensure --dry-run` 실행 결과 확인
- 실제 Notion workspace에서 `working-diary diary-notion ensure` 실행 후 core views 렌더링 확인
- `작업 그룹별` core follow-up view 추가 여부 결정
- view conflict를 더 자세히 설명하는 `--plan` 출력 설계
- 기존 수동 view를 보호하면서 system-managed view만 갱신하는 apply 모델 설계

## 관련 문서

- `docs/02-design/features/diary-notion-hierarchical.design.md`
- `docs/02-design/features/diary-notion-views.design.md`
- `docs/02-design/features/working-diary-os.vision.md`
