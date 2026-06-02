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
    if btype == "table_row":
        cells = block["table_row"]["cells"]
        return " | ".join(
            "".join(r["text"]["content"] for r in cell)
            for cell in cells
        )
    if "rich_text" not in block[btype]:
        return ""
    rt = block[btype]["rich_text"]
    return "".join(r["text"]["content"] for r in rt)


def _flatten_blocks(blocks):
    for block in blocks:
        yield block
        children = block[block["type"]].get("children", [])
        yield from _flatten_blocks(children)


class TestBuildNotionBlocks:
    def test_empty_task_returns_empty(self):
        blocks = build_notion_blocks({})
        assert blocks == []

    def test_body_intro_becomes_first_paragraph(self):
        blocks = build_notion_blocks({"body_intro": "한 줄 요약."})
        assert blocks[0]["type"] == "callout"
        assert _block_text(blocks[0]) == "한 줄 요약."

    def test_user_prompts_section(self):
        blocks = build_notion_blocks({"user_prompts": ["첫 요청", "두 번째 요청"]})
        flat = list(_flatten_blocks(blocks))
        assert blocks[0]["type"] == "heading_2"
        assert "부록" in _block_text(blocks[0])
        assert blocks[1]["type"] == "toggle"
        assert _block_text(blocks[1]) == "원문 요청"
        assert _block_text(flat[2]) == "작업 요청: 첫 요청"
        assert _block_text(flat[3]) == "작업 요청: 두 번째 요청"

    def test_rich_notion_body_sections(self):
        blocks = build_notion_blocks({
            "body_intro": "Implemented richer Notion body content.",
            "summary_hints": ["Added structured body sections"],
            "key_changes": ["Notion entries now read as developer work records"],
            "work_context": "The previous body looked like a raw log.",
            "work_scope": "Reorganize the Notion body for daily reporting.",
            "approach": "Group high-level information above raw evidence.",
            "outcome": "The body reads as a brief.",
            "impact": ["Managers can scan the result quickly"],
            "code_change_highlights": [
                "`formatter.py`: renders high-signal code change bullets without full diff",
            ],
            "decisions": ["Keep Notion view automation separate"],
            "implementation_notes": ["Render optional fields only when present"],
            "verification": "pytest passed",
            "risks": ["Existing sessions need refreshed installed commands"],
            "next_steps": ["Install refreshed Codex skills"],
            "user_prompts": ["Make the Notion body less sparse"],
        }, lang="en")
        flat = list(_flatten_blocks(blocks))
        texts = [_block_text(b) for b in flat]
        headings = [_block_text(b) for b in blocks if b["type"] == "heading_2"]

        assert texts[0] == "Implemented richer Notion body content."
        assert "Results" in headings
        assert "Work Snapshot" in headings
        assert "Impact" in headings
        assert "Verification" in headings
        assert "Risks / Next Actions" in headings
        assert "Appendix" in headings
        assert "Added structured body sections" in texts
        assert "Key Changes: Notion entries now read as developer work records" in texts
        assert "Context | The previous body looked like a raw log." in texts
        assert "Impact" in headings
        assert "Managers can scan the result quickly" in texts
        assert "Code Change Highlights: `formatter.py`: renders high-signal code change bullets without full diff" in texts
        assert "pytest passed" in texts
        assert "Existing sessions need refreshed installed commands" in texts
        assert "Next Steps: Install refreshed Codex skills" in texts
        assert "Developer Evidence" in texts
        assert "Original Requests" in texts
        assert texts.index("Results") < texts.index("Appendix")

    def test_rich_notion_body_limits_summary_bullets(self):
        blocks = build_notion_blocks({
            "summary_hints": ["summary-%d" % i for i in range(9)],
        }, lang="en")
        texts = [_block_text(b) for b in _flatten_blocks(blocks)]

        assert "summary-2" in texts
        assert "summary-3" not in texts
        assert [b["type"] for b in blocks[:4]] == ["heading_2", "to_do", "to_do", "to_do"]

    def test_work_snapshot_uses_table_not_callouts(self):
        blocks = build_notion_blocks({
            "work_context": "Started from UX feedback.",
            "work_scope": "Changed the Notion body renderer.",
            "approach": "Use a compact table.",
            "outcome": "The page scans faster.",
        }, lang="en")
        flat = list(_flatten_blocks(blocks))
        texts = [_block_text(b) for b in flat]

        assert "Work Snapshot" in texts
        assert any(b["type"] == "table" for b in blocks)
        assert "Item | Content" in texts
        assert "Context | Started from UX feedback." in texts
        assert not any(b["type"] == "callout" for b in blocks)

    def test_callout_count_is_limited_to_intro_and_combined_risks(self):
        blocks = build_notion_blocks({
            "body_intro": "핵심 요약.",
            "summary_hints": ["결과 1", "결과 2"],
            "work_context": "배경.",
            "impact": ["영향 1", "영향 2"],
            "verification": ["검증 1"],
            "risks": ["리스크 1", "리스크 2"],
            "next_steps": ["다음 작업"],
        })
        callouts = [b for b in _flatten_blocks(blocks) if b["type"] == "callout"]

        assert len(callouts) == 2
        assert _block_text(callouts[0]) == "핵심 요약."
        assert _block_text(callouts[1]) == "리스크 1\n리스크 2"

    def test_code_changes_alias_limits_to_three_bullets(self):
        blocks = build_notion_blocks({
            "code_changes": ["change-%d" % i for i in range(8)],
        }, lang="en")
        texts = [_block_text(b) for b in _flatten_blocks(blocks)]

        assert "Appendix" in texts
        assert "Code Change Highlights: change-2" in texts
        assert "Code Change Highlights: change-3" not in texts

    def test_files_section_marks_created_with_plus(self):
        blocks = build_notion_blocks({
            "files_modified": ["src/main.py"],
            "files_created": ["src/new.py"],
        })
        texts = [_block_text(b) for b in _flatten_blocks(blocks) if b["type"] == "bulleted_list_item"]
        assert "수정된 파일: src/main.py" in texts
        assert "생성된 파일: src/new.py" in texts

    def test_trivial_commands_filtered_out(self):
        blocks = build_notion_blocks({
            "commands_run": ["ls", "pwd", "npm test", "git status"],
        })
        bullets = [_block_text(b) for b in _flatten_blocks(blocks) if b["type"] == "bulleted_list_item"]
        assert "주요 명령어: npm test" in bullets
        assert "주요 명령어: git status" in bullets
        assert all("ls" not in b for b in bullets)
        assert all("pwd" not in b for b in bullets)

    def test_git_section_with_branch_and_commits(self):
        git_info = {
            "branch": "feat/diary-notion",
            "commits": [
                {"hash": "abc1234ef", "short_hash": "abc1234", "message": "feat: x"},
            ],
            "diff_stat": {"added": 42, "deleted": 8, "files": 3},
        }
        blocks = build_notion_blocks({"title": "t"}, git_info=git_info)
        text = "\n".join(_block_text(b) for b in _flatten_blocks(blocks))
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
        text = "\n".join(_block_text(b) for b in _flatten_blocks(blocks_dirty))
        assert "부록" in text
        assert "발생한 이슈: ImportError: requests" in text

    def test_errors_encountered_fallback(self):
        blocks = build_notion_blocks({"errors_encountered": ["ImportError: requests"]}, lang="en")
        text = "\n".join(_block_text(b) for b in _flatten_blocks(blocks))
        assert "Issues Encountered" in text
        assert "ImportError: requests" in text

    def test_long_text_truncated_below_2000(self):
        long_intro = "x" * 5000
        blocks = build_notion_blocks({"body_intro": long_intro})
        content = blocks[0]["callout"]["rich_text"][0]["text"]["content"]
        assert len(content) <= 2000

    def test_english_labels(self):
        blocks = build_notion_blocks({"user_prompts": ["hello"]}, lang="en")
        assert _block_text(blocks[0]) == "Appendix"

    def test_compact_body_stays_under_notion_children_limit(self):
        task = {
            "body_intro": "x",
            "summary_hints": ["summary-%d" % i for i in range(7)],
            "key_changes": ["change-%d" % i for i in range(6)],
            "work_context": ["context-%d" % i for i in range(3)],
            "work_scope": ["scope-%d" % i for i in range(3)],
            "approach": ["approach-%d" % i for i in range(3)],
            "outcome": ["outcome-%d" % i for i in range(3)],
            "impact": ["impact-%d" % i for i in range(6)],
            "code_change_highlights": ["code-%d" % i for i in range(6)],
            "decisions": ["decision-%d" % i for i in range(5)],
            "implementation_notes": ["note-%d" % i for i in range(8)],
            "verification": ["verify-%d" % i for i in range(5)],
            "risks": ["risk-%d" % i for i in range(5)],
            "next_steps": ["next-%d" % i for i in range(5)],
            "support_needed": ["support-%d" % i for i in range(4)],
            "user_prompts": ["prompt-%d" % i for i in range(5)],
            "files_modified": ["modified-%d.py" % i for i in range(15)],
            "files_created": ["created-%d.py" % i for i in range(15)],
            "commands_run": ["npm test %d" % i for i in range(10)],
            "errors": ["error-%d" % i for i in range(5)],
        }
        git_info = {
            "branch": "main",
            "commits": [{"hash": "abc1234%d" % i, "message": "msg-%d" % i} for i in range(10)],
            "diff_stat": {"added": 42, "deleted": 8, "files": 3},
        }
        blocks = build_notion_blocks(task, git_info=git_info)

        assert len(blocks) <= 95
