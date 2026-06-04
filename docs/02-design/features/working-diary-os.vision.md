# Working Diary OS Vision

> **Summary**: AI 코딩 세션, Git, Notion 작업 DB, 로컬 작업 메모를 연결해 기록, 구조화, 조회, 운영, 리뷰까지 지원하는 개인 업무 운영 시스템의 최종 방향
>
> **Project**: claude-code-hooks-diary
> **Date**: 2026-06-01
> **Status**: Vision Draft

## 1. 목적

Working Diary OS는 단순 작업일지 생성기가 아니다. 최종 목표는 사용자가 여러 프로젝트와 여러 AI 세션에서 수행한 일을 자동으로 기록하고, 작업 구조와 근거를 잃지 않으며, 다음 행동과 우선순위를 판단할 수 있게 만드는 개인 업무 운영 시스템이다.

핵심 질문은 다음 세 가지다.

- 오늘 무엇을 했는가?
- 무엇이 막혀 있고 왜 막혀 있는가?
- 다음에 무엇을 해야 하는가?

## 2. 최종 사용자 경험

사용자는 평소에는 세션 안에서 짧게 명령만 실행한다.

```bash
$diary
$diary-notion
```

시스템은 세션의 대화, 도구 사용, 파일 변경, 명령어, Git 정보를 기반으로 작업 단위 row를 만든다. Notion에서는 다음과 같이 볼 수 있어야 한다.

```text
프로젝트 A
  큰 작업 1
    세부 작업 1
    세부 작업 2
  큰 작업 2

프로젝트 B
  막힌 작업
  검증 대기 작업
```

추가 명령은 필요할 때만 실행한다.

```bash
working-diary diary-notion ensure
working-diary diary-notion ensure --dry-run
working-diary diary-notion today-plan
working-diary diary-notion review
working-diary diary-notion weekly-brief
```

최종 모델에서도 사용자-facing 명령은 최소화한다. Notion 기반 정비는 `working-diary diary-notion ensure` 하나를 기본 진입점으로 두고, schema/view/status/drift 관련 세부 작업은 내부 단계와 옵션으로 확장한다.

최종적으로 사용자는 Notion DB를 열어 다음을 확인할 수 있어야 한다.

- 작업 계층: 어떤 일이 어떤 큰 작업의 하위인지
- 상태: 논의, 설계, 구현, 테스트, 배포 중 어디인지
- 종속성: 무엇이 선행되어야 하는지
- 근거: 어떤 파일, 명령어, 커밋, 테스트가 있었는지
- 리스크: 무엇이 막혀 있고 누가 결정해야 하는지
- 다음 액션: 다음 세션에서 무엇부터 해야 하는지
- 오늘 계획: 전날 남긴 todo와 `next_steps`를 기준으로 무엇을 우선 처리해야 하는지

## 3. 핵심 원칙

### 3.1 기록은 자동, 판단은 보수적으로

세션에서 관찰된 사실은 자동으로 남긴다. 하지만 상태 변경, 우선순위, blocked 판정처럼 사용자 판단에 영향을 주는 값은 보수적으로 계산하고, 가능하면 dry-run으로 먼저 보여준다.

### 3.2 구조는 DB, 근거는 본문

작업 구조는 Notion DB property로 표현한다.

- `Project`
- `Purpose`
- `Task Group`
- `Status`
- `Parent Task`
- `Depends On`
- `Work Period`
- `Priority`
- `Next Action`
- `Blocked`
- `Block Reason`
- `Carryover`
- `Review Status`
- `Last Reviewed`

본문은 사람이 읽는 근거를 담당한다.

- 요약
- 작업 한눈에
- 검증 및 상태
- 다음 액션
- 접힌 부록: 코드 변경, 파일, 명령어, Git, 원문 요청

### 3.3 포함 관계와 선행 관계를 분리

`Parent Task`와 `Depends On`은 의미가 다르다.

```text
Parent Task = 포함 관계
예: "상품 목록 포커싱"은 "로컬 테스트 진행"의 하위 작업

Depends On = 큰 메인 작업끼리의 선행 관계
예: "2차 view 자동화 구현"은 "schema v7 보장"이 끝나야 가능
```

하위 작업은 `Parent Task`와 Notion sub-item으로 표현하고, 종속성으로 연결하지 않는다. 두 관계를 섞으면 view, 진행률, blocked 계산이 모두 부정확해진다.

### 3.4 수동 수정은 자동화보다 우선

사용자가 Notion에서 직접 고친 값은 자동화가 함부로 덮어쓰지 않는다. 자동화가 값을 바꿀 때는 다음 중 하나를 만족해야 한다.

- 명령에 `--apply`가 명시되어 있다.
- 값이 시스템 전용 컬럼이다.
- 사용자가 명시적으로 force/sync를 요청했다.

### 3.5 작업 row는 의미 단위로만 만든다

row로 만들 기준:

- 독립적으로 상태를 추적할 작업
- 다른 작업의 선행 조건이 되는 작업
- 파일/코드/테스트/커밋 근거가 남는 작업
- 며칠 뒤 다시 찾아야 하는 작업

본문 checklist로 둘 기준:

- 단순 확인 항목
- 긴 SQL/JS/로그/메모
- 참고 링크
- 너무 작은 단계

## 4. 데이터 모델

### 4.1 현재 고정 모델

| 필드 | 역할 |
|------|------|
| `Name` | 작업 제목 |
| `Date` | 작업 기록일 |
| `Work Period` | 실제 작업 기간. 프로젝트/작업 그룹 기간 계산 재료 |
| `Project` | 프로젝트 필터/그룹 |
| `Purpose` | Feature, Bugfix, Planning 등 목적 |
| `Status` | Discussion, Design, Implementation, Testing, Deployed |
| `Task Group` | 여러 세션을 묶는 큰 작업 단위 |
| `Parent Task` | 포함 관계. Notion 하위항목/sub-item 기반 |
| `Depends On` | 큰 메인 작업끼리의 선행 관계 |
| `Priority` | P0/P1/P2/P3 우선순위 |
| `Next Action` | 다음에 바로 실행할 행동 |
| `Blocked`, `Block Reason` | 현재 진행 불가 여부와 막힘 원인 |
| `Carryover` | 전날/이전 세션 미완료 작업 이어가기 |
| `Review Status`, `Last Reviewed` | 검토 필요/완료/보류와 실제 검토일 |
| `Categories` | 보조 라벨 |
| `Files`, `Commits`, `Lines` | 변경 규모 |
| `Session ID`, `Task Index` | 멱등성 |

### 4.2 확장 후보 모델

3차 이후 추가를 검토한다.

| 필드 | 역할 |
|------|------|
| `Stale Score` | 오래 방치된 정도 |
| `Progress` | 하위 작업 기준 진행률 |
| `Review Notes` | 주간/일간 리뷰 결과 |

확장 컬럼은 기존 핵심 모델을 대체하지 않고 보조한다.

### 4.3 Work Period 적용 원칙

`Date`와 `Work Period`는 최종 모델에서도 분리한다.

```text
Date = 기록일
Work Period = 실제 작업 기간
```

`오늘 작업` view와 daily brief는 `Date`를 기준으로 한다. 사용자가 오늘 `$diary-notion`으로 남긴 수행분을 보여주는 것이 목적이기 때문이다.

프로젝트 산출물, 작업 그룹, 주간/월간 회고의 실제 작업 기간은 `Work Period`를 기준으로 계산한다.

집계 규칙:

```text
Project duration
= 같은 Project row들의 min(Work Period.start) ~ max(Work Period.end)

Task Group duration
= 같은 Task Group row들의 min(Work Period.start) ~ max(Work Period.end)

Work days
= Work Period가 포함하는 날짜의 unique day count
```

어제 시작한 작업을 오늘 이어서 했다면 오늘 수행분은 새 row로 남기고 같은 `Task Group`으로 묶는다. 기존 row의 `Work Period`를 자동으로 늘리지 않는다.

```text
2026-06-01 row
Date = 2026-06-01
Work Period = 2026-06-01
Task Group = diary-notion-view-design

2026-06-02 row
Date = 2026-06-02
Work Period = 2026-06-02
Task Group = diary-notion-view-design
```

최종 모델에서는 이 row들을 읽어 프로젝트/작업 그룹 단위의 기간을 제안한다. 실제 요약 row, 요약 DB, `First Worked On`, `Last Worked On`, `Work Days` 같은 계산 컬럼을 만들지는 Phase 3 이후 별도 apply 단계로 둔다.

## 5. 자동화 경계

### 5.1 에이전트 책임

- 세션을 의미 단위 작업으로 나눈다.
- 제목과 설명형 본문을 한국어로 작성한다.
- 파일, 명령어, branch, commit hash, 코드 식별자는 원문을 보존한다.
- `parent_index`와 `depends_on_indices`를 구분해 작성한다.
- 하위 작업은 `parent_index`로 연결하고, `depends_on_indices`는 최상위 메인 작업 간 선행 관계에만 사용한다.
- `Priority`, `Next Action`, `Blocked`, `Block Reason`, `Carryover`, `Review Status`, `Last Reviewed`를 보수적으로 작성한다.

### 5.2 CLI 책임

- JSON을 검증하고 Notion row를 생성한다.
- Git 메타데이터를 수집한다.
- `Parent Task`와 `Depends On` relation을 row 생성 후 연결한다.
- `Depends On` 연결 시 하위 작업 row는 제외해 sub-item 구조와 선행 관계가 섞이지 않게 한다.
- `Project` 누락/unknown은 명령 실행 cwd 폴더명으로 보정한다.
- Notion schema/view 동기화는 `diary-notion ensure` 명령 단위로 분리한다.

### 5.3 운영/리뷰 엔진 책임

3차 이후의 책임이다.

- 오래 방치된 작업을 찾는다.
- 반복되는 리스크를 요약한다.
- schema/view conflict를 drift 관리 대상으로 분류하고 해결 계획을 제안한다.
- `Project` 또는 `Task Group`별 `Work Period`의 최소 시작일과 최대 종료일을 계산해 실제 작업 기간을 제안한다.
- 전날/최근 N일의 미완료 todo와 `next_steps`를 수집한다.
- `Depends On`, `Blocked`, `Status`, `Task Group` 연속성을 반영해 오늘 우선순위를 제안한다.
- 다음 액션 후보를 제안한다.
- 상사 보고용 daily/weekly brief를 생성한다.

리뷰 엔진은 기본적으로 제안만 한다. 실제 Status/Priority/schema/view 변경은 별도 apply 단계가 필요하다.

### 5.4 Conflict / Drift 관리

최종 모델에서 conflict는 단순 실패 메시지가 아니라 시스템 drift 관리 대상이다.

기본 흐름:

```text
Conflict 감지
→ 원인 분류
→ 해결 계획 제안
→ dry-run 출력
→ 사용자 승인 시 apply
→ 변경 내역 기록
```

명령 방향:

```bash
working-diary diary-notion ensure
working-diary diary-notion ensure --dry-run
working-diary diary-notion ensure --plan
working-diary diary-notion ensure --apply
working-diary diary-notion ensure --force
```

동작:

- `diary-notion ensure`: conflict를 감지하고 이유와 수동 해결 안내를 출력한다.
- `diary-notion ensure --dry-run`: 생성/수정 없이 현재 상태 기준 계획만 출력한다.
- `diary-notion ensure --plan`: 어떤 view/schema를 어떻게 고칠지 변경 계획만 출력한다.
- `diary-notion ensure --apply`: 사용자가 승인한 변경만 적용한다.
- `diary-notion ensure --force`: 시스템이 관리하는 view만 재생성하거나 업데이트한다.

conflict 유형:

| 유형 | 예시 | 기본 처리 |
|------|------|-----------|
| Name conflict | 같은 이름 view가 있지만 type/filter/group이 다름 | conflict, exit 1 |
| Required setting conflict | `오늘 작업`에 today filter 없음 | conflict, exit 1 |
| Presentation drift | column width, group order, wrap 차이 | warning |
| Unsupported capability | `subtasks` API 실패 | fallback + warning |
| Schema conflict | `Work Period` 누락 | schema ensure로 보강, 실패 시 exit 1 |

원칙:

- 자동화는 감지와 제안까지 기본값이다.
- 수정은 `--apply` 또는 `--force`가 있어야 한다.
- 사용자 수동 view는 기본적으로 보호한다.
- conflict 해결을 위해 `오늘 작업 (Generated)` 같은 대체 view를 자동 생성하지 않는다.
- 반복 conflict는 review/weekly brief에서 내부 운영 리스크로 요약할 수 있지만, 상사 보고용 핵심 성과와는 분리한다.

## 6. Phase Roadmap

### Phase 1. Structure

목표: 작업을 정확한 DB row와 relation으로 기록한다.

완료 기준:

- Claude `/diary-notion`과 Codex `$diary-notion`이 동일한 작업 구조를 생성한다.
- `Parent Task`와 `Depends On`이 분리된다.
- page body는 compact body와 접힌 근거로 정리된다.

### Phase 2. Views

목표: Notion에서 작업 관리 화면처럼 보이게 만든다.

예상 명령:

```bash
working-diary diary-notion ensure
```

Core Views:

- 작업 계층
- 오늘 작업: 오늘 해야 할 일이 아니라 오늘 실제로 기록된 수행분
- 상태별
- 목적별
- 프로젝트별

Core follow-up:

- 없음. Core Views 5개는 최종 모델에서도 기본 화면으로 유지한다.

Operations/Intelligence views:

- 오늘 우선순위
- 전날 미완료
- Blocked
- 리뷰 필요
- 작업 그룹별

Phase 2에서 보장하는 schema v7 운영 컬럼:

- `Priority`
- `Next Action`
- `Blocked`
- `Block Reason`
- `Carryover`
- `Review Status`
- `Last Reviewed`

하위 항목 정책:

- 메인 작업과 하위 작업의 `Parent Task` 데이터 구조는 2차에서 필수로 보장한다.
- Notion의 접기/펼치기 sub-item UI는 최종 목표이며 2차에서는 best-effort로 활성화한다.
- sub-item UI 설정이 실패하면 `Parent Task`와 `Work Period`가 표시되는 base table view로 fallback한다.

View 자동화는 push 실패와 분리한다. view 생성/갱신 실패가 작업 기록 실패로 이어지면 안 된다.

### Phase 3. Operations

목표: 쌓인 DB를 읽어 상태를 점검하고 운영 정보를 계산한다.

예상 명령:

```bash
working-diary diary-notion ensure --dry-run
working-diary diary-notion ensure --apply
```

기능 후보:

- 하위 작업 기반 진행률 계산
- schema/view conflict 유형 분류
- conflict dry-run plan 출력
- 반복 conflict 추적
- `Project`/`Task Group`별 실제 작업 기간 계산
- `Work Period` 기반 work days 계산
- 오래 방치된 작업 탐지
- 검증 누락 탐지
- 상위 작업 상태 제안
- 전날 미완료 row와 `Next Action`을 기반으로 today-plan 후보 제안

### Phase 4. Intelligence

목표: 쌓인 작업 데이터를 바탕으로 우선순위, 리스크, 다음 액션을 제안한다.

예상 명령:

```bash
working-diary diary-notion today-plan
working-diary diary-notion review
working-diary diary-notion weekly-brief
```

기능 후보:

- 전날 남긴 todo/`next_steps` 기반 오늘 작업 우선순위 Top N 생성
- 선행 작업이 완료된 후속 작업을 오늘 후보로 승격
- 아직 막힌 작업은 blocker로 분리하고 우선순위 산정에서 제외하거나 낮춤
- 프로젝트별 이번 주 요약과 실제 작업 기간 요약
- 다음 작업 우선순위 추천
- 반복 이슈 탐지
- weekly review에 view/schema drift 요약
- 상사 보고용 brief 생성
- 다음 세션 시작용 handoff 생성

`today-plan`은 하루 시작 시 사용하는 명령이다. 기본 출력은 제안이며 Notion 값을 변경하지 않는다.

```text
오늘 작업 우선순위

1. 결제 진행 중 키패드 차단
   이유: 전날 next_steps에 남았고 배리어프리 로컬 테스트 완료를 막고 있음

2. 테스트 DB 복구 상태 확인
   이유: 상품 목록/결제 플로우 테스트의 선행 조건

3. Terraform 04-modules-basic 진행
   이유: 01~03이 완료됐고 다음 학습 순서
```

### Phase 5. Multi-project OS

목표: Notion만이 아니라 Git/GitHub/로컬 문서/AI 세션을 연결한다.

기능 후보:

- GitHub issue/PR 연결
- 프로젝트별 backlog와 diary 연결
- commit/PR 기준 작업 회고
- 여러 프로젝트의 오늘 우선순위 통합
- 로컬 Markdown diary와 Notion DB 양방향 참조
- 여러 Notion DB/프로젝트의 schema/view drift 관리
- 시스템 관리 view와 사용자 view 분리
- 승인 기반 apply/force 운영

## 7. Non-goals

현재 비목표:

- 사용자의 모든 Notion 수동 편집을 자동으로 추적하거나 병합
- Notion을 완전한 Jira 대체제로 만드는 것
- 매 push마다 view/status/review 자동화를 모두 실행
- AI가 사용자 승인 없이 우선순위나 Status를 확정 변경
- 과거 모든 diary를 자동 마이그레이션

## 8. 리스크

| 리스크 | 설명 | 대응 |
|--------|------|------|
| 과도한 row 분리 | 체크리스트 수준 항목까지 row가 되어 DB가 지저분해짐 | row 생성 기준을 skill에 유지 |
| 자동화의 과잉 판단 | Status/Priority를 잘못 바꿈 | dry-run, 수동 우선 원칙 |
| API 버전 변화 | Notion View/Data Source API가 변경됨 | view 자동화를 push와 분리 |
| relation 오용 | Parent와 Depends On이 섞임 | 문서/skill/test에서 의미 고정 |
| 본문 장황화 | page body가 다시 보고서처럼 길어짐 | compact body와 toggle 부록 유지 |

## 9. 성공 기준

최고모델의 성공 기준은 기능 개수가 아니라 사용자의 다음 행동 판단이 쉬워졌는지다.

- 작업 하나를 열면 무엇을 했는지 30초 안에 파악된다.
- 프로젝트 하나를 보면 진행 중/막힌 일/다음 액션이 보인다.
- 프로젝트나 작업 그룹을 모아 보면 실제 작업 기간이 파악된다.
- 하루 시작 시 전날 todo와 미완료 작업을 다시 훑지 않아도 오늘 우선순위가 제안된다.
- 다음 세션을 시작할 때 이전 맥락을 다시 설명하지 않아도 된다.
- 상사 보고용 daily/weekly brief를 별도 정리 없이 만들 수 있다.
- 자동화가 사용자의 수동 판단을 방해하지 않는다.
