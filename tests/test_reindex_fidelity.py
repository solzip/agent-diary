"""A rebuilt index must not be thinner than an incrementally built one.

`reindex_all` used to write `session_id: ""`, `git_commits: []` and zeroed
line counts, so running the maintenance command silently degraded the index
and anything reading those fields got plausible-looking nothing.
"""

import json

from claude_diary.indexer import reindex_all

ENTRY = """### ⏰ 14:30:15 | 📁 `my-app`

**🏷️ 카테고리:** `feature` `test`

**📋 작업 요청:**
  1. add jwt authentication

**📄 생성된 파일:**
  - `src/auth.py`

**🔀 Git:**
  - 🌿 브랜치: `feat/jwt`
  - 커밋: `a1b2c3d` feat: verify tokens
  - 커밋: `e4f5g6h` test: cover the failure path

**📊 변경 통계:** +145 / -12 lines (5 files)

**📝 작업 요약:**
  - Added JWT verification middleware

<details><summary>x</summary>
<code>7b285f1f-3540-420d-b4f4-50aa9d2a788b</code>
</details>
"""

ENGLISH_ENTRY = """### ⏰ 09:00:00 | 📁 `other-app`

**🏷️ Categories:** `bugfix`

**📋 Task Requests:**
  1. fix the parser

**🔀 Git:**
  - Commit: `9f8e7d6` fix: handle empty input

**📊 Code Stats:** +3 / -9 lines (2 files)

<details><summary>x</summary>
<code>11112222-3333-4444-5555-666677778888</code>
</details>
"""


def _write(tmp_path, name, body):
    (tmp_path / name).write_text("# header\n\n---\n" + body, encoding="utf-8")


def _entries(tmp_path):
    return json.loads((tmp_path / ".diary_index.json").read_text(encoding="utf-8"))["entries"]


def test_rebuild_recovers_the_session_id(tmp_path):
    """Without it nothing can join the index back to the diary text."""
    _write(tmp_path, "2026-07-01.md", ENTRY)
    assert reindex_all(str(tmp_path)) == 1
    assert _entries(tmp_path)[0]["session_id"] == "7b285f1f-3540-420d-b4f4-50aa9d2a788b"


def test_rebuild_recovers_line_counts(tmp_path):
    _write(tmp_path, "2026-07-01.md", ENTRY)
    reindex_all(str(tmp_path))
    entry = _entries(tmp_path)[0]
    assert entry["lines_added"] == 145
    assert entry["lines_deleted"] == 12


def test_rebuild_recovers_every_category_not_just_the_first(tmp_path):
    """The fixture above has carried two categories the whole time and nothing
    asserted on them, so the index quietly kept one.

    Measured on a real 73-file diary: 7,131 entries, 91.6% of them with three
    categories, 20,424 categories in the files and 7,048 reaching the index.
    `search refactor` was answering from 35 entries where 1,183 exist."""
    _write(tmp_path, "2026-07-01.md", ENTRY)
    assert reindex_all(str(tmp_path)) == 1
    assert _entries(tmp_path)[0]["categories"] == ["feature", "test"]


def test_the_word_in_prose_does_not_become_a_category(tmp_path):
    """From a real entry: a commit line mentioning categories with a hash in
    backticks beside it. The old pattern indexed the hash."""
    _write(tmp_path, "2026-07-01.md", ENTRY.replace(
        "  - `src/auth.py`",
        "  - `src/auth.py`\n  - 커밋: `f98c96ec5` fix: 신규 카테고리 첫 부팅 레이스"))
    assert reindex_all(str(tmp_path)) == 1
    assert _entries(tmp_path)[0]["categories"] == ["feature", "test"]


def test_rebuild_recovers_commits(tmp_path):
    _write(tmp_path, "2026-07-01.md", ENTRY)
    reindex_all(str(tmp_path))
    assert _entries(tmp_path)[0]["git_commits"] == ["a1b2c3d", "e4f5g6h"]


def test_english_labels_are_recovered_too(tmp_path):
    _write(tmp_path, "2026-07-02.md", ENGLISH_ENTRY)
    reindex_all(str(tmp_path))
    entry = _entries(tmp_path)[0]
    assert entry["session_id"] == "11112222-3333-4444-5555-666677778888"
    assert entry["lines_added"] == 3
    assert entry["lines_deleted"] == 9
    assert entry["git_commits"] == ["9f8e7d6"]


def test_an_entry_without_git_or_stats_still_indexes(tmp_path):
    minimal = (
        "### ⏰ 08:00:00 | 📁 `bare`\n\n"
        "**📋 작업 요청:**\n  1. do a thing\n\n"
        "<details><summary>x</summary>\n<code>aaaabbbb-cccc-dddd-eeee-ffff00001111</code>\n"
        "</details>\n"
    )
    _write(tmp_path, "2026-07-03.md", minimal)
    reindex_all(str(tmp_path))
    entry = _entries(tmp_path)[0]
    assert entry["session_id"] == "aaaabbbb-cccc-dddd-eeee-ffff00001111"
    assert entry["git_commits"] == []
    assert entry["lines_added"] == 0
