"""Tests for Notion ID cache."""

import json
import os
from unittest.mock import patch

from claude_diary.lib import notion_cache


def _patch_cache_dir(tmp_path):
    return patch(
        "claude_diary.lib.notion_cache.get_config_dir",
        return_value=str(tmp_path),
    )


class TestLoadSave:
    def test_load_missing_file_returns_empty(self, tmp_path):
        with _patch_cache_dir(tmp_path):
            cache = notion_cache.load("root_abc")
        assert cache["root_page_id"] == "root_abc"
        assert cache["years"] == {}
        assert cache["databases"] == {}
        assert cache["rows"] == {}

    def test_save_then_load_roundtrips(self, tmp_path):
        with _patch_cache_dir(tmp_path):
            cache = notion_cache.load("root_abc")
            notion_cache.set_year_page(cache, 2026, "page_2026")
            notion_cache.set_database(cache, 2026, "db_2026")
            notion_cache.set_row(cache, "sess1", 0, "row_xyz")
            notion_cache.save(cache)

            loaded = notion_cache.load("root_abc")

        assert loaded["years"]["2026"] == "page_2026"
        assert loaded["databases"]["2026"] == "db_2026"
        assert loaded["rows"]["sess1:0"] == "row_xyz"

    def test_root_change_invalidates_cache(self, tmp_path):
        """If config's root_page_id changes, the on-disk cache is discarded."""
        with _patch_cache_dir(tmp_path):
            cache = notion_cache.load("root_old")
            notion_cache.set_year_page(cache, 2026, "page_old")
            notion_cache.save(cache)

            # Different root_page_id → fresh empty cache
            cache2 = notion_cache.load("root_new")

        assert cache2["years"] == {}

    def test_corrupt_file_returns_empty(self, tmp_path):
        cache_file = tmp_path / "notion-cache.json"
        cache_file.write_text("not valid json {{{", encoding="utf-8")
        with _patch_cache_dir(tmp_path):
            cache = notion_cache.load("root_abc")
        assert cache["years"] == {}


class TestGetSet:
    def test_year_page_roundtrip(self):
        cache = notion_cache._empty("root")
        assert notion_cache.get_year_page(cache, 2026) is None
        notion_cache.set_year_page(cache, 2026, "page_id")
        assert notion_cache.get_year_page(cache, 2026) == "page_id"

    def test_database_roundtrip(self):
        cache = notion_cache._empty("root")
        notion_cache.set_database(cache, 2026, "db_id")
        assert notion_cache.get_database(cache, 2026) == "db_id"

    def test_row_roundtrip(self):
        cache = notion_cache._empty("root")
        notion_cache.set_row(cache, "sess1", 0, "row_id")
        assert notion_cache.get_row(cache, "sess1", 0) == "row_id"
        # Different task_index → different key
        assert notion_cache.get_row(cache, "sess1", 1) is None


class TestInvalidate:
    def test_invalidate_year_clears_year_db_and_rows(self):
        cache = notion_cache._empty("root")
        notion_cache.set_year_page(cache, 2026, "page_2026")
        notion_cache.set_database(cache, 2026, "db_2026")
        notion_cache.set_row(cache, "sess1", 0, "row_xyz")

        notion_cache.invalidate_year(cache, 2026)

        assert notion_cache.get_year_page(cache, 2026) is None
        assert notion_cache.get_database(cache, 2026) is None
        assert cache["rows"] == {}

    def test_invalidate_year_preserves_other_years(self):
        cache = notion_cache._empty("root")
        notion_cache.set_year_page(cache, 2026, "page_2026")
        notion_cache.set_year_page(cache, 2027, "page_2027")

        notion_cache.invalidate_year(cache, 2026)

        assert notion_cache.get_year_page(cache, 2026) is None
        assert notion_cache.get_year_page(cache, 2027) == "page_2027"

    def test_invalidate_row_removes_specific_row(self):
        cache = notion_cache._empty("root")
        notion_cache.set_row(cache, "sess1", 0, "row_a")
        notion_cache.set_row(cache, "sess1", 1, "row_b")

        notion_cache.invalidate_row(cache, "sess1", 0)

        assert notion_cache.get_row(cache, "sess1", 0) is None
        assert notion_cache.get_row(cache, "sess1", 1) == "row_b"

    def test_invalidate_rows_for_session(self):
        cache = notion_cache._empty("root")
        notion_cache.set_row(cache, "sess1", 0, "row_a")
        notion_cache.set_row(cache, "sess1", 1, "row_b")
        notion_cache.set_row(cache, "sess2", 0, "row_c")

        notion_cache.invalidate_rows_for_session(cache, "sess1")

        assert notion_cache.get_row(cache, "sess1", 0) is None
        assert notion_cache.get_row(cache, "sess1", 1) is None
        assert notion_cache.get_row(cache, "sess2", 0) == "row_c"
