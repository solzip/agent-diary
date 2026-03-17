#!/usr/bin/env python3
"""
Claude Code Working Diary - 주간 요약 생성기
=============================================
일일 작업일지(.md)를 읽어 주간 요약 리포트를 자동 생성합니다.

사용법:
  python3 weekly-summary.py              # 이번 주 요약 생성
  python3 weekly-summary.py 2026-03-09   # 특정 주의 월요일 날짜 지정
  python3 weekly-summary.py --cron       # cron용 (매주 금요일/일요일 실행)
"""

import os
import re
import sys
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from collections import Counter, defaultdict

# 설정
DIARY_DIR = os.environ.get(
    "CLAUDE_DIARY_DIR",
    os.path.expanduser("~/working-diary")
)
KST = timezone(timedelta(hours=9))


def get_week_range(target_date=None):
    """
    주어진 날짜가 포함된 주의 월~일 날짜 범위를 반환합니다.
    target_date가 None이면 오늘 기준.
    """
    if target_date is None:
        target_date = datetime.now(KST).date()
    
    # 월요일로 이동
    monday = target_date - timedelta(days=target_date.weekday())
    sunday = monday + timedelta(days=6)
    
    dates = []
    for i in range(7):
        dates.append(monday + timedelta(days=i))
    
    return monday, sunday, dates


def parse_daily_file(filepath):
    """일일 일지 파일을 파싱하여 통계를 추출"""
    stats = {
        "sessions": 0,
        "projects": set(),
        "files_created": [],
        "files_modified": [],
        "commands": [],
        "tasks": [],
        "issues": [],
        "raw_entries": [],
    }

    if not os.path.exists(filepath):
        return stats

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except:
        return stats

    # 세션 수 카운트
    stats["sessions"] = content.count("### ⏰")

    # 프로젝트 추출
    project_matches = re.findall(r'📁 `([^`]+)`', content)
    stats["projects"] = set(project_matches)

    # 생성된 파일 추출
    created_matches = re.findall(r'생성된 파일.*?\n((?:\s+- `[^`]+`\n?)+)', content)
    for block in created_matches:
        files = re.findall(r'`([^`]+)`', block)
        stats["files_created"].extend(files)

    # 수정된 파일 추출
    modified_matches = re.findall(r'수정된 파일.*?\n((?:\s+- `[^`]+`\n?)+)', content)
    for block in modified_matches:
        files = re.findall(r'`([^`]+)`', block)
        stats["files_modified"].extend(files)

    # 작업 요약 추출
    summary_matches = re.findall(r'작업 요약.*?\n((?:\s+- .+\n?)+)', content)
    for block in summary_matches:
        items = re.findall(r'- (.+)', block)
        stats["tasks"].extend(items)

    # 이슈 추출
    issue_matches = re.findall(r'발생한 이슈.*?\n((?:\s+- .+\n?)+)', content)
    for block in issue_matches:
        items = re.findall(r'- (.+)', block)
        stats["issues"].extend(items)

    # 작업 요청 추출
    request_matches = re.findall(r'작업 요청.*?\n((?:\s+\d+\. .+\n?)+)', content)
    for block in request_matches:
        items = re.findall(r'\d+\. (.+)', block)
        stats["raw_entries"].extend(items)

    return stats


def generate_weekly_summary(monday_date=None):
    """주간 요약 리포트를 생성합니다."""
    monday, sunday, dates = get_week_range(monday_date)
    
    weekday_names = ["월", "화", "수", "목", "금", "토", "일"]
    
    # 주간 통합 통계
    total_sessions = 0
    all_projects = set()
    all_files_created = []
    all_files_modified = []
    all_tasks = []
    all_issues = []
    all_requests = []
    daily_stats = []

    for i, date in enumerate(dates):
        date_str = date.strftime("%Y-%m-%d")
        filepath = os.path.join(DIARY_DIR, f"{date_str}.md")
        stats = parse_daily_file(filepath)
        
        total_sessions += stats["sessions"]
        all_projects |= stats["projects"]
        all_files_created.extend(stats["files_created"])
        all_files_modified.extend(stats["files_modified"])
        all_tasks.extend(stats["tasks"])
        all_issues.extend(stats["issues"])
        all_requests.extend(stats["raw_entries"])
        
        daily_stats.append({
            "date": date_str,
            "weekday": weekday_names[i],
            "stats": stats,
        })

    # 리포트 생성
    week_str = f"{monday.strftime('%Y-%m-%d')} ~ {sunday.strftime('%Y-%m-%d')}"
    week_num = monday.isocalendar()[1]

    lines = []
    lines.append(f"# 📊 주간 작업 리포트 — W{week_num}")
    lines.append(f"### {week_str}")
    lines.append("")
    lines.append("> 이 파일은 일일 작업일지를 기반으로 자동 생성됩니다.")
    lines.append("")
    lines.append("---")
    lines.append("")

    # ── 주간 요약 통계 ──
    lines.append("## 📈 주간 요약")
    lines.append("")
    lines.append(f"| 항목 | 수치 |")
    lines.append(f"|------|------|")
    lines.append(f"| 총 세션 수 | **{total_sessions}** |")
    lines.append(f"| 활동일 수 | **{sum(1 for d in daily_stats if d['stats']['sessions'] > 0)}** / 7 |")
    lines.append(f"| 관련 프로젝트 | **{len(all_projects)}** |")
    lines.append(f"| 생성 파일 수 | **{len(all_files_created)}** |")
    lines.append(f"| 수정 파일 수 | **{len(all_files_modified)}** |")
    lines.append(f"| 발생 이슈 | **{len(all_issues)}** |")
    lines.append("")

    # ── 프로젝트별 활동 ──
    if all_projects:
        lines.append("## 🗂️ 프로젝트별 활동")
        lines.append("")
        project_counter = Counter()
        for ds in daily_stats:
            for proj in ds["stats"]["projects"]:
                project_counter[proj] += ds["stats"]["sessions"]
        
        for proj, count in project_counter.most_common():
            lines.append(f"- **{proj}**: {count}회 세션")
        lines.append("")

    # ── 일별 활동 요약 ──
    lines.append("## 📅 일별 활동")
    lines.append("")

    for ds in daily_stats:
        date_str = ds["date"]
        weekday = ds["weekday"]
        stats = ds["stats"]
        sessions = stats["sessions"]

        if sessions == 0:
            lines.append(f"### {weekday}요일 ({date_str}) — _활동 없음_")
            lines.append("")
            continue

        projects_str = ", ".join(f"`{p}`" for p in stats["projects"]) if stats["projects"] else "-"
        lines.append(f"### {weekday}요일 ({date_str}) — {sessions}회 세션")
        lines.append(f"- 프로젝트: {projects_str}")
        
        if stats["tasks"]:
            lines.append(f"- 주요 작업:")
            for task in stats["tasks"][:5]:
                lines.append(f"  - {task}")
        
        if stats["files_created"]:
            lines.append(f"- 생성: {len(stats['files_created'])}개 파일")
        if stats["files_modified"]:
            lines.append(f"- 수정: {len(stats['files_modified'])}개 파일")
        if stats["issues"]:
            lines.append(f"- ⚠️ 이슈: {len(stats['issues'])}건")
        
        lines.append("")

    # ── 주요 성과/작업 목록 ──
    if all_tasks:
        lines.append("## ✅ 이번 주 주요 작업")
        lines.append("")
        # 중복 제거
        unique_tasks = list(dict.fromkeys(all_tasks))
        for i, task in enumerate(unique_tasks[:20], 1):
            lines.append(f"{i}. {task}")
        lines.append("")

    # ── 자주 수정된 파일 ──
    if all_files_modified:
        lines.append("## 🔥 자주 수정된 파일 (Top 10)")
        lines.append("")
        file_counter = Counter(all_files_modified)
        for filepath, count in file_counter.most_common(10):
            bar = "█" * min(count, 20)
            lines.append(f"- `{filepath}` — {count}회 {bar}")
        lines.append("")

    # ── 이슈/문제 ──
    if all_issues:
        lines.append("## ⚠️ 발생한 이슈")
        lines.append("")
        for issue in all_issues[:10]:
            lines.append(f"- {issue}")
        lines.append("")

    lines.append("---")
    lines.append(f"_Generated at {datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S')} KST_")
    lines.append("")

    return "\n".join(lines)


def save_weekly_summary(monday_date=None):
    """주간 요약을 파일로 저장"""
    monday, sunday, _ = get_week_range(monday_date)
    
    summary = generate_weekly_summary(monday_date)
    
    weekly_dir = os.path.join(DIARY_DIR, "weekly")
    Path(weekly_dir).mkdir(parents=True, exist_ok=True)
    
    week_num = monday.isocalendar()[1]
    filename = f"W{week_num:02d}_{monday.strftime('%Y-%m-%d')}.md"
    filepath = os.path.join(weekly_dir, filename)
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(summary)
    
    print(f"✅ 주간 요약 생성 완료: {filepath}")
    return filepath


def main():
    target_date = None
    
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if arg == "--cron":
            # cron 모드: 자동 실행
            target_date = datetime.now(KST).date()
        elif arg == "--help":
            print(__doc__)
            sys.exit(0)
        else:
            try:
                target_date = datetime.strptime(arg, "%Y-%m-%d").date()
            except ValueError:
                print(f"❌ 잘못된 날짜 형식: {arg} (YYYY-MM-DD 형식 사용)")
                sys.exit(1)
    
    filepath = save_weekly_summary(target_date)
    
    # 표준출력으로 요약 내용도 출력
    monday, _, _ = get_week_range(target_date)
    summary = generate_weekly_summary(target_date)
    print("\n" + summary)


if __name__ == "__main__":
    main()
