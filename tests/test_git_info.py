"""Tests for git information collector."""

import subprocess
from unittest.mock import patch, MagicMock

from claude_diary.lib.git_info import (
    collect_git_info,
    get_diff_stat,
    _is_git_repo,
    _get_branch,
    _get_recent_commits,
)


class TestIsGitRepo:
    def test_valid_repo(self):
        mock_result = MagicMock(returncode=0)
        with patch("claude_diary.lib.git_info.subprocess.run", return_value=mock_result):
            assert _is_git_repo("/some/repo") is True

    def test_not_a_repo(self):
        mock_result = MagicMock(returncode=128)
        with patch("claude_diary.lib.git_info.subprocess.run", return_value=mock_result):
            assert _is_git_repo("/some/dir") is False

    def test_git_not_installed(self):
        with patch(
            "claude_diary.lib.git_info.subprocess.run",
            side_effect=FileNotFoundError,
        ):
            assert _is_git_repo("/some/dir") is False

    def test_timeout(self):
        with patch(
            "claude_diary.lib.git_info.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="git", timeout=5),
        ):
            assert _is_git_repo("/some/dir") is False

    def test_os_error(self):
        with patch(
            "claude_diary.lib.git_info.subprocess.run",
            side_effect=OSError("permission denied"),
        ):
            assert _is_git_repo("/some/dir") is False


class TestGetBranch:
    def test_returns_branch_name(self):
        mock_result = MagicMock(stdout="feature/login\n")
        with patch("claude_diary.lib.git_info.subprocess.run", return_value=mock_result):
            assert _get_branch("/repo") == "feature/login"

    def test_empty_stdout_returns_head(self):
        mock_result = MagicMock(stdout="")
        with patch("claude_diary.lib.git_info.subprocess.run", return_value=mock_result):
            assert _get_branch("/repo") == "HEAD"

    def test_exception_returns_unknown(self):
        with patch(
            "claude_diary.lib.git_info.subprocess.run",
            side_effect=Exception("boom"),
        ):
            assert _get_branch("/repo") == "unknown"


class TestGetRecentCommits:
    def test_parses_oneline_output(self):
        mock_result = MagicMock(stdout="abc1234 Fix login bug\ndef5678 Add tests\n")
        with patch("claude_diary.lib.git_info.subprocess.run", return_value=mock_result):
            commits = _get_recent_commits("/repo")
            assert len(commits) == 2
            assert commits[0] == {"hash": "abc1234", "message": "Fix login bug"}
            assert commits[1] == {"hash": "def5678", "message": "Add tests"}

    def test_since_parameter_adds_flag(self):
        mock_result = MagicMock(stdout="abc1234 Fix bug\n")
        with patch("claude_diary.lib.git_info.subprocess.run", return_value=mock_result) as mock_run:
            _get_recent_commits("/repo", since="2026-03-17T10:00:00Z")
            cmd = mock_run.call_args[0][0]
            assert "--since" in cmd
            assert "2026-03-17T10:00:00Z" in cmd

    def test_no_since_parameter(self):
        mock_result = MagicMock(stdout="abc1234 Fix bug\n")
        with patch("claude_diary.lib.git_info.subprocess.run", return_value=mock_result) as mock_run:
            _get_recent_commits("/repo")
            cmd = mock_run.call_args[0][0]
            assert "--since" not in cmd

    def test_empty_output(self):
        mock_result = MagicMock(stdout="")
        with patch("claude_diary.lib.git_info.subprocess.run", return_value=mock_result):
            commits = _get_recent_commits("/repo")
            assert commits == []

    def test_hash_only_line(self):
        mock_result = MagicMock(stdout="abc1234\n")
        with patch("claude_diary.lib.git_info.subprocess.run", return_value=mock_result):
            commits = _get_recent_commits("/repo")
            assert len(commits) == 1
            assert commits[0] == {"hash": "abc1234", "message": ""}

    def test_truncates_to_10(self):
        lines = "\n".join(f"hash{i:02d} Commit {i}" for i in range(15))
        mock_result = MagicMock(stdout=lines)
        with patch("claude_diary.lib.git_info.subprocess.run", return_value=mock_result):
            commits = _get_recent_commits("/repo")
            assert len(commits) == 10

    def test_exception_returns_empty(self):
        with patch(
            "claude_diary.lib.git_info.subprocess.run",
            side_effect=Exception("timeout"),
        ):
            commits = _get_recent_commits("/repo")
            assert commits == []


class TestGetDiffStat:
    def test_full_stat_output(self):
        stat_output = (
            " src/app.py  | 10 ++++------\n"
            " src/util.py |  3 +++\n"
            " 2 files changed, 7 insertions(+), 6 deletions(-)\n"
        )
        mock_result = MagicMock(stdout=stat_output)
        with patch("claude_diary.lib.git_info.subprocess.run", return_value=mock_result):
            result = get_diff_stat("/repo")
            assert result == {"added": 7, "deleted": 6, "files": 2}

    def test_insertions_only(self):
        stat_output = " 1 file changed, 5 insertions(+)\n"
        mock_result = MagicMock(stdout=stat_output)
        with patch("claude_diary.lib.git_info.subprocess.run", return_value=mock_result):
            result = get_diff_stat("/repo")
            assert result == {"added": 5, "deleted": 0, "files": 1}

    def test_deletions_only(self):
        stat_output = " 3 files changed, 12 deletions(-)\n"
        mock_result = MagicMock(stdout=stat_output)
        with patch("claude_diary.lib.git_info.subprocess.run", return_value=mock_result):
            result = get_diff_stat("/repo")
            assert result == {"added": 0, "deleted": 12, "files": 3}

    def test_empty_diff(self):
        mock_result = MagicMock(stdout="")
        with patch("claude_diary.lib.git_info.subprocess.run", return_value=mock_result):
            result = get_diff_stat("/repo")
            assert result == {"added": 0, "deleted": 0, "files": 0}

    def test_exception_returns_zeros(self):
        with patch(
            "claude_diary.lib.git_info.subprocess.run",
            side_effect=Exception("fatal"),
        ):
            result = get_diff_stat("/repo")
            assert result == {"added": 0, "deleted": 0, "files": 0}

    def test_singular_file_changed(self):
        stat_output = " 1 file changed, 1 insertion(+), 1 deletion(-)\n"
        mock_result = MagicMock(stdout=stat_output)
        with patch("claude_diary.lib.git_info.subprocess.run", return_value=mock_result):
            result = get_diff_stat("/repo")
            assert result == {"added": 1, "deleted": 1, "files": 1}


class TestCollectGitInfo:
    def test_returns_none_for_empty_cwd(self):
        assert collect_git_info("") is None
        assert collect_git_info(None) is None

    def test_returns_none_for_non_git_dir(self):
        mock_result = MagicMock(returncode=128)
        with patch("claude_diary.lib.git_info.subprocess.run", return_value=mock_result):
            assert collect_git_info("/some/dir") is None

    def test_successful_collection(self):
        def fake_run(cmd, **kwargs):
            if "rev-parse" in cmd:
                return MagicMock(returncode=0)
            if "branch" in cmd:
                return MagicMock(stdout="main\n")
            if "log" in cmd:
                return MagicMock(stdout="abc123 Fix tests\n")
            if "diff" in cmd:
                return MagicMock(stdout=" 1 file changed, 3 insertions(+)\n")
            return MagicMock(returncode=0, stdout="")

        with patch("claude_diary.lib.git_info.subprocess.run", side_effect=fake_run):
            result = collect_git_info("/repo")
            assert result is not None
            assert result["branch"] == "main"
            assert len(result["commits"]) == 1
            assert result["commits"][0]["hash"] == "abc123"
            assert result["diff_stat"]["added"] == 3

    def test_returns_none_on_exception(self):
        with patch("claude_diary.lib.git_info._is_git_repo", return_value=True), \
             patch("claude_diary.lib.git_info._get_branch", side_effect=RuntimeError("unexpected error")):
            result = collect_git_info("/repo")
            assert result is None

    def test_with_session_start(self):
        def fake_run(cmd, **kwargs):
            if "rev-parse" in cmd:
                return MagicMock(returncode=0)
            if "branch" in cmd:
                return MagicMock(stdout="dev\n")
            if "log" in cmd:
                assert "--since" in cmd
                return MagicMock(stdout="fff000 New feature\n")
            if "diff" in cmd:
                return MagicMock(stdout="")
            return MagicMock(returncode=0, stdout="")

        with patch("claude_diary.lib.git_info.subprocess.run", side_effect=fake_run):
            result = collect_git_info("/repo", session_start="2026-03-17T09:00:00Z")
            assert result is not None
            assert result["branch"] == "dev"
