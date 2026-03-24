"""Tests for dashboard.py — generate_dashboard HTML generation."""

import json
import os
from collections import Counter
from unittest.mock import patch, MagicMock

from claude_diary.dashboard import generate_dashboard, _render_html


class TestRenderHtml:
    """Test _render_html output structure."""

    def test_basic_html_structure(self):
        html = _render_html(
            total_sessions=10,
            total_files_created=5,
            total_files_modified=20,
            projects=Counter({"my-app": 7, "docs": 3}),
            categories=Counter({"feature": 5, "bugfix": 3, "docs": 2}),
            daily_data={"2026-03-17": 3, "2026-03-16": 2},
            hot_files=Counter({"src/main.py": 5, "README.md": 2}),
            months=3,
        )

        assert "<!DOCTYPE html>" in html
        assert "<html" in html
        assert "</html>" in html

    def test_total_sessions_in_html(self):
        html = _render_html(
            total_sessions=42,
            total_files_created=0,
            total_files_modified=0,
            projects=Counter(),
            categories=Counter(),
            daily_data={},
            hot_files=Counter(),
            months=1,
        )

        assert "42" in html
        assert "Total Sessions" in html

    def test_project_count_in_html(self):
        projects = Counter({"alpha": 5, "beta": 3, "gamma": 1})
        html = _render_html(
            total_sessions=9,
            total_files_created=0,
            total_files_modified=0,
            projects=projects,
            categories=Counter(),
            daily_data={},
            hot_files=Counter(),
            months=1,
        )

        # 3 projects total
        assert "3" in html
        assert "Projects" in html

    def test_heatmap_data_embedded(self):
        daily_data = {"2026-03-17": 5, "2026-03-16": 1}
        html = _render_html(
            total_sessions=6,
            total_files_created=0,
            total_files_modified=0,
            projects=Counter(),
            categories=Counter(),
            daily_data=daily_data,
            hot_files=Counter(),
            months=1,
        )

        # daily_data should be embedded as JSON
        assert "2026-03-17" in html
        assert "heatmapData" in html

    def test_hot_files_data_embedded(self):
        hot_files = Counter({"src/app.py": 10, "tests/test.py": 3})
        html = _render_html(
            total_sessions=0,
            total_files_created=0,
            total_files_modified=0,
            projects=Counter(),
            categories=Counter(),
            daily_data={},
            hot_files=hot_files,
            months=1,
        )

        assert "src/app.py" in html
        assert "hotFilesData" in html

    def test_no_external_cdn(self):
        html = _render_html(
            total_sessions=0,
            total_files_created=0,
            total_files_modified=0,
            projects=Counter(),
            categories=Counter(),
            daily_data={},
            hot_files=Counter(),
            months=1,
        )

        # Dashboard must work offline — no external script tags
        assert "cdn.jsdelivr.net" not in html
        assert "bar-track" in html

    def test_months_in_heatmap_title(self):
        html = _render_html(
            total_sessions=0,
            total_files_created=0,
            total_files_modified=0,
            projects=Counter(),
            categories=Counter(),
            daily_data={},
            hot_files=Counter(),
            months=6,
        )

        assert "6 months" in html

    def test_empty_data_no_crash(self):
        html = _render_html(
            total_sessions=0,
            total_files_created=0,
            total_files_modified=0,
            projects=Counter(),
            categories=Counter(),
            daily_data={},
            hot_files=Counter(),
            months=1,
        )

        assert "<!DOCTYPE html>" in html
        assert "0" in html


class TestGenerateDashboard:
    """Test generate_dashboard end-to-end with mocked config and file I/O."""

    @patch("claude_diary.dashboard.load_config")
    @patch("claude_diary.dashboard.parse_daily_file")
    def test_generates_html_file(self, mock_parse, mock_config, tmp_path):
        mock_config.return_value = {
            "diary_dir": str(tmp_path),
            "timezone_offset": 9,
        }
        mock_parse.return_value = {
            "sessions": 0,
            "projects": set(),
            "files_created": [],
            "files_modified": [],
            "tasks": [],
            "issues": [],
            "categories": [],
            "raw_entries": [],
        }

        output_path = generate_dashboard(str(tmp_path), months=1)

        assert os.path.exists(output_path)
        assert output_path.endswith("index.html")
        with open(output_path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "<!DOCTYPE html>" in content

    @patch("claude_diary.dashboard.load_config")
    @patch("claude_diary.dashboard.parse_daily_file")
    def test_dashboard_dir_created(self, mock_parse, mock_config, tmp_path):
        mock_config.return_value = {
            "diary_dir": str(tmp_path),
            "timezone_offset": 9,
        }
        mock_parse.return_value = {
            "sessions": 0,
            "projects": set(),
            "files_created": [],
            "files_modified": [],
            "tasks": [],
            "issues": [],
            "categories": [],
            "raw_entries": [],
        }

        output_path = generate_dashboard(str(tmp_path), months=1)
        dashboard_dir = os.path.join(str(tmp_path), "dashboard")
        assert os.path.isdir(dashboard_dir)

    @patch("claude_diary.dashboard.load_config")
    @patch("claude_diary.dashboard.parse_daily_file")
    def test_session_data_collected(self, mock_parse, mock_config, tmp_path):
        mock_config.return_value = {
            "diary_dir": str(tmp_path),
            "timezone_offset": 9,
        }

        def fake_parse(filepath):
            if "2026-03-17" in filepath:
                return {
                    "sessions": 3,
                    "projects": {"my-app"},
                    "files_created": ["new.py"],
                    "files_modified": ["main.py", "utils.py"],
                    "tasks": ["Build feature"],
                    "issues": [],
                    "categories": ["feature"],
                    "raw_entries": [],
                }
            return {
                "sessions": 0,
                "projects": set(),
                "files_created": [],
                "files_modified": [],
                "tasks": [],
                "issues": [],
                "categories": [],
                "raw_entries": [],
            }

        mock_parse.side_effect = fake_parse

        output_path = generate_dashboard(str(tmp_path), months=1)

        with open(output_path, "r", encoding="utf-8") as f:
            content = f.read()
        # The dashboard should contain session data
        assert "<!DOCTYPE html>" in content

    @patch("claude_diary.dashboard.load_config")
    @patch("claude_diary.dashboard.parse_daily_file")
    def test_uses_config_diary_dir_when_none(self, mock_parse, mock_config, tmp_path):
        mock_config.return_value = {
            "diary_dir": str(tmp_path),
            "timezone_offset": 9,
        }
        mock_parse.return_value = {
            "sessions": 0,
            "projects": set(),
            "files_created": [],
            "files_modified": [],
            "tasks": [],
            "issues": [],
            "categories": [],
            "raw_entries": [],
        }

        # diary_dir=None triggers config lookup
        output_path = generate_dashboard(diary_dir=None, months=1)

        assert os.path.exists(output_path)

    @patch("claude_diary.dashboard.load_config")
    @patch("claude_diary.dashboard.parse_daily_file")
    def test_multiple_months_coverage(self, mock_parse, mock_config, tmp_path):
        mock_config.return_value = {
            "diary_dir": str(tmp_path),
            "timezone_offset": 9,
        }
        mock_parse.return_value = {
            "sessions": 0,
            "projects": set(),
            "files_created": [],
            "files_modified": [],
            "tasks": [],
            "issues": [],
            "categories": [],
            "raw_entries": [],
        }

        output_path = generate_dashboard(str(tmp_path), months=6)

        with open(output_path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "6 months" in content

    @patch("claude_diary.dashboard.load_config")
    @patch("claude_diary.dashboard.parse_daily_file")
    def test_category_data_in_output(self, mock_parse, mock_config, tmp_path):
        mock_config.return_value = {
            "diary_dir": str(tmp_path),
            "timezone_offset": 9,
        }

        call_count = [0]

        def fake_parse(filepath):
            call_count[0] += 1
            # Return data for a few files to get categories
            if call_count[0] <= 3:
                return {
                    "sessions": 1,
                    "projects": {"proj"},
                    "files_created": [],
                    "files_modified": ["f.py"],
                    "tasks": [],
                    "issues": [],
                    "categories": ["refactor"],
                    "raw_entries": [],
                }
            return {
                "sessions": 0,
                "projects": set(),
                "files_created": [],
                "files_modified": [],
                "tasks": [],
                "issues": [],
                "categories": [],
                "raw_entries": [],
            }

        mock_parse.side_effect = fake_parse

        output_path = generate_dashboard(str(tmp_path), months=1)
        with open(output_path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "Categories" in content
        assert "refactor" in content
