#!/usr/bin/env python3
"""
Claude Code Working Diary - Auto Logger
========================================
Stop Hook에서 자동 실행되어 세션 내용을 일일 작업일지에 기록합니다.

사용법:
  - Claude Code의 Stop Hook으로 등록
  - stdin으로 세션 JSON 데이터를 받음
  - ~/working-diary/YYYY-MM-DD.md 파일에 자동 기록
"""

import json
import sys
import os
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ============================================================
# 설정 (사용자 환경에 맞게 수정)
# ============================================================
# 작업일지 저장 경로 (기본: ~/working-diary)
DIARY_DIR = os.environ.get(
    "CLAUDE_DIARY_DIR",
    os.path.expanduser("~/working-diary")
)
# 타임존 (한국 KST = UTC+9)
KST = timezone(timedelta(hours=9))
# 일지에 포함할 최대 항목 수
MAX_ACTIONS_PER_ENTRY = 30
# transcript에서 읽을 최대 줄 수 (너무 큰 세션 방지)
MAX_TRANSCRIPT_LINES = 2000


def get_today_str():
    """오늘 날짜 문자열 (KST 기준)"""
    return datetime.now(KST).strftime("%Y-%m-%d")


def get_now_str():
    """현재 시각 문자열 (KST 기준)"""
    return datetime.now(KST).strftime("%H:%M:%S")


def get_weekday_kr():
    """한국어 요일"""
    days = ["월", "화", "수", "목", "금", "토", "일"]
    return days[datetime.now(KST).weekday()]


def ensure_diary_dir():
    """일지 디렉토리 생성"""
    Path(DIARY_DIR).mkdir(parents=True, exist_ok=True)
    # weekly 서브디렉토리도 생성
    Path(DIARY_DIR, "weekly").mkdir(parents=True, exist_ok=True)


def parse_transcript(transcript_path):
    """
    JSONL 트랜스크립트를 파싱하여 주요 작업 내용을 추출합니다.
    
    Returns:
        dict: {
            "user_prompts": [...],       # 사용자가 요청한 내용들
            "files_modified": [...],     # 수정/생성된 파일 목록
            "commands_run": [...],       # 실행된 명령어들
            "tools_used": [...],         # 사용된 도구들
            "summary_hints": [...]       # 요약을 위한 힌트들
        }
    """
    result = {
        "user_prompts": [],
        "files_modified": set(),
        "files_created": set(),
        "commands_run": [],
        "tools_used": set(),
        "errors_encountered": [],
        "summary_hints": [],
    }

    if not transcript_path or not os.path.exists(transcript_path):
        return result

    try:
        line_count = 0
        with open(transcript_path, "r", encoding="utf-8") as f:
            for line in f:
                line_count += 1
                if line_count > MAX_TRANSCRIPT_LINES:
                    break

                line = line.strip()
                if not line:
                    continue

                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                # 사용자 메시지 추출
                if entry.get("type") == "human" or entry.get("role") == "user":
                    content = extract_text_content(entry)
                    if content and len(content) > 5:
                        # 첫 100자만 저장 (간결하게)
                        result["user_prompts"].append(content[:200])

                # 도구 사용 추출
                if entry.get("type") == "tool_use" or "tool_name" in entry:
                    tool_name = entry.get("tool_name") or entry.get("name", "")
                    tool_input = entry.get("tool_input") or entry.get("input", {})

                    if tool_name:
                        result["tools_used"].add(tool_name)

                    # 파일 수정/생성 감지
                    if tool_name in ("Write", "write_to_file", "file_write"):
                        file_path = tool_input.get("file_path") or tool_input.get("path", "")
                        if file_path:
                            result["files_created"].add(shorten_path(file_path))

                    elif tool_name in ("Edit", "MultiEdit", "edit_file", "str_replace_editor"):
                        file_path = tool_input.get("file_path") or tool_input.get("path", "")
                        if file_path:
                            result["files_modified"].add(shorten_path(file_path))

                    # 명령어 실행 감지
                    elif tool_name in ("Bash", "execute_command", "bash"):
                        command = tool_input.get("command", "")
                        if command and not is_noise_command(command):
                            result["commands_run"].append(command[:150])

                # assistant 메시지에서 요약 힌트 추출
                if entry.get("type") == "assistant" or entry.get("role") == "assistant":
                    content = extract_text_content(entry)
                    if content:
                        # "완료", "구현", "수정", "추가" 등의 키워드 포함 문장 추출
                        for keyword in ["완료", "구현", "수정", "추가", "삭제", "생성",
                                        "설정", "배포", "테스트", "리팩토링", "fixed",
                                        "implemented", "created", "updated", "added",
                                        "configured", "deployed", "tested", "refactored"]:
                            if keyword in content.lower():
                                # 해당 키워드가 포함된 문장 추출
                                sentences = re.split(r'[.!?\n]', content)
                                for sent in sentences:
                                    if keyword in sent.lower() and 10 < len(sent.strip()) < 200:
                                        result["summary_hints"].append(sent.strip())
                                break

    except Exception as e:
        result["errors_encountered"].append(f"Transcript parse error: {str(e)}")

    # set을 list로 변환
    result["files_modified"] = sorted(result["files_modified"])
    result["files_created"] = sorted(result["files_created"])
    result["tools_used"] = sorted(result["tools_used"])

    # 중복 제거
    result["summary_hints"] = list(dict.fromkeys(result["summary_hints"]))[:10]
    result["commands_run"] = result["commands_run"][:MAX_ACTIONS_PER_ENTRY]

    return result


def extract_text_content(entry):
    """메시지 엔트리에서 텍스트 내용을 추출"""
    content = entry.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                texts.append(block.get("text", ""))
            elif isinstance(block, str):
                texts.append(block)
        return " ".join(texts)
    return ""


def shorten_path(file_path):
    """파일 경로를 간결하게 줄임"""
    # 홈 디렉토리 축약
    home = os.path.expanduser("~")
    if file_path.startswith(home):
        file_path = "~" + file_path[len(home):]
    # 너무 긴 경로는 마지막 3 세그먼트만
    parts = file_path.split("/")
    if len(parts) > 4:
        file_path = ".../" + "/".join(parts[-3:])
    return file_path


def is_noise_command(command):
    """의미 없는 노이즈 명령어 필터링"""
    noise_patterns = [
        r"^(cat|ls|pwd|echo|cd|which|type|file)\s",
        r"^(cat|ls|pwd)$",
        r"^head\s",
        r"^tail\s",
        r"^wc\s",
        r"^find .* -name",
        r"^grep -r",
    ]
    for pattern in noise_patterns:
        if re.match(pattern, command.strip()):
            return True
    return False


def extract_project_name(cwd):
    """작업 디렉토리에서 프로젝트 이름 추출"""
    if not cwd:
        return "unknown"
    return os.path.basename(cwd.rstrip("/"))


def format_diary_entry(session_id, cwd, parsed_data):
    """마크다운 형식의 일지 엔트리 생성"""
    now = get_now_str()
    project = extract_project_name(cwd)

    lines = []
    lines.append(f"### ⏰ {now} | 📁 `{project}`")
    lines.append("")

    # 사용자 요청 (무엇을 했는지의 핵심)
    if parsed_data["user_prompts"]:
        lines.append("**📋 작업 요청:**")
        for i, prompt in enumerate(parsed_data["user_prompts"][:5], 1):
            # 긴 프롬프트는 자르기
            prompt_short = prompt.replace("\n", " ").strip()
            if len(prompt_short) > 150:
                prompt_short = prompt_short[:150] + "..."
            lines.append(f"  {i}. {prompt_short}")
        lines.append("")

    # 생성된 파일
    if parsed_data["files_created"]:
        lines.append("**📄 생성된 파일:**")
        for f in parsed_data["files_created"][:15]:
            lines.append(f"  - `{f}`")
        lines.append("")

    # 수정된 파일
    if parsed_data["files_modified"]:
        lines.append("**✏️ 수정된 파일:**")
        for f in parsed_data["files_modified"][:15]:
            lines.append(f"  - `{f}`")
        lines.append("")

    # 실행된 주요 명령어
    significant_commands = [
        cmd for cmd in parsed_data["commands_run"]
        if not is_trivial_command(cmd)
    ][:10]
    if significant_commands:
        lines.append("**⚡ 주요 명령어:**")
        for cmd in significant_commands:
            cmd_short = cmd[:120] + ("..." if len(cmd) > 120 else "")
            lines.append(f"  - `{cmd_short}`")
        lines.append("")

    # AI 작업 요약 힌트
    if parsed_data["summary_hints"]:
        lines.append("**📝 작업 요약:**")
        for hint in parsed_data["summary_hints"][:5]:
            lines.append(f"  - {hint}")
        lines.append("")

    # 에러가 있었다면
    if parsed_data["errors_encountered"]:
        lines.append("**⚠️ 발생한 이슈:**")
        for err in parsed_data["errors_encountered"][:3]:
            lines.append(f"  - {err}")
        lines.append("")

    lines.append(f"<details><summary>세션 ID: <code>{session_id[:8]}...</code></summary>")
    lines.append(f"<code>{session_id}</code>")
    lines.append("</details>")
    lines.append("")
    lines.append("---")
    lines.append("")

    return "\n".join(lines)


def is_trivial_command(cmd):
    """사소한 명령어 필터링"""
    trivial = ["ls", "pwd", "cat", "echo", "cd", "which", "type", "clear"]
    first_word = cmd.strip().split()[0] if cmd.strip() else ""
    return first_word in trivial


def create_daily_header(date_str):
    """일일 일지 헤더 생성"""
    weekday = get_weekday_kr()
    return f"""# 📓 작업일지 — {date_str} ({weekday}요일)

> 이 파일은 Claude Code Stop Hook에 의해 자동 생성됩니다.
> 각 세션이 종료될 때마다 작업 내용이 자동으로 기록됩니다.

---

"""


def append_to_diary(entry_text, date_str=None):
    """일지 파일에 엔트리 추가"""
    if date_str is None:
        date_str = get_today_str()

    diary_path = os.path.join(DIARY_DIR, f"{date_str}.md")

    # 파일이 없으면 헤더와 함께 생성
    if not os.path.exists(diary_path):
        with open(diary_path, "w", encoding="utf-8") as f:
            f.write(create_daily_header(date_str))

    # 엔트리 추가
    with open(diary_path, "a", encoding="utf-8") as f:
        f.write(entry_text)


def update_session_count(date_str):
    """하루 세션 카운트를 별도 파일로 추적"""
    count_file = os.path.join(DIARY_DIR, ".session_counts.json")
    counts = {}
    if os.path.exists(count_file):
        try:
            with open(count_file, "r") as f:
                counts = json.load(f)
        except:
            counts = {}
    
    counts[date_str] = counts.get(date_str, 0) + 1
    
    with open(count_file, "w") as f:
        json.dump(counts, f, indent=2)
    
    return counts[date_str]


def main():
    """메인 실행 로직"""
    try:
        # stdin에서 Hook 데이터 읽기
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        # JSON 파싱 실패시 조용히 종료
        sys.exit(0)

    session_id = input_data.get("session_id", "unknown")
    transcript_path = input_data.get("transcript_path", "")
    cwd = input_data.get("cwd", "")

    # 일지 디렉토리 확인
    ensure_diary_dir()

    # 트랜스크립트 파싱
    parsed = parse_transcript(transcript_path)

    # 내용이 너무 적으면 (사소한 세션) 기록 생략
    has_content = (
        len(parsed["user_prompts"]) > 0 or
        len(parsed["files_modified"]) > 0 or
        len(parsed["files_created"]) > 0 or
        len(parsed["commands_run"]) > 0
    )
    if not has_content:
        sys.exit(0)

    # 일지 엔트리 생성
    entry = format_diary_entry(session_id, cwd, parsed)

    # 오늘 날짜의 일지에 추가
    date_str = get_today_str()
    append_to_diary(entry, date_str)

    # 세션 카운트 업데이트
    count = update_session_count(date_str)

    # 성공 메시지 (verbose 모드에서 표시됨)
    project = extract_project_name(cwd)
    sys.stderr.write(
        f"[diary] Logged session #{count} for {date_str} | project: {project}\n"
    )

    sys.exit(0)


if __name__ == "__main__":
    main()
