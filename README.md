# 📓 Claude Code Working Diary

[![CI](https://github.com/solzip/claude-code-hooks-diary/actions/workflows/ci.yml/badge.svg)](https://github.com/solzip/claude-code-hooks-diary/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.7+](https://img.shields.io/badge/python-3.7+-blue.svg)](https://www.python.org/downloads/)

> **[English](README.en.md)** | 한국어

> ⚠️ This is a community project, not officially affiliated with Anthropic.

Claude Code에서 작업한 내용을 **자동으로** 일일/주간 작업일지로 기록하는 시스템

## 어떻게 동작하나요?

```
Claude Code 세션 종료
        │
        ▼
  Stop Hook 실행 ──→ working-diary.py
        │
        ▼
  transcript.jsonl 파싱
  (사용자 요청, 수정 파일, 실행 명령어 추출)
        │
        ▼
  ~/working-diary/2026-03-17.md 에 자동 기록
```

매 세션이 끝날 때마다 Claude Code의 **Stop Hook**이 자동 실행되어,
트랜스크립트를 분석하고 당일 날짜의 마크다운 파일에 작업 내용을 추가합니다.

## 지원 환경

| 플랫폼 | Python | 자동 일지 | 주간 요약 | Cron |
|--------|--------|-----------|-----------|------|
| macOS | python3 | ✅ | ✅ | ✅ |
| Linux | python3 | ✅ | ✅ | ✅ |
| Windows (Git Bash) | python | ✅ | ✅ | ❌ (Task Scheduler 사용) |

## 기록되는 내용

| 항목 | 설명 |
|------|------|
| 📋 작업 요청 | 사용자가 Claude에게 요청한 내용 |
| 📄 생성된 파일 | 새로 만들어진 파일 목록 |
| ✏️ 수정된 파일 | 편집된 파일 목록 |
| ⚡ 주요 명령어 | 실행된 중요 shell 명령어 |
| 📝 작업 요약 | AI가 수행한 작업의 요약 |
| ⚠️ 이슈 | 발생한 오류나 문제 |

## 설치

### 방법 1: pip (권장)

```bash
pip install claude-diary
claude-diary init
```

### 방법 2: Claude Code 플러그인

```bash
# Claude Code 안에서
/plugin marketplace add https://github.com/solzip/claude-code-hooks-diary
/plugin install working-diary
```

### 방법 3: 수동 설치

```bash
git clone https://github.com/solzip/claude-code-hooks-diary.git
cd claude-code-hooks-diary/working-diary-system
./install.sh
```

설치 후 자동으로:
- Stop Hook 등록 (세션 종료마다 자동 실행)
- `~/working-diary/` 디렉토리 생성
- 설정 파일 생성

## 디렉토리 구조

```
~/working-diary/
├── 2026-03-15.md          ← 일일 작업일지
├── 2026-03-16.md
├── 2026-03-17.md
├── .session_counts.json    ← 내부 카운트 (자동)
├── .gitignore
└── weekly/
    ├── W11_2026-03-09.md   ← 주간 요약 리포트
    └── W12_2026-03-16.md
```

## 일지 예시

```markdown
# 📓 작업일지 — 2026-03-17 (화요일)

> 이 파일은 Claude Code Stop Hook에 의해 자동 생성됩니다.
> 각 세션이 종료될 때마다 작업 내용이 자동으로 기록됩니다.

---

### ⏰ 09:32:15 | 📁 `ai-chatbot`

**📋 작업 요청:**
  1. WebSocket 핸들러에 circuit breaker 패턴 구현해줘
  2. 에러 코드 정의서 업데이트

**📄 생성된 파일:**
  - `.../handler/CircuitBreakerHandler.java`

**✏️ 수정된 파일:**
  - `.../config/WebSocketConfig.java`
  - `.../constant/ErrorCode.java`

**⚡ 주요 명령어:**
  - `./gradlew test`
  - `./gradlew bootRun`

**📝 작업 요약:**
  - Circuit breaker 패턴이 WebSocket 핸들러에 구현 완료
  - 3단계 상태 전환(CLOSED→OPEN→HALF_OPEN) 로직 추가
```

## 환경변수 설정

| 환경변수 | 설명 | 기본값 |
|----------|------|--------|
| `CLAUDE_DIARY_LANG` | 일지 언어 (`ko` 또는 `en`) | `ko` |
| `CLAUDE_DIARY_DIR` | 일지 저장 경로 | `~/working-diary` |
| `CLAUDE_DIARY_TZ_OFFSET` | UTC 오프셋 | `9` (KST) |

```bash
# ~/.bashrc 또는 ~/.zshrc에 추가
export CLAUDE_DIARY_LANG="ko"
export CLAUDE_DIARY_DIR="$HOME/working-diary"
export CLAUDE_DIARY_TZ_OFFSET="9"
```

**Windows 환경변수 설정:**
```powershell
# PowerShell (영구 설정)
[Environment]::SetEnvironmentVariable("CLAUDE_DIARY_LANG", "ko", "User")
[Environment]::SetEnvironmentVariable("CLAUDE_DIARY_DIR", "$env:USERPROFILE\working-diary", "User")
```

## 주간 요약 생성

```bash
# 이번 주 요약
python ~/.claude/hooks/weekly-summary.py

# 특정 주 요약
python ~/.claude/hooks/weekly-summary.py 2026-03-10
```

## Hook 설정 확인

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python ~/.claude/hooks/working-diary.py"
          }
        ]
      }
    ]
  }
}
```

## 제거

```bash
./install.sh --uninstall
```

작업일지 데이터(`~/working-diary/`)는 보존됩니다.

## 요구사항

- Python 3.6+ (`python3` or `python`)
- Claude Code (hooks 지원 버전)

## 팁

**CLAUDE.md에 추가하면 더 좋은 일지가 생성됩니다:**

```markdown
## 작업일지
- 세션 종료 시 작업 내용이 자동 기록됩니다
- 작업 완료/구현/수정 시 한국어로 명확한 요약을 출력해주세요
```

**Git으로 일지를 관리하면** 작업 이력을 추적할 수 있습니다:

```bash
cd ~/working-diary
git init && git add -A && git commit -m "diary: $(date +%Y-%m-%d)"
```

## 로드맵

이 프로젝트는 3단계로 진화합니다:

| Phase | 목표 | 상태 |
|-------|------|------|
| **A** | 개인 생산성 도구 (카테고리, Git연동, CLI, 플러그인, 대시보드) | 📋 Plan |
| **B** | 오픈소스 커뮤니티 (보안 강화, pip 배포, 테스트, CI/CD) | 📋 Plan |
| **C** | 팀/회사 도구 (접근 제어, Git 중앙 repo, 팀 리포트) | 📋 Plan |

자세한 내용은 [`docs/plans/`](docs/plans/) 디렉토리를 참고하세요.

## 라이선스

MIT License
