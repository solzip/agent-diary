#!/usr/bin/env python
"""agent-diary CLI — search, filter, stats, and manage your work diary."""

import argparse
import os
import sys

from claude_diary.cli.notion_push.artifacts import default_artifact_dir

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
from claude_diary.cli.backfill import cmd_backfill
from claude_diary.cli.doctor import cmd_doctor
from claude_diary.cli.report import cmd_report
from claude_diary.cli.notion_push import cmd_notion_push
from claude_diary.cli.notion_init import cmd_notion_init
from claude_diary.cli.notion_ensure import cmd_notion_ensure
from claude_diary.cli.notion_ops import cmd_notion_ops
from claude_diary.cli.notion_review import cmd_notion_review


def cmd_notion(args):
    """Dispatch `diary-notion|notion <action>` to the right command."""
    if args.action == "push":
        cmd_notion_push(args)
    elif args.action == "init":
        cmd_notion_init(args)
    elif args.action == "ensure":
        cmd_notion_ensure(args)
    elif args.action == "ops":
        cmd_notion_ops(args)
    elif args.action == "review":
        cmd_notion_review(args)


def _add_diary_notion_parser(sub, name):
    p_notion = sub.add_parser(name, help="Notion hierarchical work diary integration")
    p_notion.add_argument("action", choices=["init", "push", "ensure", "ops", "review"],
                          help="Action to perform")
    p_notion.add_argument("--input", help="JSON input file (push only)")
    p_notion.add_argument("--force", action="store_true",
                          help="Archive prior rows for the session before pushing (push only)")
    p_notion.add_argument("--year", type=int, help="Target year (ensure/ops/review only)")
    p_notion.add_argument("--apply", action="store_true",
                          help="Mark the listed rows reviewed (review only)")
    p_notion.add_argument("--dry-run", action="store_true",
                          help="Preview push body without writing, or print ensure plan")
    p_notion.add_argument("--preview-file",
                          help="Write push dry-run/preview Markdown to this file")
    # Resolved here rather than inside the command: an absent `--artifact-dir`
    # on the parsed args means "no artifacts", which is what the tests rely on.
    p_notion.add_argument("--artifact-dir", default=default_artifact_dir(os.getcwd()),
                          help=("Directory for local run artifacts (push only). "
                                "Defaults to .agent-diary/runs, or .codefleet/runs "
                                "if that already exists here."))
    p_notion.add_argument("--no-artifacts", action="store_true",
                          help="Do not write local run artifacts (push only)")
    p_notion.add_argument("--stale-days", type=int, default=7,
                          help="Mark active rows stale after N days (ops only)")
    p_notion.add_argument("--json", dest="json_output", action="store_true",
                          help="Output operations report as JSON (ops only)")


# Twenty-one subcommands in one alphabetical wall tells a newcomer nothing
# about where to begin — `init` sits seventh and `backfill`, which is the
# thing that makes the tool worth having on day one, seventeenth. argparse
# will not group subcommands, so the route in is spelled out instead.
GETTING_STARTED = """
start here:
  agent-diary init                 set up, and register the Claude Code hook
  agent-diary backfill             import the sessions you already have
  agent-diary doctor               check it is set up and still recording

then, day to day:
  agent-diary report --days 7      one document for a period, to send someone
  agent-diary search "keyword"     find an entry
  agent-diary diary-notion push    push a session to a Notion work log

everything else is listed above. docs: https://github.com/solzip/agent-diary
"""


def main():
    parser = argparse.ArgumentParser(
        prog="agent-diary",
        description="Auto-generated work diary from Claude Code and Codex sessions",
        epilog=GETTING_STARTED,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    from claude_diary import __version__
    parser.add_argument("--version", action="version", version="agent-diary %s" % __version__)

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
    p_init = sub.add_parser("init", help="Initialize agent-diary setup")
    init_mode = p_init.add_mutually_exclusive_group()
    init_mode.add_argument("--team", dest="team_repo", help="Team repo URL for team mode")
    init_mode.add_argument("--codex-only", action="store_true",
                           help="Initialize config/diary directories without registering Claude Code hooks")

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
    p_install = sub.add_parser("install", help="Register agent-diary hook in Claude Code")
    p_install.add_argument("--force", action="store_true",
                           help=("Refresh hook command and overwrite managed slash command files "
                                 "(preserves user-modified ones)"))
    install_agent = p_install.add_mutually_exclusive_group()
    install_agent.add_argument("--codex", action="store_true",
                               help="Also install Codex skills under ~/.codex/skills")
    install_agent.add_argument("--codex-only", action="store_true",
                               help="Install only Codex skills; do not modify Claude Code settings")
    p_uninstall = sub.add_parser("uninstall", help="Remove agent-diary hook from Claude Code")
    uninstall_agent = p_uninstall.add_mutually_exclusive_group()
    uninstall_agent.add_argument("--codex", action="store_true",
                                 help="Also remove Codex skills installed by agent-diary")
    uninstall_agent.add_argument("--codex-only", action="store_true",
                                 help="Remove only Codex skills; do not modify Claude Code settings")

    # write (manual diary — for /diary slash command)
    p_write = sub.add_parser("write", help="Write current session diary to <manual_dir>/<date>/<project>/")
    p_write.add_argument("--input", help="JSON input file for agent-authored diary entries")

    # backfill (import sessions that predate installation)
    p_backfill = sub.add_parser(
        "backfill",
        help="Import Claude Code sessions recorded before agent-diary was installed",
    )
    p_backfill.add_argument("--since", help="Only import sessions from this date onward (YYYY-MM-DD)")
    p_backfill.add_argument("--limit", type=int, help="Import at most N sessions")
    p_backfill.add_argument("--dry-run", action="store_true",
                            help="List what would be imported without writing")
    p_backfill.add_argument("--transcripts",
                            help="Transcript directory (default: ~/.claude/projects)")

    # doctor (is it still recording?)
    p_doctor = sub.add_parser(
        "doctor",
        help="Check that the hook is registered and the diary is still being written",
    )
    p_doctor.add_argument("--notion", action="store_true",
                          help="Also make a read-only request to Notion")

    # report (one document for a period, for someone else to read)
    p_report = sub.add_parser(
        "report",
        help="Write one document covering a period and project",
    )
    p_report.add_argument("--from", dest="date_from", help="Start date (YYYY-MM-DD)")
    p_report.add_argument("--to", dest="date_to", help="End date (YYYY-MM-DD)")
    p_report.add_argument("--month", "-m", help="Whole calendar month (YYYY-MM)")
    p_report.add_argument("--days", type=int, help="The last N days, including today")
    p_report.add_argument("--project", "-p", help="Limit to one project")
    p_report.add_argument("--output", "-o", help="Write to this file instead of stdout")
    p_report.add_argument("--detail", action="store_true",
                          help="Include the requests as typed alongside the summaries")
    p_report.add_argument("--json", action="store_true", help="Output as JSON")

    # notion (hierarchical Notion DB integration — for /diary-notion slash command)
    _add_diary_notion_parser(sub, "diary-notion")
    _add_diary_notion_parser(sub, "notion")

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
        "backfill": cmd_backfill,
        "doctor": cmd_doctor,
        "report": cmd_report,
        "diary-notion": cmd_notion,
        "notion": cmd_notion,
    }

    fn = commands.get(args.command)
    if fn:
        fn(args)


if __name__ == "__main__":
    main()
