"""Tests for markdown formatter."""

from claude_diary.formatter import format_entry, format_daily_header, build_notion_blocks


class TestFormatEntry:
    def test_basic_entry_korean(self):
        entry = {
            "time": "15:30:00",
            "project": "my-app",
            "session_id": "test-12345678",
            "categories": ["feature"],
            "user_prompts": ["Fix the login bug"],
            "files_created": ["src/auth.py"],
            "files_modified": ["src/main.py"],
            "commands_run": ["npm test"],
            "summary_hints": ["Fixed login issue"],
            "errors_encountered": [],
            "git_info": None,
            "code_stats": None,
            "secrets_masked": 0,
        }
        result = format_entry(entry, lang="ko")
        assert "15:30:00" in result
        assert "my-app" in result
        assert "작업 요청" in result
        assert "생성된 파일" in result
        assert "수정된 파일" in result
        assert "test-123" in result

    def test_basic_entry_english(self):
        entry = {
            "time": "10:00:00",
            "project": "test",
            "session_id": "abc12345678",
            "categories": [],
            "user_prompts": ["Hello"],
            "files_created": [],
            "files_modified": [],
            "commands_run": [],
            "summary_hints": [],
            "errors_encountered": [],
            "git_info": None,
            "code_stats": None,
            "secrets_masked": 0,
        }
        result = format_entry(entry, lang="en")
        assert "Task Requests" in result
        assert "Session ID" in result

    def test_git_info_displayed(self):
        entry = {
            "time": "10:00:00", "project": "test", "session_id": "abc12345678",
            "categories": [], "user_prompts": [], "files_created": [],
            "files_modified": [], "commands_run": [], "summary_hints": [],
            "errors_encountered": [],
            "git_info": {
                "branch": "feature/auth",
                "commits": [{"hash": "abc1234", "message": "feat: add auth"}],
                "diff_stat": {"added": 50, "deleted": 10, "files": 3},
            },
            "code_stats": {"added": 50, "deleted": 10, "files": 3},
            "secrets_masked": 0,
        }
        result = format_entry(entry, lang="ko")
        assert "feature/auth" in result
        assert "abc1234" in result
        assert "+50 / -10" in result

    def test_secrets_masked_shown(self):
        entry = {
            "time": "10:00:00", "project": "test", "session_id": "abc12345678",
            "categories": [], "user_prompts": [], "files_created": [],
            "files_modified": [], "commands_run": [], "summary_hints": [],
            "errors_encountered": [], "git_info": None, "code_stats": None,
            "secrets_masked": 3,
        }
        result = format_entry(entry, lang="ko")
        assert "3" in result
        assert "마스킹" in result


class TestFormatDailyHeader:
    def test_korean_header(self):
        header = format_daily_header("2026-03-17", lang="ko")
        assert "작업일지" in header
        assert "2026-03-17" in header
        assert "화" in header

    def test_english_header(self):
        header = format_daily_header("2026-03-17", lang="en")
        assert "Work Diary" in header
        assert "Tue" in header

    def test_invalid_date(self):
        header = format_daily_header("invalid", lang="ko")
        assert "작업일지" in header


def _block_text(block):
    """Helper: extract content string from a Notion block."""
    btype = block["type"]
    rt = block[btype]["rich_text"]
    return "".join(r["text"]["content"] for r in rt)


class TestBuildNotionBlocks:
    def test_empty_task_returns_empty(self):
        blocks = build_notion_blocks({})
        assert blocks == []

    def test_body_intro_becomes_first_paragraph(self):
        blocks = build_notion_blocks({"body_intro": "한 줄 요약."})
        assert blocks[0]["type"] == "paragraph"
        assert _block_text(blocks[0]) == "한 줄 요약."

    def test_user_prompts_section(self):
        blocks = build_notion_blocks({"user_prompts": ["첫 요청", "두 번째 요청"]})
        # heading_2 + 2 bullets
        assert blocks[0]["type"] == "heading_2"
        assert "작업 요청" in _block_text(blocks[0])
        assert blocks[1]["type"] == "bulleted_list_item"
        assert _block_text(blocks[1]) == "첫 요청"
        assert _block_text(blocks[2]) == "두 번째 요청"

    def test_files_section_marks_created_with_plus(self):
        blocks = build_notion_blocks({
            "files_modified": ["src/main.py"],
            "files_created": ["src/new.py"],
        })
        texts = [_block_text(b) for b in blocks if b["type"] == "bulleted_list_item"]
        assert "src/main.py" in texts
        assert any("src/new.py" in t and "(+)" in t for t in texts)

    def test_trivial_commands_filtered_out(self):
        blocks = build_notion_blocks({
            "commands_run": ["ls", "pwd", "npm test", "git status"],
        })
        bullets = [_block_text(b) for b in blocks if b["type"] == "bulleted_list_item"]
        assert "npm test" in bullets
        assert "git status" in bullets
        assert "ls" not in bullets
        assert "pwd" not in bullets

    def test_git_section_with_branch_and_commits(self):
        git_info = {
            "branch": "feat/diary-notion",
            "commits": [
                {"hash": "abc1234ef", "short_hash": "abc1234", "message": "feat: x"},
            ],
            "diff_stat": {"added": 42, "deleted": 8, "files": 3},
        }
        blocks = build_notion_blocks({"title": "t"}, git_info=git_info)
        text = "\n".join(_block_text(b) for b in blocks)
        assert "feat/diary-notion" in text
        assert "abc1234" in text
        assert "feat: x" in text
        assert "+42 / -8" in text

    def test_errors_section_only_when_present(self):
        # no errors → no "issues" heading
        blocks_clean = build_notion_blocks({"title": "t"})
        for b in blocks_clean:
            if b["type"] == "heading_2":
                assert "이슈" not in _block_text(b)

        blocks_dirty = build_notion_blocks({"errors": ["ImportError: requests"]})
        headings = [_block_text(b) for b in blocks_dirty if b["type"] == "heading_2"]
        assert any("이슈" in h for h in headings)

    def test_long_text_truncated_below_2000(self):
        long_intro = "x" * 5000
        blocks = build_notion_blocks({"body_intro": long_intro})
        content = blocks[0]["paragraph"]["rich_text"][0]["text"]["content"]
        assert len(content) <= 2000

    def test_english_labels(self):
        blocks = build_notion_blocks({"user_prompts": ["hello"]}, lang="en")
        assert _block_text(blocks[0]) == "Task Requests"
