"""Git information collector — branch, commits, diff stats."""

import os
import subprocess


def collect_git_info(cwd, session_start=None):
    """Collect git info from the working directory.

    Args:
        cwd: Working directory path
        session_start: ISO timestamp for filtering commits (optional)

    Returns:
        dict with branch, commits, diff_stat — or None if not a git repo.
    """
    if not cwd or not _is_git_repo(cwd):
        return None

    try:
        branch = _get_branch(cwd)
        commits = _get_recent_commits(cwd, session_start)
        diff_stat = _get_diff_stat(cwd)

        return {
            "branch": branch,
            "commits": commits,
            "diff_stat": diff_stat,
        }
    except Exception:
        return None


def _is_git_repo(cwd):
    """Check if directory is inside a git repository."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=cwd, capture_output=True, text=True, timeout=5
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False


def _get_branch(cwd):
    """Get current git branch name."""
    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=cwd, capture_output=True, text=True, timeout=5
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
            cmd, cwd=cwd, capture_output=True, text=True, timeout=5
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


def _get_diff_stat(cwd):
    """Get diff stat (added/deleted lines, files changed).
    Includes both staged and unstaged changes.
    """
    added = 0
    deleted = 0
    files = 0

    try:
        # Staged + unstaged
        result = subprocess.run(
            ["git", "diff", "--stat", "HEAD"],
            cwd=cwd, capture_output=True, text=True, timeout=5
        )
        lines = result.stdout.strip().split("\n")
        if lines:
            summary = lines[-1]
            # Parse: " 5 files changed, 142 insertions(+), 38 deletions(-)"
            import re
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
