"""Team management commands."""

import json
import os
from pathlib import Path

import claude_diary.cli as _cli


def cmd_team(args):
    from claude_diary.team import (
        init_team, get_team_repo_path, team_stats,
        print_team_stats, team_weekly_report
    )

    if args.action == "init":
        repo_url = args.repo
        if not repo_url:
            repo_url = input("Team repo URL: ").strip()
        name = args.name
        if not name:
            name = input("Your name: ").strip()
        print("Initializing team mode...")
        init_team(repo_url, name)
        print("\nDone! Sessions will auto-push to team repo.")
        return

    config = _cli.load_config()
    repo_path = get_team_repo_path(config)
    if not repo_path or not os.path.isdir(repo_path):
        print("Team not configured. Run: claude-diary team init --repo <url>")
        return

    if args.action == "stats":
        data = team_stats(repo_path, month=args.month)
        print_team_stats(data)

    elif args.action in ("weekly", "monthly"):
        lang = config.get("lang", "ko")
        result = team_weekly_report(repo_path, lang=lang)
        if result:
            report, filepath = result
            print(report)
            print("---")
            print("Saved: %s" % filepath)
        else:
            print("No team data found.")

    elif args.action == "add-member":
        from claude_diary.team import validate_member_name
        name = args.name or input("Member name: ").strip()
        try:
            validate_member_name(name)
        except ValueError as e:
            print(str(e))
            return
        role = args.role
        team_config_path = os.path.join(repo_path, ".team-config.json")
        tc = {}
        if os.path.exists(team_config_path):
            with open(team_config_path, "r") as f:
                tc = json.load(f)
        tc.setdefault("members", [])
        tc.setdefault("roles", {})
        if name not in tc["members"]:
            tc["members"].append(name)
        tc["roles"][name] = role
        with open(team_config_path, "w") as f:
            json.dump(tc, f, indent=2, ensure_ascii=False)
        # Create member dir
        Path(os.path.join(repo_path, "members", name)).mkdir(parents=True, exist_ok=True)
        print("Added member '%s' with role '%s'" % (name, role))
