"""A project is its repository, not the folder the session happened to be in.

Sessions move. Of the twenty largest transcripts on one machine, seventeen
record more than one working directory and one records twenty-six — every `cd`
into a subdirectory is another. The project name came from the last path
segment, so work was filed under whatever folder it was standing in:

    936x  harness  -> _verification
    827x  dev      -> erp_chatbot_solzip
    411x  chatbot  -> erp_chatbot_solzip
    180x  docs     -> LottoMap_back

Of the 89 recorded directories that still exist and are repositories, 75% have
a last segment that is not the repository. Only 4% of existing entries are
misfiled, because most turns are recorded from the project root and only the
wandering one goes wrong — a ratio that holds only while the diary samples the
path this rarely, and stops holding the moment every turn is recorded.
"""

import subprocess

import pytest

from claude_diary.cli.notion_push.properties import _project_name_from_cwd
from claude_diary.core import _extract_project_name
from claude_diary.lib.git_info import get_repo_root


@pytest.fixture
def repo(tmp_path):
    """A real git repository with a subdirectory in it."""
    root = tmp_path / "my-project"
    (root / "src" / "deep").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(root)], check=True,
                   capture_output=True)
    return root


class TestFindingTheRepository:
    def test_the_root_is_its_own_repository(self, repo):
        assert get_repo_root(str(repo)).endswith("my-project")

    def test_a_subdirectory_resolves_to_the_root(self, repo):
        assert get_repo_root(str(repo / "src" / "deep")).endswith("my-project")

    def test_outside_a_repository_there_is_no_root(self, tmp_path):
        plain = tmp_path / "not-a-repo"
        plain.mkdir()
        assert get_repo_root(str(plain)) == ""

    def test_a_missing_directory_is_not_an_error(self, tmp_path):
        assert get_repo_root(str(tmp_path / "gone")) == ""

    def test_no_directory_at_all(self):
        assert get_repo_root("") == ""
        assert get_repo_root(None) == ""


class TestNamingTheProject:
    def test_a_subdirectory_is_filed_under_the_repository(self, repo):
        """The defect: `docs` instead of the project it belongs to."""
        assert _extract_project_name(str(repo / "src" / "deep")) == "my-project"

    def test_the_root_still_names_itself(self, repo):
        assert _extract_project_name(str(repo)) == "my-project"

    def test_outside_a_repository_the_folder_name_stands(self, tmp_path):
        """The best answer available there, and what it always did."""
        plain = tmp_path / "some-folder"
        plain.mkdir()
        assert _extract_project_name(str(plain)) == "some-folder"

    @pytest.mark.parametrize("value", ["", None])
    def test_nothing_becomes_unknown(self, value):
        assert _extract_project_name(value) == "unknown"

    def test_a_path_that_no_longer_exists_falls_back(self):
        """Projects move. `E:\\dev\\erp\\erp_chatbot_solzip` did."""
        assert _extract_project_name("/gone/my-project") == "my-project"


class TestNotionAgrees:
    """A session filed as `erp_chatbot_solzip` locally must not arrive in
    Notion as `dev`; both sides resolve the same way."""

    def test_the_notion_side_resolves_to_the_repository_too(self, repo):
        assert _project_name_from_cwd(str(repo / "src")) == "my-project"

    def test_both_sides_agree(self, repo):
        deep = str(repo / "src" / "deep")
        assert _project_name_from_cwd(deep) == _extract_project_name(deep)

    def test_the_notion_side_still_handles_nothing(self):
        assert _project_name_from_cwd("") == "unknown"
        assert _project_name_from_cwd("/") == "unknown"
