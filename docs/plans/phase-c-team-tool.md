# Phase C — 팀/회사 도구 (Team/Company Tool)

## Executive Summary

| 관점 | 내용 |
|------|------|
| **Problem** | 개인 일지 도구로는 팀 단위 작업 추적/보안/리포팅이 불가능 |
| **Solution** | 보안 강화(마스킹/필터/접근제어) + Git 중앙 repo + 팀 리포트 |
| **Function UX Effect** | `init --team` 1분 온보딩 → 자동 팀 일지 수집 → `claude-diary team`으로 팀 현황 파악 |
| **Core Value** | 팀 개발 활동의 가시성과 보안을 동시에 확보 |

> Claude Code Working Diary v4.0
> 작성일: 2026-03-17
> 상태: Plan
> 선행 조건: Phase A + Phase B 완료

---

## 1. 개요

### 목표
개인 도구(A) + 오픈소스 도구(B)를 기반으로, **팀 단위로 작업 일지를 수집, 보호, 분석**할 수 있는 기능을 추가한다.

### 핵심 원칙
- **보안 최우선** — 팀원의 민감 정보 보호, 접근 제어, opt-out 보장
- **서버리스 우선** — Git + Notion으로 시작, 자체 서버는 향후 확장
- **프로젝트 중심** — 개인이 아닌 프로젝트 단위로 활동을 조망

---

## 2. 보안 (최우선)

### 2.1 경로 마스킹

민감한 파일 경로를 자동 필터링.

**`~/.config/claude-diary/config.json`:**

```json
{
  "security": {
    "mask_paths": [
      "**/credentials/**",
      "**/secrets/**",
      "**/\.env*",
      "**/*secret*",
      "**/*credential*"
    ]
  }
}
```

**동작:**
```
원본: /srv/payment/src/credentials/StripeKeyManager.java
마스킹: /srv/payment/src/****/****
```

- glob 패턴 매칭
- 파일명과 디렉토리명 모두 마스킹
- 팀 config에서 공통 규칙 설정 가능

### 2.2 콘텐츠 필터

프롬프트/요약에서 특정 키워드를 포함한 문장 제거.

**`~/.config/claude-diary/config.json`:**

```json
{
  "security": {
    "content_filters": [
      "salary", "compensation", "급여", "연봉",
      "personal", "private", "개인정보"
    ],
    "filter_mode": "redact"
  }
}
```

**filter_mode:**
- `redact`: 해당 문장을 `[REDACTED]`로 치환
- `skip`: 해당 키워드가 포함된 세션 전체를 기록하지 않음

### 2.3 접근 제어

팀 일지에 대한 열람 권한 계층.

| 역할 | 본인 일지 | 타인 일지 (요약) | 타인 일지 (상세) | 팀 통계 |
|------|-----------|-----------------|-----------------|---------|
| member | ✅ 전체 | ✅ 프로젝트/카테고리만 | ❌ | ✅ |
| lead | ✅ 전체 | ✅ 전체 | ✅ 같은 프로젝트만 | ✅ |
| admin | ✅ 전체 | ✅ 전체 | ✅ 전체 | ✅ |

**구현 방식:**
- Git repo: GitHub/GitLab 팀 권한으로 제어
- Notion DB: Notion 권한 시스템 활용
- CLI: `claude-diary team` 명령 시 config의 `role` 기반 필터링

### 2.4 세션 Opt-out

특정 세션을 기록에서 제외하는 방법.

**방법 1 — 환경변수:**

```bash
# 이 세션은 기록하지 않음
export CLAUDE_DIARY_SKIP=1
claude  # 세션 시작
```

**방법 2 — 프로젝트별 제외:**

```json
// ~/.config/claude-diary/config.json
{
  "skip_projects": [
    "personal-notes",
    "salary-calculator"
  ]
}
```

**방법 3 — 대화형 제외:**

```bash
# 직전 세션 삭제
claude-diary delete --last

# 특정 세션 삭제
claude-diary delete --session abc12345
```

### 2.5 시크릿 스캔 강화 (B에서 확장)

팀 환경에서 추가 패턴:

```json
{
  "security": {
    "additional_secret_patterns": [
      "internal\\.company\\.com",
      "\\b\\d{3}-\\d{2}-\\d{4}\\b",
      "사번|employee.?id"
    ]
  }
}
```

- 팀 admin이 공통 패턴을 설정
- 팀 config가 개인 config보다 우선 (보안 규칙은 강화만 가능)

---

## 3. 팀 아키텍처

### 3.1 Phase C-1: Git 중앙 Repo (서버리스)

```
team-diary-repo/                    ← 팀 공유 Git 저장소
├── .team-config.json               ← 팀 공통 설정
├── members/
│   ├── sol/
│   │   ├── 2026-03-17.md
│   │   └── 2026-03-18.md
│   ├── alex/
│   │   ├── 2026-03-17.md
│   │   └── 2026-03-18.md
│   └── ...
├── weekly/
│   ├── team-W12_2026-03-16.md      ← 팀 주간 리포트
│   └── team-W13_2026-03-23.md
└── dashboard/
    └── index.html                  ← 팀 HTML 대시보드
```

**동작 흐름:**

```
세션 종료
    │
    ▼
working-diary.py (코어)
    ├── ~/working-diary/2026-03-17.md (개인 로컬)
    │
    └── GitHub exporter
        ├── 보안 필터 적용 (마스킹, 콘텐츠 필터)
        ├── members/sol/2026-03-17.md에 push
        └── (접근 제어는 GitHub 권한으로)
```

**팀 설정 파일 (.team-config.json):**

```json
{
  "team_name": "backend-team",
  "members": ["sol", "alex", "jordan"],
  "security": {
    "mask_paths": ["**/credentials/**"],
    "content_filters": ["salary"],
    "required_secret_scan": true
  },
  "roles": {
    "sol": "admin",
    "alex": "lead",
    "jordan": "member"
  }
}
```

### 3.2 Phase C-2: Notion 팀 DB (선택 추가)

Git repo와 병행 가능.

**Notion DB 구조:**

| 컬럼 | 타입 | 설명 |
|------|------|------|
| 날짜 | Date | 자동 |
| 작성자 | Select | 팀원 이름 |
| 프로젝트 | Select | cwd 기반 |
| 카테고리 | Multi-select | 자동 분류 |
| 작업 요약 | Rich Text | summary_hints |
| 변경량 | Number | +/- lines |
| Git 커밋 | Rich Text | 커밋 목록 |
| 수정 파일 수 | Number | 파일 개수 |

- 팀 Notion workspace에 공유 DB 생성
- 각 팀원의 exporter가 같은 DB에 기록
- Notion의 필터/정렬/뷰로 팀 분석

### 3.3 Phase C-3: 자체 서버 (향후 확장)

**현재는 plan에만 기록. 필요 시 구현.**

- FastAPI 경량 서버
- REST API: POST /entries, GET /stats, GET /dashboard
- 인증: API key 또는 OAuth
- 저장: SQLite → PostgreSQL
- 배포: Docker 컨테이너

---

## 4. 팀 CLI 명령어

### 4.1 팀 활동 조회

```bash
# 팀 전체 이번 주 요약
claude-diary team

# 프로젝트별 팀 활동
claude-diary team --project ai-chatbot

# 특정 팀원의 활동 (권한에 따라 상세도 다름)
claude-diary team --member alex

# 팀 주간 리포트 생성
claude-diary team weekly

# 팀 월간 리포트
claude-diary team monthly --month 2026-03
```

### 4.2 팀 stats 출력 예시

```
╔══════════════════════════════════════════════════╗
║  📊 Team Stats — backend-team | W12              ║
╠══════════════════════════════════════════════════╣
║                                                  ║
║  👥 팀원: 3  |  세션: 23  |  +2,481 / -567 lines ║
║                                                  ║
║  📁 프로젝트별                                    ║
║  ai-chatbot   ████████████░░░░ 14  (sol:8 alex:4 jordan:2)
║  blog         ████░░░░░░░░░░░░  5  (sol:3 alex:2)
║  infra        ████░░░░░░░░░░░░  4  (jordan:4)
║                                                  ║
║  👤 팀원별                                        ║
║  sol    ████████████░░░░ 12  feature(7) bugfix(3) refactor(2)
║  alex   ████████░░░░░░░░  7  feature(3) docs(2) bugfix(2)
║  jordan ██████░░░░░░░░░░  4  config(3) feature(1)
║                                                  ║
╚══════════════════════════════════════════════════╝
```

### 4.3 팀 주간 리포트 예시

```markdown
# 📊 팀 주간 리포트 — backend-team W12
### 2026-03-16 ~ 2026-03-22

## 📈 주간 요약

| 항목 | 수치 |
|------|------|
| 총 세션 | **23** |
| 활동 팀원 | **3** / 3 |
| 관련 프로젝트 | **3** |
| 코드 변경량 | **+2,481 / -567** |

## 👤 팀원별 활동

### sol (12세션)
- 🏷️ feature(7) bugfix(3) refactor(2)
- 📁 ai-chatbot, blog
- 주요: Circuit breaker 패턴 구현, 로그인 버그 수정

### alex (7세션)
- 🏷️ feature(3) docs(2) bugfix(2)
- 📁 ai-chatbot, blog
- 주요: API 문서 업데이트, 페이지네이션 구현

### jordan (4세션)
- 🏷️ config(3) feature(1)
- 📁 infra
- 주요: CI/CD 파이프라인 설정, 모니터링 추가
```

---

## 5. 팀 온보딩

### 5.1 팀 설정 흐름

```bash
# 1. admin이 팀 diary repo 생성
gh repo create team-diary --private

# 2. 각 팀원이 설치 + 팀 연결
pip install claude-diary
claude-diary init --team https://github.com/org/team-diary.git

# init --team이 하는 일:
# ✓ 개인 설정 (Phase A init과 동일)
# ✓ 팀 repo clone
# ✓ .team-config.json에서 팀 보안 규칙 로드
# ✓ GitHub exporter 자동 활성화
# ✓ 팀원 이름 설정
```

### 5.2 팀원 추가

```bash
# admin이 팀 config에 추가
claude-diary team add-member --name newbie --role member

# newbie가 자기 PC에서
claude-diary init --team https://github.com/org/team-diary.git
```

---

## 6. 구현 순서

### Sprint C-1 — 보안 강화 (최우선)

```
1. 경로 마스킹 (glob 패턴 기반)
2. 콘텐츠 필터 (키워드 기반 redact/skip)
3. 세션 opt-out (환경변수, 프로젝트별, 대화형 삭제)
4. 팀 시크릿 패턴 확장
5. 접근 제어 역할 시스템 (member/lead/admin)
```

### Sprint C-2 — Git 중앙 Repo

```
1. GitHub exporter 확장 (팀 repo 구조)
2. .team-config.json 스키마 정의
3. 보안 필터 → push 파이프라인 통합
4. claude-diary init --team 명령어
5. claude-diary team 기본 명령어 (요약, 프로젝트별)
```

### Sprint C-3 — 팀 리포트 + 통계

```
1. claude-diary team stats (터미널 대시보드)
2. claude-diary team weekly/monthly (마크다운 리포트)
3. 팀원별 활동 조회 (권한 기반 필터링)
4. 프로젝트 중심 뷰
5. 팀 HTML 대시보드 (Phase A dashboard 확장)
```

### Sprint C-4 — Notion 팀 DB (선택)

```
1. Notion exporter 팀 모드 (공유 DB)
2. 작성자 컬럼 자동 설정
3. 팀 Notion 뷰 가이드 문서
```

### (향후) Sprint C-5 — 자체 서버

```
1. FastAPI 서버 설계
2. REST API 구현
3. 웹 대시보드
4. Docker 이미지
5. 인증/인가
```

---

## 7. 기술 제약 및 결정

### 7.1 팀 Config 우선순위

```
팀 보안 규칙 (.team-config.json)
    ↓ (강화만 가능, 약화 불가)
개인 보안 규칙 (~/.config/claude-diary/config.json)
    ↓ (추가 규칙 가능)
기본 시크릿 스캔 (항상 활성)
```

- 팀 admin이 `mask_paths`에 추가한 경로는 개인이 해제할 수 없음
- 개인은 추가 마스킹만 가능
- 시크릿 스캔은 비활성화 불가

### 7.2 Git Push 전략

- auto push: 세션 종료마다 자동 (기본, 권장)
- manual push: `claude-diary team sync`로 수동
- batch push: 하루 1회 일괄 (cron/scheduler)

config에서 선택:

```json
{
  "team": {
    "push_strategy": "auto"
  }
}
```

### 7.3 충돌 방지

- 각 팀원은 `members/{name}/` 하위에만 쓰기
- 동일 파일 수정 불가 → 충돌 원천 차단
- 팀 리포트(`weekly/`)는 admin만 생성

---

## 8. Phase C 완료 기준

- [ ] 민감 경로가 자동 마스킹됨
- [ ] 콘텐츠 필터가 키워드 기반으로 동작함
- [ ] `CLAUDE_DIARY_SKIP=1`로 세션 제외 가능
- [ ] `claude-diary delete --last`로 직전 세션 삭제 가능
- [ ] 팀 Git repo에 각 팀원 일지가 자동 push됨
- [ ] `.team-config.json` 보안 규칙이 개인 설정보다 우선 적용됨
- [ ] `claude-diary team` 명령으로 팀 활동 조회 가능
- [ ] `claude-diary team weekly`로 팀 주간 리포트 생성 가능
- [ ] member/lead/admin 역할별 접근 범위가 다름
- [ ] `claude-diary init --team`으로 1분 내 팀 온보딩 완료
- [ ] 한국어/영어 모두 동작

---

## 9. YAGNI Review

**전체 기능 유지: 0건 deferred.**

Phase C에서 정의한 모든 기능은 유지 대상으로 확정됨.

**검토 사항:**
- 3-tier 접근 제어 (member/lead/admin)가 과도한지 논의됨 — Git repo 권한만으로 충분할 수 있으나, Notion DB나 향후 자체 서버 시나리오에서는 Git 권한으로 커버 불가능하므로 **유지** 결정.

---

## 10. Cross-Phase Validation

### Phase A/B 의존성

- **Phase A**: `src/claude_diary/` 패키지 구조를 그대로 사용. GitHub exporter를 팀 repo push에 재활용.
- **Phase B**: `pip install claude-diary` 패키지 배포 기반, secret scanner 모듈, audit 기능 활용.

### Config 우선순위 규칙

- 팀 config (`.team-config.json`)는 개인 config (`~/.config/claude-diary/config.json`)를 override함.
- **보안은 강화만 가능** — 팀에서 설정한 마스킹/필터/시크릿 패턴은 개인이 해제할 수 없고, 개인은 추가 규칙만 설정 가능.

### Exporter 재사용

- Phase A에서 구현한 GitHub exporter를 팀 repo push에 그대로 재사용.
- 팀 모드에서는 보안 필터 파이프라인을 push 전에 추가 적용.

---

## 11. Brainstorming Log

### 핵심 결정 사항

1. **기능 우선순위**: 보안 > 프로젝트 뷰 > 팀 리포트 = 대시보드
   - 팀 도구에서 보안이 확보되지 않으면 아무도 채택하지 않음. 보안이 반드시 먼저.

2. **아키텍처 진행 순서**: Git repo → Notion → 자체 서버
   - Git repo는 서버리스이고 팀 대부분이 이미 사용 중. 가장 낮은 진입 장벽.
   - Notion은 비개발 직군과의 공유에 유용하므로 선택 옵션으로 추가.
   - 자체 서버는 YAGNI 원칙에 따라 plan에만 기록하고, 실제 필요가 확인될 때까지 구현 보류.

3. **Opt-out은 팀 채택의 핵심**
   - 팀원이 "감시당한다"고 느끼면 도구 자체를 거부함.
   - 환경변수/프로젝트별/대화형 삭제 등 다양한 opt-out 경로를 보장해야 자발적 채택이 가능.

4. **하이브리드 아키텍처 + 자체 서버 YAGNI**
   - Git + Notion 하이브리드로 대부분의 팀 시나리오를 커버 가능.
   - 자체 서버는 수십 명 이상 규모에서만 의미가 있으므로, 현재 단계에서는 구현하지 않음.
