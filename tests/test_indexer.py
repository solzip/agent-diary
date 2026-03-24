"""Tests for search index manager."""

import json
import os
from unittest.mock import patch, MagicMock

from claude_diary.indexer import (
    update_index,
    load_index,
    reindex_all,
    _load_index,
    _save_index,
)


class TestLoadIndex:
    def test_returns_empty_when_no_file(self, tmp_path):
        index_path = str(tmp_path / ".diary_index.json")
        result = _load_index(index_path)
        assert result == {"entries": [], "last_indexed": ""}

    def test_loads_existing_index(self, tmp_path):
        index_path = tmp_path / ".diary_index.json"
        data = {"entries": [{"date": "2026-03-17"}], "last_indexed": "2026-03-17T10:00:00"}
        index_path.write_text(json.dumps(data), encoding="utf-8")
        result = _load_index(str(index_path))
        assert result["entries"][0]["date"] == "2026-03-17"
        assert result["last_indexed"] == "2026-03-17T10:00:00"

    def test_returns_empty_on_corrupt_json(self, tmp_path):
        index_path = tmp_path / ".diary_index.json"
        index_path.write_text("{corrupt json!!!", encoding="utf-8")
        result = _load_index(str(index_path))
        assert result == {"entries": [], "last_indexed": ""}


class TestSaveIndex:
    def test_writes_index_file(self, tmp_path):
        index_path = str(tmp_path / ".diary_index.json")
        data = {"entries": [{"date": "2026-03-17"}], "last_indexed": "2026-03-17T12:00:00"}
        _save_index(index_path, data)
        with open(index_path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        assert loaded["entries"][0]["date"] == "2026-03-17"

    def test_save_does_not_raise_on_error(self, tmp_path):
        """Save to an invalid path should silently fail."""
        _save_index("/nonexistent/deep/path/.diary_index.json", {"entries": []})
        # No exception raised


class TestLoadIndexPublic:
    def test_delegates_to_internal(self, tmp_path):
        index_path = tmp_path / ".diary_index.json"
        data = {"entries": [{"date": "2026-03-10"}], "last_indexed": "2026-03-10T08:00:00"}
        index_path.write_text(json.dumps(data), encoding="utf-8")
        result = load_index(str(tmp_path))
        assert result["entries"][0]["date"] == "2026-03-10"

    def test_returns_empty_for_missing_dir(self, tmp_path):
        result = load_index(str(tmp_path / "nonexistent"))
        assert result == {"entries": [], "last_indexed": ""}


class TestUpdateIndex:
    def test_adds_entry_to_empty_index(self, tmp_path):
        entry_data = {
            "date": "2026-03-17",
            "time": "10:00:00",
            "project": "my-app",
            "categories": ["feature"],
            "files_created": ["src/new.py"],
            "files_modified": ["src/old.py"],
            "user_prompts": ["Implement the login feature quickly"],
            "git_info": {"commits": [{"hash": "abc123", "message": "Fix"}]},
            "code_stats": {"added": 10, "deleted": 2},
            "session_id": "sess-001",
        }
        update_index(str(tmp_path), entry_data)

        index = load_index(str(tmp_path))
        assert len(index["entries"]) == 1
        entry = index["entries"][0]
        assert entry["date"] == "2026-03-17"
        assert entry["project"] == "my-app"
        assert "src/new.py" in entry["files"]
        assert "src/old.py" in entry["files"]
        assert "abc123" in entry["git_commits"]
        assert entry["lines_added"] == 10
        assert entry["lines_deleted"] == 2
        assert entry["session_id"] == "sess-001"
        assert "implement" in entry["keywords"]  # lowercased
        assert index["last_indexed"] == "2026-03-17T10:00:00"

    def test_appends_to_existing_index(self, tmp_path):
        # Seed an existing index
        index_path = tmp_path / ".diary_index.json"
        existing = {"entries": [{"date": "2026-03-16"}], "last_indexed": "2026-03-16T12:00:00"}
        index_path.write_text(json.dumps(existing), encoding="utf-8")

        entry_data = {
            "date": "2026-03-17",
            "time": "14:00:00",
            "project": "other",
            "categories": [],
            "files_created": [],
            "files_modified": [],
            "user_prompts": [],
            "session_id": "sess-002",
        }
        update_index(str(tmp_path), entry_data)
        index = load_index(str(tmp_path))
        assert len(index["entries"]) == 2

    def test_keyword_extraction_filters_short_words(self, tmp_path):
        entry_data = {
            "date": "2026-03-17",
            "time": "10:00:00",
            "project": "x",
            "categories": [],
            "files_created": [],
            "files_modified": [],
            "user_prompts": ["I am ok to go ahead with implementation"],
            "session_id": "sess-003",
        }
        update_index(str(tmp_path), entry_data)
        index = load_index(str(tmp_path))
        keywords = index["entries"][0]["keywords"]
        # Words 2 chars or less ("I", "am", "ok", "to", "go") should be filtered
        assert "am" not in keywords
        assert "ok" not in keywords
        assert "to" not in keywords
        assert "go" not in keywords
        assert "ahead" in keywords
        assert "implementation" in keywords

    def test_no_git_info(self, tmp_path):
        entry_data = {
            "date": "2026-03-17",
            "time": "10:00:00",
            "project": "my-app",
            "categories": [],
            "files_created": [],
            "files_modified": [],
            "user_prompts": [],
            "session_id": "sess-004",
        }
        update_index(str(tmp_path), entry_data)
        index = load_index(str(tmp_path))
        assert index["entries"][0]["git_commits"] == []

    def test_no_code_stats(self, tmp_path):
        entry_data = {
            "date": "2026-03-17",
            "time": "10:00:00",
            "project": "my-app",
            "categories": [],
            "files_created": [],
            "files_modified": [],
            "user_prompts": [],
            "session_id": "sess-005",
        }
        update_index(str(tmp_path), entry_data)
        index = load_index(str(tmp_path))
        assert index["entries"][0]["lines_added"] == 0
        assert index["entries"][0]["lines_deleted"] == 0

    def test_files_truncated_to_20(self, tmp_path):
        entry_data = {
            "date": "2026-03-17",
            "time": "10:00:00",
            "project": "big-proj",
            "categories": [],
            "files_created": [f"file_{i}.py" for i in range(15)],
            "files_modified": [f"mod_{i}.py" for i in range(10)],
            "user_prompts": [],
            "session_id": "sess-006",
        }
        update_index(str(tmp_path), entry_data)
        index = load_index(str(tmp_path))
        assert len(index["entries"][0]["files"]) == 20

    def test_keywords_truncated_to_30(self, tmp_path):
        long_prompt = " ".join(f"keyword{i}" for i in range(50))
        entry_data = {
            "date": "2026-03-17",
            "time": "10:00:00",
            "project": "proj",
            "categories": [],
            "files_created": [],
            "files_modified": [],
            "user_prompts": [long_prompt],
            "session_id": "sess-007",
        }
        update_index(str(tmp_path), entry_data)
        index = load_index(str(tmp_path))
        assert len(index["entries"][0]["keywords"]) == 30


class TestReindexAll:
    def test_reindex_empty_directory(self, tmp_path):
        count = reindex_all(str(tmp_path))
        assert count == 0
        index = load_index(str(tmp_path))
        assert index["entries"] == []

    def test_reindex_with_sessions(self, tmp_path):
        content = (
            "# 2026-03-17\n\n"
            "### \u23f0 10:00:00\n"
            "\U0001f4c1 `my-project`\n\n"
            "\uce74\ud14c\uace0\ub9ac: `feature`\n\n"
            "\uc791\uc5c5 \uc694\uccad:\n"
            "  1. Build authentication module\n"
            "  2. Write tests for login\n\n"
            "  - `src/auth.py`\n\n"
            "### \u23f0 14:00:00\n"
            "\U0001f4c1 `other-project`\n"
        )
        (tmp_path / "2026-03-17.md").write_text(content, encoding="utf-8")

        count = reindex_all(str(tmp_path))
        assert count == 2
        index = load_index(str(tmp_path))
        assert len(index["entries"]) == 2
        assert index["entries"][0]["project"] == "my-project"
        assert index["entries"][0]["time"] == "10:00:00"
        assert index["entries"][1]["project"] == "other-project"
        assert index["entries"][1]["time"] == "14:00:00"

    def test_reindex_skips_zero_session_files(self, tmp_path):
        (tmp_path / "2026-03-17.md").write_text("No sessions here\n", encoding="utf-8")
        count = reindex_all(str(tmp_path))
        assert count == 0

    def test_reindex_multiple_files(self, tmp_path):
        day1 = (
            "### \u23f0 10:00:00\n"
            "\U0001f4c1 `proj-a`\n"
        )
        day2 = (
            "### \u23f0 09:00:00\n"
            "\U0001f4c1 `proj-b`\n"
        )
        (tmp_path / "2026-03-16.md").write_text(day1, encoding="utf-8")
        (tmp_path / "2026-03-17.md").write_text(day2, encoding="utf-8")

        count = reindex_all(str(tmp_path))
        assert count == 2
        index = load_index(str(tmp_path))
        dates = [e["date"] for e in index["entries"]]
        assert "2026-03-16" in dates
        assert "2026-03-17" in dates

    def test_reindex_extracts_keywords_from_task_requests(self, tmp_path):
        content = (
            "### \u23f0 10:00:00\n"
            "\U0001f4c1 `proj`\n\n"
            "\uc791\uc5c5 \uc694\uccad:\n"
            "  1. Implement authentication flow\n"
        )
        (tmp_path / "2026-03-17.md").write_text(content, encoding="utf-8")
        reindex_all(str(tmp_path))
        index = load_index(str(tmp_path))
        keywords = index["entries"][0]["keywords"]
        assert "implement" in keywords or "authentication" in keywords

    def test_reindex_handles_unreadable_file(self, tmp_path):
        """A file that parse_daily_file can read but read_text fails for."""
        content = "### \u23f0 10:00:00\n\U0001f4c1 `proj`\n"
        f = tmp_path / "2026-03-17.md"
        f.write_text(content, encoding="utf-8")

        # Patch Path.read_text to fail for this specific call
        from pathlib import Path
        original_read_text = Path.read_text

        def mock_read_text(self, *args, **kwargs):
            if self.name == "2026-03-17.md" and "diary" not in str(self):
                raise PermissionError("no access")
            return original_read_text(self, *args, **kwargs)

        with patch.object(Path, "read_text", mock_read_text):
            count = reindex_all(str(tmp_path))
        # The session is detected by parse_daily_file, but read_text fails => continue
        assert count == 0

    def test_reindex_session_without_time(self, tmp_path):
        content = (
            "### \u23f0\n"
            "\U0001f4c1 `proj`\n"
        )
        (tmp_path / "2026-03-17.md").write_text(content, encoding="utf-8")
        count = reindex_all(str(tmp_path))
        assert count == 1
        index = load_index(str(tmp_path))
        assert index["entries"][0]["time"] == ""

    def test_reindex_session_without_project(self, tmp_path):
        content = "### \u23f0 10:00:00\nSome work\n"
        (tmp_path / "2026-03-17.md").write_text(content, encoding="utf-8")
        count = reindex_all(str(tmp_path))
        assert count == 1
        index = load_index(str(tmp_path))
        assert index["entries"][0]["project"] == ""

    def test_reindex_sets_last_indexed(self, tmp_path):
        content = "### \u23f0 10:00:00\n\U0001f4c1 `proj`\n"
        (tmp_path / "2026-03-17.md").write_text(content, encoding="utf-8")
        reindex_all(str(tmp_path))
        index = load_index(str(tmp_path))
        assert index["last_indexed"] != ""
