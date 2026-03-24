"""Search, filter, and trace commands."""

import json
import os
import re
from pathlib import Path

import claude_diary.cli as _cli


def cmd_search(args):
    config = _cli.load_config()
    lang = config.get("lang", "ko")
    L = lambda key: _cli.get_label(key, lang)
    diary_dir = os.path.expanduser(config["diary_dir"])
    keyword = args.keyword.lower()

    index = _cli.load_index(diary_dir)
    entries = index.get("entries", [])

    # Auto-reindex if no index but diary files exist
    if not entries:
        diary_files = list(Path(diary_dir).glob("*.md"))
        if diary_files:
            print(L("cli_no_index"))
            from claude_diary.indexer import reindex_all
            reindex_all(diary_dir)
            index = _cli.load_index(diary_dir)
            entries = index.get("entries", [])

    if not entries:
        entries = _cli._fallback_search_from_files(diary_dir, keyword)
        if not entries:
            print(L("cli_no_results") % args.keyword)
            return
        for e in entries:
            print("%s | %s | %s" % (e["date"], e["project"], e["line"]))
        return

    results = []
    for e in entries:
        # Date range filter
        if args.date_from and e["date"] < args.date_from:
            continue
        if args.date_to and e["date"] > args.date_to:
            continue
        # Project filter
        if args.project and args.project.lower() != e.get("project", "").lower():
            continue
        # Category filter
        if args.category and args.category.lower() not in [c.lower() for c in e.get("categories", [])]:
            continue
        # Keyword match
        searchable = " ".join(e.get("keywords", []) + e.get("files", []) + e.get("categories", []))
        if keyword in searchable.lower() or keyword in e.get("project", "").lower():
            results.append(e)

    if not results:
        print("No results found for '%s'" % args.keyword)
        return

    if getattr(args, 'json_output', False):
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return

    print(L("cli_found_entries") % len(results))
    print()
    for e in results:
        cats = ",".join(e.get("categories", [])) or "uncategorized"
        stats = ""
        if e.get("lines_added", 0) > 0 or e.get("lines_deleted", 0) > 0:
            stats = " | +%d/-%d" % (e["lines_added"], e["lines_deleted"])
        print("  %s %s | %-20s | %-12s%s" % (
            e["date"], e.get("time", "")[:5], e.get("project", ""), cats, stats
        ))


def _fallback_search_from_files(diary_dir, keyword):
    """Search directly from .md files when no index exists."""
    results = []
    for f in sorted(Path(diary_dir).glob("*.md")):
        try:
            content = f.read_text(encoding="utf-8")
        except Exception:
            continue
        for line in content.split("\n"):
            if keyword in line.lower():
                date = f.stem
                project = ""
                pm = re.search(r'📁 `([^`]+)`', content)
                if pm:
                    project = pm.group(1)
                results.append({"date": date, "project": project, "line": line.strip()[:100]})
                break
    return results


def cmd_filter(args):
    config = _cli.load_config()
    lang = config.get("lang", "ko")
    diary_dir = os.path.expanduser(config["diary_dir"])
    index = _cli.load_index(diary_dir)
    entries = index.get("entries", [])

    if not entries:
        print("No index found. Run 'claude-diary reindex' first.")
        return

    results = []
    for e in entries:
        if args.project and args.project.lower() != e.get("project", "").lower():
            continue
        if args.category and args.category.lower() not in [c.lower() for c in e.get("categories", [])]:
            continue
        if args.month and not e["date"].startswith(args.month):
            continue
        results.append(e)

    if not results:
        print(_cli.get_label("cli_no_match", lang))
        return

    print(_cli.get_label("cli_found_entries", lang) % len(results))
    print()
    for e in results:
        cats = ",".join(e.get("categories", [])) or "-"
        print("  %s %s | %-20s | %s" % (
            e["date"], e.get("time", "")[:5], e.get("project", ""), cats
        ))


def cmd_trace(args):
    config = _cli.load_config()
    diary_dir = os.path.expanduser(config["diary_dir"])
    index = _cli.load_index(diary_dir)
    entries = index.get("entries", [])
    target = args.filepath.lower().replace("\\", "/")

    results = []
    for e in entries:
        if args.project and args.project.lower() != e.get("project", "").lower():
            continue
        for f in e.get("files", []):
            if target in f.lower():
                results.append((e, f))
                break

    if not results:
        print("No history found for '%s'" % args.filepath)
        return

    print("File trace for '%s' (%d entries):" % (args.filepath, len(results)))
    print()
    for e, f in results:
        cats = ",".join(e.get("categories", [])) or "-"
        print("  %s | %-20s | %-12s | %s" % (e["date"], e.get("project", ""), cats, f))
