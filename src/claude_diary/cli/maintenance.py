"""Reindex, audit, delete, and dashboard commands."""

import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

import claude_diary.cli as _cli


def cmd_reindex(args):
    from claude_diary.indexer import reindex_all
    config = _cli.load_config()
    diary_dir = os.path.expanduser(config["diary_dir"])

    print("Rebuilding search index...")
    count = reindex_all(diary_dir)
    index_path = os.path.join(diary_dir, ".diary_index.json")
    print("Indexed %d sessions." % count)
    print("Index: %s" % index_path)


def cmd_audit(args):
    from claude_diary.lib.audit import read_audit_log, verify_checksum
    config = _cli.load_config()
    diary_dir = os.path.expanduser(config["diary_dir"])

    if args.verify:
        is_valid, current, last = verify_checksum(diary_dir)
        if is_valid:
            print("Checksum OK: %s" % current)
        else:
            print("WARNING: Checksum mismatch!")
            print("  Current:  %s" % current)
            print("  Last log: %s" % last)
            print("  Source files may have been modified since last Hook execution.")
        return

    entries = read_audit_log(diary_dir, days=args.days, limit=args.n)

    if not entries:
        print("No audit log entries found.")
        return

    print("Audit log (%d entries):" % len(entries))
    print()
    for e in entries:
        ts = e.get("timestamp", "")[:19]
        sid = e.get("session_id", "")[:8]
        masked = e.get("secrets_masked", 0)
        written = len(e.get("files_written", []))
        exporters = e.get("exporters_called", [])
        failed = e.get("exporters_failed", [])

        line = "  %s | session:%s | wrote:%d" % (ts, sid, written)
        if masked > 0:
            line += " | secrets_masked:%d" % masked
        if exporters:
            line += " | exporters:%s" % ",".join(exporters)
        if failed:
            line += " | FAILED:%s" % ",".join(failed)
        print(line)


def cmd_delete(args):
    config = _cli.load_config()
    diary_dir = os.path.expanduser(config["diary_dir"])
    tz_offset = config.get("timezone_offset", 9)
    local_tz = timezone(timedelta(hours=tz_offset))

    if args.last:
        today = datetime.now(local_tz).strftime("%Y-%m-%d")
        filepath = os.path.join(diary_dir, "%s.md" % today)
        if not os.path.exists(filepath):
            print("No diary file for today (%s)" % today)
            return

        # Confirmation prompt
        confirm = input("Delete last session entry from %s? [y/N]: " % today).strip().lower()
        if confirm not in ("y", "yes"):
            print("Cancelled.")
            return

        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        # Split by session markers and remove last
        parts = content.split("### ⏰")
        if len(parts) <= 1:
            print("No session entries found in today's diary.")
            return

        # Remove last entry (everything after last "### ⏰")
        new_content = "### ⏰".join(parts[:-1])
        # Remove trailing "---\n\n" if present
        new_content = new_content.rstrip()
        if new_content.endswith("---"):
            new_content = new_content[:-3].rstrip()
        new_content += "\n\n"

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(new_content)

        print("Last session entry deleted from %s" % filepath)
        return

    if args.session:
        # Search all files for session ID and remove that entry
        found = False
        for f in sorted(Path(diary_dir).glob("*.md")):
            try:
                content = f.read_text(encoding="utf-8")
            except Exception:
                continue
            if args.session in content:
                parts = content.split("### ⏰")
                new_parts = [parts[0]]
                for part in parts[1:]:
                    if args.session not in part:
                        new_parts.append(part)
                    else:
                        found = True
                new_content = "### ⏰".join(new_parts).rstrip() + "\n"
                f.write_text(new_content, encoding="utf-8")
                print("Session %s deleted from %s" % (args.session, f.name))
                break

        if not found:
            print("Session '%s' not found." % args.session)
        return

    print("Specify --last or --session <id>")


def cmd_dashboard(args):
    from claude_diary.dashboard import generate_dashboard, serve_dashboard
    config = _cli.load_config()
    diary_dir = os.path.expanduser(config["diary_dir"])

    path = generate_dashboard(diary_dir, months=args.months)
    print("Dashboard generated: %s" % path)

    if args.serve:
        serve_dashboard(diary_dir, port=args.port)
    else:
        import webbrowser
        webbrowser.open("file://%s" % os.path.abspath(path))
