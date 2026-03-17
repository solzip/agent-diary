# Phase A — 개인 생산성 도구 (Personal Productivity Tool)

> Claude Code Working Diary v2.0
> 작성일: 2026-03-17
> 상태: Plan

---

## 1. 개요

### 현재 상태 (v1.0)
- Stop Hook 기반 자동 일지 기록
- 주간 요약 리포트 생성
- 한국어/영어 다국어 지원
- Windows/macOS/Linux 크로스 플랫폼

### 목표 (v2.0)
v1.0은 "기록만" 한다. v2.0은 **기록을 풍부하게 하고, 찾기 쉽게 하고, 어디서든 볼 수 있게** 만든다.

### 핵심 원칙
- **시간보다 내용** — 세션 소요 시간은 후순위. 뭘 했는지, 얼마나 변했는지가 중요
- **플러그인 구조** — 외부 연동은 독립 모듈. 코어를 건드리지 않고 확장
- **CLI 우선** — 개발 흐름을 끊지 않는 터미널 중심 UX

---

## 2. 아키텍처

### 2.1 디렉토리 구조 (목표)

```
~/.claude/hooks/
├── working-diary.py          ← 코어 (Stop Hook 엔트리포인트)
├── weekly-summary.py         ← 주간 요약 생성기
├── diary-cli.py              ← CLI 도구 (검색/필터/통계)
├── config.json               ← 사용자 설정 (언어, 연동, 경로 등)
├── exporters/                ← 외부 연동 플러그인
│   ├── __init__.py
│   ├── base.py               ← BaseExporter 인터페이스
│   ├── notion.py
│   ├── obsidian.py
│   ├── slack.py
│   ├── discord.py
│   └── github.py
└── lib/                      ← 공유 유틸리티
    ├── __init__.py
    ├── parser.py             ← transcript 파싱 (코어에서 분리)
    ├── git_info.py           ← git 커밋/브랜치/diff 수집
    ├── categorizer.py        ← 자동 카테고리 분류
    └── stats.py              ← 통계 계산 엔진

~/working-diary/
├── 2026-03-17.md             ← 일일 일지
├── .session_counts.json
├── .gitignore
├── weekly/
│   └── W12_2026-03-16.md     ← 주간 요약
└── dashboard/                ← (P2) HTML 대시보드 출력
    └── index.html
```

### 2.2 데이터 흐름

```
세션 종료
    │
    ▼
working-diary.py (코어)
    │
    ├── lib/parser.py         → transcript 파싱
    ├── lib/git_info.py       → git 커밋/브랜치/diff 수집
    ├── lib/categorizer.py    → 자동 카테고리 분류
    │
    ├── .md 파일에 엔트리 추가 (기존)
    │
    └── exporters/ 순회
        ├── notion.py         → Notion DB에 row 추가
        ├── slack.py          → 웹훅 POST
        └── (활성화된 것만)
```

### 2.3 config.json 구조

```json
{
  "lang": "ko",
  "timezone_offset": 9,
  "diary_dir": "~/working-diary",

  "enrichment": {
    "git_info": true,
    "auto_category": true,
    "code_stats": true,
    "session_time": false
  },

  "exporters": {
    "notion": {
      "enabled": false,
      "api_token": "",
      "database_id": ""
    },
    "obsidian": {
      "enabled": false,
      "vault_path": ""
    },
    "slack": {
      "enabled": false,
      "webhook_url": ""
    },
    "discord": {
      "enabled": false,
      "webhook_url": ""
    },
    "github": {
      "enabled": false,
      "repo": "",
      "token": ""
    }
  }
}
```

---

## 3. 기능 상세

### 3.1 기록 풍부화

#### 3.1.1 자동 카테고리 분류 (P0)

키워드 기반으로 작업 유형을 자동 태깅.

**분류 규칙:**

| 카테고리 | 감지 키워드 (한/영) |
|----------|---------------------|
| feature | 구현, 추가, 기능, implement, add, feature, new |
| bugfix | 수정, 버그, 에러, fix, bug, error, resolve |
| refactor | 리팩토링, 정리, 개선, refactor, clean, improve |
| docs | 문서, README, 주석, doc, comment, readme |
| test | 테스트, 검증, test, verify, assert |
| config | 설정, 환경, config, setup, install, deploy |
| style | 스타일, UI, CSS, design, layout, style |

**출력 형태:**
```markdown
**🏷️ 카테고리:** `feature` `config`
```

**구현:** `lib/categorizer.py`
- 사용자 프롬프트 + 요약 힌트 + 파일 확장자 종합 분석
- 복수 카테고리 허용 (최대 3개)
- `config.json`에서 커스텀 규칙 추가 가능

#### 3.1.2 Git 연동 (P0)

세션 중 발생한 git 변경사항을 일지에 자동 포함.

**수집 정보:**
- 현재 브랜치명
- 세션 중 새로 생긴 커밋 (hash + message)
- 변경된 파일 수

**출력 형태:**
```markdown
**🔀 Git:**
  - 🌿 브랜치: `feature/circuit-breaker`
  - 커밋: `abc1234` feat: add circuit breaker
  - 커밋: `def5678` test: add circuit breaker tests
```

**구현:** `lib/git_info.py`
- `git log --oneline --since="N minutes ago"` 로 세션 중 커밋 추출
- `git branch --show-current`로 브랜치명
- 세션 시작 시점은 transcript의 첫 번째 타임스탬프에서 추출
- git이 없는 디렉토리에서는 조용히 생략

#### 3.1.3 코드 변경 통계 (P0)

세션 중 변경된 코드의 양적 통계.

**수집 방법:**
- transcript에서 Write/Edit 도구의 입력을 분석
- 또는 `git diff --stat`으로 실제 변경량 측정

**출력 형태:**
```markdown
**📊 변경 통계:** +142 / -38 lines (5 files)
```

**구현:** `lib/git_info.py` 에 포함
- `git diff --stat HEAD~N` 또는 커밋 범위 기반
- git 없으면 transcript의 Write/Edit 횟수로 대체

---

### 3.2 CLI 도구 (P0)

`diary-cli.py` — 통합 CLI 인터페이스.

#### 설치 후 사용법

```bash
# alias 설정 (install.sh에서 자동)
alias diary="python ~/.claude/hooks/diary-cli.py"
```

#### 명령어 목록

```bash
# 검색
diary search "circuit breaker"
diary search "circuit breaker" --project ai-chatbot
diary search "circuit breaker" --category feature
diary search "circuit breaker" --from 2026-03-01 --to 2026-03-17

# 프로젝트별 필터
diary filter --project ai-chatbot
diary filter --project ai-chatbot --category bugfix

# 카테고리별 필터
diary filter --category bugfix
diary filter --category bugfix --month 2026-03

# 파일 추적
diary trace src/WebSocketConfig.java
diary trace "*.py" --project my-project

# 통계 (터미널 대시보드)
diary stats                    # 이번 주
diary stats --month 2026-03    # 월간
diary stats --project ai-chatbot

# 주간 요약
diary weekly                   # 이번 주
diary weekly 2026-03-10        # 특정 주

# 설정
diary config                   # 현재 설정 표시
diary config --set lang=en     # 설정 변경
diary config --add-exporter notion  # 연동 추가 (대화형 설정)

# HTML 대시보드 (P2)
diary dashboard                # HTML 생성 후 브라우저 열기
```

#### CLI stats 출력 예시

```
╔══════════════════════════════════════════════════╗
║  📊 Working Diary Stats — 2026-03 W12            ║
╠══════════════════════════════════════════════════╣
║                                                  ║
║  세션: 18  |  프로젝트: 4  |  +1,247 / -389 lines ║
║                                                  ║
║  🔥 프로젝트별 세션                                ║
║  ai-chatbot   ████████████░░░░ 12                ║
║  blog         ████░░░░░░░░░░░░  3                ║
║  docs         ██░░░░░░░░░░░░░░  2                ║
║  infra        █░░░░░░░░░░░░░░░  1                ║
║                                                  ║
║  🏷️ 카테고리                                      ║
║  feature ██████████ 10                            ║
║  bugfix  ████░░░░░░  4                            ║
║  refactor ██░░░░░░░  2                            ║
║  config  ██░░░░░░░░  2                            ║
║                                                  ║
║  📅 일별 활동                                      ║
║  월 ████  화 ██████  수 ████                       ║
║  목 ██    금 ██████  토 ░░  일 ░░                  ║
║                                                  ║
╚══════════════════════════════════════════════════╝
```

---

### 3.3 HTML 대시보드 (P2)

`diary dashboard` 명령으로 정적 HTML 생성.

**포함 차트:**
- GitHub 잔디 스타일 연간 히트맵
- 프로젝트별 세션 파이차트
- 주간 트렌드 라인차트
- 카테고리별 분포 바차트
- 자주 수정되는 파일 Top 10

**기술:**
- 순수 HTML + CSS + JS (외부 의존성 없음)
- 차트는 인라인 SVG 또는 경량 라이브러리 (Chart.js CDN)
- `~/working-diary/dashboard/index.html`에 생성
- `diary dashboard --serve`로 로컬 서버 옵션

---

### 3.4 외부 연동 플러그인 (P1)

#### 공통 인터페이스

```python
# exporters/base.py
class BaseExporter:
    def __init__(self, config: dict):
        self.config = config

    def export(self, entry_data: dict) -> bool:
        """일지 엔트리를 외부 서비스로 내보내기. 성공 시 True."""
        raise NotImplementedError

    def validate_config(self) -> bool:
        """설정 유효성 검증."""
        raise NotImplementedError
```

#### 3.4.1 Notion Exporter

**동작:**
- Notion API로 database에 row 추가
- 세션 종료 시 자동 실행

**DB 컬럼 매핑:**

| Notion 컬럼 | 타입 | 소스 |
|-------------|------|------|
| 날짜 | Date | 자동 |
| 프로젝트 | Select | cwd 기반 |
| 카테고리 | Multi-select | 자동 분류 |
| 작업 요청 | Rich Text | user_prompts |
| 수정 파일 | Rich Text | files_modified |
| 작업 요약 | Rich Text | summary_hints |
| Git 커밋 | Rich Text | git_info |
| 변경량 | Number | +/- lines |

**필요 설정:**
- `api_token`: Notion Integration 토큰
- `database_id`: 대상 DB ID

**의존성:** `requests` (표준 라이브러리 아님 — 설치 안내 필요)

#### 3.4.2 Obsidian Exporter

**동작:**
- Obsidian vault 경로에 동일한 .md 파일 복사/심볼릭 링크
- 또는 Obsidian 형식 (frontmatter YAML, [[wikilink]]) 으로 변환

**필요 설정:**
- `vault_path`: Obsidian vault 절대 경로

**의존성:** 없음 (파일 복사)

#### 3.4.3 Slack Exporter

**동작:**
- Incoming Webhook으로 일지 요약 POST
- Block Kit 형식으로 깔끔하게 전송

**메시지 예시:**
```
📓 작업일지 — ai-chatbot
🏷️ feature, refactor
📋 Circuit breaker 패턴 구현
📊 +142 / -38 lines (5 files)
🔀 2 commits on feature/circuit-breaker
```

**필요 설정:**
- `webhook_url`: Slack Incoming Webhook URL

**의존성:** `requests` 또는 `urllib` (표준 라이브러리)

#### 3.4.4 Discord Exporter

**동작:** Slack과 동일 구조, Discord Webhook 형식으로 전송

**필요 설정:**
- `webhook_url`: Discord Webhook URL

**의존성:** `urllib` (표준 라이브러리)

#### 3.4.5 GitHub Exporter

**동작:**
- 프로젝트 repo의 Wiki 또는 Issue에 작업 로그 추가
- 또는 별도 diary repo에 자동 커밋

**모드:**
- `wiki`: 프로젝트 Wiki 페이지에 추가
- `issue`: 일일 Issue에 코멘트로 추가
- `repo`: diary 전용 repo에 자동 push

**필요 설정:**
- `mode`: wiki / issue / repo
- `token`: GitHub Personal Access Token
- `repo`: 대상 레포지토리 (owner/repo)

**의존성:** `requests` 또는 `gh` CLI

---

## 4. 구현 순서

### Sprint 1 — 코어 리팩토링 + 기록 풍부화 (P0)

```
1. lib/ 분리 (parser.py, git_info.py, categorizer.py, stats.py)
2. config.json 도입 (기존 환경변수와 호환)
3. 자동 카테고리 분류 구현
4. Git 연동 (브랜치, 커밋, diff stat)
5. 코드 변경 통계
6. working-diary.py에 enrichment 통합
7. 테스트 + 기존 기능 회귀 확인
```

### Sprint 2 — CLI 도구 (P0)

```
1. diary-cli.py 기본 프레임워크 (argparse)
2. search 명령어 (키워드 + 날짜 범위)
3. filter 명령어 (project, category, month)
4. trace 명령어 (파일 추적)
5. stats 명령어 (터미널 대시보드)
6. weekly 명령어 (기존 weekly-summary.py 통합)
7. config 명령어 (설정 관리)
8. install.sh에 alias 등록 추가
```

### Sprint 3 — 외부 연동 플러그인 (P1)

```
1. exporters/base.py 인터페이스
2. 플러그인 로더 (config 기반 동적 로드)
3. Notion exporter
4. Slack exporter
5. Discord exporter
6. Obsidian exporter
7. GitHub exporter
8. diary config --add-exporter 대화형 설정
```

### Sprint 4 — HTML 대시보드 (P2)

```
1. stats.py 데이터를 JSON으로 직렬화
2. HTML 템플릿 (히트맵, 차트)
3. diary dashboard 명령어
4. --serve 로컬 서버 옵션
```

### (후순위) 세션 시간 추적 (P3)

```
1. transcript 첫/마지막 타임스탬프에서 시간 추출
2. 일지에 소요 시간 표시
```

---

## 5. 기술 제약 및 결정

### 5.1 의존성 정책

| 구분 | 정책 |
|------|------|
| 코어 + CLI | **Python 표준 라이브러리만** (외부 의존성 없음) |
| Notion exporter | `requests` 필요 — `pip install requests` 안내 |
| Slack/Discord | `urllib.request` 사용 (표준 라이브러리) |
| Obsidian/GitHub repo | 외부 의존성 없음 |
| HTML 대시보드 | Chart.js CDN (오프라인은 인라인 SVG) |

### 5.2 하위 호환성

- 기존 v1.0 환경변수 (`CLAUDE_DIARY_LANG`, `CLAUDE_DIARY_DIR`, `CLAUDE_DIARY_TZ_OFFSET`) 유지
- `config.json` 없어도 환경변수만으로 동작
- `config.json`이 있으면 환경변수보다 우선

### 5.3 보안

- `config.json`에 API 토큰 저장 시 파일 권한 600 설정
- `.gitignore`에 `config.json` 기본 추가
- 토큰 값은 `diary config` 출력 시 마스킹 (`sk-...****`)

### 5.4 에러 처리

- 외부 연동 실패 시 코어 동작에 영향 없음 (try/except + stderr 로깅)
- 네트워크 오류 시 재시도 없음 (Hook은 빠르게 종료되어야 함)
- 실패한 export는 `~/working-diary/.export_queue.json`에 저장, 다음 세션에서 재시도

### 5.5 대용량 세션 / Transcript 보완 전략

긴 세션에서 Claude Code가 context 압축을 하면 transcript가 불완전할 수 있다.

**해결: transcript + git diff 이중 수집**

```
transcript (1차) → "왜 했는지" (사용자 프롬프트, AI 요약)
git diff   (2차) → "실제로 뭐가 변했는지" (파일, 라인, 커밋)
```

- transcript가 부족해도 git이 실제 변경 결과를 보장
- git 정보가 없으면 (non-git 디렉토리) transcript만으로 기록
- 두 소스를 병합하여 최종 일지 생성

### 5.6 v1.0 → v2.0 마이그레이션

기존 v1.0 사용자의 데이터와 설정을 보존.

**환경변수 → config.json 자동 전환:**

```bash
claude-diary migrate
# ✓ CLAUDE_DIARY_LANG=ko → config.json { "lang": "ko" }
# ✓ CLAUDE_DIARY_DIR → config.json { "diary_dir": "..." }
# ✓ CLAUDE_DIARY_TZ_OFFSET → config.json { "timezone_offset": 9 }
# ✓ 기존 환경변수도 계속 동작 (하위 호환)
```

**기존 .md 일지 파일:**
- v1.0 형식 그대로 호환 (카테고리/git 정보가 없을 뿐)
- CLI 검색/필터 시 카테고리 없는 엔트리는 `uncategorized`로 처리
- 기존 파일 수정/변환 없음

**디렉토리 구조:**
- `~/working-diary/` 경로 유지
- 새 파일(`config.json`, `.audit.jsonl` 등)만 추가

### 5.7 CLI 검색 성능

일지가 수개월~수년 쌓이면 매번 .md 풀스캔은 느려진다.

**경량 인덱스:**

```
~/working-diary/.diary_index.json
{
  "entries": [
    {
      "date": "2026-03-17",
      "time": "15:30:00",
      "project": "ai-chatbot",
      "categories": ["feature", "refactor"],
      "files": ["src/handler/CircuitBreaker.java"],
      "keywords": ["circuit breaker", "websocket"],
      "git_commits": ["abc1234"],
      "lines_added": 142,
      "lines_deleted": 38
    }
  ],
  "last_indexed": "2026-03-17T15:30:00"
}
```

- 새 엔트리 추가 시 인덱스 자동 업데이트 (incremental)
- `diary search`는 인덱스 먼저 조회 → 매칭된 .md만 읽기
- `diary reindex`로 전체 재구축 가능
- 인덱스 없으면 폴백으로 풀스캔 (v1.0 호환)

---

## 6. Phase A 완료 기준

- [ ] 자동 카테고리가 일지에 표시됨
- [ ] Git 커밋/브랜치가 일지에 표시됨
- [ ] 코드 변경량(+/- lines)이 일지에 표시됨
- [ ] `diary search` / `diary filter` / `diary trace`가 동작함
- [ ] `diary stats`로 터미널 대시보드 확인 가능
- [ ] 최소 1개 exporter (Notion 또는 Slack)가 동작함
- [ ] `diary config`로 설정 관리 가능
- [ ] Windows/macOS/Linux 모두 동작
- [ ] 한국어/영어 모두 동작
- [ ] 기존 v1.0 기능 회귀 없음
- [ ] transcript 부족 시 git diff로 보완되어 기록됨
- [ ] `claude-diary migrate`로 v1.0 설정 자동 전환
- [ ] 검색 인덱스로 수개월 일지에서도 빠른 검색 가능
