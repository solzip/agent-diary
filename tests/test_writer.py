"""Tests for diary writer."""

import os
from claude_diary.writer import append_entry, update_session_count, ensure_diary_dir


class TestEnsureDiaryDir:
    def test_creates_directory(self, tmp_path):
        diary_dir = str(tmp_path / "my-diary")
        ensure_diary_dir(diary_dir)
        assert os.path.isdir(diary_dir)
        assert os.path.isdir(os.path.join(diary_dir, "weekly"))

    def test_idempotent(self, tmp_path):
        diary_dir = str(tmp_path / "my-diary")
        ensure_diary_dir(diary_dir)
        ensure_diary_dir(diary_dir)
        assert os.path.isdir(diary_dir)


class TestAppendEntry:
    def test_creates_file_with_header(self, tmp_path):
        diary_dir = str(tmp_path)
        append_entry(diary_dir, "2026-03-17", "### test entry\n", lang="ko")
        filepath = os.path.join(diary_dir, "2026-03-17.md")
        assert os.path.exists(filepath)
        content = open(filepath, "r", encoding="utf-8").read()
        assert "작업일지" in content
        assert "### test entry" in content

    def test_appends_to_existing(self, tmp_path):
        diary_dir = str(tmp_path)
        append_entry(diary_dir, "2026-03-17", "entry1\n", lang="en")
        append_entry(diary_dir, "2026-03-17", "entry2\n", lang="en")
        content = open(os.path.join(diary_dir, "2026-03-17.md"), "r", encoding="utf-8").read()
        assert "entry1" in content
        assert "entry2" in content

    def test_english_header(self, tmp_path):
        diary_dir = str(tmp_path)
        append_entry(diary_dir, "2026-03-17", "test\n", lang="en")
        content = open(os.path.join(diary_dir, "2026-03-17.md"), "r", encoding="utf-8").read()
        assert "Work Diary" in content


class TestUpdateSessionCount:
    def test_first_session(self, tmp_path):
        count = update_session_count(str(tmp_path), "2026-03-17")
        assert count == 1

    def test_increments(self, tmp_path):
        d = str(tmp_path)
        update_session_count(d, "2026-03-17")
        update_session_count(d, "2026-03-17")
        count = update_session_count(d, "2026-03-17")
        assert count == 3

    def test_separate_dates(self, tmp_path):
        d = str(tmp_path)
        update_session_count(d, "2026-03-17")
        count = update_session_count(d, "2026-03-18")
        assert count == 1
