# Contributing to claude-diary

> [한국어](#한국어) | [English](#english)

## English

Thank you for your interest in contributing to claude-diary!

### How to Contribute

#### Reporting Bugs
- Use the [Bug Report](https://github.com/solzip/claude-code-hooks-diary/issues/new?template=bug_report.md) template
- Include: OS, Python version, steps to reproduce

#### Feature Requests
- Use the [Feature Request](https://github.com/solzip/claude-code-hooks-diary/issues/new?template=feature_request.md) template

#### Contributing an Exporter
1. Inherit from `exporters/base.py` → `BaseExporter`
2. Implement `export()` and `validate_config()`
3. Set `TRUST_LEVEL = "community"`
4. Write tests in `tests/test_exporters/`
5. Submit PR

#### Rules
- Core code modifications are not accepted (exporters/categorizers only)
- External dependencies must be optional (`[project.optional-dependencies]`)
- Documentation in both Korean and English
- Security review required for all PRs
- All tests must pass (`pytest tests/`)

### Development Setup

```bash
git clone https://github.com/solzip/claude-code-hooks-diary.git
cd claude-code-hooks-diary
pip install pytest
PYTHONPATH=src pytest tests/ -v
```

### Exporter Trust Levels

| Level | Description |
|-------|-------------|
| 🟢 Official | Included in the project, code-reviewed |
| 🟡 Community | Contributed via PR, reviewed |
| 🔴 Custom | User-created, not verified |

---

## 한국어

claude-diary에 기여해 주셔서 감사합니다!

### 기여 방법

#### 버그 리포트
- [Bug Report](https://github.com/solzip/claude-code-hooks-diary/issues/new?template=bug_report.md) 템플릿 사용
- OS, Python 버전, 재현 단계 포함

#### 기능 요청
- [Feature Request](https://github.com/solzip/claude-code-hooks-diary/issues/new?template=feature_request.md) 템플릿 사용

#### Exporter 기여
1. `exporters/base.py`의 `BaseExporter` 상속
2. `export()`, `validate_config()` 구현
3. `TRUST_LEVEL = "community"` 설정
4. `tests/test_exporters/`에 테스트 작성
5. PR 제출

#### 규칙
- 코어 코드 수정은 받지 않습니다 (exporter/categorizer만)
- 외부 의존성은 optional dependency로 추가
- 한국어/영어 문서 모두 작성
- 모든 PR은 보안 리뷰 필수
- 모든 테스트 통과 필수 (`pytest tests/`)
