"""Git information collector — branch, commits, diff stats."""

from __future__ import annotations

import subprocess
from typing import List, Optional

from claude_diary.lib.nonfatal import non_fatal
from claude_diary.types import CommitInfo, DiffStat, GitInfo


def collect_git_info(cwd: str, session_start: Optional[str] = None) -> Optional[GitInfo]:
    """Collect git info from the working directory.

    Args:
        cwd: Working directory path
        session_start: ISO timestamp for filtering commits (optional)

    Returns:
        dict with branch, commits, diff_stat — or None if not a git repo.
    """
    if not cwd or not _is_git_repo(cwd):
        return None

    with non_fatal("git info collection"):
        branch = _get_branch(cwd)
        commits = _get_recent_commits(cwd, session_start)
        diff_stat = _session_diff_stat(cwd, commits, session_start)

        return {
            "branch": branch,
            "commits": commits,
            "diff_stat": diff_stat,
        }
    return None


def _session_diff_stat(cwd, commits, session_start=None):
    """Lines this session landed, measured on its own commits.

    It used to be `git diff --stat HEAD` — the *uncommitted* working tree at
    the moment the session ended — which is a different quantity wearing the
    same name, and wrong in three directions at once:

    - a session that committed everything it did recorded nothing, because the
      tree was clean;
    - a repository holding a pile of uncommitted generated files recorded that
      same pile again for every session in it, so summing across a project
      counted one working tree hundreds of times. Measured across this diary,
      one project came to -1,547,143 lines;
    - the `session_start` argument was accepted and never used, so the window
      the caller asked for had no effect.

    The commits are the durable record of what the session produced, and
    `get_diff_stat_for_commits` was already there — the Notion push path used
    it while the diary did not.

    With no commits the answer is zero, and that is the honest one: nothing
    landed. Whether the session changed files without committing them is
    already recorded as a session outcome, which is where that belongs.
    """
    hashes = [c.get("hash") for c in (commits or []) if c.get("hash")]
    if not hashes:
        return {"added": 0, "deleted": 0, "files": 0}
    return get_diff_stat_for_commits(cwd, hashes)


def get_repo_root(cwd):
    """The repository this directory belongs to, or "" if it is not in one.

    A session does not stay where it started. Of the twenty largest transcripts
    on one machine, seventeen record more than one working directory and one
    records twenty-six — every `cd` into a subdirectory is another one. Naming
    the project after the last path segment therefore files work under whatever
    folder it happened to be in: `harness` instead of `_verification` 936
    times, `dev` instead of `erp_chatbot_solzip` 827 times. Measured across the
    89 recorded directories that still exist and are repositories, 75% have a
    last segment that is not the repository.

    Only 4% of existing entries are wrong, because most turns are recorded from
    the project root and only the wandering one is misfiled. That ratio is a
    property of how often the diary samples the path, and it stops holding the
    moment every turn is recorded.
    """
    if not cwd:
        return ""
    try:
        result = subprocess.run(
            ["git", "-C", cwd, "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=5,
        )
    except Exception:
        return ""
    if result.returncode != 0:
        return ""
    return (result.stdout or "").strip()


def _is_git_repo(cwd):
    """Check if directory is inside a git repository."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False


def _get_branch(cwd):
    """Get current git branch name."""
    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5
        )
        return result.stdout.strip() or "HEAD"
    except Exception:
        return "unknown"


def _get_recent_commits(cwd, since=None):
    """Get commits since the given timestamp (or last 10)."""
    cmd = ["git", "log", "--oneline", "-n", "20"]
    if since:
        cmd.extend(["--since", since])

    try:
        result = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5
        )
        commits = []
        for line in result.stdout.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            parts = line.split(" ", 1)
            if len(parts) == 2:
                commits.append({"hash": parts[0], "message": parts[1]})
            elif len(parts) == 1:
                commits.append({"hash": parts[0], "message": ""})
        return commits[:10]
    except Exception:
        return []


def get_branch_for_commit(cwd: str, commit_hash: str) -> str:
    """Return the (first) branch containing the given commit.

    Used by /diary-notion to label each task with its branch. Falls back to
    HEAD branch when `git branch --contains` returns nothing (detached HEAD,
    commit not in any branch, etc).
    """
    if not cwd or not commit_hash:
        return get_head_branch(cwd)
    try:
        result = subprocess.run(
            ["git", "branch", "--contains", commit_hash, "--format=%(refname:short)"],
            cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5
        )
        for line in result.stdout.strip().split("\n"):
            line = line.strip().lstrip("* ").strip()
            if line and not line.startswith("("):
                return line
    except Exception:
        pass
    return get_head_branch(cwd)


def get_head_branch(cwd: str) -> str:
    """Return current HEAD branch, or empty string if detached/unknown."""
    if not cwd:
        return ""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5
        )
        branch = result.stdout.strip()
        if branch and branch != "HEAD":
            return branch
    except Exception:
        pass
    return ""


def get_commit_info(cwd: str, commit_hash: str) -> Optional[CommitInfo]:
    """Return {hash, short_hash, message} for a commit, or None if not found."""
    if not cwd or not commit_hash:
        return None
    try:
        result = subprocess.run(
            ["git", "log", "-n", "1", "--format=%H%x09%h%x09%s", commit_hash],
            cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5
        )
        line = result.stdout.strip()
        if not line:
            return None
        parts = line.split("\t")
        if len(parts) < 3:
            return None
        return {"hash": parts[0], "short_hash": parts[1], "message": parts[2]}
    except Exception:
        return None


def get_diff_stat_for_commits(cwd: str, commit_hashes: List[str]) -> DiffStat:
    """Sum diff stats across the given commits.

    Returns {"added": int, "deleted": int, "files": int}. Files count is
    a sum-of-touched (may double-count if a file changed in multiple commits).
    """
    total: DiffStat = {"added": 0, "deleted": 0, "files": 0}
    if not cwd or not commit_hashes:
        return total
    import re
    for h in commit_hashes:
        try:
            result = subprocess.run(
                ["git", "show", "--stat", "--format=", h],
                cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5
            )
            lines = result.stdout.strip().split("\n")
            if not lines:
                continue
            summary = lines[-1]
            f = re.search(r'(\d+) files? changed', summary)
            a = re.search(r'(\d+) insertions?', summary)
            d = re.search(r'(\d+) deletions?', summary)
            if f:
                total["files"] += int(f.group(1))
            if a:
                total["added"] += int(a.group(1))
            if d:
                total["deleted"] += int(d.group(1))
        except Exception:
            continue
    return total


def get_diff_stat(cwd: str, since: Optional[str] = None) -> DiffStat:
    """Get diff stat (added/deleted lines, files changed).

    Args:
        cwd: Working directory
        since: ISO timestamp — if provided, diff from merge-base (optional)

    Returns:
        {"added": int, "deleted": int, "files": int}
    """
    added = 0
    deleted = 0
    files = 0

    try:
        import re
        cmd = ["git", "diff", "--stat", "HEAD"]
        result = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5
        )
        lines = result.stdout.strip().split("\n")
        if lines:
            summary = lines[-1]
            files_match = re.search(r'(\d+) files? changed', summary)
            add_match = re.search(r'(\d+) insertions?', summary)
            del_match = re.search(r'(\d+) deletions?', summary)

            if files_match:
                files = int(files_match.group(1))
            if add_match:
                added = int(add_match.group(1))
            if del_match:
                deleted = int(del_match.group(1))
    except Exception:
        pass

    return {"added": added, "deleted": deleted, "files": files}
