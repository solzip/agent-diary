"""Tests for git information collector."""

import os
import subprocess
from unittest.mock import patch, MagicMock

from claude_diary.lib.git_info import (
    collect_git_info,
    get_diff_stat,
    get_branch_for_commit,
    get_head_branch,
    get_commit_info,
    get_diff_stat_for_commits,
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
        """The stat comes from the session's own commits.

        It used to come from `git diff --stat HEAD`, the uncommitted tree at
        session end, which is a different quantity under the same name: a
        session that committed its work recorded nothing, and a repo with
        uncommitted generated files recorded them again for every session.
        """
        def fake_run(cmd, **kwargs):
            if "rev-parse" in cmd:
                return MagicMock(returncode=0)
            if "branch" in cmd:
                return MagicMock(stdout="main\n")
            if "log" in cmd:
                return MagicMock(stdout="abc123 Fix tests\n")
            if "show" in cmd:
                return MagicMock(stdout=" 1 file changed, 3 insertions(+)\n")
            return MagicMock(returncode=0, stdout="")

        with patch("claude_diary.lib.git_info.subprocess.run", side_effect=fake_run):
            result = collect_git_info("/repo")
            assert result is not None
            assert result["branch"] == "main"
            assert len(result["commits"]) == 1
            assert result["commits"][0]["hash"] == "abc123"
            assert result["diff_stat"]["added"] == 3

    def test_a_session_with_no_commits_lands_nothing(self):
        """Zero, not the working tree. Whether files changed without being
        committed is recorded as a session outcome, not as lines landed."""
        def fake_run(cmd, **kwargs):
            if "rev-parse" in cmd:
                return MagicMock(returncode=0)
            if "branch" in cmd:
                return MagicMock(stdout="main\n")
            if "log" in cmd:
                return MagicMock(stdout="")
            if "diff" in cmd:
                return MagicMock(stdout=" 9 files changed, 4000 insertions(+)\n")
            return MagicMock(returncode=0, stdout="")

        with patch("claude_diary.lib.git_info.subprocess.run", side_effect=fake_run):
            result = collect_git_info("/repo")
            assert result["commits"] == []
            assert result["diff_stat"] == {"added": 0, "deleted": 0, "files": 0}

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


class TestGetBranchForCommit:
    def test_returns_first_branch(self):
        mock_result = MagicMock(stdout="feat/diary-notion\nmain\n")
        with patch("claude_diary.lib.git_info.subprocess.run", return_value=mock_result):
            assert get_branch_for_commit("/repo", "abc1234") == "feat/diary-notion"

    def test_empty_falls_back_to_head(self):
        # First call: branch --contains returns nothing
        # Second call (from get_head_branch): rev-parse returns "main"
        outputs = [MagicMock(stdout=""), MagicMock(stdout="main\n")]
        with patch("claude_diary.lib.git_info.subprocess.run", side_effect=outputs):
            assert get_branch_for_commit("/repo", "abc1234") == "main"

    def test_no_commit_hash_returns_head(self):
        with patch("claude_diary.lib.git_info.subprocess.run",
                   return_value=MagicMock(stdout="main\n")):
            assert get_branch_for_commit("/repo", None) == "main"


class TestGetHeadBranch:
    def test_returns_branch(self):
        with patch("claude_diary.lib.git_info.subprocess.run",
                   return_value=MagicMock(stdout="main\n")):
            assert get_head_branch("/repo") == "main"

    def test_detached_head_returns_empty(self):
        with patch("claude_diary.lib.git_info.subprocess.run",
                   return_value=MagicMock(stdout="HEAD\n")):
            assert get_head_branch("/repo") == ""

    def test_empty_cwd_returns_empty(self):
        assert get_head_branch("") == ""

    def test_exception_returns_empty(self):
        with patch("claude_diary.lib.git_info.subprocess.run",
                   side_effect=Exception("boom")):
            assert get_head_branch("/repo") == ""


class TestGetCommitInfo:
    def test_returns_parsed_fields(self):
        out = "abc1234deadbeef\tabc1234\tfeat: add login\n"
        with patch("claude_diary.lib.git_info.subprocess.run",
                   return_value=MagicMock(stdout=out)):
            info = get_commit_info("/repo", "abc1234")
        assert info["hash"] == "abc1234deadbeef"
        assert info["short_hash"] == "abc1234"
        assert info["message"] == "feat: add login"

    def test_empty_returns_none(self):
        with patch("claude_diary.lib.git_info.subprocess.run",
                   return_value=MagicMock(stdout="")):
            assert get_commit_info("/repo", "abc1234") is None

    def test_no_inputs_returns_none(self):
        assert get_commit_info(None, "abc1234") is None
        assert get_commit_info("/repo", None) is None


class TestGetDiffStatForCommits:
    def test_sums_across_commits(self):
        def fake_run(cmd, **kwargs):
            if "abc1" in cmd:
                return MagicMock(stdout="\n 2 files changed, 10 insertions(+), 3 deletions(-)\n")
            if "def5" in cmd:
                return MagicMock(stdout="\n 1 file changed, 5 insertions(+), 2 deletions(-)\n")
            return MagicMock(stdout="")

        with patch("claude_diary.lib.git_info.subprocess.run", side_effect=fake_run):
            total = get_diff_stat_for_commits("/repo", ["abc1", "def5"])
        assert total["files"] == 3
        assert total["added"] == 15
        assert total["deleted"] == 5

    def test_empty_list_returns_zeros(self):
        total = get_diff_stat_for_commits("/repo", [])
        assert total == {"added": 0, "deleted": 0, "files": 0}


class TestSubprocessEncoding:
    """Git emits UTF-8; on non-UTF-8 locales (e.g. cp949) text=True without an
    explicit encoding raises UnicodeDecodeError on Korean output, which the
    broad excepts swallow into silent loss of git info. Every git subprocess
    call must pin encoding='utf-8' with errors='replace'.
    """

    def _run_all_git_calls(self):
        recorded = []

        def fake_run(cmd, **kwargs):
            recorded.append(kwargs)
            return MagicMock(returncode=0, stdout="main\n")

        with patch("claude_diary.lib.git_info.subprocess.run", side_effect=fake_run):
            _is_git_repo("/repo")
            _get_branch("/repo")
            _get_recent_commits("/repo")
            get_branch_for_commit("/repo", "abc1234")
            get_head_branch("/repo")
            get_commit_info("/repo", "abc1234")
            get_diff_stat("/repo")
            get_diff_stat_for_commits("/repo", ["abc1234"])
        return recorded

    def test_all_git_calls_pin_utf8(self):
        recorded = self._run_all_git_calls()
        assert recorded, "expected at least one git subprocess call"
        for kwargs in recorded:
            assert kwargs.get("encoding") == "utf-8"
            assert kwargs.get("errors") == "replace"

    def test_korean_commit_decoded_end_to_end(self, tmp_path):
        """Real git repo with a Korean commit subject must decode without loss.

        Under text=True on a cp949 locale this raised UnicodeDecodeError and the
        commit info was silently dropped; encoding='utf-8' preserves it.
        """
        import shutil
        if shutil.which("git") is None:
            import pytest
            pytest.skip("git not available")

        repo = tmp_path / "repo"
        repo.mkdir()
        env = {
            **os.environ,
            "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
        }
        for cmd in (
            ["git", "init", "-q"],
            ["git", "commit", "-q", "--allow-empty", "-m", "feat: 한글 커밋 메시지"],
        ):
            subprocess.run(cmd, cwd=str(repo), env=env,
                           capture_output=True, encoding="utf-8", timeout=10)

        commits = _get_recent_commits(str(repo))
        assert len(commits) == 1
        assert "한글 커밋 메시지" in commits[0]["message"]
