# Phase B — 오픈소스 커뮤니티 도구 (Open Source Community Tool)

> Claude Code Working Diary v3.0
> 작성일: 2026-03-17
> 상태: Plan
> 선행 조건: Phase A 완료

---

## 1. 개요

### 목표
Phase A의 개인 도구를 **누구나 쉽게 설치하고, 신뢰하고, 확장하고, 기여할 수 있는** 오픈소스 프로젝트로 만든다.

### 핵심 원칙
- **보안 최우선** — 사용자가 Stop Hook에 타인의 코드를 돌리는 것에 대한 불안을 해소
- **설치 1분** — `pip install` + `init` 한 줄이면 끝
- **코드 안 건드리고 확장** — 플러그인만으로 커스터마이징

### 커뮤니티 고지

```markdown
> ⚠️ This is a community project, not officially affiliated with Anthropic.
```

README 상단에 명시.

---

## 2. 보안 (최우선)

### 2.1 코드 투명성

- README에 "이 도구가 하는 일 / 하지 않는 일" 섹션 명시
- 코어는 **네트워크 접근 제로** (표준 라이브러리만 사용)
- 코드 라인 수 badge 표시 ("Core: ~500 lines")
- 각 함수에 "이 함수가 읽는 것 / 쓰는 것" 주석

### 2.2 권한 최소화

| 구성요소 | 읽기 | 쓰기 |
|----------|------|------|
| 코어 | transcript (readonly) | `~/working-diary/` 만 |
| CLI | `~/working-diary/` (readonly) | 없음 (stats/search) |
| exporter | entry_data (메모리 전달) | 외부 API (활성화 시만) |

- exporter 비활성화 시 네트워크 접근 완전 제로
- 코어가 exporter에 전달하는 데이터는 **가공된 entry_data만** (원본 transcript 접근 불가)

### 2.3 자동 시크릿 스캔

일지에 기록하기 전 민감 정보를 자동 감지 및 마스킹.

**감지 패턴:**

```python
SECRET_PATTERNS = [
    r'(?i)(password|passwd|pwd)\s*[=:]\s*\S+',
    r'(?i)(api[_-]?key|apikey)\s*[=:]\s*\S+',
    r'(?i)(secret|token)\s*[=:]\s*\S+',
    r'sk-[a-zA-Z0-9]{20,}',           # OpenAI / Stripe
    r'ghp_[a-zA-Z0-9]{36,}',          # GitHub PAT
    r'xoxb-[a-zA-Z0-9\-]+',           # Slack Bot Token
    r'AKIA[A-Z0-9]{16}',              # AWS Access Key
    r'(?i)bearer\s+[a-zA-Z0-9\-._~+/]+=*',  # Bearer tokens
]
```

**동작:**
- user_prompts, summary_hints, commands에서 패턴 매칭
- 감지 시 `****` 로 치환
- `diary audit` 에서 "N개 시크릿 마스킹됨" 표시

### 2.4 Exporter 신뢰 등급

```
🟢 Official  — 프로젝트에 포함된 공식 exporter (코드 리뷰 완료)
🟡 Community — 커뮤니티 기여 exporter (CONTRIBUTING.md 가이드라인 준수)
🔴 Custom    — 사용자 로컬에서 직접 만든 exporter (검증 없음)
```

- `diary config`에서 exporter별 신뢰 등급 표시
- Community exporter는 PR 리뷰 후에만 merge
- Custom exporter는 config에서 `"trust": "custom"` 명시 필요

### 2.5 공급망 보안

- 코어 + CLI: **외부 의존성 제로** (Python 표준 라이브러리만)
- Notion exporter만 `requests` 필요 — optional dependency로 분리
- `pyproject.toml`에 의존성 핀 고정
- GitHub Dependabot 활성화

### 2.6 Audit 로그

매 Hook 실행마다 audit 기록:

```json
// ~/working-diary/.audit.jsonl
{
  "timestamp": "2026-03-17T15:30:00+09:00",
  "session_id": "abc123...",
  "action": "diary_entry_created",
  "files_read": ["~/.claude/projects/.../transcript.jsonl"],
  "files_written": ["~/working-diary/2026-03-17.md"],
  "secrets_masked": 0,
  "exporters_called": ["notion"],
  "exporters_failed": [],
  "checksum": "sha256:abcdef..."
}
```

```bash
# 감사 로그 조회
diary audit                    # 최근 10건
diary audit --days 7           # 7일간
diary audit --verify           # checksum 무결성 검증
```

### 2.7 Checksum 변조 감지

- Hook 스크립트 파일의 SHA-256 해시를 audit 로그에 기록
- `diary audit --verify`로 현재 파일과 비교
- 불일치 시 경고 출력

### 2.8 SECURITY.md

```markdown
# Security Policy

## Supported Versions
| Version | Supported |
|---------|-----------|
| 2.x     | ✅        |
| 1.x     | ❌        |

## Reporting a Vulnerability
- Email: [maintainer email]
- Do NOT open a public issue for security vulnerabilities
- Response within 48 hours
```

---

## 3. 설치 간소화

### 3.1 패키지 구조 (PyPI)

```
claude-diary/
├── pyproject.toml
├── src/
│   └── claude_diary/
│       ├── __init__.py
│       ├── __main__.py        ← python -m claude_diary
│       ├── cli.py             ← diary-cli 엔트리포인트
│       ├── hook.py            ← Stop Hook 엔트리포인트
│       ├── config.py          ← 설정 관리
│       ├── lib/
│       │   ├── parser.py
│       │   ├── git_info.py
│       │   ├── categorizer.py
│       │   ├── stats.py
│       │   └── secret_scanner.py
│       └── exporters/
│           ├── base.py
│           ├── notion.py
│           ├── obsidian.py
│           ├── slack.py
│           ├── discord.py
│           └── github.py
├── tests/
│   ├── test_parser.py
│   ├── test_categorizer.py
│   ├── test_secret_scanner.py
│   ├── test_cli.py
│   └── test_exporters/
└── docs/
```

### 3.2 설치 흐름

```bash
# 1. 설치
pip install claude-diary

# 2. 초기화 (대화형)
claude-diary init

# init이 하는 일:
# ✓ ~/.claude/settings.json에 Stop Hook 자동 등록
# ✓ ~/working-diary/ 디렉토리 생성
# ✓ config.json 대화형 생성 (언어, 타임존, exporter 선택)
# ✓ alias 등록 안내 (diary → claude-diary cli)
```

### 3.3 pyproject.toml 핵심

```toml
[project]
name = "claude-diary"
version = "2.0.0"
description = "Auto-generate work diaries from Claude Code sessions"
requires-python = ">=3.7"
license = {text = "MIT"}
dependencies = []  # 코어는 의존성 제로

[project.optional-dependencies]
notion = ["requests>=2.28"]
all = ["requests>=2.28"]

[project.scripts]
claude-diary = "claude_diary.cli:main"
```

---

## 4. 커스터마이징 + 기여

### 4.1 플러그인 인터페이스

**Exporter:**

```python
# exporters/base.py
class BaseExporter:
    """
    공식 exporter 인터페이스.
    이 클래스를 상속하여 새 exporter를 만들 수 있습니다.

    entry_data 구조:
      - date: str (YYYY-MM-DD)
      - time: str (HH:MM:SS)
      - project: str
      - categories: list[str]
      - user_prompts: list[str]
      - files_created: list[str]
      - files_modified: list[str]
      - commands_run: list[str]
      - summary_hints: list[str]
      - git_info: dict (branch, commits, diff_stat)
      - code_stats: dict (added, deleted, files_changed)

    NOTE: 원본 transcript에는 접근할 수 없습니다. (보안)
    """

    TRUST_LEVEL = "custom"  # "official", "community", "custom"

    def __init__(self, config: dict):
        self.config = config

    def export(self, entry_data: dict) -> bool:
        raise NotImplementedError

    def validate_config(self) -> bool:
        raise NotImplementedError
```

**Categorizer:**

```python
# lib/categorizer.py
class BaseCategorizer:
    """
    카테고리 규칙 인터페이스.
    한/영 키워드 규칙을 커스터마이징할 수 있습니다.
    """

    def categorize(self, entry_data: dict) -> list[str]:
        raise NotImplementedError
```

### 4.2 CONTRIBUTING.md 핵심 내용

```markdown
# Contributing

## Exporter 기여 방법
1. `exporters/base.py`의 `BaseExporter`를 상속
2. `export()`, `validate_config()` 구현
3. `TRUST_LEVEL = "community"` 설정
4. 테스트 작성 (`tests/test_exporters/`)
5. PR 제출

## 규칙
- 코어 코드 수정 금지 (exporter/categorizer만)
- 외부 의존성 추가 시 optional dependency로
- 한국어/영어 문서 모두 작성
- 보안 리뷰 통과 필수
```

### 4.3 Issue/PR 템플릿

- Bug Report: 재현 단계, OS, Python 버전, config.json (토큰 마스킹)
- Feature Request: 유스케이스, 제안 방법
- Exporter 기여: 어떤 서비스, 인터페이스 준수 여부

---

## 5. 테스트 전략

### 5.1 테스트 범위

| 영역 | 테스트 종류 | 도구 |
|------|------------|------|
| parser.py | 유닛 | pytest |
| categorizer.py | 유닛 | pytest |
| secret_scanner.py | 유닛 (패턴별) | pytest |
| CLI commands | 통합 | pytest + click.testing |
| exporters | 유닛 (mock API) | pytest + unittest.mock |
| Hook 전체 흐름 | E2E | 샘플 transcript로 실행 |

### 5.2 CI/CD (GitHub Actions)

```yaml
# .github/workflows/ci.yml
- Python 3.7, 3.8, 3.9, 3.10, 3.11, 3.12 매트릭스
- OS: ubuntu, macos, windows
- pytest + coverage (80% 이상)
- flake8 / ruff 린트

# .github/workflows/release.yml
- tag push 시 PyPI 자동 배포
- CHANGELOG 자동 생성
```

---

## 6. 발견성

### 6.1 GitHub 최적화

- Topics: `claude-code`, `productivity`, `work-diary`, `automation`, `hooks`, `developer-tools`
- About: "Auto-generate work diaries from Claude Code sessions (KO/EN)"
- GIF 데모: 세션 종료 → 일지 생성 → CLI 검색 (30초)
- Badges: PyPI version, downloads, CI status, coverage, license

### 6.2 Claude 커뮤니티

- Claude Code 공식 Discord/Forum에 소개 포스트
- "How I automated my work diary with Claude Code hooks" 형태
- 설치부터 일지 확인까지 3분 가이드

---

## 7. 릴리스 전략

### Semantic Versioning

```
MAJOR.MINOR.PATCH
  │     │     └── 버그 수정
  │     └────── 기능 추가 (하위 호환)
  └──────────── 호환 깨지는 변경
```

- v2.0.0: Phase A 완료 (pip 패키지 초기 릴리스)
- v2.x.x: Phase A 기능 추가/수정
- v3.0.0: Phase B 완료 (보안 강화, 플러그인 구조 확정)
- v4.0.0: Phase C 완료 (팀 기능)

### CHANGELOG 자동화

- Conventional Commits 형식 사용 (`feat:`, `fix:`, `security:`)
- GitHub Release에 자동 생성

---

## 8. 구현 순서

### Sprint B-1 — 보안 기반 (최우선)

```
1. secret_scanner.py 구현 (패턴 기반 시크릿 감지)
2. audit 로그 시스템 구현
3. checksum 변조 감지
4. 코어에서 exporter로 전달하는 데이터 범위 제한
5. SECURITY.md 작성
```

### Sprint B-2 — PyPI 패키지화

```
1. 디렉토리 구조를 src/ 레이아웃으로 리팩토링
2. pyproject.toml 작성
3. claude-diary init 대화형 설정
4. 기존 install.sh → init 명령어로 마이그레이션
5. PyPI 테스트 배포 (TestPyPI)
```

### Sprint B-3 — 테스트 + CI

```
1. 유닛 테스트 (parser, categorizer, secret_scanner)
2. CLI 통합 테스트
3. E2E 테스트 (샘플 transcript)
4. GitHub Actions CI 구성
5. coverage 80% 이상 달성
```

### Sprint B-4 — 커뮤니티 준비

```
1. CONTRIBUTING.md
2. Issue/PR 템플릿
3. LICENSE (MIT)
4. CHANGELOG.md
5. GitHub 최적화 (topics, badges, GIF 데모)
6. exporter 신뢰 등급 시스템
7. PyPI 정식 배포
```

---

## 9. Phase B 완료 기준

- [ ] `pip install claude-diary && claude-diary init`으로 1분 내 설치 완료
- [ ] 시크릿 스캔이 API 키/토큰/패스워드를 자동 마스킹
- [ ] `diary audit`으로 모든 Hook 실행 내역 조회 가능
- [ ] `diary audit --verify`로 스크립트 변조 감지 가능
- [ ] exporter에 원본 transcript 접근 불가
- [ ] 테스트 커버리지 80% 이상
- [ ] GitHub Actions CI가 Python 3.7~3.12 + 3 OS에서 통과
- [ ] PyPI에 정식 배포 완료
- [ ] SECURITY.md, CONTRIBUTING.md, LICENSE 존재
- [ ] README에 GIF 데모 + 커뮤니티 고지문 포함
