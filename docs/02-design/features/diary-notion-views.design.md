# /diary-notion Views — Core View Automation

> **Summary**: 1차에서 만든 Notion 작업 DB 구조를 실제 업무 관리 화면으로 탐색할 수 있도록 core views를 자동 보장한다.
>
> **Project**: claude-code-hooks-diary
> **Date**: 2026-06-02
> **Status**: Draft (설계 의논 중)

> 상위 비전: [`working-diary-os.vision.md`](working-diary-os.vision.md)
>
> 선행 설계: [`diary-notion-hierarchical.design.md`](diary-notion-hierarchical.design.md)

## Executive Summary

| 관점 | 내용 |
|------|------|
| **Problem** | 1차에서 `Parent Task`, `Depends On`, `Project`, `Purpose`, `Status` 등 구조화 컬럼을 만들었지만 Notion 사용자는 여전히 직접 view를 구성해야 한다. |
| **Solution** | `working-diary notion views ensure` 명령으로 기본 탐색 화면인 Core Views를 자동 생성/보장한다. |
| **Core Value** | 같은 작업 row를 계층, 오늘, 상태, 목적, 프로젝트 관점으로 즉시 탐색할 수 있게 한다. |

---

## 1. Core Views 원칙

Core Views는 모든 작업 row가 공통으로 가지는 DB 컬럼을 기준으로 제공하는 기본 화면이다.

MVP 5개 view는 임시가 아니라 최종 모델에서도 유지되는 core view다.

`작업 그룹별`은 2차 후속 core view로 둔다.

Blocked/stale/today-plan/weekly brief는 core가 아니라 3차 이후 운영/지능화 view로 분리한다.

### 1.1 왜 Core Views인가

2차 View 자동화는 화면을 많이 만드는 작업이 아니다. 1차에서 만든 공통 데이터 모델을 사용자가 실제로 탐색할 수 있게 만드는 최소 화면을 자동 보장하는 작업이다.

공통 데이터 모델:

```text
Name
Date
Work Period
Project
Purpose
Branch
Status
Task Group
Parent Task
Depends On
Categories
Files
Commits
Lines
Session ID
Task Index
```

Core Views는 이 공통 컬럼을 다른 질문으로 재배열한다.

```text
작업 계층 = 이 일은 어떤 큰 작업의 일부인가
오늘 작업 = 오늘 기록된 수행분은 무엇인가
상태별 = 어디까지 진행됐는가
목적별 = 어떤 성격의 일인가
프로젝트별 = 어느 프로젝트의 일인가
```

`Date`와 `Work Period`는 의미가 다르다.

```text
Date = 기록일. 오늘 작업 view의 기준
Work Period = 실제 작업 기간. 프로젝트/작업 그룹 산출물의 기간 계산 재료
```

---

## 2. 2차 MVP Scope

### 2.1 명령

```bash
working-diary notion views ensure
```

역할:

- 현재 연도 Entries DB와 schema v5를 보장한다.
- 현재 설정된 hierarchical Notion DB에 core view가 있는지 확인한다.
- 없는 view만 생성한다.
- 같은 이름의 view가 있으면 required 설정을 검사한다.
- required 설정을 충족하면 verified로 처리한다.
- required 설정이 맞지 않으면 기존 view를 자동 수정하지 않고 conflict로 보고한다.
- 기존 row는 생성/수정/삭제하지 않는다.
- 실패해도 `/diary-notion` 또는 `$diary-notion` push 기능에 영향을 주지 않는다.

### 2.2 MVP Required Core Views

2차 MVP에서 자동 보장할 view는 다음 5개다.

| View | 주 질문 | 기준 컬럼 |
|------|---------|-----------|
| 작업 계층 | 이 일은 어떤 큰 작업의 일부인가? | `Parent Task`, `Task Group` |
| 오늘 작업 | 오늘 기록된 수행분은 무엇인가? | `Date`, `Status` |
| 상태별 | 어디까지 진행됐는가? | `Status` |
| 목적별 | 어떤 성격의 일인가? | `Purpose` |
| 프로젝트별 | 어느 프로젝트의 일인가? | `Project`, `Work Period` |

### 2.3 Core Follow-up

`작업 그룹별`은 core follow-up으로 둔다.

| View | 주 질문 | 기준 컬럼 | 이유 |
|------|---------|-----------|------|
| 작업 그룹별 | 며칠/여러 세션에 걸친 큰 작업 흐름은 무엇인가? | `Task Group` | 최고모델에서는 중요하지만 MVP 5개보다 우선순위가 낮다. |

### 2.4 3차 이후로 미루는 View

다음 view는 core가 아니라 운영/지능화 view다.

| View | 단계 | 보류 이유 |
|------|------|-----------|
| 막힌 작업 | Phase 3 Operations | `Blocked` 컬럼과 blocked 계산 규칙이 필요하다. |
| 오래 방치된 작업 | Phase 3 Operations | stale 기준과 마지막 검토일 계산이 필요하다. |
| 검증 대기 | Phase 3 Operations | status와 verification 누락 규칙이 필요하다. |
| 오늘 우선순위 | Phase 4 Intelligence | 전날 todo/`next_steps`와 우선순위 scoring이 필요하다. |
| 주간 보고 | Phase 4 Intelligence | summary/review 생성 로직이 필요하다. |

---

## 3. View 정의

### 3.1 작업 계층

목적:

- `Parent Task` 기반으로 큰 작업과 하위 작업을 탐색한다.
- 1차에서 추가한 포함 관계를 사용자가 실제로 확인하게 한다.
- 메인 작업을 두고, 메인 작업을 수행하기 위한 세부 작업을 하위 항목으로 연결한다.

2차 MVP는 **하위 항목 데이터 구조**를 필수로 보장한다.

작업 계층 view는 메인 작업과 하위 작업의 `Parent Task` 관계를 반드시 노출한다.

Notion의 접기/펼치기 sub-item UI는 최종 목표이며, 2차에서는 API 지원 여부에 따라 best-effort로 활성화한다.

예시:

```text
Working Diary OS
  Notion 작업 계층 1차 구조 구현
  Working Diary OS 최고모델 비전 정리
  2차 View 설계
```

초기 표시 컬럼:

- `Name`
- `Status`
- `Project`
- `Purpose`
- `Task Group`
- `Parent Task`
- `Depends On`
- `Work Period`
- `Date`

정렬/그룹:

- `Parent Task` 컬럼 표시는 required다.
- `Work Period` 컬럼 표시는 required다.
- `subtasks` configuration 적용은 시도하되, Notion UI의 접기/펼치기 렌더링 성공은 best-effort다.
- sub-item UI 자동화가 API 제약으로 실패하면 `subtasks`를 제거한 base table view로 fallback한다.

필수 성공 기준:

- `작업 계층` view가 생성된다.
- `Parent Task` 컬럼이 표시된다.
- `Work Period` 컬럼이 표시된다.
- 메인 작업과 하위 작업의 포함 관계를 view에서 확인할 수 있다.

Best-effort 기준:

- Notion table의 접기/펼치기 sub-item UI를 활성화한다.
- sub-item UI 설정 실패 후 base table fallback이 성공하면 전체 `views ensure` 실패로 보지 않고 warning으로 보고한다.

실패 기준:

- fallback base table view까지 생성에 실패하면 core view 생성 실패로 보고 exit 1을 반환한다.

### 3.2 오늘 작업

목적:

- 오늘 기록된 작업을 빠르게 확인한다.
- 오늘 실제로 수행하고 `$diary-notion`으로 남긴 작업 row를 확인한다.
- 이후 `today-plan`이 제안하는 오늘 후보와 구분되는 기록용 기본 화면이다.

초기 기준:

```text
Date = today
Sort: Date desc
```

초기 표시 컬럼:

- `Name`
- `Status`
- `Project`
- `Purpose`
- `Task Group`
- `Work Period`
- `Parent Task`
- `Depends On`

주의:

- `오늘 작업`은 “오늘 해야 할 일”이 아니라 “오늘 기록된 작업”이다.
- 어제부터 이어진 작업을 오늘도 수행했다면 오늘 수행분을 새 row로 남긴다.
- 이어진 작업은 같은 `Task Group`을 사용해 여러 날짜의 수행분을 하나의 흐름으로 묶는다.
- 오늘 수행분을 `$diary-notion`으로 새로 기록하지 않았다면 `오늘 작업` view에는 나타나지 않는다.
- `Date`는 오늘로 기록하고, `Work Period`는 오늘 수행분의 실제 작업일 또는 작업 구간을 기록한다.
- 같은 push 안에서 메인 작업과 세부 작업이 함께 생성된 경우에는 `Parent Task`로 포함 관계를 연결한다.
- 과거 row를 찾아 cross-day `Parent Task` relation으로 자동 연결하는 것은 2차 MVP 범위가 아니며, 필요하면 후속 작업으로 분리한다.
- 2차 MVP에서는 “오늘 해야 할 작업 추천”까지 하지 않는다.
- 추천은 Phase 4 `today-plan`에서 처리한다.

예시:

```text
어제 row
Date = 2026-06-01
Work Period = 2026-06-01
Task Group = diary-notion-view-design

오늘 row
Date = 2026-06-02
Work Period = 2026-06-02
Task Group = diary-notion-view-design
```

### 3.3 상태별

목적:

- 작업이 Discussion, Design, Implementation, Testing, Deployed 중 어디에 있는지 확인한다.

그룹:

```text
Group by Status
```

초기 표시 컬럼:

- `Name`
- `Project`
- `Purpose`
- `Task Group`
- `Parent Task`
- `Work Period`
- `Date`

상태 순서:

```text
Discussion
Design
Implementation
Testing
Deployed
```

### 3.4 목적별

목적:

- Feature, Bugfix, Planning, Docs 등 작업 성격을 기준으로 회고/보고 관점을 제공한다.

그룹:

```text
Group by Purpose
```

초기 표시 컬럼:

- `Name`
- `Status`
- `Project`
- `Task Group`
- `Work Period`
- `Date`

활용:

- 주간 회고에서 구현/버그수정/문서/설계 비중을 확인한다.
- 상사 보고용 요약의 근거가 된다.

### 3.5 프로젝트별

목적:

- 여러 repo/프로젝트에서 생성된 row를 프로젝트 기준으로 분리해서 본다.

그룹:

```text
Group by Project
```

초기 표시 컬럼:

- `Name`
- `Status`
- `Purpose`
- `Task Group`
- `Parent Task`
- `Work Period`
- `Date`

활용:

- `claude-code-hooks-diary`, `api-server`, `admin-web` 등 여러 작업이 섞여도 프로젝트별 흐름을 확인한다.
- 최종 Multi-project OS의 기본 진입점이 된다.

---

## 4. 자동화 정책

### 4.1 DB/schema 보장

`views ensure`는 현재 연도 Entries DB와 schema v5까지 보장한다.

```text
working-diary notion views ensure
→ year page 확인/생성
→ Entries DB 확인/생성
→ schema v5 확인/보강
→ core views 확인/생성
```

정책:

- DB가 없으면 현재 연도 기준으로 생성할 수 있다.
- schema가 오래됐으면 core view 생성에 필요한 v5 schema까지 보강한다.
- schema v5는 기존 v4에 `Work Period` date range 컬럼을 추가한다.
- 기존 row는 생성/수정/삭제하지 않는다.
- view 생성 전 root page, year, database 상태를 CLI 출력에 표시한다.
- 이 명령의 DB/schema 보장은 view 생성의 전제 조건을 맞추기 위한 것이며 작업 기록 push를 대신하지 않는다.

예상 출력:

```text
[working-diary notion views ensure]
Root page: ...
Year: 2026
Database: Entries (created)
Schema: v5 ensured
Views:
  + 작업 계층
  + 오늘 작업
  + 상태별
  + 목적별
  + 프로젝트별
```

이미 모두 있으면:

```text
[working-diary notion views ensure]
Root page: ...
Year: 2026
Database: Entries (existing)
Schema: v5 already ensured
Views:
  = 작업 계층 (verified)
  = 오늘 작업 (verified)
  = 상태별 (verified)
  = 목적별 (verified)
  = 프로젝트별 (verified)
```

### 4.2 기본은 non-destructive

View 자동화는 사용자의 수동 Notion 편집을 존중한다.

- `views ensure`는 core view를 create + verify 한다.
- 이름이 같은 view가 있으면 무조건 skip하지 않고 required 설정을 검사한다.
- required 설정을 충족하면 verified로 처리한다.
- required 설정이 맞지 않으면 기존 view를 자동 수정하지 않고 conflict로 보고한다.
- 없는 view만 required 설정으로 create 한다.
- 기존 view의 수동 설정을 덮어쓰지 않음
- 기존 row는 수정하지 않음
- conflict가 있으면 core view 보장이 실패한 것이므로 exit 1을 반환한다.
- view 생성/검증 실패가 diary push 실패로 전파되지 않음

### 4.3 Force는 후속

2차 MVP에서는 `--force`를 필수로 구현하지 않는다.

후속 옵션:

```bash
working-diary notion views ensure --force
```

예상 동작:

- 시스템이 관리하는 view만 재생성 또는 업데이트
- 사용자 정의 view는 건드리지 않음
- 적용 전 변경 계획을 출력

### 4.4 Push와 분리

`$diary-notion`은 작업 기록에 집중한다.

```text
$diary-notion
→ row 생성
→ Parent Task / Depends On 연결
→ body blocks 기록
```

View 자동화는 별도 명령으로 둔다.

```text
working-diary notion views ensure
→ 현재 연도 Entries DB/schema v5 보장
→ core view 존재 확인
→ 없으면 생성
→ 있으면 required 설정 검증
→ required 설정 미충족 시 conflict 보고
```

이 분리를 유지하는 이유:

- view는 매 push마다 만들 필요가 없다.
- View API 권한/버전 문제가 작업 기록 실패로 이어지면 안 된다.
- 사용자가 원하는 시점에 화면 구성을 갱신할 수 있다.

### 4.5 기본 설정 보장 범위

공식 Views API 확인 결과, table view 생성/수정 시 다음 설정은 API 모델 안에서 직접 다룰 수 있다.

- `filter`
- `sorts`
- `configuration.properties`
- `configuration.group_by`
- `configuration.subtasks`
- `wrap_cells`
- `frozen_column_index`
- `show_vertical_lines`

따라서 2차 MVP의 “이름 + 기본 설정 보장”은 이름만 만드는 수준이 아니다. Core view 생성 시 다음을 required 설정으로 둔다.

Required:

- view 이름
- view type: `table`
- core property 표시
- hidden property 숨김
- view별 최소 filter/sort/group
- `Work Period` 컬럼 표시
- `작업 계층` view의 `Parent Task` 컬럼 표시

Required mismatch:

- view type이 `table`이 아님
- `Session ID`, `Task Index`가 표시됨
- `Work Period` 컬럼이 표시되지 않음
- `오늘 작업`에 `Date = today` filter가 없음
- `상태별`에 `Status` group_by가 없음
- `목적별`에 `Purpose` group_by가 없음
- `프로젝트별`에 `Project` group_by가 없음
- `작업 계층`에 `Parent Task` 컬럼 표시가 없음

Best-effort:

- `작업 계층` view의 `Parent Task` 기반 subtask configuration payload 구성
- Notion UI의 접기/펼치기 sub-item 렌더링이 실제 workspace에서 기대대로 활성화되는지
- group order 세부 순서
- column width, frozen column, wrap, vertical line 같은 presentation detail
- view tab 위치

Best-effort mismatch는 warning만 남기고 실패로 보지 않는다.

`subtasks`는 API상 table configuration의 일부로 지원되므로 생성 payload에는 우선 포함한다. 다만 workspace/API 버전/권한/Notion 동작 차이로 sub-item UI 설정이 거절되거나 기대와 다르게 보일 수 있으므로, 이 실패는 2차 MVP의 전체 실패가 아니라 warning으로 처리한다.

`subtasks` 포함 create/update가 실패하면 CLI는 `subtasks`를 제거한 base table view 생성으로 fallback한다. fallback view가 생성되면 전체 명령은 성공으로 처리하되 warning을 출력한다. base table view 생성까지 실패하면 core view 생성 실패로 보고 exit 1을 반환한다.

Core view별 required 설정:

| View | Required 설정 |
|------|---------------|
| 작업 계층 | `table`, 핵심 properties 표시, `Parent Task` 표시, `Work Period` 표시 |
| 오늘 작업 | `table`, `Date = today` filter, `Date desc` sort, `Work Period` 표시, 핵심 properties 표시 |
| 상태별 | `table`, `Status` group_by, `Work Period` 표시, 핵심 properties 표시 |
| 목적별 | `table`, `Purpose` group_by, `Work Period` 표시, 핵심 properties 표시 |
| 프로젝트별 | `table`, `Project` group_by, `Work Period` 표시, 핵심 properties 표시 |

작업 계층 view의 best-effort 설정:

| 설정 | 기준 |
|------|------|
| `subtasks.property_id` | `Parent Task` relation property id |
| `display_mode` | `show` |
| `filter_scope` | `parents_and_subitems` |

모든 core view에서 기본적으로 숨긴다:

- `Session ID`
- `Task Index`

다음 컬럼은 view별로 표시가 필요하지 않으면 숨길 수 있다.

- `Files`
- `Commits`
- `Lines`
- `Categories`
- `Branch`

확인한 공식 문서:

- Notion Developers: Working with views
- Notion Developers: Upgrading to 2025-09-03
- Notion Developers: Upgrading to 2026-03-11

---

## 5. API 경계

### 5.1 API version 분리 정책

Notion API version은 workspace나 database를 전역 업그레이드하는 값이 아니라, 요청마다 `Notion-Version` header로 선택하는 값이다.

2차 MVP에서는 Notion API version을 전역으로 올리지 않는다.

결정:

```text
기존 기록 경로
NotionHierarchicalExporter
Notion-Version: 2022-06-28
역할: DB 생성, schema 보강, row 생성, body blocks append, relation 연결

신규 view 경로
NotionViewsClient
Notion-Version: 2025-09-03
역할: data_source_id 확인, view 조회, core view 생성
```

이유:

- `$diary-notion` push 경로는 이미 작업 기록의 핵심 경로이므로 안정성이 가장 중요하다.
- `2025-09-03`부터 Notion이 database와 data source를 더 명확히 분리했기 때문에 기존 push 경로를 통째로 올리면 DB 생성, relation, page parent, query 쪽 영향 범위가 커진다.
- `views ensure`는 Views API가 필요하므로 `2025-09-03` 이상이 필수다.
- 따라서 view 자동화만 새 API version을 쓰고, 기존 기록 기능은 안정 버전에 남긴다.

`2026-03-11`은 2차 MVP에서 바로 적용하지 않는다. 이 버전은 view 생성 때문에 필수인 버전이 아니며, block append의 `after` → `position`, `archived` → `in_trash`, `transcription` → `meeting_notes` 변경이 있어 기존 push/body append 경로까지 함께 검토해야 한다.

후속으로 `2026-03-11`을 적용할 때는 전체 Notion API 호출 목록을 기준으로 별도 migration 문서를 만든다.

### 5.2 기존 push 경로

기존 row push는 안정성이 중요하므로 현재 구조를 유지한다.

```text
NotionHierarchicalExporter
Notion-Version: 2022-06-28
역할: year page, database, row, schema, relation
```

`views ensure`는 view 생성 전 이 경로의 `ensure_database(year)`를 재사용해 현재 연도 DB와 schema v5를 보장한다.

### 5.3 view 자동화 경로

Views API는 별도 client로 분리한다.

```text
NotionViewsExporter 또는 NotionViewsClient
Notion-Version: 2025-09-03
역할: view 조회, view 생성, view 설정
```

구현 시 고려:

- `database_id`와 `data_source_id` 관계 확인
- property id 조회
- existing view 조회
- 같은 이름 view required 설정 검사
- required 설정 충족 시 verified 처리
- required 설정 미충족 시 conflict 처리
- API 버전 변경 영향 격리

공식 API 확인 사항:

- Views API는 API version `2025-09-03` 이상이 필요하다.
- 2차 MVP의 view client는 `2025-09-03`을 사용한다.
- 2026-06-02 기준 공식 문서에는 `2026-03-11` 업그레이드도 존재하지만, 기존 body append/push 경로까지 함께 검토해야 하므로 후속 단계로 둔다.
- view 생성에는 `data_source_id`, `name`, `type`이 필요하고, top-level database view에는 `database_id`가 필요하다.
- filter/sorts는 data source query와 같은 shape를 사용한다.
- table configuration은 `properties`, `group_by`, `subtasks`를 지원한다.
- property configuration은 `visible`, `width`, `wrap`, date/time format 같은 표시 설정을 지원한다.
- subtask configuration은 self-referencing relation property를 사용해 parent-child hierarchy를 표시한다.

### 5.4 실패 처리

View ensure 실패는 다음처럼 처리한다.

```text
Auth/permission error → 명확한 안내 후 종료
Bad request → view 이름과 요청 payload 요약 출력
Network/rate limit → retry 또는 재실행 안내
Partial failure → 성공/실패 view를 나눠 보고
```

작업 기록 push와 다르게, view ensure는 실패해도 데이터 손실이 없다.

### 5.5 exit code와 partial failure

`views ensure`는 core view 자동 보장 명령이므로 core view 생성 실패와 best-effort 실패를 구분한다.

| 상황 | exit code | rollback | 이유 |
|------|-----------|----------|------|
| core view 전부 생성 | 0 | 없음 | 성공 |
| core view 전부 verified | 0 | 없음 | 성공 |
| 기존 core view required 설정 conflict | 1 | 없음 | 보장 실패 |
| 일부 core view 실패 | 1 | 없음 | partial failure |
| 인증/권한 실패 | 1 | 없음 | 전제 실패 |
| DB/schema 보장 실패 | 1 | 없음 | 전제 실패 |
| `subtasks` 설정 실패 후 base table fallback 성공 | 0 | 없음 | best-effort warning |
| `subtasks` 설정 실패 후 base table fallback 실패 | 1 | 없음 | core view 생성 실패 |

정책:

- Core view 생성 실패는 partial failure로 보고 exit 1을 반환한다.
- 기존 view가 required 설정을 충족하지 못하면 conflict로 보고 exit 1을 반환한다.
- 이미 생성된 view는 rollback하지 않는다.
- rollback이 기존 사용자 view나 새로 생성된 정상 view를 건드릴 수 있으므로 더 위험하다.
- `subtasks` 설정 실패 후 base table fallback이 성공하면 best-effort warning이며 exit code에 영향을 주지 않는다.
- base table fallback까지 실패하면 core view 생성 실패이므로 exit 1을 반환한다.
- warning은 CLI 출력에 남겨 사용자가 추후 수동 설정하거나 후속 개선을 요청할 수 있게 한다.

내부 결과 모델 후보:

```python
{
    "created": ["작업 계층", "오늘 작업"],
    "verified": ["상태별"],
    "conflicts": [("목적별", "missing Purpose group_by")],
    "failed": [("프로젝트별", "Notion API 400 ...")],
    "warnings": [("작업 계층", "subtasks fallback: base table created")]
}
```

CLI 출력 예시:

```text
[working-diary notion views ensure]
Database: Entries (existing)
Schema: v5 already ensured
Views:
  + 작업 계층
  + 오늘 작업
  ! 상태별 -- Notion API 400: ...
  x 목적별 -- conflict: missing Purpose group_by
  = 프로젝트별 (verified)
Warnings:
  ! 작업 계층 subtasks not enabled: base table fallback created
```

---

## 6. 구현 순서

### Step 1. 설계 고정

- Core Views 5개 확정
- `작업 그룹별`은 core follow-up으로 명시
- Operations/Intelligence views는 3차 이후로 분리
- `views ensure`가 현재 연도 Entries DB와 schema v5를 보장한다고 명시

### Step 2. CLI 뼈대

예상 명령:

```bash
working-diary notion views ensure
claude-diary notion views ensure
```

CLI 구조 후보:

```text
claude_diary.cli.notion_views
  cmd_notion_views_ensure(args)
```

### Step 3. DB/schema 보장

기존 hierarchical exporter를 재사용한다.

```text
NotionHierarchicalExporter.ensure_database(year)
→ year page 보장
→ Entries DB 보장
→ schema v5 보장
```

이 단계에서 row는 만들지 않는다.

### Step 4. View client 추가

후보 파일:

```text
src/claude_diary/exporters/notion_views.py
```

역할:

- credential resolve는 기존 notion push/init과 공유
- target database/data source 확인
- existing views 조회
- existing views required 설정 검증
- missing views 생성
- `subtasks` 포함 작업 계층 view 생성 실패 시 base table fallback

### Step 5. 테스트

테스트는 네트워크 없이 mock 기반으로 작성한다.

필수 테스트:

- DB가 없으면 현재 연도 DB와 schema를 보장하는 경로를 호출
- 이미 있고 required 설정을 충족하는 view는 verified
- 이미 있지만 required 설정이 부족한 view는 conflict
- 없는 core view는 create
- partial failure를 report
- conflict가 있으면 exit 1
- 일부 core view 실패 시 exit 1
- `subtasks` 설정 실패 후 base table fallback 성공 시 warning만 남기고 exit 0
- `subtasks` 설정 실패 후 base table fallback 실패 시 exit 1
- credential missing 시 안내
- 기존 row를 수정하지 않음
- push 경로와 view 경로가 분리되어 있음
- `작업 그룹별`, `막힌 작업`, `today-plan` view는 MVP에서 생성하지 않음

---

## 7. Non-goals

2차 MVP에서 하지 않는다.

- `$diary-notion` 실행마다 view ensure 자동 실행
- `Blocked`, `Progress`, `Priority` 컬럼 추가
- stale/blocked/review/today-plan view 생성
- weekly brief 생성
- 프로젝트/작업 그룹 전체 기간 자동 계산
- 기존 사용자 view 강제 수정
- 기존 row 생성/수정/삭제
- 기존 DB 전체 마이그레이션
- Notion을 Jira처럼 완전한 issue tracker로 만드는 것

---

## 8. 성공 기준

2차 MVP 성공 기준:

- `working-diary notion views ensure`가 현재 연도 Entries DB와 schema v5를 보장한다.
- `Work Period` date range 컬럼을 보장하고 core view에 표시한다.
- `working-diary notion views ensure`가 core view 5개를 자동 보장한다.
- 같은 이름의 view가 이미 있으면 중복 생성하지 않는다.
- 같은 이름의 view가 required 설정을 충족하면 verified로 처리한다.
- 같은 이름의 view가 required 설정을 충족하지 않으면 conflict로 보고 exit 1을 반환한다.
- 기존 row는 수정하지 않는다.
- 기존 `$diary-notion` push는 변경 없이 계속 동작한다.
- 사용자가 Notion DB에서 작업 계층, 오늘 작업, 상태별, 목적별, 프로젝트별로 즉시 탐색할 수 있다.
- 3차 Operations와 4차 Intelligence view는 core view와 혼동되지 않는다.
