# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- **`agent-diary report`**: 기간·프로젝트 단위로 문서 하나를 만든다. `search`는 항목을 찾고 `stats`는 개수를 세고 `weekly`는 이번 주 고정에 옵션도 없어서, "스탠드업·월간 보고·청구 근거로 쓸 문서"를 만드는 명령이 없었다
  - 세션 목록은 검색 인덱스, 서술은 일지에서 가져와 **session id로 조인**한다. 한 프로젝트로 필터링하면 같은 날 다른 프로젝트 문장이 섞이지 않는다. `parse_daily_file`을 재사용하지 않은 이유가 이것 — 그건 하루를 통째로 뭉쳐서 어느 문장이 어느 프로젝트 것인지 말할 수 없다
  - 작업 요약을 우선하고 원본 요청은 fallback. 요약이 없으면 요청을 쓰되 그 사실을 문서에 밝힌다. `--detail`로 둘 다
  - `--from/--to`, `--month`, `--days`, `--project`, `--output`, `--json`

### Fixed

- **`reindex`가 인덱스를 조용히 열화시키던 문제**: `reindex_all`이 `session_id`·`git_commits`·`lines_added`·`lines_deleted` 네 필드를 하드코딩으로 비워 썼다. 증분 경로(`update_index`)는 채우는 값들이라, 유지보수 명령을 한 번 돌리면 인덱스가 더 얇아지고 그 필드를 읽는 쪽은 **0과 빈 값을 그럴듯하게** 받았다
  - 네 값 모두 일지 Markdown에 있으므로 재구성 시 복원한다 (KO/EN 라벨 모두)
  - 실측: 6816개 엔트리에서 session_id 85 → 6816, 라인 수 보유 7 → 4082, 커밋 보유 66 → 3119
  - 이 결함 때문에 `report`가 서술을 하나도 못 붙이고 라인 수를 0으로 보고했다

## [4.7.0] - 2026-08-11

### Added

- **`agent-diary doctor`**: 이 도구가 아직 기록하고 있는지 점검한다. postmortem이 지목한 실패 유형 — *일지가 안 쌓이는 것은 조용한 하루와 구별되지 않는다* — 에 대한 탐지 수단이 그동안 없었다. 같은 유형을 오늘 한 번 더 만들 뻔했다(import 패키지를 바꿨다면 사용자 `settings.json`의 hook이 에러 없이 죽었을 것)
  - Stop Hook 등록 여부, 그 hook이 명시한 모듈이 실제로 임포트되는지, 마지막 기록으로부터 며칠 지났는지(7일 초과 시 경고), config 존재, 일지 경로 쓰기 가능 여부
  - `--notion`을 주면 Notion에 **읽기 전용** 요청 1회. `ensure_database`는 부르지 않는다 — 없으면 연도 페이지와 DB를 만들기 때문에 상태 점검이 할 일이 아니다
  - 실패가 있으면 exit code 1이라 cron이나 사전 점검에 그대로 물릴 수 있다

### Changed

- **run artifact 기본 경로 `.codefleet/runs` → `.agent-diary/runs`**: `.codefleet`은 별개 프로젝트 이름이라, 이 도구를 설치한 사람의 저장소에 **자기가 깔지 않은 소프트웨어 이름의 디렉터리**가 생겼다 (로컬에서 무관한 프로젝트 6곳에 만들어져 있었다)
  - 이미 `.codefleet/runs`가 있는 프로젝트는 계속 그걸 쓴다. 중간에 바꾸면 한 프로젝트의 실행 기록이 두 폴더로 갈라진다

## [4.6.0] - 2026-08-11

### Added

- **커밋 줄 Gitmoji** (`formatting.gitmoji`, 기본 꺼짐): 켜면 각 커밋 줄에 Conventional Commit 타입에 해당하는 [gitmoji](https://gitmoji.dev)가 붙는다. 타입을 알아볼 수 없는 커밋은 그대로 두고, 이미 이모지로 시작하는 메시지에는 덧붙이지 않는다 (`ai-commit` 같은 도구가 먼저 붙였을 수 있으므로)
  - **카테고리 태그에는 적용하지 않는다.** 📝·⚡·🔒 세 개가 일지에서 이미 작업 요약·주요 명령어·시크릿 마스킹을 뜻해서, 카테고리까지 장식하면 한 항목 안에서 같은 글자가 두 의미를 갖는다. 글자가 없는 것보다 나쁘다
  - 기본을 꺼둔 이유: 일지는 영구 기록이고, 이모지는 취향이 갈린다

## [4.5.0] - 2026-08-11

### Added

- **`agent-diary backfill`**: 설치 이전 세션을 가져온다. `init` 직후에는 세션이 하나 끝날 때까지 보여줄 게 없었는데, Claude Code는 그동안 `~/.claude/projects/`에 transcript를 남겨왔다. 이걸 읽어서 **실제로 작업한 날짜**로 일지를 만든다 (가져온 날짜가 아니라)
  - **재실행 안전**: 이미 일지에 있는 세션은 건너뛴다. 판정 기준은 일지 Markdown에 남은 session id 자체 — audit 로그나 검색 인덱스는 파생물이라 낡으면 중복을 통과시킨다. 실제 트리로 두 번 돌려 결과가 sha256까지 동일함을 확인
  - **서브에이전트 제외**: 서브에이전트도 각자 transcript 파일을 갖는다. 실측 194개 중 **115개(59%)** 가 그것이었고, 그대로 넣으면 일지 절반이 세션이 아니라 조각이 된다. `agent-` 파일명과 `agentId` 필드가 194개 전부에서 같은 115개를 가리켜 두 신호를 함께 쓴다. 조용히 버리지 않고 몇 개를 걸렀는지 출력한다
  - `--dry-run`, `--since`, `--limit`, `--transcripts` 지원
- `core.process_session()`에 `when` 인자 추가. 기본값은 현재 시각이고 Stop Hook에는 그게 맞다(세션 종료 시점에 실행되므로). backfill은 transcript의 시작 시각을 넘긴다

## [4.4.0] - 2026-08-11

### Added

- **[Architecture 문서](docs/ARCHITECTURE.md)**: 멱등성 키와 캐시 무효화, 원인별로 갈리는 재시도 정책, 스키마 버전 관리, 부분 실패의 의미, 의존성 0개를 택한 이유. 코드에 이미 있던 판단들이 README에서는 보이지 않던 것을 드러냄
- **[Postmortem: 2026-08-07 ensure 사고](docs/postmortem/2026-08-07-ensure-wipe.md)**: 스키마 PATCH 하나가 497 row에서 6개 속성을 지운 경위. 원인을 좁힌 측정(`Project`·`Branch`가 무사했던 것), 수정, 회귀 테스트를 그렇게 짠 이유, 아직 복구되지 않은 것까지
- **타입 검사**: `mypy`가 CI에서 주석 처리된 코어 모듈을 검사한다. `pyproject.toml`의 목록이 검사 범위이고, 저장소 전체에 켜고 나머지를 `ignore_errors`로 덮는 방식은 택하지 않았다

### Changed

- **`types.py`가 주석이 아니라 실제 타입이 됨**: `EntryData`, `GitInfo`, `DiffStat`, `CommitInfo`, `Config` 등을 `TypedDict`로 정의. 기존 주석은 Python 3.7 호환을 이유로 들었지만 하한은 이미 3.8이었고, 그 사이 주석이 실제와 어긋나 있었다(커밋의 `short_hash` 누락, parser가 만드는 키 3개 누락). 주석은 실패할 수 없다는 게 문제였다
  - 코어에 타입을 붙이자 **타입이 실제로는 흐르지 않던 6곳**이 드러났다. `entry_data`가 dict 리터럴로 만들어져서 `_supplement_from_git`·`scan_entry_data`·`format_entry`·`_run_exporters`가 전부 `dict[str, Any]`를 받고 있었다
  - 시그니처만 변경. 함수 본문은 손대지 않아 동작 변화는 없다
- **`Schema Version`의 `vlegacy`를 우연이 아니라 의도로** ([#11](https://github.com/solzip/agent-diary/issues/11)): 값은 그대로 유지한다. 실측 결과 509 row 중 350개가 쓰는 실존 select 옵션이라, 다른 문자열을 쓰면 세 번째 옵션이 생기고 기존 row가 옛 옵션에 남는다. 이름 변경은 여기서 할 편집이 아니라 데이터베이스 마이그레이션이다. 이제 `LEGACY_SCHEMA_VERSION` 상수로 명시하고 테스트로 고정했다

### Fixed

- **dry-run이 실제 push와 다른 제목을 보여주던 문제** ([#10](https://github.com/solzip/agent-diary/issues/10)): 미리보기가 자격증명 해석 **전에** 끝나서 차수 조회를 못 했고, 결과적으로 이어지는 task group인데도 `(N차)` 없이 렌더링됐다. 미리보기가 예측 대상과 어긋나는 상태였다
  - 자격증명이 있으면 dry-run도 차수를 조회해 제목에 반영한다
  - **`ensure_database`는 호출하지 않는다.** 이 함수는 없으면 연도 페이지와 데이터베이스를 *생성*하므로 미리보기가 불러선 안 된다. DB ID는 로컬 캐시에서만 읽고, 캐시가 없으면 조회를 포기한다
  - 자격증명이 없거나 캐시가 비었거나 조회가 실패하면 제목을 건드리지 않고, 미리보기 상단에 "차수가 확정되지 않았다"고 밝힌다. `diary-notion init` 전에도 dry-run은 그대로 쓸 수 있다

### Known

- 실제 push가 저장하는 `preview.md`는 차수 부여 **전에** 렌더링된다. `--force` archive 이후에 차수를 매겨야 하고, 미리보기는 네트워크 호출 전에 남겨야 push가 중간에 실패해도 기록이 보존되기 때문이다. 화면 출력과 Notion row는 정확하지만 저장된 `preview.md`의 제목에는 `(N차)`가 빠진다

## [4.3.1] - 2026-08-11

### Fixed

- **CLI가 스스로를 옛 이름으로 소개하던 문제**: `argparse`의 `prog`와 `--version` 문자열이 `claude-diary`로 하드코딩돼 있어서, `pip install agent-diary` 후 `agent-diary --version`을 실행하면 `claude-diary 4.3.0`이라고 답했다. `--help`의 usage 줄도 마찬가지
- 사용자 눈에 보이는 나머지 옛 이름 정리: `uninstall --codex` 도움말, `write`의 안내 출력, HTML 대시보드 footer
- Obsidian exporter의 `subfolder` 기본값(`claude-diary`)은 **유지**. 이건 이름이 아니라 사용자 vault 안의 경로라, 바꾸면 기존 노트가 두 폴더로 갈라진다

## [4.3.0] - 2026-08-11

### Changed — 이름

- **`claude-diary` → `agent-diary`**: 저장소, PyPI 배포명, 기본 CLI 명령을 한 이름으로 통일. 저장소가 `working-diary`, 설치가 `pip install claude-diary`, 명령이 `working-diary`로 갈라져 있어 README가 그 불일치를 해명해야 했고, 실제로 PyPI trusted publisher가 저장소 이름 변경 때문에 깨진 적이 있다
  - `working-diary`, `claude-diary` 명령은 alias로 계속 동작
  - **import 패키지는 `claude_diary`로 유지**. `install`이 사용자 `settings.json`에 `python -m claude_diary.hook`을 기록하므로, 바꾸면 기존 사용자의 Stop Hook이 조용히 멈춘다
  - config 디렉터리(`claude-diary/`)와 일지 디렉터리(`~/working-diary/`)도 유지. 사용자 데이터와 자격증명이 들어 있고, 옮기면 조용히 갈라진다

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
- **테스트 보강**: Notion Purpose, Codex plugin/skills, Codex JSON input 경로 검증 (전체 737 통과)

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
- **작업한 순서대로 row 정렬**: 한 push가 만드는 row는 `Date`가 전부 같아 `Date desc`만으로는 하루치 순서가 임의로 결정됐다. 5개 뷰 전부 `Task Index` 오름차순을 2차 정렬로 사용한다. 정렬은 숨김 속성도 참조할 수 있어 테이블 폭 비용은 없다. `_verify_view`도 이 정렬을 검사하므로 이전에 만든 뷰는 `ensure`가 복구한다. 한계: `Task Index`는 push마다 리셋되므로 같은 날짜에 두 번 push하면 두 묶음이 섞인다

### Fixed
- **`ensure`가 데이터베이스의 select 값을 전부 지우던 문제**: `_ensure_db_schema_extensions`가 매 실행마다 확장 속성 전체를 PATCH했다. `{"select": {}}`는 no-op이 아니라 옵션 목록을 빈 것으로 교체하며, Notion은 제거된 옵션을 참조하던 **모든 row에서 그 속성을 비운다**. 결과적으로 `ensure`를 돌릴 때마다 `Status` `Purpose` `Task Group` `Priority` `Review Status` `Schema Version`이 DB 전체에서 조용히 비워졌다 (실측: 2026 DB 497 row에서 6개 속성 전멸, 옵션 수 0). base schema에 있어 재PATCH되지 않는 `Project` `Branch`는 무사했다. 이제 현재 property map을 먼저 읽고 실제로 없는 속성만 전송하므로 기존 속성을 다시 쓰지 않는다
- **처음 쓰는 task group을 오류로 처리하던 문제**: Notion은 아직 존재하지 않는 select 옵션을 지정한 필터를 거부하므로, 새 task group마다 차수 조회가 400을 냈다. 조회는 best-effort라 push 자체는 성공했지만 로그가 두 화면씩 찍혔다 — Notion의 select 오류가 기존 옵션을 전부 나열하는데 그 메시지를 자르지 않고 그대로 흘려보냈기 때문이다. 알 수 없는 옵션은 선행 세션이 없다는 뜻이므로 조용히 1차로 확정한다. `short_error`도 이름값대로 200자에서 자른다
- **폐기된 뷰 경고가 `unknown`으로 분류되던 문제**: 손으로 삭제하라는 안내 바로 밑에 "문제를 확인한 뒤 `ensure`를 다시 실행하라"가 붙었다. 재실행으로는 해결되지 않는 항목이라 별도로 분류한다
- **dry-run이 artifact ref를 잘라서 보여주던 문제** 및 v2 artifact 리포트 출력 보강
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
