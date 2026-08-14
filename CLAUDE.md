# 이 저장소에서 작업할 때

에이전트와 사람이 같이 읽는 문서다. 개인 메모리가 아니라 여기 두는 이유는
**여러 PC에서 작업하기 때문이다** — 메모리는 따라오지 않는다.

일반적인 기여 방법(이슈 템플릿, exporter 추가, 리뷰 규칙)은
[CONTRIBUTING.md](CONTRIBUTING.md)에 있다. 여기 있는 건 그것과 겹치지 않는,
**이 저장소에서 반복해서 틀렸던 것들**이다.

## README는 변경을 따라간다

**사용자에게 보이는 동작을 바꿨으면 같은 PR에서 `README.md`와 `README.ko.md`를
둘 다 고친다.** 나중으로 미루지 않는다.

미룬 결과가 실제로 어떻게 됐는지가 이 규칙의 근거다. 2026-08-14 기준 README는
커밋 65개 동안 방치돼 v4.9.0~v4.11.3의 변경을 하나도 반영하지 못했고, 그 사이
**도입부의 동작 설명 자체가 틀린 상태**가 됐다.

- "세션 하나가 끝나면 항목 하나" — 4.9.0부터 항목의 단위는 턴이다
- 예시 항목에 훅이 쓰지 않는 `📝 Work Summary`가 있고, 실제로 쓰는
  `💬 Response`가 없었다
- 4.11.3이 고친 인덱스를 복구하려면 `reindex`를 한 번 돌려야 하는데
  그 안내가 어디에도 없었다

아무것도 실패하지 않았다. 문서가 조용히 틀린 답을 하고 있었을 뿐이고, 그건 이
프로젝트가 코드에서 반복해 만난 실패 모양과 같다.

지킬 것:

- **두 파일은 항상 같은 커밋에서 움직인다.** 한쪽만 고치면 다른 언어 독자에게는
  안 고친 것과 같다
- README에는 **실제 출력 예시**가 들어 있다(§1의 일지 항목 블록). 출력 형식을
  바꿨으면 그 블록도 `formatter.py`의 실제 출력과 맞춘다. 손으로 짜맞추지 말고
  `agent-diary try`를 돌려서 대조한다
- 고칠 게 없다고 판단했으면 **PR 본문에 왜 없는지 한 줄** 적는다. 조용히
  건너뛰지 않는다

## 사실은 한 곳에만 적는다

같은 내용을 두 곳에 적으면 반드시 어긋난다. 아래가 각 주제의 정본이다.
**다른 문서에서는 판단 근거를 다시 쓰지 말고 여기를 가리킨다.**

| 무엇 | 어디 |
|---|---|
| 지금 어디까지 왔고 다음에 뭘 읽어야 하는지 | [`docs/plans/next-session.md`](docs/plans/next-session.md) |
| 선택지를 비교해서 정한 것 | [`docs/decisions/`](docs/decisions/README.md) |
| 릴리스마다 무엇이 바뀌었는지 | [`CHANGELOG.md`](CHANGELOG.md) |
| 멱등성·재시도·부분 실패 설계 | [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) |
| 기록/작업항목 분리 설계와 그 실측값 | [`docs/02-design/features/records-and-work-items.design.md`](docs/02-design/features/records-and-work-items.design.md) |

`next-session.md`에는 **다시 재지 말아야 할 실측값과, 코드에 적혀 있지 않은
사실**이 모여 있다(버전 문자열이 몇 개 파일에 있는지, PyPI 배포가 어떻게 도는지,
어떤 지표를 읽으면 안 되는지). 코드를 건드리기 전에 그 문서의
「Things that are true and are not written in the code」를 먼저 읽는다.

## 즉석 스크립트는 `PYTHONPATH=src`로 돌린다

`src/` 레이아웃이다. 저장소 루트에서 그냥 `python -c "import claude_diary"`를
하면 **작업 트리가 아니라 site-packages의 설치본을 읽는다.** 고친 코드를 확인한
줄 알았는데 실제로는 배포된 옛 버전을 잰 것이 된다.

```bash
PYTHONPATH=src python -c "import claude_diary.indexer as i; print(i.__file__)"
```

`pytest`는 `pyproject.toml`의 `pythonpath = ["src"]`가 처리하므로 그냥 돌리면
된다. 문제가 되는 건 **손으로 돌리는 한 줄짜리 확인**이다. 그리고 그런 확인은
틀려도 조용히 그럴듯한 답을 낸다 — 이 저장소가 반복해서 걸린 모양 그대로다.

실제로 2026-08-14에 `count_branch_sessions` 수정을 검증하면서 이걸로 "수정 전후
값이 같다"는 결과를 받았다. 설치본을 재고 있었다.

## 실험이 실제 일지를 건드리지 않게

`CLAUDE_DIARY_DIR`만 바꾸는 걸로는 부족하다. `config.json`이 환경변수보다
우선하도록 일부러 만들어져 있어서, 격리된 실행에는 `APPDATA`·`XDG_CONFIG_HOME`·
`CLAUDE_DIARY_DIR` 세 개가 전부 돌려져 있어야 한다. `agent-diary try`가 그 일을
한다.

이걸 틀린 테스트가 실제 일지에 항목 5건을 쓴 적이 있다.
