# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Fixed

- **README가 안내하는 Claude Code 플러그인 설치가 처음부터 동작하지 않던 문제**: 이 프로젝트가 광고하는 배포 경로는 둘(PyPI, Claude Code 플러그인)인데 후자가 끝에서 끝까지 막혀 있었다. 4.8.1에서 고친 "Windows에서 안 되는 안내문"과 같은 유형 — 독자의 기계에서 실행되지 않는 지시문이다
  - `/plugin marketplace add`는 저장소 루트의 `.claude-plugin/marketplace.json`을 읽는데 **그 파일이 없었다.** 첫 줄에서 실패한다
  - `plugin.json`의 `dependencies`가 `{"python": ">=3.8"}` 였다. 스키마는 배열을 받는다. 인식되는 필드의 타입이 틀리면 경고가 아니라 **로드 실패**다 — 설치에 성공해도 훅이 안 붙는다
  - `hooks`가 `"hooks.json"` 이었다. 이 경로는 플러그인 루트 기준인데 파일은 `.claude-plugin/` 안에 있어서 로더가 못 찾는다. `./.claude-plugin/hooks.json` 으로 고쳤다
  - `claude plugin validate . --strict` 기준 **에러 3건·경고 1건 → 통과**
  - 마켓플레이스 이름은 `solzip`이라 설치 명령이 `/plugin install agent-diary@solzip` 이다. README(EN/KO) 둘 다 갱신
- **기존 테스트가 깨진 값을 고정하고 있던 문제**: `test_codex_plugin.py`가 `assert data["hooks"] == "hooks.json"` 으로 리터럴을 박아둬서, 런타임이 해석하지 못하는 경로를 **초록불로 지키고 있었다.** 경로가 실제 파일로 해석되는지 검사하도록 바꿨다

### Added

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
