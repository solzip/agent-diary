#!/usr/bin/env python
"""claude-diary CLI — search, filter, stats, and manage your work diary."""

import argparse
import sys

# Re-export dependencies so submodules can access them via claude_diary.cli.*
# and so that tests can patch them at claude_diary.cli.<name>.
from claude_diary.config import load_config, save_config, get_config_path, migrate_from_env
from claude_diary.i18n import get_label
from claude_diary.indexer import load_index
from claude_diary.lib.stats import parse_daily_file
from claude_diary.writer import ensure_diary_dir

# Import command functions from submodules
from claude_diary.cli.search import cmd_search, cmd_filter, cmd_trace, _fallback_search_from_files
from claude_diary.cli.stats import cmd_stats, cmd_weekly, _get_terminal_width, _print_box_top, _print_box_bottom
from claude_diary.cli.config import cmd_config, cmd_init, cmd_migrate, _add_exporter_interactive
from claude_diary.cli.team import cmd_team
from claude_diary.cli.maintenance import cmd_reindex, cmd_audit, cmd_delete, cmd_dashboard
from claude_diary.cli.setup import cmd_install, cmd_uninstall
from claude_diary.cli.write import cmd_write


def main():
    parser = argparse.ArgumentParser(
        prog="claude-diary",
        description="Auto-generated work diary from Claude Code sessions",
    )
    from claude_diary import __version__
    parser.add_argument("--version", action="version", version="claude-diary %s" % __version__)

    sub = parser.add_subparsers(dest="command")

    # search
    p_search = sub.add_parser("search", help="Search diary entries by keyword")
    p_search.add_argument("keyword", help="Keyword to search")
    p_search.add_argument("--project", "-p", help="Filter by project")
    p_search.add_argument("--category", "-c", help="Filter by category")
    p_search.add_argument("--from", dest="date_from", help="Start date (YYYY-MM-DD)")
    p_search.add_argument("--to", dest="date_to", help="End date (YYYY-MM-DD)")
    p_search.add_argument("--json", dest="json_output", action="store_true", help="Output as JSON")

    # filter
    p_filter = sub.add_parser("filter", help="Filter diary entries")
    p_filter.add_argument("--project", "-p", help="Filter by project")
    p_filter.add_argument("--category", "-c", help="Filter by category")
    p_filter.add_argument("--month", "-m", help="Filter by month (YYYY-MM)")
    p_filter.add_argument("--json", dest="json_output", action="store_true", help="Output as JSON")

    # trace
    p_trace = sub.add_parser("trace", help="Trace file change history")
    p_trace.add_argument("filepath", help="File path or glob pattern to trace")
    p_trace.add_argument("--project", "-p", help="Filter by project")

    # stats
    p_stats = sub.add_parser("stats", help="Show terminal dashboard")
    p_stats.add_argument("--month", "-m", help="Month (YYYY-MM)")
    p_stats.add_argument("--project", "-p", help="Filter by project")

    # weekly
    p_weekly = sub.add_parser("weekly", help="Generate weekly summary")
    p_weekly.add_argument("date", nargs="?", help="Any date in target week (YYYY-MM-DD)")

    # config
    p_config = sub.add_parser("config", help="View or update configuration")
    p_config.add_argument("--set", dest="set_value", help="Set config (key=value)")
    p_config.add_argument("--add-exporter", help="Add exporter (interactive)")

    # init
    p_init = sub.add_parser("init", help="Initialize claude-diary setup")
    p_init.add_argument("--team", dest="team_repo", help="Team repo URL for team mode")

    # migrate
    sub.add_parser("migrate", help="Migrate v1.0 env vars to config.json")

    # team
    p_team = sub.add_parser("team", help="Team management commands")
    p_team.add_argument("action", nargs="?", default="stats",
                        choices=["stats", "weekly", "monthly", "init", "add-member"],
                        help="Team action")
    p_team.add_argument("--project", "-p", help="Filter by project")
    p_team.add_argument("--member", help="Filter by member")
    p_team.add_argument("--month", "-m", help="Month (YYYY-MM)")
    p_team.add_argument("--repo", help="Team repo URL (for init)")
    p_team.add_argument("--name", help="Member name (for init/add-member)")
    p_team.add_argument("--role", default="member", help="Role (for add-member)")

    # reindex
    sub.add_parser("reindex", help="Rebuild search index")

    # audit
    p_audit = sub.add_parser("audit", help="View audit log and verify integrity")
    p_audit.add_argument("--days", type=int, help="Show entries from last N days")
    p_audit.add_argument("--verify", action="store_true", help="Verify source code checksum")
    p_audit.add_argument("-n", type=int, default=10, help="Number of entries (default: 10)")

    # delete
    p_delete = sub.add_parser("delete", help="Delete a diary session entry")
    p_delete.add_argument("--last", action="store_true", help="Delete the last session entry")
    p_delete.add_argument("--session", help="Delete by session ID prefix")

    # dashboard
    p_dashboard = sub.add_parser("dashboard", help="Generate HTML dashboard")
    p_dashboard.add_argument("--serve", action="store_true", help="Start local server")
    p_dashboard.add_argument("--port", type=int, default=8787, help="Server port (default: 8787)")
    p_dashboard.add_argument("--months", type=int, default=3, help="Months of data (default: 3)")

    # install / uninstall
    sub.add_parser("install", help="Register claude-diary hook in Claude Code")
    sub.add_parser("uninstall", help="Remove claude-diary hook from Claude Code")

    # write (manual diary — for /diary slash command)
    sub.add_parser("write", help="Write current session diary to <manual_dir>/<date>/<project>/")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return

    commands = {
        "search": cmd_search,
        "filter": cmd_filter,
        "trace": cmd_trace,
        "stats": cmd_stats,
        "weekly": cmd_weekly,
        "config": cmd_config,
        "init": cmd_init,
        "migrate": cmd_migrate,
        "reindex": cmd_reindex,
        "team": cmd_team,
        "audit": cmd_audit,
        "delete": cmd_delete,
        "dashboard": cmd_dashboard,
        "install": cmd_install,
        "uninstall": cmd_uninstall,
        "write": cmd_write,
    }

    fn = commands.get(args.command)
    if fn:
        fn(args)


if __name__ == "__main__":
    main()
