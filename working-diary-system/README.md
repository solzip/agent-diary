# 📓 Claude Code Working Diary

> Claude Code에서 작업한 내용을 **자동으로** 일일/주간 작업일지로 기록하는 시스템

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

```bash
# 1. 이 디렉토리를 원하는 위치에 다운로드
git clone <repo> ~/working-diary-system
# 또는 그냥 파일들을 복사

# 2. 설치 스크립트 실행
cd ~/working-diary-system
chmod +x install.sh
./install.sh
```

설치 스크립트가 자동으로:
- `~/.claude/hooks/` 에 스크립트 복사
- `~/.claude/settings.json` 에 Stop Hook 등록
- `~/working-diary/` 디렉토리 생성
- (선택) 주간 요약 cron job 등록

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

## 일일 일지 예시

```markdown
# 📓 작업일지 — 2026-03-17 (화요일)

> 이 파일은 Claude Code Stop Hook에 의해 자동 생성됩니다.

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

---

### ⏰ 14:15:42 | 📁 `hunikflow-docs`

...
```

## 주간 요약 생성

```bash
# 이번 주 요약
python3 ~/.claude/hooks/weekly-summary.py

# 특정 주 요약 (해당 주의 아무 날짜 지정)
python3 ~/.claude/hooks/weekly-summary.py 2026-03-10
```

cron 등록 시 매주 금요일 18:00에 자동 생성됩니다.

## 커스터마이징

### 저장 경로 변경

```bash
# 환경변수로 경로 지정 (~/.bashrc 또는 ~/.zshrc에 추가)
export CLAUDE_DIARY_DIR="$HOME/Documents/work-diary"
```

### Hook 설정 확인

```bash
# settings.json 직접 확인
cat ~/.claude/settings.json | jq '.hooks.Stop'

# 또는 Claude Code 내에서
/hooks
```

### 현재 등록된 Hook 구조

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 ~/.claude/hooks/working-diary.py"
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

- Python 3.6+
- Claude Code (hooks 지원 버전)
- (권장) jq — JSON 처리용

## 팁

- **CLAUDE.md에 추가하면 더 좋은 일지가 생성됩니다:**

```markdown
## 작업일지
- 세션 종료 시 작업 내용이 자동 기록됩니다
- 작업 완료/구현/수정 시 한국어로 명확한 요약을 출력해주세요
```

- **Git으로 일지를 관리하면** 작업 이력을 추적할 수 있습니다:

```bash
cd ~/working-diary
git init
git add -A
git commit -m "diary: $(date +%Y-%m-%d)"
```
