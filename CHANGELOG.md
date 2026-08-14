# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Changed

- **한 번만 적혀야 할 값들을 한 곳으로**: 전수 검사에서 **정의만 되고 아무 데서도 안 읽히는 상수 3개**가 나왔다. 죽은 줄 자체가 문제가 아니라 **그 옆에 자란 것**이 문제였다 — 이름이 붙은 자리 하나와, 손으로 다시 쓴 자리 여럿이 서로를 모른다
  - `RICH_TEXT_LIMIT`이 아무 데서도 안 쓰이는 동안 **`[:2000]` 리터럴 8개가 3개 모듈에서** 실제로 자르고 있었다. `formatter.py`는 docstring에 "RICH_TEXT_LIMIT으로 자른다"고 적어놓고 **그 이름을 임포트할 수조차 없었다** — `notion_hierarchical`이 `formatter`를 임포트하므로 화살표가 한 방향뿐이다. 그래서 아무것도 임포트하지 않는 잎 모듈 `lib/notion_api.py`를 만들었다. API 버전(`2022-06-28`, 두 곳)과 베이스 URL도 같은 길을 가고 있어 함께 옮겼다
  - `ACTIVE_STATUSES`가 안 쓰이는 동안 **바로 아래 파일에서 같은 상태 문자열이 인라인으로 여섯 번** 비교되고 있었고, `properties.py`엔 별도로 `VALID_STATUSES`가 또 있었다. `lib/statuses.py`로 통합했다. **의미는 하나도 바꾸지 않았다** — `Deployed`가 "배포"인지 "완료"인지는 records/work-items 설계가 아직 들고 있는 질문이고, 여기서는 현재 의미를 그대로 옮기기만 했다. 어제 적어둔 **착수 순서 1번("상태 정의 통합")이 이것**이다
  - `DEFAULT_VERIFICATION_LIMIT`은 대응하는 인라인 값도 없는 순수한 죽은 줄이라 지웠다
  - `config.get("diary_dir", "~/working-diary")`가 **7개 호출부에 각자 기본값 사본**을 들고 있었다. **그 사본들은 발화될 수 없다** — `load_config`가 `DEFAULT_CONFIG`를 deepcopy하므로 키는 항상 있다. 즉 아무도 갱신하지 않을 기본값 7개가, 실제로 유효한 형태(`os.path.join`)와 **다른 형태**(POSIX 리터럴)로 적혀 있었다. `resolve_diary_dir(config)` 하나로 모았다
  - **transcript 루트는 세 철자였고, 그게 Windows에서 동등하지 않았다.** `expanduser("~/.claude/projects")`는 `C:\Users\me/.claude/projects`(구분자 혼용), `os.path.join` 형태는 `C:\Users\me\.claude\projects`를 준다. 같은 디렉터리를 열지만 **다른 문자열과만 같다.** 둘을 합치는 순간 기존 테스트가 이 차이를 잡았다. 그래서 상수 하나가 아니라 **사람이 읽는 기본값 문자열(`CLAUDE_TRANSCRIPT_ROOT`)과 코드가 쓰는 `resolve_transcript_root()`로 나눴다**
  - 회귀 테스트: **정의만 되고 안 읽히는 상수가 생기면 실패한다.** 참조는 텍스트가 아니라 **구문 트리에서** 센다 — docstring에 이름이 적혀 있는 것이 `RICH_TEXT_LIMIT`이 오랫동안 쓰이는 것처럼 보였던 이유다. 통합한 값 넷이 다시 흩어져도 잡는다. 이때도 **리터럴만 보고 산문은 보지 않는다** — 디렉터리 구조를 설명하는 docstring을 상수 보간으로 바꾸는 건 개악이다
  - 가드 4개를 변형으로 검증했다 — **4/4**. 그 과정에서 가드가 **자기가 옮겨놓은 죽은 상수(`ACTIVE`)를 즉시 잡았다.** 죽은 상수를 지운 게 아니라 자리만 옮긴 셈이어서, 호출부에 맞는 이름(`EARLY`)으로 바꾸고 인라인 튜플 하나를 마저 없앴다

### Fixed

- **sdist가 자기가 실은 테스트를 돌릴 수 없던 문제**: sdist는 `tests/`를 같이 싣는데, 그중 여럿이 패키지가 아니라 **저장소**를 읽는다(플러그인 매니페스트, CI 매트릭스, 릴리스 워크플로, CHANGELOG 추출기). 그 파일들이 sdist에 없었다
  - 실측: sdist를 풀어 `pytest`를 돌리면 **수집 오류 2 + 실패 4 + 오류 14.** 수집 자체가 중단돼 한 줄도 못 돈다. 아무도 자기 sdist를 풀어보지 않아서 조용했다
  - `MANIFEST.in`이 `.codex-plugin`은 싣고 `.claude-plugin`은 안 실었다. **둘 다 런타임에는 읽히지 않는다** — 코드에서 참조하는 곳이 없다. 판정 기준이 된 건 "누가 읽는가"가 아니라 **"실어 보낸 테스트가 통과하는가"**였다
  - `.claude-plugin`, `.github/workflows`, `scripts`, 그리고 PyPI 사이드바가 약속하는 `docs/ARCHITECTURE.md`를 추가했다. `docs/` 나머지 344KB는 설계 노트라 뺐다
  - 수정 후 sdist에서 **1,153개 전부 통과**. 163개 파일, 332KB
  - 테스트가 새 저장소 파일을 읽기 시작하면 걸리도록, **테스트 소스에서 `ROOT / "..."` 경로를 뽑아 MANIFEST가 그걸 싣는지 검사**한다. 목록을 손으로 적지 않는다

- **읽을 수 없는 입력이 "빈 입력"과 구별되지 않던 자리 4곳**: 광범위 `except`를 전수 조사했다 — **핸들러 175곳 중 광범위 80곳, 그중 본문에 흔적이 없는 것 33곳**(수정 전 82/39). 다시 읽어보니 **대부분은 조용하지 않았다.** 반환값이나 `failures` 목록으로 호출자에게 넘기고 명령이 나중에 출력한다. 진짜 문제는 실패했을 때의 값이 **정상적인 빈 결과와 똑같아지는** 자리였다
  - `parse_daily_file` — 일지 파일이 안 열리면 0세션. **조용한 하루와 같은 답이다.** 4.8.3이 디코딩 쪽을(`errors="replace"`) 고쳤지만 파일이 안 열리는 경우는 그대로 남아 있었다
  - `read_audit_log` — 감사 로그가 안 열리면 "항목 없음". 세션이 기록됐는지 확인하려고 여는 게 그 파일이다
  - `load_team_config` — 팀 설정이 깨지면 `None`, 즉 "팀이 없음"과 같은 값이라 팀 기능 전체가 설정된 적 없는 것처럼 동작한다
  - `_compute_source_checksum` — 해시 못 뜬 파일을 조용히 빼고 계산한다. **안정적이고 그럴듯한데 자기가 말하는 것보다 적게 덮는 체크섬**이다
  - 넷 다 `logger.warning`으로 파일명과 함께 말한다(기본 레벨이 WARNING이라 바로 보인다). 깨끗한 실행에서는 아무것도 출력하지 않으며, 그것도 테스트로 고정했다

- **드물게 도는 git 헬퍼 2곳에 버그 가드**: `get_branch_for_commit`, `get_diff_stat_for_commits`. 후자는 **한동안 아무도 호출하지 않던 함수**다 — 그런 코드가 광범위 핸들러 안에 있으면 첫 실행의 결함이 "변경 없는 세션"처럼 보인다. `non_fatal`을 적용했다
  - **나머지 `git_info` 6곳은 일부러 놔뒀다.** 매 항목마다 도는 짧은 본문이라 `NameError`는 CI 첫 실행에 죽는다. 어제 세운 기준 그대로다
  - 남은 33곳은 **읽고 남긴 것**이라는 사실을 목록으로 고정했다. 새 침묵 핸들러가 생기면 테스트가 잡고, 목록이 낡아도 잡는다. 스캔이 아무것도 못 찾는 상태로 통과하는 것도 막았다
  - 이전 집계가 두 번 틀렸다. `except json.JSONDecodeError`처럼 **점 있는 예외명(`ast.Attribute`)을 bare로 오분류**해서 85/42가 나왔다. 분류기를 고친 값이 위 숫자다

- **공개 저장소에 개발자의 홈 경로와 실명이 들어가 있던 문제**: `try_run.py`의 docstring이 "transcript 폴더명은 원래 경로로 되돌릴 수 없다"를 설명하면서 **작성자 본인의 `C:\Users\<이름>\...`을 예시로** 썼다. 같은 예시가 `test_try_run.py`에도 있었다. 비ASCII 경로면 무엇이든 같은 요점을 보여주므로 실명이 있을 이유가 없었다
  - 자리표시자 경로로 교체했다. 새 예시가 실제 인코딩과 맞는지 확인하고 적었다 — `C:\Users\홍길동\Desktop\문서\sol\working-diary` → `C--Users-----Desktop----sol-working-diary` (대시 개수가 다르다. 지운 글자 수는 남고 어느 글자였는지는 안 남는다는 게 원래 요점이다)
  - **이미 나간 것은 회수되지 않는다.** 4.10.0의 sdist와 wheel에 그대로 들어 있고 GitHub에도 있다. 다음 버전부터 사라진다
  - 재발 방지 테스트를 붙였다. **테스트에 이름을 박으면 자기모순이므로**, 실행 중인 기계의 홈 디렉터리를 런타임에 구해 추적 파일이 그걸 인용하는지 본다. CI에서는 그 경로가 나올 일이 없어 사실상 no-op인데 그게 맞다 — 이 실수는 CI가 아니라 노트북에서 난다
  - 유출은 docstring 안이라 백슬래시가 이중(`C:\\Users\\...`)이다. 그대로 찾으면 안 걸리므로 비교 전에 구분자를 정규화한다. **가드가 실제로 보는지도 테스트로 고정했다**
  - 첫 검증에서 "안 잡힌다"고 나왔는데 원인은 가드가 아니라 **심어놓은 유출이 파일에 적용되지 않은 것**이었다. 적용 전후를 찍어 다시 확인했다 (`before: False → after: True`)

### Added

- **태그를 밀면 릴리스 노트가 같이 발행된다**: `release.yml`은 `v*` 태그에 PyPI만 올렸고 릴리스 노트는 아무것도 만들지 않았다. 그래서 **태그 18개에 릴리스 0개**였다. 2026-08-14에 CHANGELOG 섹션을 그대로 옮겨 18개를 손으로 채웠지만, **손으로 채운 건 다음 릴리스에 다시 벌어진다** — 자동인 쪽(배포)과 수동인 쪽(노트)이 갈려 있는 게 원인이었다
  - `scripts/changelog_section.py`가 CHANGELOG에서 해당 버전 섹션을 꺼낸다. **요약하지 않고 원문 그대로** — 요약은 따로 관리해야 하는 두 번째 사실이 된다
  - **섹션이 없으면 빈 릴리스를 만들지 않고 실패한다.** 그리고 이 단계는 **빌드·배포보다 앞에 둔다**: CHANGELOG에 없는 버전을 태그하면 PyPI에 올라가기 전에 멈춰야 한다. PyPI 버전은 되돌릴 수 없고 릴리스 제목은 언제든 고칠 수 있다
  - **제목에 CHANGELOG 날짜를 넣는다** (`v4.10.0 — 2026-08-13`). GitHub은 생성 시각을 찍으므로, 소급해 만든 릴리스에서는 제목이 실제 출시일이 남는 유일한 자리다
  - 릴리스 생성은 배포 **뒤**다. 아무도 설치할 수 없는 버전을 발표하지 않는다. 실패한 워크플로를 재실행하는 경우가 정확히 릴리스가 이미 있는 상황이라, 있으면 만들지 않고 고친다
  - 회귀 테스트 23개. **절반이 배선에 대한 것이다** — 스크립트가 완벽해도 워크플로가 호출하지 않으면 노트 없이 나간다. 4.10.0의 드리프트 결함이 테스트 17개를 통과한 채 하루를 버틴 이유가 그것이었다. 호출 순서(추출이 배포보다 앞, 생성이 배포보다 뒤)도 고정한다
  - `pyproject.toml`의 버전에 CHANGELOG 섹션이 있는지도 검사한다. 태그를 밀기 전, 버전을 올리는 PR에서 걸린다
  - **가드 4개를 하나씩 되돌려 해당 테스트가 실제로 실패하는 것을 4/4 확인했다.** 첫 시도에서 한 개가 통과해버렸는데, 원인은 단정이 스크립트 **이름**만 찾고 있어서였다 — 주석 한 줄로도 만족되는 검사였다. 파일을 만드는 호출 자체를 집도록 고쳤다
  - 에러 메시지를 stderr에 UTF-8로 강제한다. 경로에 한글이 들어가면(이 프로젝트의 개발 기계가 그렇다) 레거시 코드페이지에서 **릴리스가 멈춘 이유를 읽을 수 없었다**


## [4.10.0] - 2026-08-13

> **한 줄 요약**: 아직 어디에도 전달되지 않은 내보내기 큐가 조용히 지워지고
> 있었습니다. 그리고 그걸 찾아낸 방법 — "실패를 삼키는 것과 버그를 삼키는 것을
> 구분한다" — 이 이번 릴리스의 나머지 전부입니다.
>
> 눈에 띄는 것:
>
> - **`.export_queue.json`이 실제로 데이터를 잃고 있었습니다.** 손상되면 큐 전체가
>   지워졌고(20건 → 1건), 동시에 끝나는 훅끼리 서로를 덮어썼습니다(40개 중 26·26·19건
>   도착). 일지 옆 다섯 개 상태 파일 중 잠금·원자적 쓰기·손상 보존을 못 받은 유일한
>   파일이었습니다
> - **`diary-notion push` 끝의 미결 작업 요약이 4.9.0 이후 한 번도 출력되지
>   않았습니다.** `--force`를 준 push에서만 동작했습니다
> - **읽을 수 없는 일지 파일이 이제 이름과 함께 보고됩니다.** 그동안 `reindex`는
>   "2건 색인함", `search`는 결과 누락, `delete --session`은 "찾을 수 없음"이라고
>   답했고 전부 진짜 답과 구별되지 않았습니다
> - 새 명령은 없습니다. 설정 변경도 없습니다

### Added

- **어시스턴트 답변을 원문 그대로 기록**: 일지는 요청은 적고 답변은 **키워드가 든 문장 조각**만 적었다. 그 조각내기가 마침표마다 잘라서 `run-local.sh`를 `run-local`과 `sh` 두 줄로 만들었고, 실측 32,887개 요약 줄 중 **5,800개(17.6%)**가 그런 식으로 훼손돼 있었다
  - **자르지 않는다.** 턴 단위로 재보니 어시스턴트 텍스트는 턴당 중앙값 1,650자, 최대 4,735자다. 자를 이유가 없고, 조용히 자르는 건 이번 릴리스가 없앤 습관이다
  - 도구 호출 사이의 진행 멘트("상황부터 파악하겠습니다.")는 뺀다 — 한 세션 기준 중앙값 61자짜리 블록들이고 답변이 아니다. 기준은 길이 하나(120자)이고 테스트가 경계를 고정한다
  - **4.9.0의 턴 단위 기록이 있어야 가능한 기능**이다. 세션 단위였다면 세션 하나의 답변 전체가 그 세션이 만든 항목 수백 개에 전부 복사됐다
  - **시크릿 스캐너에 추가했다.** 답변은 명령 출력·파일 내용·설정을 그대로 인용하고, 프롬프트와 달리 통째로 보관된다
  - `_extract_summary_hints` 제거. `summary_hints` 필드는 스키마에 남는다 — `write --input`이 에이전트가 쓴 JSON에서 받는다. 훅이 만들어내지 않을 뿐이다

### Fixed

- **`diary-notion push`의 미결 작업 요약이 `--force`일 때만 출력되던 문제**: 호출부가 `--force` 분기 안에서만 바인딩되는 `db_id`를 읽었다. 일반 push에서는 `NameError`가 나고 그것을 `except Exception`이 debug 로그로 삼켜서, 4.9.0에 실려나간 뒤로 **한 번도 출력된 적이 없다**
  - 기존 테스트 17개가 전부 요약 함수를 직접 호출해서 배선이 덮이지 않았다. `push`를 끝까지 도는 테스트를 `--force` 유무 양쪽으로 추가했다
  - 이 프로젝트에서 오늘만 네 번째인 모양이다 — **코드는 있는데 그 경로가 실행된 적 없음**

- **버그를 조용히 삼키던 예외 처리**: 위 결함을 하루 동안 감춘 건 `db_id`가 아니라 그걸 잡은 `except Exception` + `logger.debug`다. 기본 로그 레벨이 WARNING이라 매 push마다 적히고 아무도 읽지 않았다
  - `NameError`만 갈라낸다. 죽은 네트워크·바뀐 Notion 응답·깨진 파일은 전부 `OSError`/`KeyError`/`TypeError`로 오고 **이 패턴은 그것들을 흡수하려고 있는 것**이다. 해석되지 않는 이름은 데이터로는 절대 생기지 않는다 — 항상 이 프로그램의 결함이다
  - 그래서 `NameError`(와 그 하위 클래스 `UnboundLocalError` — 4.9.0 결함이 정확히 이 모양이었다)만 stderr에 "BUG" 한 줄을 남긴다. 나머지는 그대로 조용하다. **어느 쪽이든 명령을 중단시키지 않는다** — 행은 이미 Notion에 쓰인 뒤다
  - 그 한 줄 자체가 명령을 깨뜨리지 않는지도 확인했다. ASCII 콘솔에 한국어가 섞인 예외 메시지를 인쇄하면 `UnicodeEncodeError`가 나고, 그건 예외 핸들러 안이라 갈 곳이 없다. 실측으로 재현한 뒤 폴백을 넣었다
  - 적용 범위는 드리프트 요약 3곳. 저장소 전체에는 **아무 흔적도 남기지 않는 광범위 핸들러가 22곳** 더 있다(51곳 중 26곳은 호출자에게 메시지를 넘긴다). 별건이다

- **`.export_queue.json`이 잠금·원자적 쓰기·손상 보존을 전부 안 갖고 있던 문제**: 위 22곳을 하나씩 읽다가 나왔다. 이 파일은 일지 옆에 두는 **다섯 번째 상태 파일**이고, 나머지 넷(일지 `.md`, `.session_counts.json`, `.diary_index.json`, `.session_progress.json`)이 4.8.2~4.8.3에서 받은 처리를 유일하게 못 받았다. 하필 **아직 어디에도 전달되지 않은 작업**을 담는 파일이다
  - **손상되면 큐가 지워졌다.** 잘린 20건짜리 큐 → 읽기 실패 → `queue = []` → 1건 추가 → 통째로 덮어쓰기 = **19건 소실**. 실측했다. 이제 `.corrupt`로 보존하고 경고한다 (인덱스·카운터와 같은 규칙)
  - **동시 쓰기에 잠금이 없었다.** 별도 프로세스 40개 → **26, 26, 19건 도착**(3회 반복). `FileLock`을 붙여 3회 모두 40/40
  - 쓰기를 원자적으로 바꿨다. 애초에 큐가 잘리지 않게 하는 쪽이 위 복구보다 낫다
  - `retry_queued`가 손상된 큐를 만나면 조용히 return만 해서 **그 뒤로 영영 재시도가 안 됐다.** 이제 보존하고 스스로 회복한다
  - 재시도는 잠금을 놓고 도는데(내보내기는 네트워크 호출이고, 느린 재시도 하나가 한 줄 추가하려는 훅을 붙잡으면 안 된다), 그래서 다 돌고 나서 **덮어쓰지 않고 병합한다** — 그 사이 들어온 항목은 우리가 지울 것이 아니다

- **Windows에서 경합 중 파일 잠금이 스스로 풀리던 문제**: 4.8.3이 `EACCES`를 "이 디렉터리는 잠금 파일을 못 만든다"로 보고 즉시 포기하게 만들어 20.2초 멈춤을 0.1초로 줄였다. 그런데 **Windows는 다른 프로세스가 삭제 중인 잠금 파일에도 `EACCES`를 준다**
  - 쓰기 가능한 디렉터리에서 12개 프로세스가 3,600번 시도 → **`EACCES` 65번(1.8%)**. 그때마다 "디렉터리 쓰기 불가"로 판단하고 **잠금 없이 진행**했다. 잠금이 필요한 바로 그 순간에
  - `EACCES`를 받으면 디렉터리에 실제로 파일을 만들 수 있는지 한 번 물어보고, 만들 수 있으면 경합으로 보고 기다린다. 못 만들면 종전대로 즉시 포기 — **쓰기 불가 디렉터리는 여전히 0.00초**
  - **다만 이걸로 항목이 실제 소실된 사례는 만들지 못했다.** 일지 파일에 프로세스 40개를 붙여도 수정 전후 모두 40/40이었다. 두 프로세스가 동시에 잠금을 놓쳐야 손실이 나므로 확률이 낮다. **잠재적 구멍이지 측정된 손실이 아니다**
  - 기존 테스트가 이 수정을 잡았다. `.lock`으로 끝나는 경로만 거부하도록 흉내내고 있었는데, 잠금 파일을 거부하는 디렉터리는 모든 파일을 거부한다 — 흉내 쪽이 비현실적이었다

- **읽을 수 없는 일지 파일이 아무 말 없이 사라지던 문제**: `*.md`를 훑는 명령 셋이 `except Exception: continue`였다. 그 뒤에 내놓는 답이 진짜 답과 구별되지 않았다
  - `reindex`: 3일 중 하루를 못 읽으면 **"2건 색인함"**. 그 하루는 검색·통계·인덱스 기반 집계에서 통째로 빠지는데 아무 표시가 없었다
  - `search`: 3개 파일에 있는 키워드가 **2건**으로 나왔다. "결과 없음"과 "열 수 있었던 파일에는 결과 없음"은 다른 답이다
  - `delete --session`: 못 읽은 파일에 그 세션이 있어도 **"찾을 수 없음"**. 사실과 반대되는 유일한 답이라 특히 나쁘다
  - 셋 다 이제 건너뛴 파일 수와 이름을 말한다. 깨끗한 실행에서는 아무것도 출력하지 않는다
  - 핸들러가 잡는 `OSError`를 주입해 재현했다. 소유자에게는 `icacls` 거부가 먹지 않아 실제 권한으로는 만들 수 없었다

- **드물게 도는 경로 두 곳에 버그 가드 적용**: `collect_git_info`(실패하면 모든 항목에서 git 정보가 통째로 빠진다)와 `_supplement_from_git`(transcript가 비었을 때만 도는 폴백)
  - 인덱스 저장 실패도 이제 말한다. 일지 쓰기를 막지 않는다는 원래 판단은 맞지만, 조용히 실패하면 그 뒤로 검색이 **낡은 인덱스에서 답한다.** 결과 없음과 구별되지 않는다
  - 남은 광범위 핸들러에 일괄 적용하지 않았다. **`non_fatal`이 잡는 건 `NameError`고, 짧고 매번 실행되는 함수 본문에서 그건 CI 첫 실행에 죽는다.** 드리프트 결함이 하루를 버틴 건 본문이 아니라 **호출부가 안 덮여 있어서**였다. 그러니 값어치가 있는 자리는 "드물게 도는 코드가 광범위 핸들러 안에 있는 곳"이지 모든 `except Exception`이 아니다


## [4.9.0] - 2026-08-13

> **업그레이드 노트 — 기록 단위가 바뀝니다**
>
> 이 버전부터 일지 항목 하나가 **그 턴**을 담습니다. 지금까지는 Stop Hook이
> 턴마다 뜨면서 매번 transcript를 처음부터 읽고 앞 5개 요청을 적었고, 그 결과
> 실측한 일지에서 항목의 **85%가 같은 세션 안 앞 항목의 복사본**이었습니다.
>
> 올린 직후 눈에 띄는 것:
>
> - **진행 중이던 세션의 첫 턴은 아무것도 기록되지 않습니다.** 그 세션이 어디까지
>   기록됐는지 표시해두는 단계라 의도된 동작입니다. 다음 턴부터 정상입니다.
>   새 세션은 해당 없습니다
> - **하루 항목 수가 줄어듭니다.** 사라지는 건 중복이고, 그동안 기록되지 않던
>   6번째 이후 요청이 대신 들어옵니다
> - **이전 항목은 그대로 둡니다.** 6,971개 중 85%가 중복이지만, 다시 만들려면
>   원본 transcript가 필요하고 그중 65%는 이미 없습니다
> - `~/working-diary/.session_progress.json`이 새로 생깁니다. 세션당 한 줄이고,
>   transcript가 사라진 세션은 스스로 정리합니다
> - **변경 전후로 항목 수·라인 수 통계는 비교할 수 없습니다.** 과거 값은 부풀려진
>   채 남습니다

### Fixed

- **README가 안내하는 Claude Code 플러그인 설치가 처음부터 동작하지 않던 문제**: 이 프로젝트가 광고하는 배포 경로는 둘(PyPI, Claude Code 플러그인)인데 후자가 끝에서 끝까지 막혀 있었다. 4.8.1에서 고친 "Windows에서 안 되는 안내문"과 같은 유형 — 독자의 기계에서 실행되지 않는 지시문이다
  - `/plugin marketplace add`는 저장소 루트의 `.claude-plugin/marketplace.json`을 읽는데 **그 파일이 없었다.** 첫 줄에서 실패한다
  - `plugin.json`의 `dependencies`가 `{"python": ">=3.8"}` 였다. 스키마는 배열을 받는다. 인식되는 필드의 타입이 틀리면 경고가 아니라 **로드 실패**다 — 설치에 성공해도 훅이 안 붙는다
  - `hooks`가 `"hooks.json"` 이었다. 이 경로는 플러그인 루트 기준인데 파일은 `.claude-plugin/` 안에 있어서 로더가 못 찾는다. `./.claude-plugin/hooks.json` 으로 고쳤다
  - `claude plugin validate . --strict` 기준 **에러 3건·경고 1건 → 통과**
  - 마켓플레이스 이름은 `solzip`이라 설치 명령이 `/plugin install agent-diary@solzip` 이다. README(EN/KO) 둘 다 갱신
- **기존 테스트가 깨진 값을 고정하고 있던 문제**: `test_codex_plugin.py`가 `assert data["hooks"] == "hooks.json"` 으로 리터럴을 박아둬서, 런타임이 해석하지 못하는 경로를 **초록불로 지키고 있었다.** 경로가 실제 파일로 해석되는지 검사하도록 바꿨다

### Added

- **항목 하나가 세션의 앞부분이 아니라 그 턴을 담는다**: Stop Hook은 세션 끝이 아니라 **어시스턴트 턴마다** 뜬다. 그런데 매번 transcript를 **1줄부터** 다시 읽고 **앞 5개** 요청을 썼다. 턴 1도 요청 1~5, 턴 400도 요청 1~5 — **6번째 요청은 영원히 기록되지 않았다**
  - 실측: 항목 6,971개 중 **5,904개(85%)가 같은 세션 안 앞 항목의 복사본**. 한 세션은 400개 중 395개가 복사본이었다
  - 이 도구에서 나온 모든 절대 수치가 여기서 부풀려졌다 — "하루 132세션"은 턴이었고, 라인 증감 -1,547,143은 작업 트리 하나를 턴마다 다시 센 것이며, 완료율 3.3%는 한 작업이 수백 번 복제돼 전부 미결로 남은 것이다
  - **지난 턴이 멈춘 줄부터 읽는다.** transcript가 append-only임을 먼저 확인했다 — 라이브 파일의 앞 100·500·1,000·2,000줄 sha256을 뜨고, 턴을 하나 보내 22줄이 늘어난 뒤 다시 떠서 **전부 동일**
  - 위치는 `.session_progress.json`에 세션당 한 줄. 검색 인덱스(재구축되면 위치를 잃는다)와 audit 로그(줄 수가 없어 3.4MB를 매 턴 훑어야 한다)를 쓰지 않은 이유를 코드에 적었다
  - 카운터·일지와 **같은 `FileLock`**. 읽고-고치고-쓰기라 두 세션이 같은 초에 끝나면 유실된다
  - **위치는 항목이 디스크에 쓰인 뒤에만 전진한다.** 쓰기가 실패하면 그 턴 분량은 다음 턴이 담는다
  - **업그레이드 시드 규칙**: 저장된 위치가 없는데 일지에 이미 그 세션 항목이 있으면, 현재 길이로 시드하고 그 턴은 아무것도 안 쓴다. 없으면 마지막에 거대한 중복을 하나 더 쓴다
  - 사라진 transcript는 정리한다. 이 일지에선 세션의 65%가 이미 원본이 없다
  - **`formatter.py`의 `prompts[:5]` 제거.** 잘라내는 지점이 파서가 아니라 포매터였다 — 파서만 고치면 한 턴에 프롬프트가 6개일 때 여전히 5개에서 잘린다
  - 검증: 실제 3,165줄 transcript를 턴 단위로 재생 → 요청이 있는 항목 43개 중 **내용 복사본 0**. 남은 2건은 `[Request interrupted by user for tool use]`가 실제로 3번 들어온 것이고, 8건은 프롬프트 없이 도구만 쓴 턴이다

- **프로젝트 이름을 저장소 루트로 정규화**: 세션은 한 디렉터리에 머물지 않는다. 가장 큰 transcript 20개 중 **17개**가 여러 `cwd`를 기록하고 한 개는 26종류다 — 하위 폴더로 `cd` 할 때마다 늘어난다. 그런데 프로젝트 이름은 경로의 **마지막 조각**에서 나왔다
  - 실측: transcript에 등장한 디렉터리 중 지금 존재하고 저장소인 89개에서, **75%가 마지막 조각 ≠ 저장소**
  - `936회 harness → _verification`, `827회 dev → erp_chatbot_solzip`, `180회 docs → LottoMap_back`
  - 지금 일지에서 틀린 이름은 **4%(6,977개 중 253개)** 뿐이다. 대부분의 턴이 프로젝트 루트에서 기록되고 하위 폴더로 들어간 턴만 어긋나기 때문이다. **이 비율은 일지가 경로를 드물게 표집하는 동안만 유지된다**
  - `git rev-parse --show-toplevel`로 해결. 저장소가 아니면 지금처럼 폴더 이름을 쓴다
  - 일지와 Notion 양쪽에 같은 규칙을 적용했다. 한쪽만 고치면 로컬은 `erp_chatbot_solzip`, Notion은 `dev`가 된다

- **`agent-diary try`**: 무엇이 기록될지 보려면 기록하게 두는 수밖에 없었다. 뻔한 방법 — `CLAUDE_DIARY_DIR`을 바꿔서 훅을 돌리는 것 — 은 **동작하지 않는다.** `config.json`이 환경변수를 이기도록 설계돼 있어서 일지 경로는 `init`이 쓴 값 그대로고, 시험 실행이 실제 일지에 쌓인다
  - 가설이 아니다. 이 프로젝트의 테스트가 이 함정에 **두 번** 걸렸고, 한 번은 5개월치가 든 일지에 5건을 썼다
  - `try`는 **Claude Code가 부르는 바로 그 진입점**(`python -m claude_diary.hook`)을 임시 디렉터리를 가리키는 세 변수와 함께 띄운다: `APPDATA`·`XDG_CONFIG_HOME`(설정을 못 찾게), `CLAUDE_DIARY_DIR`(일지가 샌드박스로)
  - **설정이 없으면 exporter도 없다.** 이게 가장 중요하다 — 시험 실행이 남의 Notion DB에 행을 밀어넣으면 안 된다
  - 인자를 안 주면 **이 디렉터리의 최근 transcript**를 쓴다. 폴더 이름이 아니라 transcript 안의 `cwd`로 찾는다. Claude Code는 경로의 비ASCII 문자를 전부 `-`로 접어서 `C--Users----Desktop----sol-working-diary`로 만들기 때문에 이름으로는 되돌릴 수 없다
  - 항목을 출력하고 디렉터리를 지운다. 훅이 죽어도 지운다
  - **서브에이전트 transcript는 고르지 않는다.** 서브에이전트도 각자 transcript를 갖는데 그건 세션이 아니라 조각이다 — `backfill`이 처음부터 제외해온 것(실측 194개 중 115개). 첫 버전은 이걸 안 걸러서 실제로 서브에이전트 조각 하나를 골랐다. 파일명 `agent-` 접두사(파일을 안 열고 판단)와 `agentId` 필드 두 신호를 함께 쓴다
  - transcript를 못 찾으면 **이유를 말한다.** 흔한 원인은 프로젝트 이동이다 — transcript는 실행된 경로를 기록하므로, 옮긴 뒤에는 그곳에서 세션을 한 번 더 하기 전까지 매칭되지 않는다

- **`변경 통계`가 세션이 한 일이 아니라 커밋 안 한 작업 트리를 재던 문제**: `git diff --stat HEAD`, 즉 **세션 종료 시점의 미커밋 상태**를 재고 있었다. 같은 이름을 쓰는 다른 값이고, 세 방향으로 틀렸다
  - 일을 다 커밋한 세션은 트리가 깨끗해서 **0으로 기록**된다
  - 생성 파일이 미커밋으로 쌓인 저장소는 그 더미를 **세션마다 다시** 기록한다. 프로젝트 단위로 합치면 작업 트리 하나를 수백 번 센 값이 나온다 — 실측 `erp_chatbot_solzip` 누적 **-1,547,143줄**
  - `session_start` 인자를 받아놓고 쓰지 않아서, 호출자가 요청한 구간이 아무 효과가 없었다
  - 이제 **그 세션의 커밋들**로 잰다. `get_diff_stat_for_commits`가 이미 있었고 **Notion push 경로는 그걸 쓰고 있었다** — 일지 경로만 안 쓰고 있었다
  - 커밋이 없으면 0이다. 그게 정직한 값이고("남긴 것 없음"), 커밋 없이 파일만 바꿨는지는 세션 결과 축이 이미 기록한다
- **`docs/notion-views.md` 정정**: 이 저장소에 **Notion Views API 클라이언트(`notion_views.py`, 539줄)가 이미 있고 `diary-notion ensure`가 뷰 5개를 만들고 검증한다**. 그런데 문서는 "API로 뷰를 만들 수 없으니 손으로 만들라"고 적혀 있었다 — 코드를 확인하지 않고 쓴 내용이다
  - 실제로 관리되는 뷰(작업 계층·오늘 작업·Blocked·전날 미완료·작업 그룹별)와 각각의 필터·정렬·표시 속성을 적었다
  - `ensure`가 **뷰를 지우지 않는다**는 것도 적었다. 은퇴한 뷰 5개는 경고로만 알린다 — 사용자가 커스터마이즈한 레이아웃을 버릴 수 있어서
  - 손으로 추가할 값어치가 있는 두 개(Stale, No task group)는 관리 대상이 아닌 이유와 함께 남겼다

- **transcript 상한 2000줄 제거 — "모두 기록"이 실제로는 67%였다**: 파서가 앞에서부터 2000줄만 읽고 멈췄다. 로컬 코퍼스 91개 109,274줄 중 **72,939줄(67%)만 읽히고 있었다.** 상한에 걸리는 파일이 22%, 가장 긴 세션은 9,465줄 중 **21%만** 기록됐다
  - 잘려나가는 건 항상 **세션의 뒷부분** — 작업이 마무리된 자리다. 그리고 조용히 잘렸다
  - 마지막 타임스탬프도 틀렸다. 어떤 세션은 일지에 `2026-07-02` 종료로 적혔는데 transcript는 `07-08`까지 이어진다
  - 상한을 둔 이유였던 비용은 실측하니 없었다: 줄 단위로 읽으므로 피크 메모리는 파일 크기가 아니라 **가장 긴 줄**을 따라가고, 28MB·9,465줄 파일 전체 파싱이 0.23초다
  - `max_transcript_lines` 설정은 남겨두되, **상한에 걸리면 그 사실을 항목에 적는다.** 자르는 건 선택이지만 조용히 자르는 건 아니다
- **작업 중 발생한 에러를 실제로 기록한다 — "올바르게 작업 중인지"의 재료**: `발생한 이슈` 섹션이 6,921건 중 **20건(0.3%)**에만 있었고, 그 20건마저 작업 중 문제가 아니라 **파서 자신의 실패**였다. 이름이 약속한 것을 하지 않는 섹션이었다
  - 재료는 처음부터 있었다. 실패한 도구 호출은 결과 블록에 `is_error`를 달고 있다. 실제 transcript 20개 표본에서 **20개 전부**가 에러를 갖고 있었고 총 244건이었다
  - 세션당 평균 12건이라 **중복 제거 + 상한 10건**. 에러 텍스트가 대부분인 항목은 작업일지가 아니다
  - `Exit code 1`만 남으면 6주 뒤에 아무 의미가 없어서, 종료 코드 뒤의 실제 메시지를 붙인다
  - **시크릿 스캐너에 `errors_encountered`를 추가했다.** 원시 도구 출력이라 쓰면 안 될 것이 들어갈 가능성이 가장 높은 필드인데 스캔 대상이 아니었다 — 섹션이 비어 있어서 그동안 드러나지 않았다
- **브랜치를 인덱스에 넣고 항목에 실 위치를 찍는다 — "연결성 파악"**: 브랜치는 이 도구가 **지시받는 게 아니라 관측하는** 유일한 세션 간 실이다. 이 일지에 39개 브랜치가 있고 main/master는 15%뿐이라 판별력이 높은데, Markdown에만 적히고 인덱스엔 없어서 **파일을 전부 다시 읽지 않으면 하루를 넘는 작업을 따라갈 수 없었다**
  - 인덱스에 `branch` 추가. `reindex`도 Markdown에서 복원한다 (4.8.0에서 겪은, 재구축이 증분 경로보다 얇아지는 문제를 반복하지 않으려고)
  - 항목의 브랜치 줄에 `(#12)` 형태로 **그 브랜치의 몇 번째 세션인지** 찍는다. 따로 명령을 쳐서 물어봐야 하는 답은 아무도 묻지 않으므로, 읽히는 자리인 일지 안에 넣었다
  - 첫 세션에는 안 붙인다. 뒤에 실이 없는데 번호를 매기면 없는 맥락을 암시한다

- **`task_group` 결손을 push 시점에 드러낸다**: Notion 행을 서로 잇는 유일한 키인데 **62%가 비어 있었다**. 원인은 지침이었다 — "multi-session work용"이라고 적혀 있어서, 이어질 작업인지 아직 모르는 시점에 판단을 미루게 했다. 그건 두 번째 세션이 와야 알 수 있고, 그때는 첫 행이 이미 그룹 없이 기록돼서 **자기 후속과 영원히 연결되지 않는다**
  - 실측: `erp_chatbot_solzip` 239건 중 222건(93%), `working-diary` 21건 중 15건이 그룹 없음
  - push 요약에 `no task group` 건수와 **그 프로젝트에서 이미 쓰이는 그룹 이름**을 함께 출력한다. 새 이름으로 기록된 후속은 후속이 아니므로, 다음 push가 고를 어휘를 보여준다
  - 절반 넘게 비어 있으면 힌트 한 줄
  - **오류가 아니라 경고다.** 여기서 push를 거부하면 기록 자체가 사라진다. 연결 안 된 행이 없는 행보다 낫다 — 이 프로젝트가 매번 해온 것과 같은 선택
  - 스킬 지침을 "항상 지정한다"로 바꿨다. `skills/diary-notion/SKILL.md`와 `setup.py`의 내장 상수 양쪽 — 둘이 갈라지면 에이전트 둘이 서로 다른 계약을 따르고 런타임에 아무도 눈치채지 못한다 (기존 테스트가 이걸 잡아줬다)

- **`diary-notion push` 끝에 그 프로젝트의 미결 작업 요약 출력**: 이 숫자들은 `diary-notion ops`가 이미 전부 계산하고 있었다. 문제는 아무도 안 본다는 것 — 실측하니 `push`가 2,286회 도는 동안 `notion` 계열은 18회였다. **탐지 수단이 없는 게 아니라 보는 자리에 없었다**
  - 실제 데이터가 왜 필요한지 말해준다: active 476건 중 **7일 이상 방치 441건(93%), 리뷰 대기 218건, next action 없음 125건**. 완료율은 `erp_chatbot_solzip` 5.9%, `_verification` 3.3%, `solarchive` 0%
  - 방금 push한 프로젝트만 조회한다. 필터 없이 전체를 받으면 push마다 6번 페이지네이션이 붙는다
  - **0인 신호는 출력하지 않는다.** 매번 같은 모양으로 0이 늘어서면 읽지 않게 되고, 그러면 이 요약이 막으려던 실패를 그대로 반복한다
  - 힌트는 드물게만 붙인다 (미결 20건 이상 + 완료율 10% 미만 / blocked 존재 / 리뷰 대기 10건 이상)
  - **push를 절대 깨뜨리지 않는다.** 이 시점엔 행이 이미 Notion에 쓰여 있어서, 요약이 예외를 던지면 성공한 push가 실패한 명령이 된다
  - `query_database_rows`에 선택적 필터 인자 추가

- **`stats`에 커밋 타입 축 추가**: 지금까지 통계의 유일한 축은 `categories`였는데, 그건 대화에 등장한 단어로 **추측한** 값이다. 커밋 prefix는 추측이 아니라 작성자가 **선언한** 작업 종류다
  - 실측(일지 6,906건): 커밋이 붙은 항목 46%, 그중 92%가 Conventional prefix를 가진다. 둘 다 있는 항목에서 **키워드 분류와 커밋 타입의 일치율은 65%**
  - 어긋나는 방향이 한쪽으로 쏠린다. `test`를 키워드는 1,231건 잡는데 `test:` 커밋은 325건뿐 — **약 4배 과다 계상**이다. 버그를 고치면서 "테스트 통과"라고 말하기만 해도 그 세션이 테스트 작업으로 분류된다
  - **대체하지 않고 나란히 보여준다.** 커버리지가 46%라 대체하면 틀린 숫자를 없는 숫자로 바꾸는 셈이다. 대신 두 블록에 각각 출처를 적는다 — 위는 `guessed from the conversation`, 아래는 `declared, N commits from M of K sessions`
  - **단위가 다르다는 것을 표기에 넣었다.** 위는 세션을 세고 아래는 커밋을 센다. 이걸 안 적으면 아래 숫자가 크다는 이유로 잘못된 결론이 나온다
  - 명세에 없는 prefix도 센다. 실제 일지에 `copy:`·`memory:`·`temp:`·`content:`·`blog:`가 쓰이고 있고, 도구가 남의 prefix를 가짜라고 판정할 근거가 없다
- **`stats`에 세션 결과 3분할 추가**: 커밋 타입 축은 전체의 46%만 덮는데, 나머지가 무엇인지 보여줄 자리가 없어서 "통계에 없는 세션"이 돼버렸다. 조사·독해만 한 세션도 결과를 남겨야 한다는 요구에서 출발했다
  - 실측(6,921건): **커밋함 46.3% / 파일은 바꿨는데 커밋 안 함 50.5% / 아무것도 안 바꿈 3.3%**
  - 예상과 달랐다. 커밋 타입이 못 보는 54%의 대부분은 조사가 아니라 **커밋하지 않은 작업**이었고, 순수 조사는 227건뿐이다
  - 세 구분 모두 **관측된 사실**이다 — 커밋이 있거나 없거나, 파일을 건드렸거나 아니거나. 키워드로 추측하는 `categories`와 성격이 다르다
  - 아무것도 안 바꾼 세션은 누락이 아니라 `investigation only`라는 **결과**로 적는다. 읽고 판단한 것도 결과다
  - 기록 자체는 이미 남고 있었다는 것도 확인했다 — 커밋 없는 세션의 98%가 '작업 요약'을 갖고 있다. 문제는 기록이 아니라 통계에서의 비가시성이었다
- `lib/conventional.py`: 커밋 타입 판정을 한 곳으로 모았다. gitmoji(4.6.0)와 이번 통계가 각자 정규식을 갖게 되면, **일지 줄에는 이모지가 붙는데 통계에는 안 잡히는** 커밋이 생긴다

### Changed

- **PyPI 페이지 사이드바에 Changelog·Documentation·Issues 추가**: `[project.urls]`가 Homepage·Repository 둘뿐이라, 대부분의 방문자가 보는 유일한 페이지에서 **무엇이 바뀌었는지·어디에 신고하는지·왜 이렇게 만들었는지로 가는 경로가 없었다**
- **`Operating System :: OS Independent`, `Topic :: Utilities` classifier 추가**: CI가 3개 OS를 전부 도는데 그 사실이 패키지 메타데이터에는 없었다

### Added

- 패키지 메타데이터 테스트 12개 (`test_package_metadata.py`). PyPI 페이지의 주장이 저장소의 실제와 맞는지 검사한다 — 사이드바 링크가 가리키는 파일이 실재하는지, **classifier가 주장하는 파이썬 버전 집합이 CI 매트릭스와 정확히 같은지**(주장은 지원 선언이고 매트릭스는 검증된 것이다), `requires-python`이 최저 테스트 버전과 맞는지
  - 되돌리기 검증 4/4 (링크 제거·없는 파일 지목·테스트 안 하는 3.13 주장·OS Independent 제거 전부 빨간불)
- 매니페스트 회귀 테스트 17개 (`test_plugin_manifests.py`). `claude plugin validate --strict`가 진짜 검사지만 CI에는 Claude Code가 없으므로, 실제로 깨졌던 불변식을 파이썬으로 못 박는다 — 마켓플레이스 필수 필드, 상대 경로가 실재하는지, 로드를 막는 타입, **README의 설치 명령이 매니페스트가 정의한 마켓플레이스·플러그인 이름과 일치하는지**, 세 곳의 버전 일치
  - 되돌리기 검증 5/5 (마켓플레이스 삭제·타입 되돌림·경로 되돌림·README 드리프트·버전 불일치 전부 빨간불)

## [4.8.3] - 2026-08-12

4.8.2가 "아직 검증 안 한 것"으로 남겨둔 네 가지 — 디스크 가득 참·쓰기 권한 거부, 손상된 `config.json`과 잘린 파일, 아주 큰 transcript, 인코딩이 깨진 transcript — 를 실제로 재현했다. 성능은 문제가 없었고(단일 파일 300MB까지 이상 없음, 피크 메모리는 파일 크기가 아니라 **가장 긴 줄의 약 2배**), 대신 데이터가 사라지는 경로가 여섯 개 나왔다.

### Fixed

- **일지 파일이 문자 중간에서 잘리면 그 날 전체가 사라지던 문제**: 일지는 UTF-8 텍스트로 append 되는데 디스크가 차면 커널은 문자 경계가 아니라 바이트 경계에서 멈춘다. 한글 한 글자의 절반이 남으면 파일 전체가 디코딩 불가가 되고, `parse_daily_file`은 이걸 `except Exception: return stats`로 삼켜 **0세션**을 돌려줬다. `reindex`는 그 0을 보고 하루를 통째로 건너뛴다
  - 실측: 항목 4개가 눈에 그대로 보이는 파일에서 `parse_daily_file` 0, `reindex` 0
  - **쓰기 쪽** — append가 실패하면 이전 길이로 되돌린다. 쓰던 항목 하나를 잃는 건 받아들이지만 하루를 잃는 건 아니다
  - **읽기 쪽** — 프로세스가 중간에 죽으면 되돌릴 주체가 없으므로 `stats`·`indexer`·`search`·`maintenance`도 `errors="replace"`로 읽는다. `backfill`과 `report`는 이미 그렇게 읽고 있었다. **같은 파일을 읽는 경로마다 strict와 replace가 갈려 있던 것**이 결함의 본체였다
  - 수정 후 절단 지점 0·5·33·50·75·95% 전부 파일 무손상, `parse_daily_file`·`reindex` 정상
- **검색 인덱스에 잠금이 없던 문제**: 4.8.2의 잠금이 `append_entry`와 `update_session_count`만 덮고 `update_index`를 빠뜨렸다. 인덱스는 전체를 읽고 하나 더해 전체를 다시 쓰므로, 경쟁하면 마지막 writer가 자기 것만 남기고 **나머지 전부를 버린다**
  - 실측(동시 프로세스 40개): 일지는 40개를 지켰는데 인덱스는 **2개**만 남았다 (12개일 때는 8개)
  - 같은 `FileLock`을 걸고, 쓰기는 임시 파일 + `os.replace`로 바꿨다. 수정 후 12·40개 모두 유실 0
- **인코딩이 깨진 transcript가 세션을 통째로 없애던 문제**: 텍스트 IO는 청크 단위로 디코딩하므로 나쁜 바이트 하나가 **그 앞의 멀쩡한 줄까지** 같이 날렸다. 아무것도 파싱되지 않으면 `has_content`가 거짓이라 `process_session`이 일지 항목도 audit 줄도 남기지 않고 끝난다 — postmortem이 지목한 바로 그 실패 유형, *일지가 안 쌓이는 것은 조용한 하루와 구별되지 않는다*
  - 실측: 정상 6줄 + 나쁜 바이트 1개 → 추출된 프롬프트 **0개**, 일지 항목 0, audit 0
  - `parse_transcript`를 `errors="replace"`로 읽는다. 글자가 깨진 항목은 읽고 고칠 수 있지만 없는 항목은 그럴 수 없다
  - 로컬 transcript 85개(332MB)를 스캔했고 현재 깨진 파일은 0개다. 잠재 위험이지 진행 중인 손실은 아니다
- **`config.json`의 타입 하나가 세션을 잃게 하던 문제**: `"diary_dir": 12345`는 `os.path.expanduser(12345)`에, `"enrichment": "yes"`는 `"yes".get(...)`에 도달했다. 둘 다 쓰기를 감싼 try **바깥**이라 Stop Hook이 exit 1로 죽고 그 세션은 기록되지 않았다
  - 이제 병합 전에 타입을 확인하고 **틀린 키만 버린다**. 기본값으로 치환하지 않는 이유는 그게 유효한 `CLAUDE_DIARY_DIR`까지 덮어썼기 때문 — 이 회귀는 새 테스트가 실제 일지에 항목을 쓰면서 드러났다
- **손상된 `config.json`이 아무 말 없이 기본값으로 떨어지던 문제**: 잘린 파일·빈 파일이 `except: pass`로 삼켜져 **exporter가 경고 없이 꺼지고** 커스텀 `diary_dir`이 기본 경로로 돌아갔다. 일지는 계속 쓰이지만 다른 폴더에, 내보내기 없이. 이제 경고를 남긴다
- **파생 파일이 손상되면 히스토리가 지워지던 문제**: `.diary_index.json`과 `.session_counts.json` 모두 읽기 실패를 빈 dict로 삼킨 뒤 **전체를 덮어썼다**. 손상이 실제 삭제로 승격된다
  - 실측: 잘린 인덱스 5항목 → 세션 1회 만에 1항목. 잘린 카운터는 세 달치가 하루치로
  - 이제 읽을 수 없는 파일은 `.corrupt`로 옮겨 바이트를 남기고 경고한다. 인덱스는 `reindex`로 복구되고, 카운터는 최소한 손실이 보인다
- **쓸 수 없는 디렉터리에서 Stop Hook이 20초를 붙잡던 문제**: 잠금 획득 실패를 한 종류로 취급해서, 잠금 파일을 **만들 수 없는** 경우에도 경합인 줄 알고 타임아웃을 다 기다렸다. 잠금 두 개 × 10초
  - `EEXIST`(누가 쥐고 있음, 기다릴 가치 있음)와 `EACCES`/`EPERM`(만들 수 없음, 기다려도 안 됨)을 구분한다. 실측 20.2초 → **0.1초**
- **`load_config()`가 모듈 전역 기본값을 오염시키던 문제**: `dict(DEFAULT_CONFIG)`가 얕은 복사라 `_deep_merge`가 중첩 dict를 그대로 수정했다. `enrichment.git_info: false`가 든 설정을 한 번 읽으면 그 프로세스에서 "기본값"의 의미가 바뀐다
- **실패한 임시 파일이 쌓이던 문제**: `.session_counts.json.tmp<pid>`가 pid마다 다른 이름이라 쓰기가 실패할 때마다 남았다. 이제 정리한다

### Added

- 회귀 테스트 43개 (`test_partial_writes.py`, `test_index_concurrency.py`, `test_damaged_inputs.py`). 동시성 테스트는 4.8.2와 같은 이유로 스레드가 아니라 **별도 프로세스**로 돈다
- **테스트가 진짜인지 확인했다.** 수정 8개를 하나씩 되돌려 해당 테스트가 실제로 실패하는 것을 8/8 확인했다

## [4.8.2] - 2026-08-12

### Fixed

- **동시에 끝난 세션의 일지 항목이 사라지던 문제**: Stop Hook은 세션이 끝날 때마다 **별도 프로세스**로 실행되는데, 일지 쓰기에 잠금이 없었다. `append_entry`는 헤더를 exists-then-create로 쓰고(둘 다 쓸 수 있음) 수 KB짜리 append도 원자적이지 않았으며, `update_session_count`는 잠금 없는 read-modify-write였다
  - 실측(12개 동시 프로세스): **항목 12개 중 9개만 기록**, session id 10개, 카운터는 4
  - 표준 라이브러리만으로 된 잠금 파일(`O_CREAT | O_EXCL`)을 도입. `fcntl`/`msvcrt`는 플랫폼마다 동작이 달라 쓰지 않았고, 코어 의존성 0 규칙도 지킨다
  - **죽은 잠금은 기다리지 않고 깬다** — hook이 잠금을 쥔 채 죽으면 이후 모든 세션이 막힌다. 항목 하나 잃는 것보다 영원히 멈추는 게 나쁘다
  - **잠금 획득 실패는 예외가 아니라 경고 후 진행** — 일지는 best-effort고, 여기서 예외를 던지면 막으려던 유실이 그대로 일어난다
  - `update_session_count`는 임시 파일에 쓰고 `os.replace` 하므로 쓰기 도중 죽어도 잘린 파일이 남지 않는다
  - 회귀 테스트는 스레드가 아니라 **별도 프로세스**로 돈다. 스레드는 파일 객체와 인터프리터를 공유해서, 실제로는 깨지는데 테스트만 통과한다
  - 수정 후 12개·40개 동시 프로세스 모두 유실 0

## [4.8.1] - 2026-08-12

### Fixed

- **`init`이 Windows에서 동작하지 않는 명령을 안내하던 문제**: 마지막 줄이 `cat <dir>/$(date +%Y-%m-%d).md` 였다. bash 문법이라 이 프로젝트가 지원하고 CI로 검증까지 하는 Windows에서는 아무 일도 하지 않는다. 온보딩의 **마지막 문장이자 성과를 확인하는 방법**이 실행한 플랫폼에서 틀린 상태였다. 이제 오늘 파일의 실제 경로를 그대로 출력한다

### Changed

- **온보딩이 `backfill`로 이어진다**: `init`이 "이제부터 자동 기록됩니다"로 끝났는데, 이건 "가서 일하다 나중에 오라"는 말이다. transcript는 이미 디스크에 있으므로 다음 단계로 `backfill`과 `doctor`를 제시한다
- **인자 없이 실행하면 시작 지점을 보여준다**: 서브커맨드가 21개인데 알파벳 나열뿐이라 `init`이 7번째, `backfill`이 17번째에 묻혀 있었다. argparse는 서브커맨드를 그룹핑하지 못하므로 epilog로 진입 경로를 명시한다

## [4.8.0] - 2026-08-11

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
