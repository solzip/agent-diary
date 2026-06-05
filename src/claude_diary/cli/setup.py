"""Install/uninstall commands — register claude-diary hook in Claude Code settings."""

import json
import os
import sys


HOOK_COMMAND = "python -m claude_diary.hook"

HOOK_ENTRY = {
    "type": "command",
    "command": HOOK_COMMAND,
}

DIARY_SLASH_COMMAND = """\
---
description: 현재 세션 작업일지를 <manual_dir>/<date>/<project>/<date>.md 에 기록 (있으면 append)
allowed-tools:
  - Bash
---

!`claude-diary write`
"""

DIARY_NOTION_SLASH_COMMAND = """\
---
description: 현재 세션을 작업 단위로 분리해 Notion 업무일지 DB에 push
allowed-tools:
  - Bash
  - Read
  - Write
---

# /diary-notion

## Testing / Verification Sessions

- If the session work is testing, QA, review, validation, or verification, create a Notion row for the verification work even when there were no code changes.
- Set `status` to `Testing` and `purpose` to `Test` for verification-only work unless a more specific enum is clearly better.
- Keep `verification` short. Put the meaningful prompt-result document in `prompt_outputs` or `verification_artifacts` so it renders inside a Notion toggle.
- Do not collapse important findings into a vague summary. Put distinct passed checks, failed checks, defects, regressions, blocked checks, skipped checks, and follow-up actions in the prompt-output artifact fields, or create a child task row with `parent_index` when the result needs its own status or owner.

## Core Report Schema

- Prefer schema v2 normalized fields: `summary`, `work`, `decisions`, `risks`, `next_actions`, `support_needed`, and `appendix`.
- Legacy flat fields are still accepted by the CLI, but new output should use v2.
- Notion is the report surface; raw logs, long diffs, and bulky evidence belong in local artifact files and should be referenced by path/hash instead of pasted.
- Page bodies render in this order: summary callout, results, work table, decisions, issues/risks, next actions/support, appendix toggles.
- Put command/file/commit evidence under `appendix`; use `appendix.artifacts` for stdout/stderr/diff/raw-log file references.

현재 세션의 transcript와 git 정보를 분석하여 Notion 업무일지 DB에 push.

## 현재 구현 계약

- `/diary-notion`은 작업 row push 전용. 사용자가 명시적으로 요청하지 않는 한 schema/view ensure를 실행하지 말 것
- `working-diary diary-notion ensure`는 schema v8, native 하위항목, core view 5개, operating view 5개를 보장하는 별도 정비 명령
- 포함 관계는 `parent_index`로 Notion native 하위항목에 기록. native 관계가 아직 활성화돼 있지 않으면 row는 그대로 push하고 하위항목 활성화가 필요함을 보고할 것
- legacy `Parent Task` / `Sub-items`는 호환용 데이터로만 취급하고 JSON에서 직접 지정하지 말 것
- `Depends On`은 큰 최상위 메인 작업끼리의 선행 연결에만 사용하고, 하위 작업에는 절대 종속성을 쓰지 말 것
- `project`에 `"unknown"`을 쓰지 말 것 — 비우거나 생략하면 CLI가 명령 실행 cwd 폴더명으로 보정
- 페이지 본문은 compact executive body로 렌더링됨: 상단 요약, 결과 체크리스트, 작업 한눈에 표, 영향, 검증, 리스크/다음 액션, 부록

## Local Artifact Store

- `diary-notion push` stores local run artifacts under `.codefleet/runs` by default: `input.json`, `git-diff.patch`, `preview.md`, and `manifest.json`.
- Use `--preview-file` for an extra Markdown preview path or `--no-artifacts` to disable local artifact writes.

## 단계

1. **컨텍스트 수집**
   - 이 세션의 user 메시지, 어시스턴트 응답, 호출한 도구 검토
   - `git log` 로 이 세션 중 만든 commit 조회

2. **작업 단위 분리 (Branch 경계 → Semantic-first)**
   - **branch 경계 최우선**: 세션 중 `git switch` 로 branch가 바뀌면 무조건 새 task
   - 같은 branch 안에서는 **의미 단위로 분리** (사고 흐름 = task)
   - 한 commit이 여러 의미 단위에 걸치면 양쪽 task에 같은 hash 매핑
   - 큰 commit("fix: 5건 개선" 같은) 한 번에 묶지 말고 의미별로 분리
   - 짧은 follow-up("ㅇㅇ", "맞아") 은 직전 task에 흡수
   - **commit이 0개인 의논 세션도 정상** — 의미 단위로 task N개 생성
   - 독립 상태/근거/코드 변경/검증 결과가 있거나 다른 작업을 막는 일만 row로 만들 것
   - 단순 확인 항목, 긴 SQL/JS/메모/참고 링크는 별도 row가 아니라 본문 근거로 남길 것
   - `parent_index`는 포함 관계와 Notion 하위항목에 사용하고, 하위 작업을 종속성으로 표현하지 말 것
   - `depends_on_indices`는 큰 메인 작업끼리의 선행 연결성에만 사용할 것
   - 전날/이전 세션에서 이어진 미완료 작업은 같은 `task_group` + `carryover=true`로 새 row 생성

3. **각 task별 추출**
   - 언어 정책:
     - `title`, `body_intro`, `summary_hints`, `key_changes`, `work_context`, `work_scope`, `approach`, `outcome`, `impact`, `decisions`, `implementation_notes`, `verification`, `risks`, `next_steps`, `support_needed`, `next_action`, `block_reason` 같은 설명형 필드는 반드시 한국어로 작성
     - `status`, `purpose` enum 값은 지정된 영어 값을 그대로 사용
     - 파일 경로, 명령어, branch, commit hash, 코드 식별자, 함수/클래스명은 원문 그대로 유지
     - `user_prompts`는 사용자가 말한 원문을 증거로 보존
   - `title`: 30~50자 명사구. 시제/주어/prefix/마침표 없음
     - ✅ "Notion DB 컬럼 스키마 결정", "git_info.py 리팩토링"
     - ❌ "오늘 DB 의논했다", "[설계] DB 컬럼"
   - `body_intro`: 1~3문장, 200~500자, 평어체, 결과 중심
     - transcript에 없는 내용 추가 금지 (추측 X)
     - markdown 강조(`**굵게**`, `` `코드` ` ` ) 사용 OK
   - Notion 작업 DB 기록처럼 작성. 상단은 짧게, 구조는 DB relation으로, 원자료는 본문 부록에 접어두는 기준
   - 본문 렌더링 기준:
     - `body_intro`는 최상단 핵심 요약 callout 1개로만 사용
     - `summary_hints`는 여러 callout이 아니라 checked 결과 항목으로 렌더링되므로 최종 결과만 작성
     - `work_context`, `work_scope`, `approach`, `outcome`은 `작업 한눈에` 표로 렌더링되므로 각각 짧게 작성
     - `verification`에는 최종 검증 상태를 우선 작성하고, 중간 명령 이력은 부록 근거로 이동
     - `risks`는 하나의 warning callout으로 합쳐지므로 간결하게 작성
   - `summary_hints`: 작업 결과/의미 요약 최대 3개. 단순 파일 나열이 아니라 무엇이 달라졌는지 기록
   - `key_changes`: 개발자가 이 일지만 봐도 흐름을 이해할 수 있는 주요 변경사항 최대 3개
   - `work_context`: 왜 이 작업을 시작했는지 0~1개
   - `work_scope`: 무엇을 바꿨는지 0~1개
   - `approach`: 어떻게 해결했는지 0~1개
   - `outcome`: 결과가 무엇인지 0~1개
   - `impact`: 사용자/운영/제품/개발 품질 영향 0~3개
   - `code_change_highlights`: 실제 코드 변화 중 중요한 것만 0~3개
     - 파일/함수/명령 단위 + 동작상 의미를 함께 기록
     - full diff, 단순 포맷팅, import 정리, 문구 수정, fixture 보정은 제외
     - 동작/스키마/CLI/사용자 흐름/검증 범위가 바뀐 코드는 포함
   - `decisions`: 사용자가 결정했거나 구현 중 확정한 선택지/트레이드오프 0~3개
   - `implementation_notes`: 코드 변경 요약에 넣기 애매한 제약/호환성/마이그레이션 메모 0~4개
   - `verification`: 실행한 테스트, 검증 결과, 검증하지 못한 이유 0~3개
   - `risks`: 주의사항, 남은 리스크, 운영/사용 시 헷갈릴 수 있는 점 0~2개
   - `next_steps`: 남은 작업이나 후속 단계 0~2개
   - `support_needed`: 필요한 결정/지원이 있으면 0~1개
   - `status`: 5단계 중 하나 — `Discussion` / `Design` / `Implementation` / `Testing` / `Deployed`
     - 한 task에 여러 단계 섞이면 **가장 진행된 단계로** (Testing 통과까지 했으면 Testing)
     - 결정만 했으면 Design, 코드 작성까지 했으면 Implementation, 테스트까지 했으면 Testing,
       머지/배포까지 했으면 Deployed
   - `work_period`: 실제 작업 기간. 기본은 오늘 날짜 `YYYY-MM-DD`; 여러 날에 걸친 수행분이면 `{"start":"YYYY-MM-DD","end":"YYYY-MM-DD"}` 사용
   - `priority`: `P0`, `P1`, `P2`, `P3` 중 하나. 오늘 바로 처리해야 하면 `P1`, 긴급/차단 해소가 최우선이면 `P0`, 일반 후속이면 `P2`, 낮은 우선순위면 `P3`
   - `next_action`: 다음에 바로 실행할 수 있는 구체적 행동 0~1개
   - `blocked`: 외부 결정/권한/정보 없이는 진행할 수 없을 때만 `true`
   - `block_reason`: `blocked`가 `true`이면 원인을 한국어로 작성
   - `carryover`: 전날 또는 이전 세션의 미완료 작업을 오늘 이어서 처리한 row이면 `true`
   - `review_status`: 검토가 필요하면 `Needs Review`, 검토 완료면 `Reviewed`, 뒤로 미루면 `Deferred`
   - `last_reviewed`: 실제로 검토한 날짜가 있으면 `YYYY-MM-DD`
   - `task_group`: 며칠/여러 세션에 걸치는 큰 작업 단위 식별자 (예: `diary-notion-impl`, `auth-refactor`)
     - 같은 큰 작업의 task들끼리 같은 그룹명 사용 → Notion에서 group view로 묶임
     - 이전 작업의 연속이면 같은 그룹명, 새 작업이면 새 그룹명 (snake-case/kebab-case 권장)
   - `purpose`: 목적별 1차 분류. 아래 영어 enum 중 하나만 사용
     - `Feature` / `Bugfix` / `Refactor` / `Docs` / `Test` / `Infra`
     - `Planning` / `Research` / `Review` / `Release` / `Support` / `Maintenance` / `General`
     - 불확실하면 `General`
   - `parent_index`: 이 task가 다른 task의 하위 작업이면 부모 task의 **같은 push 내 인덱스**. 최상위 task면 `null`
     - 포함 관계와 Notion 하위항목에만 사용. 예: "상품 목록 포커싱"의 parent는 "로컬 테스트 진행"
   - `depends_on_indices`: 이 task가 선행을 의존하는 다른 task의 **같은 push 내 인덱스 배열** (예: `[0, 1]`)
     - 같은 JSON 안의 tasks 배열 순서 (0-base) 기준
     - 하위 작업이 아니라 큰 메인 작업끼리의 선행 연결성에만 사용. 없으면 빈 배열 `[]`
   - `categories`: 1~3개 (design/refactor/bugfix/test/docs/infra/discussion 등 자유 라벨)
   - `project`: 현재 명령 실행 cwd의 폴더명. `"unknown"`을 쓰지 말 것. 확실하지 않으면 생략하거나 빈 값으로 두면 CLI가 cwd에서 보정함
   - `user_prompts`, `files_modified`, `files_created`, `commands_run`, `errors`
   - `commit_hashes`: 이 task에 해당하는 commit (0개도 OK)

4. **JSON 저장 및 CLI 호출**
   - cwd 에 `.diary-notion-<8자리random>.json` 파일을 Write 도구로 생성
   - `!claude-diary diary-notion push --input .diary-notion-<8자리>.json --dry-run`으로 본문 구조를 먼저 확인
   - 구조가 맞으면 `!claude-diary diary-notion push --input .diary-notion-<8자리>.json` 실행
   - 종료 후 임시 파일 삭제 (CLI도 try/finally로 삭제하지만 보험)

## JSON 형식

```json
{
  "session_id": "<현재 세션 ID>",
  "tasks": [
    {
      "title": "...",
      "body_intro": "...",
      "summary_hints": ["..."],
      "key_changes": ["..."],
      "work_context": ["..."],
      "work_scope": ["..."],
      "approach": ["..."],
      "outcome": ["..."],
      "impact": ["..."],
      "code_change_highlights": ["..."],
      "decisions": ["..."],
      "implementation_notes": ["..."],
      "verification": ["..."],
      "risks": ["..."],
      "next_steps": ["..."],
      "support_needed": ["..."],
      "status": "Implementation",
      "work_period": "2026-06-02",
      "priority": "P1",
      "next_action": "...",
      "blocked": false,
      "block_reason": "",
      "carryover": false,
      "review_status": "Needs Review",
      "last_reviewed": "2026-06-02",
      "task_group": "diary-notion-impl",
      "purpose": "Feature",
      "parent_index": null,
      "depends_on_indices": [0, 1],
      "categories": ["..."],
      "project": "<cwd folder name>",
      "user_prompts": ["..."],
      "files_modified": ["..."],
      "files_created": ["..."],
      "commands_run": ["..."],
      "commit_hashes": ["..."],
      "errors": ["..."]
    }
  ]
}
```

## 빈 결과

`tasks` 가 0개라면 사용자에게 이유 설명 후 CLI 호출 없이 종료.

## 보고

CLI 출력을 사용자에게 그대로 보여주고 어떤 task가 push/skip/fail 되었는지 간략 요약.
"""


CODEX_DIARY_SKILL = """\
---
name: diary
description: Write the current Codex work session to the manual working diary. Use when the user invokes $diary or asks Codex to record the current work session as a Markdown diary entry, including prompts, files, commands, summaries, errors, categories, and git metadata.
---

# Diary

Record the current Codex session as a manual Markdown work diary entry.

## Workflow

1. Summarize the current conversation and tool activity into one diary entry.
2. Use the current cwd folder name as `project`.
3. Create `.diary-<8-random>.json` in cwd with this shape:

```json
{
  "session_id": "<current session id or manual-codex>",
  "project": "<cwd folder name>",
  "user_prompts": ["..."],
  "files_modified": ["..."],
  "files_created": ["..."],
  "commands_run": ["..."],
  "summary_hints": ["..."],
  "errors": ["..."],
  "categories": ["feature"]
}
```

4. Run `working-diary write --input .diary-<8-random>.json`.
5. If `working-diary` is not available, run `claude-diary write --input .diary-<8-random>.json`.
6. Report the CLI result. The CLI removes the temp file after a successful write.

Only include content visible in the current conversation or tool history. Do not invent work.
"""


CODEX_DIARY_NOTION_SKILL = """\
---
name: diary-notion
description: Push the current Codex work session to the hierarchical Notion working diary DB. Use when the user invokes $diary-notion or asks Codex to record the current session in Notion by project, purpose, task group, status, priority, sub-items, dependencies, blockers, next actions, files, commands, and commits.
---

# Diary Notion

Split the current Codex session into task-sized entries and push them to Notion.

## Current Implementation Contract

- `$diary-notion` is a row push workflow only. Do not run schema/view ensure unless the user explicitly asks for it.
- `working-diary diary-notion ensure` is the separate maintenance command that guarantees schema v8, native sub-items, 5 core views, and 5 operating views.
- Use Notion native sub-items for containment by setting `parent_index`. If the native relation is not enabled in Notion, still push the rows and report that sub-item activation is needed.
- Treat legacy `Parent Task` / `Sub-items` as compatibility data only. Do not target them directly in JSON.
- Use `Depends On` only for prerequisite links between large top-level main tasks. Never use dependencies for child tasks.
- Never write `"unknown"` as `project`; omit it or leave it blank so the CLI falls back to the command cwd folder name.
- Page bodies render as compact work reports: summary, results, work table, decisions, issues/risks, next actions/support, and appendix toggles.
- Notion is the report surface; raw logs, long diffs, and bulky evidence belong in local artifact files and should be referenced by path/hash instead of pasted.
- `diary-notion push` writes local run artifacts under `.codefleet/runs` by default: `input.json`, `git-diff.patch`, `preview.md`, and `manifest.json`. Use `--preview-file` for an extra Markdown preview path or `--no-artifacts` to disable local artifact writes.
- For testing, QA, review, validation, or verification sessions, create a row even without code changes; keep `verification` short and place the meaningful prompt-result document in `prompt_outputs` or `verification_artifacts` so it renders inside a toggle.

## Workflow

1. Review the current conversation, tool calls, git branch, and relevant git commits.
2. Split work into task-sized database rows. Branch changes are hard task boundaries; within a branch, split by semantic work unit.
   - Create a row for work that has its own status, evidence, code/test output, or can block another task
   - Create a row for verification-only work even when the session produced no file changes or commits
   - Keep tiny check items, raw notes, long SQL/JS snippets, and reference links inside the page body evidence instead of making them separate rows
   - Create a separate row only when the work has an independent status, verification/evidence, code change, commit, blocker, or follow-up owner
   - For tester/verification sessions, summarize the final state in `verification` and put each meaningful pass, fail, blocker, skipped check, regression, defect, and follow-up in the prompt-output artifact fields
   - Use `parent_index` for containment hierarchy and Notion sub-items; do not model subtasks with dependencies
   - Use `depends_on_indices` only for prerequisite links between large top-level tasks
   - Mark continued work from an earlier day/session as a new row with the same `task_group` and `carryover=true` when it is still unfinished
3. For each task, produce:
   - Prefer schema v2 normalized fields: `summary`, `work`, `decisions`, `risks`, `next_actions`, `support_needed`, and `appendix`.
   - Legacy flat fields are still accepted by the CLI, but new agent output should use v2 unless compatibility with an older installed version is required.
   - Language policy:
     - Write `title`, `summary`, `work`, `decisions`, `risks`, `next_actions`, `support_needed`, `appendix`, `next_action`, and `block_reason` narrative values in Korean
     - Keep `status` and `purpose` as the exact English enum values below
     - Preserve file paths, commands, branches, commit hashes, code identifiers, function names, and class names as written
     - Preserve `user_prompts` in the user's original wording as evidence
   - `title`: concise Korean noun phrase, no prefix or period
   - `body_intro`: 1-3 factual Korean sentences based only on observed work
   - Write it like a Notion task database record: compact top summary, structured relations in DB properties, and raw evidence hidden in the page body appendix
   - Body rendering policy:
     - Use `summary.intro` as the only top summary callout
     - Treat `summary.outcomes`, `summary.verification`, and `summary.remaining` as the compact results checklist
     - Keep `work.context`, `work.scope`, `work.approach`, and `work.state` short because they render as a compact work table
     - Put settled choices in `decisions`; put unresolved external asks in `support_needed`
     - Keep `risks` concise as issue/risk bullets, not raw logs
     - Put developer evidence, prompt outputs, original requests, and command/file/commit evidence in `appendix` toggles
     - For tester/verification sessions, keep `summary.verification` to 1-3 summary items and put the meaningful prompt-result document in `appendix.prompt_outputs` or `appendix.verification_artifacts`; summarize long raw logs instead of pasting them
   - `summary_hints`: up to 3 outcome-focused result items that explain what changed and why it matters
   - `key_changes`: up to 3 major behavior/schema/workflow changes a developer can understand without opening the diff
   - `work_context`: 0-1 bullet explaining why this work started
   - `work_scope`: 0-1 bullet explaining what changed
   - `approach`: 0-1 bullet explaining how it was solved
   - `outcome`: 0-1 bullet explaining the resulting state
   - `impact`: 0-3 user, operations, product, or engineering-quality impacts
   - `code_change_highlights`: 0-3 important code changes only
     - Include file/function/command scope plus runtime or developer-facing meaning
     - Exclude full diffs, formatting-only edits, import cleanup, wording-only edits, and fixture-only noise
     - Include changes to behavior, schema, CLI flow, user workflow, or verification scope
   - `decisions`: 0-3 decisions or tradeoffs made by the user or settled during implementation
   - `implementation_notes`: 0-4 constraints, compatibility notes, migrations, or details that do not fit code highlights
   - `verification`: 0-3 summary tests/checks run, final results, or explicit reasons checks were not run
   - `prompt_outputs`: 0-15 meaningful prompt-result items for tester/verification sessions; include distinct pass/fail/blocker/skipped/regression/defect/follow-up results, not raw logs
   - `verification_artifacts`: 0-15 structured verification artifact items when the prompt output is better grouped as a generated test report or review document
   - `appendix.artifacts`: 0-5 local artifact references with `path`, `kind`, `summary`, and optional `sha256`; use this for stdout/stderr/diff/raw-log evidence
   - `risks`: 0-2 cautions, remaining risks, or usage/operation notes
   - `next_steps`: 0-2 remaining follow-ups
   - `support_needed`: 0-1 decisions or support needed from others
   - `status`: `Discussion`, `Design`, `Implementation`, `Testing`, or `Deployed`
   - `purpose`: `Feature`, `Bugfix`, `Refactor`, `Docs`, `Test`, `Infra`, `Planning`, `Research`, `Review`, `Release`, `Support`, `Maintenance`, or `General`
     - Use `Test` for tester, QA, validation, and verification-only sessions unless another enum is clearly more accurate
   - `work_period`: actual work period; use today's `YYYY-MM-DD` by default, or `{"start":"YYYY-MM-DD","end":"YYYY-MM-DD"}` for a range
   - `priority`: one of `P0`, `P1`, `P2`, `P3`; use `P0` for urgent/blocking work, `P1` for today's highest priority, `P2` for normal follow-up, and `P3` for low priority
   - `next_action`: 0-1 concrete Korean action that can be started next
   - `blocked`: `true` only when the task cannot continue without external decision, permission, or information
   - `block_reason`: Korean reason when `blocked` is `true`
   - `carryover`: `true` when this row continues unfinished work from a previous day/session
   - `review_status`: `Needs Review`, `Reviewed`, or `Deferred`
   - `last_reviewed`: `YYYY-MM-DD` when this work was actually reviewed
   - `task_group`: stable kebab-case/snake-case group for multi-session work
   - `parent_index`: zero-based index of the parent task in this push, or `null`; use it for "part of" hierarchy and Notion sub-items
   - `depends_on_indices`: zero-based indices in this push, or `[]`
     - Use this only when a top-level main task cannot proceed before another top-level main task is done
     - Do not use this for child/subtask rows; use `parent_index` instead
   - `project`: current command cwd folder/repository name. Never write `"unknown"`; if you are not sure, omit the field or leave it empty so the CLI falls back to cwd.
   - `categories`, `user_prompts`, `files_modified`, `files_created`, `commands_run`, `commit_hashes`, `errors`
4. Create `.diary-notion-<8-random>.json` in cwd:

```json
{
  "session_id": "<current session id or codex-manual>",
  "schema_version": 2,
  "tasks": [
    {
      "title": "...",
      "summary": {
        "intro": "...",
        "outcomes": ["..."],
        "verification": ["..."],
        "remaining": ["..."]
      },
      "work": {
        "context": "...",
        "scope": "...",
        "approach": "...",
        "state": "..."
      },
      "decisions": ["..."],
      "risks": ["..."],
      "next_actions": ["..."],
      "support_needed": ["..."],
      "appendix": {
        "key_changes": ["..."],
        "implementation_notes": ["..."],
        "prompt_outputs": ["..."],
        "verification_artifacts": ["..."],
        "user_prompts": ["..."],
        "files_modified": ["..."],
        "files_created": ["..."],
        "commands_run": ["..."],
        "commit_hashes": ["..."],
        "errors": ["..."],
        "artifacts": [
          {
            "kind": "stdout",
            "path": ".codefleet/runs/<run-id>/stdout.log",
            "summary": "raw command output",
            "sha256": "..."
          }
        ]
      },
      "status": "Implementation",
      "purpose": "Feature",
      "work_period": "2026-06-02",
      "priority": "P1",
      "next_action": "...",
      "blocked": false,
      "block_reason": "",
      "carryover": false,
      "review_status": "Needs Review",
      "last_reviewed": "2026-06-02",
      "task_group": "working-diary-notion",
      "parent_index": null,
      "depends_on_indices": [],
      "categories": ["feature"],
      "project": "<cwd folder name>"
    }
  ]
}
```

5. Run `working-diary diary-notion push --input .diary-notion-<8-random>.json --dry-run` to validate v2 input, write local artifacts, and preview the compact report body and appendix toggles without writing to Notion.
6. If the preview is structurally wrong, fix the JSON before pushing.
7. Run `working-diary diary-notion push --input .diary-notion-<8-random>.json`.
8. If `working-diary` is not available, run `claude-diary diary-notion push --input .diary-notion-<8-random>.json`.
9. Report pushed/skipped/failed tasks from the CLI output.

If there are no task-worthy changes, explain that and do not call the CLI.
"""


SLASH_COMMANDS = {
    # filename: (file content, marker substring used to detect "ours")
    "diary.md": (DIARY_SLASH_COMMAND, "claude-diary write"),
    "diary-notion.md": (DIARY_NOTION_SLASH_COMMAND, "claude-diary diary-notion push"),
}


CODEX_SKILLS = {
    "diary": (CODEX_DIARY_SKILL, "working-diary write --input"),
    "diary-notion": (CODEX_DIARY_NOTION_SKILL, "working-diary diary-notion push"),
}


def _get_slash_command_path(filename="diary.md"):
    """Return path to ~/.claude/commands/<filename>."""
    home = os.path.expanduser("~")
    return os.path.join(home, ".claude", "commands", filename)


def _get_codex_skill_path(skill_name):
    """Return path to ~/.codex/skills/<skill_name>/SKILL.md."""
    home = os.path.expanduser("~")
    return os.path.join(home, ".codex", "skills", skill_name, "SKILL.md")


def _get_claude_settings_path():
    """Return path to ~/.claude/settings.json."""
    home = os.path.expanduser("~")
    return os.path.join(home, ".claude", "settings.json")


def _load_claude_settings(path):
    """Load existing settings or return empty dict."""
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {}


def _save_claude_settings(path, settings):
    """Save settings to file, creating directory if needed."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)
        f.write("\n")


def _is_diary_hook(hook):
    """Check if a hook entry is a claude-diary hook."""
    command = hook.get("command", "")
    return "claude_diary.hook" in command


def _find_existing_hook(settings):
    """Return the first claude-diary hook entry if one is registered."""
    hooks = settings.get("hooks", {})
    stop_hooks = hooks.get("Stop", [])
    for group in stop_hooks:
        for hook in group.get("hooks", []):
            if _is_diary_hook(hook):
                return hook
    return None


def cmd_install(args):
    """Register claude-diary Stop hook + all slash commands.

    With --force, refresh the managed hook command and overwrite existing slash
    command files (useful after a claude-diary upgrade).
    """
    force = getattr(args, "force", False) is True
    codex_only = getattr(args, "codex_only", False) is True
    if codex_only:
        codex_statuses = _install_all_codex_skills(force=force)
        print("claude-diary install (codex-only):")
        for skill_name, (path, status) in codex_statuses.items():
            print("  Codex skill $%s: %s (%s)" % (skill_name, path, status))
        print()
        print("In Codex, use $diary or $diary-notion. Open a new Codex session after refresh.")
        return

    settings_path = _get_claude_settings_path()
    settings = _load_claude_settings(settings_path)

    existing_hook = _find_existing_hook(settings)
    if existing_hook:
        if force and existing_hook.get("command") != HOOK_COMMAND:
            existing_hook["type"] = "command"
            existing_hook["command"] = HOOK_COMMAND
            _save_claude_settings(settings_path, settings)
            hook_status = "updated"
        else:
            hook_status = "already installed"
    else:
        if "hooks" not in settings:
            settings["hooks"] = {}
        if "Stop" not in settings["hooks"]:
            settings["hooks"]["Stop"] = []
        settings["hooks"]["Stop"].append({"hooks": [HOOK_ENTRY]})
        _save_claude_settings(settings_path, settings)
        hook_status = "installed"

    install_codex = getattr(args, "codex", False) is True
    # Slash command install runs unconditionally — fixes upgrade path for
    # users who installed before a given slash command was a feature.
    slash_statuses = _install_all_slash_commands(force=force)
    codex_statuses = _install_all_codex_skills(force=force) if install_codex else {}

    print("claude-diary install:")
    print("  Hook: %s (%s)" % (HOOK_COMMAND, hook_status))
    print("  Settings: %s" % settings_path)
    for filename, (path, status) in slash_statuses.items():
        print("  Slash command %s: %s (%s)" % (filename, path, status))
    for skill_name, (path, status) in codex_statuses.items():
        print("  Codex skill $%s: %s (%s)" % (skill_name, path, status))
    print()
    print("Stop Hook auto-writes a diary entry on session exit.")
    print("Type /diary to write a manual entry, or /diary-notion to push to Notion.")
    if install_codex:
        print("In Codex, use $diary or $diary-notion.")


def _install_all_slash_commands(force=False):
    """Install every slash command in SLASH_COMMANDS. Returns {filename: (path, status)}."""
    results = {}
    for filename, (content, marker) in SLASH_COMMANDS.items():
        path = _get_slash_command_path(filename)
        results[filename] = (path, _install_slash_command(path, content, marker, force))
    return results


def _install_all_codex_skills(force=False):
    """Install Codex skills in ~/.codex/skills. Returns {skill: (path, status)}."""
    results = {}
    for skill_name, (content, marker) in CODEX_SKILLS.items():
        path = _get_codex_skill_path(skill_name)
        results[skill_name] = (path, _install_slash_command(path, content, marker, force))
    return results


def _install_slash_command(path, content, marker=None, force=False):
    """Create or refresh the slash command file.

    Without `force`: skip if the file already exists (preserves user customizations).
    With `force`: overwrite only if the existing file looks like ours (contains
    `marker`); files modified by the user are still preserved.

    Returns 'installed', 'overwritten', 'already exists', 'skipped (modified by user)',
    or 'failed: <reason>'.
    """
    exists = os.path.exists(path)
    if exists and not force:
        return "already exists"
    if exists and force:
        try:
            with open(path, "r", encoding="utf-8") as f:
                existing = f.read()
        except OSError as e:
            return "failed: %s" % e
        if marker and marker not in existing:
            return "skipped (modified by user)"
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return "overwritten" if exists else "installed"
    except OSError as e:
        return "failed: %s" % e


def _uninstall_slash_command(path, marker):
    """Remove the slash command file only if its content contains the marker."""
    if not os.path.exists(path):
        return "not present"
    try:
        with open(path, "r", encoding="utf-8") as f:
            existing = f.read()
        if marker not in existing:
            return "skipped (modified by user)"
        os.remove(path)
        return "removed"
    except OSError as e:
        return "failed: %s" % e


def _uninstall_all_slash_commands():
    """Uninstall every slash command in SLASH_COMMANDS. Returns {filename: (path, status)}."""
    results = {}
    for filename, (_content, marker) in SLASH_COMMANDS.items():
        path = _get_slash_command_path(filename)
        results[filename] = (path, _uninstall_slash_command(path, marker))
    return results


def _uninstall_all_codex_skills():
    """Uninstall Codex skills that still contain our marker."""
    results = {}
    for skill_name, (_content, marker) in CODEX_SKILLS.items():
        path = _get_codex_skill_path(skill_name)
        results[skill_name] = (path, _uninstall_slash_command(path, marker))
    return results


def cmd_uninstall(args):
    """Remove claude-diary Stop hook + slash commands."""
    uninstall_codex = getattr(args, "codex", False) is True
    codex_only = getattr(args, "codex_only", False) is True
    if codex_only:
        codex_statuses = _uninstall_all_codex_skills()
        print("claude-diary uninstall (codex-only):")
        for skill_name, (path, status) in codex_statuses.items():
            print("  Codex skill $%s: %s (%s)" % (skill_name, path, status))
        return

    settings_path = _get_claude_settings_path()
    settings = _load_claude_settings(settings_path)

    if not _find_existing_hook(settings):
        print("claude-diary hook is not installed.")
        # Still clean up slash commands if any are present
        slash_statuses = _uninstall_all_slash_commands()
        for filename, (path, status) in slash_statuses.items():
            if status != "not present":
                print("  Slash command %s: %s (%s)" % (filename, path, status))
        if uninstall_codex:
            codex_statuses = _uninstall_all_codex_skills()
            for skill_name, (path, status) in codex_statuses.items():
                if status != "not present":
                    print("  Codex skill $%s: %s (%s)" % (skill_name, path, status))
        return

    # Remove diary hooks
    stop_hooks = settings.get("hooks", {}).get("Stop", [])
    new_stop = []
    for group in stop_hooks:
        remaining = [h for h in group.get("hooks", []) if not _is_diary_hook(h)]
        if remaining:
            new_stop.append({"hooks": remaining})

    settings["hooks"]["Stop"] = new_stop

    # Clean up empty structures
    if not settings["hooks"]["Stop"]:
        del settings["hooks"]["Stop"]
    if not settings["hooks"]:
        del settings["hooks"]

    _save_claude_settings(settings_path, settings)

    slash_statuses = _uninstall_all_slash_commands()
    codex_statuses = _uninstall_all_codex_skills() if uninstall_codex else {}

    print("claude-diary hook uninstalled.")
    print("  Settings: %s" % settings_path)
    for filename, (path, status) in slash_statuses.items():
        print("  Slash command %s: %s (%s)" % (filename, path, status))
    for skill_name, (path, status) in codex_statuses.items():
        print("  Codex skill $%s: %s (%s)" % (skill_name, path, status))
