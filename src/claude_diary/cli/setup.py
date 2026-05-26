"""Install/uninstall commands — register claude-diary hook in Claude Code settings."""

import json
import os
import sys


HOOK_COMMAND = "PYTHONIOENCODING=utf-8 python -m claude_diary.hook"

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

현재 세션의 transcript와 git 정보를 분석하여 Notion 업무일지 DB에 push.

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

3. **각 task별 추출**
   - `title`: 30~50자 명사구. 시제/주어/prefix/마침표 없음
     - ✅ "Notion DB 컬럼 스키마 결정", "git_info.py 리팩토링"
     - ❌ "오늘 DB 의논했다", "[설계] DB 컬럼"
   - `body_intro`: 1~3문장, 200~500자, 평어체, 결과 중심
     - transcript에 없는 내용 추가 금지 (추측 X)
     - markdown 강조(`**굵게**`, `` `코드` ` ` ) 사용 OK
   - `categories`: 1~3개 (design/refactor/bugfix/test/docs/infra/discussion 등 자유 라벨)
   - `project`: 현재 cwd의 폴더명
   - `user_prompts`, `files_modified`, `files_created`, `commands_run`, `errors`
   - `commit_hashes`: 이 task에 해당하는 commit (0개도 OK)

4. **JSON 저장 및 CLI 호출**
   - cwd 에 `.diary-notion-<8자리random>.json` 파일을 Write 도구로 생성
   - `!claude-diary notion push --input .diary-notion-<8자리>.json` 실행
   - 종료 후 임시 파일 삭제 (CLI도 try/finally로 삭제하지만 보험)

## JSON 형식

```json
{
  "session_id": "<현재 세션 ID>",
  "tasks": [
    {
      "title": "...",
      "body_intro": "...",
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


SLASH_COMMANDS = {
    # filename: (file content, marker substring used to detect "ours")
    "diary.md": (DIARY_SLASH_COMMAND, "claude-diary write"),
    "diary-notion.md": (DIARY_NOTION_SLASH_COMMAND, "claude-diary notion push"),
}


def _get_slash_command_path(filename="diary.md"):
    """Return path to ~/.claude/commands/<filename>."""
    home = os.path.expanduser("~")
    return os.path.join(home, ".claude", "commands", filename)


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
    """Check if claude-diary hook is already registered.
    Returns True if found.
    """
    hooks = settings.get("hooks", {})
    stop_hooks = hooks.get("Stop", [])
    for group in stop_hooks:
        for hook in group.get("hooks", []):
            if _is_diary_hook(hook):
                return True
    return False


def cmd_install(args):
    """Register claude-diary Stop hook + all slash commands."""
    settings_path = _get_claude_settings_path()
    settings = _load_claude_settings(settings_path)

    if _find_existing_hook(settings):
        hook_status = "already installed"
    else:
        if "hooks" not in settings:
            settings["hooks"] = {}
        if "Stop" not in settings["hooks"]:
            settings["hooks"]["Stop"] = []
        settings["hooks"]["Stop"].append({"hooks": [HOOK_ENTRY]})
        _save_claude_settings(settings_path, settings)
        hook_status = "installed"

    # Slash command install runs unconditionally — fixes upgrade path for
    # users who installed before a given slash command was a feature.
    slash_statuses = _install_all_slash_commands()

    print("claude-diary install:")
    print("  Hook: %s (%s)" % (HOOK_COMMAND, hook_status))
    print("  Settings: %s" % settings_path)
    for filename, (path, status) in slash_statuses.items():
        print("  Slash command %s: %s (%s)" % (filename, path, status))
    print()
    print("Stop Hook auto-writes a diary entry on session exit.")
    print("Type /diary to write a manual entry, or /diary-notion to push to Notion.")


def _install_all_slash_commands():
    """Install every slash command in SLASH_COMMANDS. Returns {filename: (path, status)}."""
    results = {}
    for filename, (content, _marker) in SLASH_COMMANDS.items():
        path = _get_slash_command_path(filename)
        results[filename] = (path, _install_slash_command(path, content))
    return results


def _install_slash_command(path, content):
    """Create the slash command file if missing.

    Returns 'installed', 'already exists', or 'failed: <reason>'.
    """
    if os.path.exists(path):
        return "already exists"
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return "installed"
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


def cmd_uninstall(args):
    """Remove claude-diary Stop hook + slash commands."""
    settings_path = _get_claude_settings_path()
    settings = _load_claude_settings(settings_path)

    if not _find_existing_hook(settings):
        print("claude-diary hook is not installed.")
        # Still clean up slash commands if any are present
        slash_statuses = _uninstall_all_slash_commands()
        for filename, (path, status) in slash_statuses.items():
            if status != "not present":
                print("  Slash command %s: %s (%s)" % (filename, path, status))
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

    print("claude-diary hook uninstalled.")
    print("  Settings: %s" % settings_path)
    for filename, (path, status) in slash_statuses.items():
        print("  Slash command %s: %s (%s)" % (filename, path, status))
