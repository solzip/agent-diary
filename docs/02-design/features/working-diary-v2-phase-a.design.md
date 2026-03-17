# Working Diary v2.0 Phase A — Design Document

> **Summary**: 개인 생산성 도구로의 진화 — 코어 리팩토링, 기록 풍부화, CLI, 플러그인
>
> **Project**: claude-code-hooks-diary
> **Version**: 2.0.0
> **Date**: 2026-03-17
> **Status**: Draft
> **Planning Doc**: [phase-a-personal-tool.plan.md](../../plans/phase-a-personal-tool.md)

## Executive Summary

| 관점 | 내용 |
|------|------|
| **Problem** | v1.0은 기록만 하고 검색/분석/연동이 없음 |
| **Solution** | 코어 리팩토링 + CLI + 플러그인 아키텍처 |
| **Function UX Effect** | 세션 종료 → 자동 풍부한 일지 + CLI로 즉시 검색/분석 |
| **Core Value** | 개발자의 작업 기록을 자산으로 전환 |

---

## 1. Overview

### 1.1 Design Goals

- v1.0 단일 스크립트를 **모듈화된 pip 패키지**로 리팩토링
- transcript 파싱 결과에 **카테고리/Git/변경통계/시크릿스캔**을 추가
- **CLI 도구**로 일지 검색/필터/통계 제공
- **플러그인 구조**로 Notion/Slack/Discord/Obsidian/GitHub 연동
- v1.0 하위 호환성 100% 유지

### 1.2 Design Principles

- **표준 라이브러리 Only** — 코어 + CLI는 외부 의존성 제로
- **Fail-safe** — enrichment/exporter 실패 시 코어 동작에 영향 없음
- **Incremental** — config 없어도 환경변수로, 인덱스 없어도 풀스캔으로 동작

---

## 2. Architecture

### 2.1 Component Diagram

```
┌──────────────────────────────────────────────────────────┐
│                    Claude Code                           │
│                    (Stop Hook)                           │
└──────────┬───────────────────────────────────────────────┘
           │ stdin (JSON: session_id, transcript_path, cwd)
           ▼
┌──────────────────────────────────────────────────────────┐
│  hook.py  (thin wrapper — settings.json에서 호출됨)       │
│    └─→ claude_diary.core.process_session()               │
└──────────┬───────────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────┐
│  core.py  (메인 파이프라인 오케스트레이터)                 │
│                                                          │
│  ┌──────────┐ ┌──────────┐ ┌──────────────┐             │
│  │ parser   │ │ git_info │ │ categorizer  │             │
│  │          │ │          │ │              │             │
│  │ transcript│ │ branch   │ │ keyword      │             │
│  │ → prompts│ │ commits  │ │ matching     │             │
│  │ → files  │ │ diff stat│ │ → categories │             │
│  │ → cmds   │ │          │ │              │             │
│  └────┬─────┘ └────┬─────┘ └──────┬───────┘             │
│       │            │              │                      │
│       └────────────┼──────────────┘                      │
│                    ▼                                     │
│  ┌──────────────────────────────────┐                    │
│  │ secret_scanner                   │                    │
│  │ (mask secrets before writing)    │                    │
│  └──────────┬───────────────────────┘                    │
│             │                                            │
│       ┌─────┴──────┐                                     │
│       ▼            ▼                                     │
│  ┌─────────┐  ┌──────────────┐                           │
│  │ .md 파일 │  │ exporters/   │                           │
│  │ (로컬)   │  │ (플러그인)    │                           │
│  │         │  │ notion.py    │                           │
│  │         │  │ slack.py     │                           │
│  │         │  │ discord.py   │                           │
│  │         │  │ obsidian.py  │                           │
│  │         │  │ github.py    │                           │
│  └─────────┘  └──────────────┘                           │
└──────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────┐
│  cli.py  (독립 엔트리포인트: claude-diary 명령어)          │
│                                                          │
│  search / filter / trace / stats / weekly / config       │
│       │                                                  │
│       ▼                                                  │
│  ┌─────────┐  ┌─────────────────────┐                    │
│  │ stats   │  │ .diary_index.json   │                    │
│  │ engine  │  │ (검색 인덱스)        │                    │
│  └─────────┘  └─────────────────────┘                    │
└──────────────────────────────────────────────────────────┘
```

### 2.2 Data Flow

```
세션 종료
    │
    ▼
hook.py (stdin에서 JSON 읽기)
    │
    ├── config.py → config.json 또는 환경변수에서 설정 로드
    │
    ├── parser.py → transcript.jsonl 파싱
    │   └→ user_prompts, files_created, files_modified, commands_run, summary_hints
    │
    ├── git_info.py → git 정보 수집
    │   └→ branch, commits (since session start), diff_stat (+/- lines)
    │
    ├── categorizer.py → 키워드 기반 자동 카테고리 분류
    │   └→ categories: ["feature", "config"]
    │
    ├── secret_scanner.py → 시크릿 마스킹
    │   └→ "ghp_abc123..." → "****"
    │
    ├── formatter.py → entry_data를 마크다운으로 변환
    │   └→ 일지 엔트리 문자열
    │
    ├── writer.py → ~/working-diary/YYYY-MM-DD.md에 append
    │
    ├── indexer.py → .diary_index.json에 메타데이터 추가 (incremental)
    │
    └── exporter_loader.py → 활성화된 exporter들에 entry_data 전달
        ├── notion.py → Notion API
        ├── slack.py → Webhook POST
        └── ...
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| hook.py | core.py | Stop Hook → 코어 진입 |
| core.py | config.py, parser, git_info, categorizer, secret_scanner | 파이프라인 오케스트레이션 |
| parser.py | (없음) | transcript JSONL 파싱 |
| git_info.py | (없음, git CLI 호출) | Git 정보 수집 |
| categorizer.py | (없음) | 키워드 매칭 |
| secret_scanner.py | (없음) | 정규식 매칭 |
| cli.py | config.py, stats.py | CLI 명령어 처리 |
| stats.py | (없음) | 통계 계산 |
| exporters/*.py | base.py | 외부 서비스 연동 |

---

## 3. Data Model

### 3.1 entry_data (코어 데이터 구조)

모든 모듈이 공유하는 중심 데이터 구조.

```python
# 타입 정의 (types.py)
from typing import TypedDict, List, Optional

class GitCommit(TypedDict):
    hash: str           # "abc1234"
    message: str        # "feat: add circuit breaker"

class GitInfo(TypedDict):
    branch: str                 # "feature/circuit-breaker"
    commits: List[GitCommit]    # 세션 중 생긴 커밋들
    diff_stat: dict             # {"added": 142, "deleted": 38, "files": 5}

class EntryData(TypedDict):
    # 메타데이터
    session_id: str
    date: str               # "2026-03-17"
    time: str               # "15:30:00"
    project: str            # "ai-chatbot"
    cwd: str                # "/path/to/project"

    # transcript에서 추출
    user_prompts: List[str]
    files_created: List[str]
    files_modified: List[str]
    commands_run: List[str]
    summary_hints: List[str]
    errors_encountered: List[str]

    # enrichment
    categories: List[str]           # ["feature", "config"]
    git_info: Optional[GitInfo]     # Git 정보 (없으면 None)
    code_stats: Optional[dict]      # {"added": 142, "deleted": 38, "files": 5}
    secrets_masked: int             # 마스킹된 시크릿 수
```

### 3.2 config.json 스키마

```python
class Config(TypedDict):
    lang: str                    # "ko" | "en"
    timezone_offset: int         # 9 (KST)
    diary_dir: str               # "~/working-diary"

    enrichment: dict             # git_info, auto_category, code_stats, session_time
    exporters: dict              # notion, obsidian, slack, discord, github
    custom_categories: dict      # 사용자 커스텀 카테고리 규칙
```

### 3.3 .diary_index.json 스키마

```python
class IndexEntry(TypedDict):
    date: str
    time: str
    project: str
    categories: List[str]
    files: List[str]          # 생성+수정 파일 통합
    keywords: List[str]       # 프롬프트에서 추출한 키워드
    git_commits: List[str]    # 커밋 해시
    lines_added: int
    lines_deleted: int
    session_id: str

class DiaryIndex(TypedDict):
    entries: List[IndexEntry]
    last_indexed: str         # ISO timestamp
```

---

## 4. Module Specification

### 4.1 config.py — 설정 관리

```python
def get_config_path() -> str:
    """XDG 표준 config 경로 반환.
    Linux/macOS: ~/.config/claude-diary/config.json
    Windows: %APPDATA%/claude-diary/config.json
    """

def load_config() -> Config:
    """config.json 로드. 없으면 환경변수에서 폴백.
    우선순위: config.json > 환경변수 > 기본값
    """

def save_config(config: Config) -> None:
    """config.json 저장. 파일 권한 600 설정 (Unix).
    """

def migrate_from_env() -> Config:
    """v1.0 환경변수를 config.json으로 마이그레이션.
    CLAUDE_DIARY_LANG → lang
    CLAUDE_DIARY_DIR → diary_dir
    CLAUDE_DIARY_TZ_OFFSET → timezone_offset
    """
```

### 4.2 parser.py — Transcript 파싱

v1.0의 `parse_transcript()` 로직을 분리. 동일 인터페이스 유지.

```python
def parse_transcript(transcript_path: str, max_lines: int = 2000) -> dict:
    """JSONL transcript를 파싱하여 주요 작업 내용 추출.
    v1.0과 동일한 반환 구조 + timestamp 추가.
    """

def get_session_time_range(transcript_path: str) -> tuple:
    """transcript의 첫/마지막 타임스탬프 추출.
    Returns: (start_iso: str, end_iso: str)
    git_info에서 세션 범위 커밋 조회에 사용.
    """
```

### 4.3 git_info.py — Git 정보 수집

```python
def collect_git_info(cwd: str, session_start: str) -> Optional[GitInfo]:
    """현재 디렉토리의 git 정보를 수집.
    - 브랜치명
    - session_start 이후 커밋들
    - diff stat (uncommitted 포함)

    git이 없거나 non-git 디렉토리면 None 반환.
    모든 git 명령은 subprocess.run(timeout=5) 사용.
    """

def get_diff_stat(cwd: str, since: str) -> dict:
    """git diff --stat 결과 파싱.
    Returns: {"added": int, "deleted": int, "files": int}
    """
```

### 4.4 categorizer.py — 자동 카테고리 분류

```python
# 기본 규칙 (한/영)
DEFAULT_RULES = {
    "feature":  ["구현", "추가", "기능", "implement", "add", "feature", "new"],
    "bugfix":   ["수정", "버그", "에러", "fix", "bug", "error", "resolve"],
    "refactor": ["리팩토링", "정리", "개선", "refactor", "clean", "improve"],
    "docs":     ["문서", "README", "주석", "doc", "comment", "readme"],
    "test":     ["테스트", "검증", "test", "verify", "assert"],
    "config":   ["설정", "환경", "config", "setup", "install", "deploy"],
    "style":    ["스타일", "UI", "CSS", "design", "layout", "style"],
}

def categorize(entry_data: dict, custom_rules: dict = None) -> List[str]:
    """user_prompts + summary_hints + 파일 확장자를 종합 분석.
    Returns: 최대 3개 카테고리 리스트 (빈도 순).
    custom_rules가 있으면 DEFAULT_RULES에 병합.
    """
```

### 4.5 secret_scanner.py — 시크릿 마스킹

```python
BASIC_PATTERNS = [
    r'(?i)(password|passwd|pwd)\s*[=:]\s*\S+',
    r'(?i)(api[_-]?key|apikey)\s*[=:]\s*\S+',
    r'sk-[a-zA-Z0-9]{20,}',
    r'ghp_[a-zA-Z0-9]{36,}',
    r'AKIA[A-Z0-9]{16}',
]

def scan_and_mask(text: str) -> tuple:
    """텍스트에서 시크릿 패턴을 찾아 마스킹.
    Returns: (masked_text: str, mask_count: int)
    """

def scan_entry_data(entry_data: dict) -> int:
    """entry_data의 모든 텍스트 필드를 스캔/마스킹.
    user_prompts, summary_hints, commands_run 대상.
    Returns: 총 마스킹 수.
    In-place 수정.
    """
```

### 4.6 exporters/base.py — Exporter 인터페이스

```python
class BaseExporter:
    TRUST_LEVEL = "custom"  # "official" | "community" | "custom"

    def __init__(self, config: dict):
        self.config = config

    def export(self, entry_data: dict) -> bool:
        """entry_data를 외부 서비스로 내보내기.
        NOTE: entry_data는 가공된 데이터만 포함.
              원본 transcript 접근 불가 (보안).
        Returns: 성공 시 True.
        """
        raise NotImplementedError

    def validate_config(self) -> bool:
        """설정값 유효성 검증."""
        raise NotImplementedError
```

### 4.7 exporter_loader.py — 플러그인 로더

```python
def load_exporters(config: Config) -> List[BaseExporter]:
    """config에서 enabled=True인 exporter를 동적 로드.
    importlib로 exporters/{name}.py 로드.
    validate_config() 실패 시 해당 exporter 건너뜀 (stderr 경고).
    """

def run_exporters(exporters: List[BaseExporter], entry_data: dict) -> dict:
    """모든 exporter에 entry_data 전달.
    Returns: {"success": ["notion"], "failed": ["slack"]}
    각 exporter는 독립 try/except로 실행 (하나 실패해도 나머지 계속).
    """
```

### 4.8 cli.py — CLI 명령어

```python
# argparse 서브커맨드 구조
commands = {
    "search":   search_command,    # 키워드 검색
    "filter":   filter_command,    # 프로젝트/카테고리/월 필터
    "trace":    trace_command,     # 파일 변경 이력 추적
    "stats":    stats_command,     # 터미널 대시보드
    "weekly":   weekly_command,    # 주간 요약
    "config":   config_command,    # 설정 관리
    "init":     init_command,      # 초기 설정
    "migrate":  migrate_command,   # v1.0 → v2.0 마이그레이션
    "reindex":  reindex_command,   # 인덱스 재구축
    "dashboard": dashboard_command, # HTML 대시보드 (P2)
}
```

---

## 5. Error Handling

### 5.1 에러 격리 원칙

```
코어 파이프라인:  parser → git_info → categorizer → scanner → writer
                                                           (여기까지 반드시 성공)
                                                                │
선택적 단계:      indexer (실패해도 OK) → exporters (실패해도 OK)
```

| 단계 | 실패 시 동작 | 로깅 |
|------|------------|------|
| parser | 빈 result로 진행 | stderr |
| git_info | None으로 진행 (git 없는 것으로 간주) | stderr |
| categorizer | 빈 categories로 진행 | stderr |
| secret_scanner | 마스킹 없이 진행 (원본 유지) | stderr |
| writer (MD) | **exit 1** (핵심 실패) | stderr |
| indexer | 인덱스 업데이트 생략 | stderr |
| exporter N | 해당 exporter만 건너뜀 | stderr + .export_queue.json |

### 5.2 export 실패 큐

```python
# ~/working-diary/.export_queue.json
[
    {
        "timestamp": "2026-03-17T15:30:00+09:00",
        "exporter": "notion",
        "entry_data": { ... },
        "error": "ConnectionError: timeout",
        "retries": 0
    }
]
```

- 다음 세션 종료 시 큐에서 재시도 (최대 3회)
- 3회 실패 시 큐에서 제거 + stderr 경고

---

## 6. Security Considerations

- [x] 시크릿 스캔 — 일지 기록 전 기본 패턴 마스킹
- [x] config.json 파일 권한 — Unix에서 600 설정
- [x] .gitignore — config.json 포함
- [x] 토큰 출력 마스킹 — `claude-diary config` 시 `sk-...****`
- [x] exporter 격리 — entry_data만 전달, 원본 transcript 접근 불가
- [ ] (Phase B) audit 로그, checksum 검증

---

## 7. Test Plan

### 7.1 Test Scope

| Type | Target | Tool | Priority |
|------|--------|------|----------|
| Unit | parser.py | pytest | P0 |
| Unit | categorizer.py | pytest | P0 |
| Unit | secret_scanner.py | pytest | P0 |
| Unit | git_info.py | pytest (mock subprocess) | P0 |
| Unit | config.py | pytest (tmp dirs) | P0 |
| Unit | stats.py | pytest | P1 |
| Integration | CLI commands | pytest + subprocess | P1 |
| E2E | hook.py → full pipeline | 샘플 transcript | P1 |
| Unit | exporters (mock API) | pytest + unittest.mock | P1 |

### 7.2 Test Cases (Key)

- [x] transcript 파싱: v1.0 형식 + Claude Code 실제 형식 모두 파싱
- [x] 카테고리: "구현" → feature, "fix bug" → bugfix, 복합 → 최대 3개
- [x] 시크릿: `ghp_abc123...` → `****`, `password=mysecret` → `password=****`
- [x] git_info: non-git 디렉토리 → None (에러 없음)
- [x] config: 환경변수 폴백, XDG 경로, Windows 경로
- [x] exporter 실패: 하나 실패해도 나머지 동작 + 일지 기록 성공
- [x] v1.0 호환: 기존 .md 파일 CLI로 검색 가능 (카테고리 없어도)

---

## 8. Implementation Guide

### 8.1 File Structure

```
src/claude_diary/
├── __init__.py              # 버전 정보
├── __main__.py              # python -m claude_diary
├── hook.py                  # Stop Hook entrypoint
├── core.py                  # 메인 파이프라인
├── cli.py                   # CLI entrypoint (argparse)
├── config.py                # 설정 관리 (XDG)
├── types.py                 # TypedDict 정의
├── formatter.py             # entry_data → 마크다운 변환
├── writer.py                # .md 파일 쓰기
├── indexer.py               # .diary_index.json 관리
├── lib/
│   ├── __init__.py
│   ├── parser.py            # transcript JSONL 파싱
│   ├── git_info.py          # git CLI wrapper
│   ├── categorizer.py       # 키워드 기반 분류
│   ├── secret_scanner.py    # 시크릿 마스킹
│   └── stats.py             # 통계 계산
├── exporters/
│   ├── __init__.py
│   ├── base.py              # BaseExporter
│   ├── loader.py            # 플러그인 동적 로더
│   ├── notion.py
│   ├── obsidian.py
│   ├── slack.py
│   ├── discord.py
│   └── github.py
└── i18n.py                  # 다국어 레이블 (v1.0 LABELS dict 이전)
```

### 8.2 Implementation Order

#### Sprint 1 — 코어 리팩토링 + 기록 풍부화 (P0)

1. [ ] `src/claude_diary/` 디렉토리 구조 생성 + `pyproject.toml`
2. [ ] `types.py` — EntryData, GitInfo, Config TypedDict 정의
3. [ ] `config.py` — XDG 경로 + 환경변수 폴백 + migrate
4. [ ] `lib/parser.py` — v1.0 parse_transcript 이전 + timestamp 추출
5. [ ] `lib/git_info.py` — branch, commits, diff_stat 수집
6. [ ] `lib/categorizer.py` — 키워드 기반 분류 (한/영)
7. [ ] `lib/secret_scanner.py` — 기본 패턴 마스킹
8. [ ] `formatter.py` — entry_data → 마크다운 (카테고리/git/stats 포함)
9. [ ] `writer.py` — .md 파일 append (v1.0 로직 이전)
10. [ ] `indexer.py` — .diary_index.json incremental 업데이트
11. [ ] `core.py` — 파이프라인 오케스트레이터
12. [ ] `hook.py` — stdin JSON → core.process_session()
13. [ ] `i18n.py` — v1.0 LABELS dict 이전
14. [ ] v1.0 회귀 테스트

#### Sprint 2 — CLI 도구 (P0)

1. [ ] `cli.py` — argparse 기본 프레임워크
2. [ ] `search` — 키워드 + 날짜 범위 + 프로젝트/카테고리 필터
3. [ ] `filter` — project, category, month 필터
4. [ ] `trace` — 파일 변경 이력 추적
5. [ ] `stats` — 터미널 대시보드 (프로젝트/카테고리/일별)
6. [ ] `weekly` — v1.0 weekly-summary.py 통합
7. [ ] `config` — 설정 조회/변경/exporter 추가
8. [ ] `init` — 초기 설정 (settings.json Hook 등록)
9. [ ] `migrate` — v1.0 환경변수 → config.json
10. [ ] `reindex` — 전체 인덱스 재구축

#### Sprint 3 — 외부 연동 플러그인 (P1)

1. [ ] `exporters/base.py` — BaseExporter 인터페이스
2. [ ] `exporters/loader.py` — config 기반 동적 로드 + 실행
3. [ ] `exporters/notion.py` — Notion API (requests)
4. [ ] `exporters/slack.py` — Webhook (urllib)
5. [ ] `exporters/discord.py` — Webhook (urllib)
6. [ ] `exporters/obsidian.py` — vault 복사/링크
7. [ ] `exporters/github.py` — repo push (gh CLI)
8. [ ] `claude-diary config --add-exporter` 대화형 설정
9. [ ] `.export_queue.json` 재시도 로직

#### Sprint 4 — HTML 대시보드 (P2)

1. [ ] `lib/stats.py` → JSON 직렬화
2. [ ] HTML 템플릿 (히트맵, 파이차트, 라인차트)
3. [ ] `claude-diary dashboard` 명령어
4. [ ] `--serve` 로컬 서버 (http.server)

---

## 9. Coding Convention

### 9.1 Naming

| Target | Rule | Example |
|--------|------|---------|
| 모듈 | snake_case | `git_info.py`, `secret_scanner.py` |
| 클래스 | PascalCase | `BaseExporter`, `NotionExporter` |
| 함수/변수 | snake_case | `parse_transcript()`, `entry_data` |
| 상수 | UPPER_SNAKE_CASE | `DEFAULT_RULES`, `BASIC_PATTERNS` |
| TypedDict | PascalCase | `EntryData`, `GitInfo` |

### 9.2 Import Order

```python
# 1. 표준 라이브러리
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional

# 2. 프로젝트 내부
from claude_diary.config import load_config
from claude_diary.lib.parser import parse_transcript
from claude_diary.types import EntryData
```

### 9.3 Python Version

- 최소: Python 3.7 (TypedDict 호환)
- 타겟: Python 3.7 ~ 3.12
- f-string 사용, walrus operator(:=) 미사용 (3.7 호환)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-03-17 | Initial draft | sol + Claude |
