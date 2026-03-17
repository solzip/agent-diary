# Phase D — 배포 전략 (Distribution Strategy)

## Executive Summary

| 관점 | 내용 |
|------|------|
| **Problem** | 코드는 완성되었지만, 사용자에게 도달하는 경로가 GitHub clone뿐 |
| **Solution** | 커뮤니티 마켓플레이스 + PyPI + 공식 마켓플레이스 3단계 배포 |
| **Function UX Effect** | `/plugin install` 또는 `pip install` 한 줄로 즉시 사용 가능 |
| **Core Value** | Claude Code 생태계 최초의 작업일지 도구로 포지셔닝 |

> Claude Code Working Diary v4.x → v5.0
> 작성일: 2026-03-17
> 상태: 🔄 In Progress (D-1, D-2, D-3 완료 / D-4 미진행)
> 선행 조건: Phase A + B + C 완료

---

## 1. 개요

### 현재 상태
- v4.0.0 코드 완성 (코어 + CLI + 5 exporters + 팀 기능 + 보안 + 40 테스트)
- GitHub public repo에 공개됨
- 설치 방법: `git clone` → `install.sh` 또는 소스 직접 사용
- **문제: 발견성 제로, 설치 허들 높음**

### 목표
사용자가 **한 줄로 설치**하고, **검색으로 발견**할 수 있게 만든다.

### 핵심 원칙
- **토큰/API 사용 제로** — 배포 과정에서도 사용자에게 비용 발생 없음
- **점진적 배포** — 커뮤니티 → PyPI → 공식, 각 단계에서 피드백 수집
- **이중 배포** — pip과 플러그인 동시 지원, 사용자가 선택

---

## 2. 배포 경로 비교

| 경로 | 설치 방법 | 대상 | 발견성 | 통제력 | 리스크 |
|------|-----------|------|--------|--------|--------|
| GitHub (현재) | `git clone` | 개발자 | 낮음 | 완전 | 없음 |
| 커뮤니티 마켓플레이스 | `/plugin marketplace add` + `/plugin install` | Claude Code 사용자 | 중간 | 완전 | 없음 |
| PyPI | `pip install claude-diary` | Python 개발자 | 높음 | 완전 | 낮음 |
| 공식 Anthropic 마켓플레이스 | `/plugin install` (기본 목록) | 전체 Claude Code 사용자 | 최고 | 낮음 | 거절 가능 |

---

## 3. Sprint 구성

### Sprint D-1 — Claude Code 플러그인 변환 (커뮤니티 마켓플레이스)

#### 3.1.1 플러그인 구조 추가

```
.claude-plugin/
├── plugin.json              ← 매니페스트
└── hooks.json               ← Stop Hook 자동 등록
```

**plugin.json:**

```json
{
  "name": "working-diary",
  "description": "Auto-generate work diaries from Claude Code sessions (KO/EN)",
  "version": "4.0.0",
  "author": {
    "name": "solzip",
    "url": "https://github.com/solzip"
  },
  "repository": "https://github.com/solzip/claude-code-hooks-diary",
  "license": "MIT",
  "keywords": ["diary", "productivity", "hooks", "work-log", "automation"],
  "engines": {
    "claude-code": ">=2.1.0"
  }
}
```

**hooks.json:**

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python -m claude_diary.hook"
          }
        ]
      }
    ]
  }
}
```

#### 3.1.2 커뮤니티 마켓플레이스 호스팅

- GitHub repo 자체가 마켓플레이스 역할
- 사용자 설치 방법:

```bash
# 1. 마켓플레이스 추가
/plugin marketplace add https://github.com/solzip/claude-code-hooks-diary

# 2. 플러그인 설치
/plugin install working-diary
```

#### 3.1.3 플러그인 설치 시 자동 수행

- `~/.claude/settings.json`에 Stop Hook 자동 등록
- `pip install claude-diary` 안내 (또는 자동 실행)
- `claude-diary init` 트리거

---

### Sprint D-2 — PyPI 정식 배포

#### 3.2.1 사전 준비

- [ ] `pyproject.toml` 최종 점검 (version, description, classifiers)
- [ ] `README.en.md`를 PyPI 표시용으로 설정
- [ ] `CHANGELOG.md` 업데이트
- [ ] 로컬 빌드 테스트: `python -m build`
- [ ] TestPyPI 배포: `twine upload --repository testpypi dist/*`
- [ ] TestPyPI에서 설치 테스트: `pip install -i https://test.pypi.org/simple/ claude-diary`

#### 3.2.2 정식 배포

- [ ] PyPI 계정 생성 + API 토큰 발급
- [ ] GitHub Actions release.yml에 PyPI 토큰 설정 (repository secret)
- [ ] `git tag v4.1.0 && git push --tags` → 자동 배포 트리거
- [ ] PyPI 페이지 확인: https://pypi.org/project/claude-diary/

#### 3.2.3 PyPI 페이지 최적화

- 프로젝트 설명 (영어)
- 키워드: claude-code, productivity, work-diary, automation, hooks
- Classifiers 확인
- 홈페이지/Repository URL 확인

---

### Sprint D-3 — GitHub 최적화 + 홍보

#### 3.3.1 GitHub Repo 최적화

- [ ] Topics 설정: `claude-code`, `productivity`, `work-diary`, `automation`, `hooks`, `developer-tools`, `python`
- [ ] About 설정: "Auto-generate work diaries from Claude Code sessions (KO/EN)"
- [ ] Social preview 이미지 (1280×640)
- [ ] Badges 추가 (README):
  - ![PyPI](https://img.shields.io/pypi/v/claude-diary)
  - ![CI](https://github.com/solzip/claude-code-hooks-diary/actions/workflows/ci.yml/badge.svg)
  - ![License](https://img.shields.io/github/license/solzip/claude-code-hooks-diary)
  - ![Python](https://img.shields.io/pypi/pyversions/claude-diary)

#### 3.3.2 GIF 데모

30초 데모 GIF 생성:
1. Claude Code 세션 → 작업 수행
2. 세션 종료 → 일지 자동 생성 확인
3. `claude-diary search` → 결과 표시
4. `claude-diary stats` → 대시보드 표시

도구: [asciinema](https://asciinema.org/) 또는 [VHS](https://github.com/charmbracelet/vhs)

#### 3.3.3 홍보 채널

| 채널 | 형태 | 시기 |
|------|------|------|
| Claude Code Discord/Forum | 소개 포스트 | PyPI 배포 후 |
| Reddit r/ClaudeAI | 사용 사례 포스트 | 피드백 수집 후 |
| GitHub Discussions | FAQ + 사용 가이드 | 즉시 |
| 개인 블로그/X | 만든 과정 + 사용법 | 선택 |

---

### Sprint D-4 — 공식 마켓플레이스 제출 (안정화 후)

#### 3.4.1 제출 전 체크리스트

- [ ] 커뮤니티 마켓플레이스에서 최소 2주 운영
- [ ] 사용자 피드백 반영 (최소 1 iteration)
- [ ] 버그 리포트 0건 (또는 모두 해결)
- [ ] 테스트 커버리지 90%+
- [ ] CI 전 플랫폼 통과 (Python 3.8~3.12 × 3 OS)
- [ ] SECURITY.md, CONTRIBUTING.md, LICENSE 완비
- [ ] README에 GIF 데모 + 명확한 설치/사용 가이드

#### 3.4.2 제출

- https://claude.ai/settings/plugins/submit
- 또는 https://platform.claude.com/plugins/submit

#### 3.4.3 거절 시 대응

- 피드백 기반 수정 후 재제출
- 커뮤니티 마켓플레이스 + PyPI는 계속 유지 (독립적)

---

## 4. 기술 결정

### 4.1 플러그인 vs pip 관계

```
사용자 선택:

경로 A (Claude Code 네이티브):
  /plugin install working-diary
  → hooks.json이 Stop Hook 자동 등록
  → pip install claude-diary 안내
  → claude-diary init 실행

경로 B (Python 개발자):
  pip install claude-diary
  → claude-diary init
  → settings.json에 Stop Hook 수동 등록

경로 C (수동):
  git clone + ./install.sh (기존 v1.0 방식)
```

두 경로 모두 결과는 동일: Stop Hook이 등록되고, 세션 종료마다 일지 자동 생성.

### 4.2 버전 동기화

- plugin.json의 version과 pyproject.toml의 version을 동기화
- Git tag가 single source of truth: `v4.1.0` → 둘 다 `4.1.0`

### 4.3 토큰 사용 제로 원칙

- 플러그인 설치/사용에 API 토큰 불필요
- PyPI 배포는 maintainer만 토큰 필요 (GitHub Actions secret)
- 사용자는 토큰 없이 100% 기능 사용 가능
- Exporter 토큰은 사용자가 직접 설정하는 **선택적** 기능

---

## 5. 완료 기준

### Sprint D-1 (커뮤니티 마켓플레이스) ✅
- [x] `.claude-plugin/plugin.json` 작성
- [x] `.claude-plugin/hooks.json` 작성
- [x] `/plugin marketplace add` 테스트
- [x] `/plugin install working-diary` 테스트

### Sprint D-2 (PyPI)
- [ ] TestPyPI 배포 성공
- [ ] `pip install claude-diary` 동작 확인
- [ ] `claude-diary --version` → `4.1.0`
- [x] GitHub Actions release workflow 동작

### Sprint D-3 (GitHub 최적화) ✅
- [x] Topics, About, Badges 설정
- [ ] GIF 데모 추가
- [ ] 최소 1개 채널에 소개 포스트

### Sprint D-4 (공식 마켓플레이스)
- [ ] 제출 완료
- [ ] 승인 또는 피드백 수신

---

## 6. YAGNI Review

| 항목 | 판정 | 비고 |
|------|------|------|
| 커뮤니티 마켓플레이스 | KEEP | 즉시 배포 가능, 리스크 제로 |
| PyPI | KEEP | Python 개발자 표준 채널 |
| GitHub 최적화 | KEEP | 비용 제로, 효과 높음 |
| GIF 데모 | KEEP | README의 핵심 (백문이불여일견) |
| 공식 마켓플레이스 | KEEP (후순위) | 안정화 후 제출 |
| 블로그/SNS 홍보 | DEFER | 도구 안정화 후 선택적 |

---

## 7. Brainstorming Log

### 결정 1: 커뮤니티 먼저, 공식은 나중에
- **근거**: 공식 마켓플레이스 리뷰 기준이 불투명. 먼저 거절되면 인상 나쁨. 커뮤니티에서 검증 후 제출이 현실적

### 결정 2: pip과 플러그인 이중 배포
- **근거**: Claude Code 사용자는 플러그인, 일반 개발자는 pip. 타겟이 다름. 코드는 동일하고 매니페스트만 추가

### 결정 3: 토큰 제로 원칙 유지
- **근거**: 이 도구의 핵심 가치는 "무료, 로컬, 자동". 배포 과정에서도 이 원칙을 깨면 안 됨
