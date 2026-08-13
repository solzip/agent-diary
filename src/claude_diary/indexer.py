"""Search index manager — incremental index for fast CLI search."""

import json
import os

from claude_diary.lib.filelock import FileLock
from claude_diary.log import get_logger

logger = get_logger("claude_diary.indexer")


def update_index(diary_dir, entry_data):
    """Add entry metadata to the search index (incremental).

    Locked for the same reason the diary file is: the Stop Hook runs once per
    session ending, as its own process. This one is worse than an append,
    though — it reads the whole index, adds one entry, and writes the whole
    thing back, so the last writer does not lose its own entry, it discards
    everybody else's. Measured unlocked: forty concurrent sessions left two
    entries in the index while the diary itself kept all forty.

    Args:
        diary_dir: Path to diary directory
        entry_data: Processed entry data dict
    """
    index_path = os.path.join(diary_dir, ".diary_index.json")

    with FileLock(index_path):
        _append_locked(index_path, entry_data)


def _append_locked(index_path, entry_data):
    index = _load_index(index_path)

    # Extract keywords from prompts (simple word tokenization)
    keywords = set()
    for prompt in entry_data.get("user_prompts", []):
        words = prompt.lower().split()
        for w in words:
            w = w.strip(".,!?:;\"'()[]{}").strip()
            if len(w) > 2:
                keywords.add(w)

    all_files = entry_data.get("files_created", []) + entry_data.get("files_modified", [])

    git_commits = []
    git_info = entry_data.get("git_info")
    if git_info:
        git_commits = [c["hash"] for c in git_info.get("commits", [])]

    code_stats = entry_data.get("code_stats") or {}

    index_entry = {
        "date": entry_data.get("date", ""),
        "time": entry_data.get("time", ""),
        "project": entry_data.get("project", ""),
        # The branch is the one thread between sessions that the tool observes
        # rather than being told: 39 distinct branches across this diary, and
        # only 15% of entries on main or master. It was written into the
        # Markdown and left out of the index, so nothing could follow a piece
        # of work across days without re-reading every file.
        "branch": (git_info or {}).get("branch", "") if git_info else "",
        "categories": entry_data.get("categories", []),
        "files": all_files[:20],
        "keywords": sorted(keywords)[:30],
        "git_commits": git_commits[:10],
        "lines_added": code_stats.get("added", 0),
        "lines_deleted": code_stats.get("deleted", 0),
        "session_id": entry_data.get("session_id", ""),
    }

    index["entries"].append(index_entry)
    index["last_indexed"] = "%sT%s" % (entry_data.get("date", ""), entry_data.get("time", ""))

    _save_index(index_path, index)


def load_index(diary_dir):
    """Load the search index."""
    index_path = os.path.join(diary_dir, ".diary_index.json")
    return _load_index(index_path)


def count_branch_sessions(diary_dir, project, branch):
    """How many sessions this project has already recorded on this branch.

    Used to stamp the sequence number into the entry being written, so the
    record itself says where it sits in a thread. The alternative was another
    command to go and ask, and the commands that have to be gone and asked are
    the ones nobody runs — the diary is read, so the answer belongs in it.

    Zero when either is missing, which reads as "no thread to place this in".
    """
    if not project or not branch:
        return 0
    index = load_index(diary_dir)
    return sum(
        1 for entry in index.get("entries", [])
        if entry.get("project") == project and entry.get("branch") == branch
    )


def reindex_all(diary_dir):
    """Rebuild entire index from all .md files."""
    import re
    from pathlib import Path
    from claude_diary.lib.stats import parse_daily_file

    index = {"entries": [], "last_indexed": ""}
    count = 0

    for f in sorted(Path(diary_dir).glob("*.md")):
        date_str = f.stem
        stats = parse_daily_file(str(f))
        if stats["sessions"] == 0:
            continue

        try:
            content = f.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        sessions = content.split("### ⏰")
        for session in sessions[1:]:
            time_match = re.match(r'\s*(\d{2}:\d{2}:\d{2})', session)
            time_str = time_match.group(1) if time_match else ""

            proj_match = re.search(r'📁 `([^`]+)`', session)
            project = proj_match.group(1) if proj_match else ""

            cats = re.findall(r'(?:카테고리|Categories).*?`([^`]+)`', session)
            files = re.findall(r'  - `([^`]+)`', session)

            keywords = set()
            prompt_section = re.search(
                r'(?:작업 요청|Task Requests).*?\n((?:\s+\d+\. .+\n?)+)', session
            )
            if prompt_section:
                for word in prompt_section.group(1).lower().split():
                    w = word.strip(".,!?:;\"'()[]{}").strip()
                    if len(w) > 2:
                        keywords.add(w)

            # These four used to be written as empty, which meant a rebuild
            # silently produced a thinner index than the incremental path:
            # session ids gone, commits gone, line counts zeroed. Anything
            # reading them got plausible-looking nothing. They are all in the
            # entry text, so a rebuild now recovers them.
            sid_match = re.search(
                r'^<code>([0-9A-Za-z][0-9A-Za-z._-]{7,})</code>\s*$', session, re.M
            )
            session_id = sid_match.group(1) if sid_match else ""

            stat_match = re.search(
                r'(?:변경 통계|Code Stats).*?\+(\d+)\s*/\s*-(\d+)', session
            )
            lines_added = int(stat_match.group(1)) if stat_match else 0
            lines_deleted = int(stat_match.group(2)) if stat_match else 0

            git_commits = re.findall(
                r'(?:커밋|Commit):\s*`([^`]+)`', session
            )

            branch_match = re.search(r'(?:브랜치|Branch):\s*`([^`]+)`', session)

            index["entries"].append({
                "date": date_str,
                "time": time_str,
                "project": project,
                "branch": branch_match.group(1) if branch_match else "",
                "categories": cats,
                "files": files[:20],
                "keywords": sorted(keywords)[:30],
                "git_commits": git_commits,
                "lines_added": lines_added,
                "lines_deleted": lines_deleted,
                "session_id": session_id,
            })
            count += 1

    from datetime import datetime
    index["last_indexed"] = datetime.now().isoformat()

    index_path = os.path.join(diary_dir, ".diary_index.json")
    with FileLock(index_path):
        _save_index(index_path, index)

    return count


def _load_index(index_path):
    """Load index from file or return empty.

    An unreadable index used to fall through to the empty one and then get
    written back over the top, which turned a truncated file into a real
    deletion — measured, a half-written index of five entries came back as
    one. The index is derived from the diary, so `reindex` can rebuild it,
    but only if somebody notices. Hence the warning and the kept copy.
    """
    if not os.path.exists(index_path):
        return _empty_index()

    try:
        with open(index_path, "r", encoding="utf-8") as f:
            index = json.load(f)
    except Exception as e:
        from claude_diary.writer import preserve_corrupt
        logger.warning(
            "Search index unreadable (%s); starting a new one. "
            "Run `agent-diary reindex` to rebuild it from the diary.", e,
        )
        preserve_corrupt(index_path)
        return _empty_index()

    if not isinstance(index, dict) or not isinstance(index.get("entries"), list):
        from claude_diary.writer import preserve_corrupt
        logger.warning(
            "Search index has an unexpected shape; starting a new one. "
            "Run `agent-diary reindex` to rebuild it from the diary."
        )
        preserve_corrupt(index_path)
        return _empty_index()

    return index


def _empty_index():
    return {"entries": [], "last_indexed": ""}


def _save_index(index_path, index):
    """Save index to file, atomically."""
    tmp = "%s.tmp%d" % (index_path, os.getpid())
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(index, f, indent=2, ensure_ascii=False)
        os.replace(tmp, index_path)
    except Exception:
        # Index failure should never block diary writing, but a half-written
        # index must not be left where the real one was.
        try:
            os.unlink(tmp)
        except OSError:
            pass
