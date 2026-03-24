"""Tests for exporters (base, loader, slack, obsidian, discord, notion, github)."""

import json
import os
from unittest.mock import patch, MagicMock, call

from claude_diary.exporters.base import BaseExporter
from claude_diary.exporters.loader import load_exporters, run_exporters, retry_queued


SAMPLE_ENTRY = {
    "date": "2026-03-17",
    "time": "15:00:00",
    "project": "test-app",
    "categories": ["feature"],
    "user_prompts": ["Add login"],
    "files_created": [],
    "files_modified": ["src/auth.py"],
    "commands_run": ["npm test"],
    "summary_hints": ["Login implemented"],
    "git_info": {"branch": "main", "commits": [], "diff_stat": {"added": 10, "deleted": 2, "files": 1}},
    "code_stats": {"added": 10, "deleted": 2, "files": 1},
    "secrets_masked": 0,
}


class TestBaseExporter:
    def test_not_implemented(self):
        exp = BaseExporter({})
        try:
            exp.export({})
            assert False, "Should raise"
        except NotImplementedError:
            pass

    def test_trust_level_default(self):
        assert BaseExporter.TRUST_LEVEL == "custom"


class TestLoadExporters:
    def test_empty_config(self):
        assert load_exporters({"exporters": {}}) == []

    def test_disabled_exporter(self):
        config = {"exporters": {"slack": {"enabled": False, "webhook_url": "https://hooks.slack.com/test"}}}
        assert load_exporters(config) == []

    def test_invalid_config_rejected(self):
        config = {"exporters": {"slack": {"enabled": True, "webhook_url": "invalid"}}}
        loaded = load_exporters(config)
        assert len(loaded) == 0

    def test_valid_slack_loaded(self):
        config = {"exporters": {"slack": {"enabled": True, "webhook_url": "https://hooks.slack.com/test"}}}
        loaded = load_exporters(config)
        assert len(loaded) == 1
        assert loaded[0][0] == "slack"

    def test_nonexistent_exporter(self):
        config = {"exporters": {"nonexistent": {"enabled": True}}}
        loaded = load_exporters(config)
        assert len(loaded) == 0


class TestRunExporters:
    def test_success(self):
        mock_exp = MagicMock()
        mock_exp.export.return_value = True
        result = run_exporters([("test", mock_exp)], SAMPLE_ENTRY)
        assert "test" in result["success"]
        assert result["failed"] == []

    def test_failure_caught(self):
        mock_exp = MagicMock()
        mock_exp.export.side_effect = Exception("Network error")
        result = run_exporters([("test", mock_exp)], SAMPLE_ENTRY)
        assert "test" in result["failed"]


class TestSlackExporter:
    def test_validate_config(self):
        from claude_diary.exporters.slack import SlackExporter
        assert SlackExporter({"webhook_url": "https://hooks.slack.com/test"}).validate_config()
        assert not SlackExporter({"webhook_url": "invalid"}).validate_config()
        assert not SlackExporter({}).validate_config()

    @patch("urllib.request.urlopen")
    def test_export_success(self, mock_urlopen):
        from claude_diary.exporters.slack import SlackExporter
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_urlopen.return_value = mock_resp

        exp = SlackExporter({"webhook_url": "https://hooks.slack.com/test"})
        result = exp.export(SAMPLE_ENTRY)
        assert result is True
        mock_urlopen.assert_called_once()


class TestObsidianExporter:
    def test_validate_config(self, tmp_path):
        from claude_diary.exporters.obsidian import ObsidianExporter
        assert ObsidianExporter({"vault_path": str(tmp_path)}).validate_config()
        assert not ObsidianExporter({"vault_path": "/nonexistent"}).validate_config()
        assert not ObsidianExporter({}).validate_config()

    def test_export_creates_file(self, tmp_path):
        from claude_diary.exporters.obsidian import ObsidianExporter
        exp = ObsidianExporter({"vault_path": str(tmp_path)})
        result = exp.export(SAMPLE_ENTRY)
        assert result is True
        diary_file = tmp_path / "claude-diary" / "2026-03-17.md"
        assert diary_file.exists()
        content = diary_file.read_text(encoding="utf-8")
        assert "test-app" in content
        assert "feature" in content

    def test_export_appends_to_existing_file(self, tmp_path):
        """When a daily note already exists, new entry is appended with separator."""
        from claude_diary.exporters.obsidian import ObsidianExporter
        exp = ObsidianExporter({"vault_path": str(tmp_path)})
        exp.export(SAMPLE_ENTRY)
        # Export again — should append
        entry2 = dict(SAMPLE_ENTRY, project="second-app", time="18:00:00")
        exp.export(entry2)
        diary_file = tmp_path / "claude-diary" / "2026-03-17.md"
        content = diary_file.read_text(encoding="utf-8")
        assert "test-app" in content
        assert "second-app" in content
        assert "\n---\n" in content  # separator between entries

    def test_export_empty_date_returns_false(self, tmp_path):
        """Export with empty date should return False."""
        from claude_diary.exporters.obsidian import ObsidianExporter
        exp = ObsidianExporter({"vault_path": str(tmp_path)})
        entry_no_date = dict(SAMPLE_ENTRY, date="")
        result = exp.export(entry_no_date)
        assert result is False

    def test_export_custom_subfolder(self, tmp_path):
        """Obsidian exporter should use custom subfolder when configured."""
        from claude_diary.exporters.obsidian import ObsidianExporter
        exp = ObsidianExporter({"vault_path": str(tmp_path), "subfolder": "my-diary"})
        result = exp.export(SAMPLE_ENTRY)
        assert result is True
        diary_file = tmp_path / "my-diary" / "2026-03-17.md"
        assert diary_file.exists()

    def test_export_frontmatter_structure(self, tmp_path):
        """Verify the YAML frontmatter contains expected fields."""
        from claude_diary.exporters.obsidian import ObsidianExporter
        exp = ObsidianExporter({"vault_path": str(tmp_path)})
        exp.export(SAMPLE_ENTRY)
        diary_file = tmp_path / "claude-diary" / "2026-03-17.md"
        content = diary_file.read_text(encoding="utf-8")
        assert content.startswith("---\n")
        assert "date: 2026-03-17" in content
        assert "project: test-app" in content
        assert "tags: [claude-diary, test-app]" in content


# ── Rich sample entry with commits and code_stats for testing embeds/fields ──
RICH_ENTRY = {
    "date": "2026-03-17",
    "time": "15:00:00",
    "project": "test-app",
    "categories": ["feature", "refactor"],
    "user_prompts": ["Add login", "Refactor auth module"],
    "files_created": ["src/new.py"],
    "files_modified": ["src/auth.py", "src/utils.py"],
    "commands_run": ["npm test"],
    "summary_hints": ["Login implemented", "Auth module refactored"],
    "git_info": {
        "branch": "feat/login",
        "commits": [
            {"hash": "abc1234", "message": "feat: add login"},
            {"hash": "def5678", "message": "refactor: auth module"},
        ],
        "diff_stat": {"added": 50, "deleted": 10, "files": 3},
    },
    "code_stats": {"added": 50, "deleted": 10, "files": 3},
    "secrets_masked": 0,
}


# ── Discord Exporter Tests ─────────────────────────────────────────────────

class TestDiscordExporter:
    def test_validate_config_valid(self):
        from claude_diary.exporters.discord import DiscordExporter
        exp = DiscordExporter({"webhook_url": "https://discord.com/api/webhooks/123/abc"})
        assert exp.validate_config() is True

    def test_validate_config_invalid_url(self):
        from claude_diary.exporters.discord import DiscordExporter
        assert not DiscordExporter({"webhook_url": "https://example.com/hook"}).validate_config()
        assert not DiscordExporter({"webhook_url": ""}).validate_config()
        assert not DiscordExporter({}).validate_config()

    @patch("urllib.request.urlopen")
    def test_export_success_200(self, mock_urlopen):
        from claude_diary.exporters.discord import DiscordExporter
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_urlopen.return_value = mock_resp

        exp = DiscordExporter({"webhook_url": "https://discord.com/api/webhooks/123/abc"})
        result = exp.export(SAMPLE_ENTRY)
        assert result is True
        mock_urlopen.assert_called_once()

    @patch("urllib.request.urlopen")
    def test_export_success_204(self, mock_urlopen):
        """Discord webhooks commonly return 204 No Content on success."""
        from claude_diary.exporters.discord import DiscordExporter
        mock_resp = MagicMock()
        mock_resp.status = 204
        mock_urlopen.return_value = mock_resp

        exp = DiscordExporter({"webhook_url": "https://discord.com/api/webhooks/123/abc"})
        result = exp.export(SAMPLE_ENTRY)
        assert result is True

    @patch("urllib.request.urlopen")
    def test_export_network_failure(self, mock_urlopen):
        from claude_diary.exporters.discord import DiscordExporter
        mock_urlopen.side_effect = Exception("Connection refused")

        exp = DiscordExporter({"webhook_url": "https://discord.com/api/webhooks/123/abc"})
        result = exp.export(SAMPLE_ENTRY)
        assert result is False

    @patch("urllib.request.urlopen")
    def test_export_payload_structure(self, mock_urlopen):
        """Verify the JSON payload sent to Discord contains proper embed fields."""
        from claude_diary.exporters.discord import DiscordExporter
        mock_resp = MagicMock()
        mock_resp.status = 204
        mock_urlopen.return_value = mock_resp

        exp = DiscordExporter({"webhook_url": "https://discord.com/api/webhooks/123/abc"})
        exp.export(RICH_ENTRY)

        # Inspect the Request object passed to urlopen
        req = mock_urlopen.call_args[0][0]
        payload = json.loads(req.data.decode("utf-8"))
        assert "embeds" in payload
        embed = payload["embeds"][0]
        assert "test-app" in embed["title"]
        field_names = [f["name"] for f in embed["fields"]]
        assert "Categories" in field_names
        assert "Summary" in field_names
        assert "Code Stats" in field_names
        assert "Git" in field_names

    @patch("urllib.request.urlopen")
    def test_export_minimal_entry(self, mock_urlopen):
        """Export with minimal data (no categories, no code_stats, no git)."""
        from claude_diary.exporters.discord import DiscordExporter
        mock_resp = MagicMock()
        mock_resp.status = 204
        mock_urlopen.return_value = mock_resp

        minimal = {"date": "2026-01-01", "project": "min"}
        exp = DiscordExporter({"webhook_url": "https://discord.com/api/webhooks/123/abc"})
        result = exp.export(minimal)
        assert result is True

        req = mock_urlopen.call_args[0][0]
        payload = json.loads(req.data.decode("utf-8"))
        embed = payload["embeds"][0]
        field_names = [f["name"] for f in embed["fields"]]
        # Should not have Code Stats or Git fields for minimal entry
        assert "Code Stats" not in field_names
        assert "Git" not in field_names


# ── Notion Exporter Tests ──────────────────────────────────────────────────

class TestNotionExporter:
    def test_validate_config_valid(self):
        from claude_diary.exporters.notion import NotionExporter
        exp = NotionExporter({"api_token": "secret_abc", "database_id": "db123"})
        assert exp.validate_config() is True

    def test_validate_config_missing_token(self):
        from claude_diary.exporters.notion import NotionExporter
        assert not NotionExporter({"database_id": "db123"}).validate_config()

    def test_validate_config_missing_database(self):
        from claude_diary.exporters.notion import NotionExporter
        assert not NotionExporter({"api_token": "secret_abc"}).validate_config()

    def test_validate_config_empty(self):
        from claude_diary.exporters.notion import NotionExporter
        assert not NotionExporter({}).validate_config()

    def test_export_success(self):
        from claude_diary.exporters.notion import NotionExporter
        mock_requests = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_requests.post.return_value = mock_resp

        with patch.dict("sys.modules", {"requests": mock_requests}):
            exp = NotionExporter({"api_token": "secret_abc", "database_id": "db123"})
            result = exp.export(SAMPLE_ENTRY)
            assert result is True
            mock_requests.post.assert_called_once()

            # Verify the API call — requests.post(url, headers=..., json=..., timeout=...)
            call_kwargs = mock_requests.post.call_args
            assert call_kwargs[0][0] == "https://api.notion.com/v1/pages"
            headers = call_kwargs[1]["headers"]
            assert headers["Authorization"] == "Bearer secret_abc"
            assert headers["Notion-Version"] == "2022-06-28"

    def test_export_failure_status(self):
        from claude_diary.exporters.notion import NotionExporter
        mock_requests = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_requests.post.return_value = mock_resp

        with patch.dict("sys.modules", {"requests": mock_requests}):
            exp = NotionExporter({"api_token": "secret_abc", "database_id": "db123"})
            result = exp.export(SAMPLE_ENTRY)
            assert result is False

    def test_export_with_team_member(self):
        """Team mode: Author field should be included in properties."""
        from claude_diary.exporters.notion import NotionExporter
        mock_requests = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_requests.post.return_value = mock_resp

        with patch.dict("sys.modules", {"requests": mock_requests}):
            exp = NotionExporter({
                "api_token": "secret_abc",
                "database_id": "db123",
                "member_name": "alice",
            })
            exp.export(SAMPLE_ENTRY)

            call_kwargs = mock_requests.post.call_args
            properties = call_kwargs[1]["json"]["properties"]
            assert "Author" in properties
            assert properties["Author"]["select"]["name"] == "alice"

    def test_export_properties_structure(self):
        """Verify properties include git commits and code stats when present."""
        from claude_diary.exporters.notion import NotionExporter
        mock_requests = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_requests.post.return_value = mock_resp

        with patch.dict("sys.modules", {"requests": mock_requests}):
            exp = NotionExporter({"api_token": "secret_abc", "database_id": "db123"})
            exp.export(RICH_ENTRY)

            call_kwargs = mock_requests.post.call_args
            properties = call_kwargs[1]["json"]["properties"]
            assert "Git Commits" in properties
            assert "Lines Changed" in properties
            assert properties["Lines Changed"]["number"] == 60  # 50 added + 10 deleted

    def test_export_requests_not_installed(self):
        """When requests is not installed, export should return False."""
        from claude_diary.exporters.notion import NotionExporter
        exp = NotionExporter({"api_token": "secret_abc", "database_id": "db123"})
        with patch.dict("sys.modules", {"requests": None}):
            # Force ImportError by making import fail
            import builtins
            original_import = builtins.__import__

            def mock_import(name, *args, **kwargs):
                if name == "requests":
                    raise ImportError("No module named 'requests'")
                return original_import(name, *args, **kwargs)

            with patch("builtins.__import__", side_effect=mock_import):
                result = exp.export(SAMPLE_ENTRY)
                assert result is False


# ── GitHub Exporter Tests ──────────────────────────────────────────────────

class TestGithubExporter:
    def test_validate_config_repo_mode_with_repo(self):
        from claude_diary.exporters.github import GithubExporter
        exp = GithubExporter({"mode": "repo", "repo": "user/diary"})
        assert exp.validate_config() is True

    def test_validate_config_repo_mode_with_local_path(self):
        from claude_diary.exporters.github import GithubExporter
        exp = GithubExporter({"mode": "repo", "local_path": "/tmp/diary"})
        assert exp.validate_config() is True

    def test_validate_config_repo_mode_missing(self):
        from claude_diary.exporters.github import GithubExporter
        exp = GithubExporter({"mode": "repo"})
        assert exp.validate_config() is False

    def test_validate_config_wiki_mode(self):
        from claude_diary.exporters.github import GithubExporter
        assert GithubExporter({"mode": "wiki", "repo": "user/diary"}).validate_config() is True
        assert GithubExporter({"mode": "wiki"}).validate_config() is False

    def test_validate_config_issue_mode(self):
        from claude_diary.exporters.github import GithubExporter
        assert GithubExporter({"mode": "issue", "repo": "user/diary"}).validate_config() is True
        assert GithubExporter({"mode": "issue"}).validate_config() is False

    def test_validate_config_default_mode_is_repo(self):
        from claude_diary.exporters.github import GithubExporter
        exp = GithubExporter({"local_path": "/tmp/diary"})
        assert exp.validate_config() is True

    @patch("subprocess.run")
    @patch("claude_diary.exporters.github.os.path.isdir", return_value=True)
    @patch("claude_diary.exporters.github.os.path.exists", return_value=False)
    @patch("claude_diary.exporters.github.os.makedirs")
    @patch("builtins.open", new_callable=MagicMock)
    @patch("claude_diary.config.load_config", return_value={"lang": "ko"})
    @patch("claude_diary.formatter.format_entry", return_value="# Diary Entry\n")
    @patch("claude_diary.formatter.format_daily_header", return_value="# Daily Header\n")
    def test_export_repo_success(self, mock_header, mock_format, mock_load,
                                  mock_open, mock_makedirs, mock_exists,
                                  mock_isdir, mock_subprocess):
        from claude_diary.exporters.github import GithubExporter
        mock_subprocess.return_value = MagicMock(returncode=0)

        exp = GithubExporter({"mode": "repo", "local_path": "/tmp/diary", "member_name": "dev1"})
        result = exp.export(SAMPLE_ENTRY)
        assert result is True
        # Should have called git add, commit, push (3 subprocess calls)
        assert mock_subprocess.call_count == 3

    def test_export_repo_no_local_path(self):
        from claude_diary.exporters.github import GithubExporter
        exp = GithubExporter({"mode": "repo"})
        result = exp.export(SAMPLE_ENTRY)
        assert result is False

    def test_export_repo_nonexistent_path(self):
        from claude_diary.exporters.github import GithubExporter
        exp = GithubExporter({"mode": "repo", "local_path": "/nonexistent/path/xyz"})
        result = exp.export(SAMPLE_ENTRY)
        assert result is False

    def test_export_wiki_not_implemented(self):
        from claude_diary.exporters.github import GithubExporter
        exp = GithubExporter({"mode": "wiki", "repo": "user/diary"})
        result = exp.export(SAMPLE_ENTRY)
        assert result is False

    def test_export_issue_not_implemented(self):
        from claude_diary.exporters.github import GithubExporter
        exp = GithubExporter({"mode": "issue", "repo": "user/diary"})
        result = exp.export(SAMPLE_ENTRY)
        assert result is False

    def test_export_unknown_mode_returns_false(self):
        from claude_diary.exporters.github import GithubExporter
        exp = GithubExporter({"mode": "unknown", "repo": "user/diary"})
        result = exp.export(SAMPLE_ENTRY)
        assert result is False

    @patch("subprocess.run")
    @patch("claude_diary.exporters.github.os.path.isdir", return_value=True)
    @patch("claude_diary.exporters.github.os.path.exists", return_value=False)
    @patch("claude_diary.exporters.github.os.makedirs")
    @patch("builtins.open", new_callable=MagicMock)
    @patch("claude_diary.config.load_config", return_value={"lang": "ko"})
    @patch("claude_diary.formatter.format_entry", return_value="# Entry\n")
    @patch("claude_diary.formatter.format_daily_header", return_value="# Header\n")
    def test_export_repo_git_push_failure(self, mock_header, mock_format, mock_load,
                                          mock_open, mock_makedirs, mock_exists,
                                          mock_isdir, mock_subprocess):
        """When git push fails, export should return False."""
        from claude_diary.exporters.github import GithubExporter
        # git add and commit succeed, push fails
        mock_subprocess.side_effect = [
            MagicMock(returncode=0),  # git add
            MagicMock(returncode=0),  # git commit
            MagicMock(returncode=1),  # git push fails
        ]

        exp = GithubExporter({"mode": "repo", "local_path": "/tmp/diary"})
        result = exp.export(SAMPLE_ENTRY)
        assert result is False


# ── Slack Exporter Tests (Extended) ────────────────────────────────────────

class TestSlackExporterExtended:
    @patch("urllib.request.urlopen")
    def test_export_network_failure(self, mock_urlopen):
        from claude_diary.exporters.slack import SlackExporter
        mock_urlopen.side_effect = Exception("Timeout")
        exp = SlackExporter({"webhook_url": "https://hooks.slack.com/test"})
        result = exp.export(SAMPLE_ENTRY)
        assert result is False

    @patch("urllib.request.urlopen")
    def test_export_payload_contains_project(self, mock_urlopen):
        """Verify the payload text includes project name and date."""
        from claude_diary.exporters.slack import SlackExporter
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_urlopen.return_value = mock_resp

        exp = SlackExporter({"webhook_url": "https://hooks.slack.com/test"})
        exp.export(SAMPLE_ENTRY)

        req = mock_urlopen.call_args[0][0]
        payload = json.loads(req.data.decode("utf-8"))
        assert "test-app" in payload["text"]
        assert "2026-03-17" in payload["text"]

    @patch("urllib.request.urlopen")
    def test_export_rich_entry_includes_code_stats(self, mock_urlopen):
        """Code stats and git info should appear in Slack message."""
        from claude_diary.exporters.slack import SlackExporter
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_urlopen.return_value = mock_resp

        exp = SlackExporter({"webhook_url": "https://hooks.slack.com/test"})
        exp.export(RICH_ENTRY)

        req = mock_urlopen.call_args[0][0]
        payload = json.loads(req.data.decode("utf-8"))
        text = payload["text"]
        assert "+50" in text
        assert "-10" in text
        assert "feat/login" in text
        assert "2 commits" in text

    @patch("urllib.request.urlopen")
    def test_export_no_summary_fallback(self, mock_urlopen):
        """When no hints or prompts exist, should use 'No summary'."""
        from claude_diary.exporters.slack import SlackExporter
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_urlopen.return_value = mock_resp

        entry = {"date": "2026-01-01", "project": "empty", "categories": []}
        exp = SlackExporter({"webhook_url": "https://hooks.slack.com/test"})
        exp.export(entry)

        req = mock_urlopen.call_args[0][0]
        payload = json.loads(req.data.decode("utf-8"))
        assert "No summary" in payload["text"]

    @patch("urllib.request.urlopen")
    def test_export_non_200_returns_false(self, mock_urlopen):
        """Non-200 status should return False."""
        from claude_diary.exporters.slack import SlackExporter
        mock_resp = MagicMock()
        mock_resp.status = 500
        mock_urlopen.return_value = mock_resp

        exp = SlackExporter({"webhook_url": "https://hooks.slack.com/test"})
        result = exp.export(SAMPLE_ENTRY)
        assert result is False


# ── Loader: retry_queued Tests ─────────────────────────────────────────────

class TestRetryQueued:
    def test_no_queue_file(self, tmp_path):
        """When no queue file exists, retry_queued should silently return."""
        config = {"exporters": {}}
        retry_queued(config, str(tmp_path))
        # Should not raise, no queue file created
        assert not (tmp_path / ".export_queue.json").exists()

    def test_empty_queue(self, tmp_path):
        """When queue file is empty list, it should be removed."""
        queue_path = tmp_path / ".export_queue.json"
        queue_path.write_text("[]", encoding="utf-8")

        config = {"exporters": {}}
        retry_queued(config, str(tmp_path))
        # Empty queue returns early before processing
        assert queue_path.exists()  # empty list triggers early return

    def test_retry_success_removes_item(self, tmp_path):
        """Successful retry should remove the item from the queue."""
        queue_path = tmp_path / ".export_queue.json"
        queue_data = [
            {
                "timestamp": "2026-03-17T10:00:00",
                "exporter": "slack",
                "entry_data": {"date": "2026-03-17", "project": "test"},
                "error": "timeout",
                "retries": 0,
            }
        ]
        queue_path.write_text(json.dumps(queue_data), encoding="utf-8")

        # Mock the slack exporter to succeed
        mock_exporter = MagicMock()
        mock_exporter.export.return_value = True
        mock_exporter.validate_config.return_value = True

        with patch("claude_diary.exporters.loader.load_exporters", return_value=[("slack", mock_exporter)]):
            retry_queued({}, str(tmp_path))

        # Queue file should be removed since all items succeeded
        assert not queue_path.exists()

    def test_retry_failure_increments_retry_count(self, tmp_path):
        """Failed retry should increment retries and keep item in queue."""
        queue_path = tmp_path / ".export_queue.json"
        queue_data = [
            {
                "timestamp": "2026-03-17T10:00:00",
                "exporter": "slack",
                "entry_data": {"date": "2026-03-17", "project": "test"},
                "error": "timeout",
                "retries": 1,
            }
        ]
        queue_path.write_text(json.dumps(queue_data), encoding="utf-8")

        mock_exporter = MagicMock()
        mock_exporter.export.return_value = False  # Still failing
        mock_exporter.validate_config.return_value = True

        with patch("claude_diary.exporters.loader.load_exporters", return_value=[("slack", mock_exporter)]):
            retry_queued({}, str(tmp_path))

        remaining = json.loads(queue_path.read_text(encoding="utf-8"))
        assert len(remaining) == 1
        assert remaining[0]["retries"] == 2

    def test_retry_max_retries_drops_item(self, tmp_path):
        """Items with retries >= 3 should be dropped from the queue."""
        queue_path = tmp_path / ".export_queue.json"
        queue_data = [
            {
                "timestamp": "2026-03-17T10:00:00",
                "exporter": "slack",
                "entry_data": {"date": "2026-03-17", "project": "test"},
                "error": "timeout",
                "retries": 3,  # Already at max
            }
        ]
        queue_path.write_text(json.dumps(queue_data), encoding="utf-8")

        with patch("claude_diary.exporters.loader.load_exporters", return_value=[]):
            retry_queued({}, str(tmp_path))

        # Queue file removed since item was dropped
        assert not queue_path.exists()

    def test_retry_exception_increments_retry_count(self, tmp_path):
        """When export raises an exception, retries should increment."""
        queue_path = tmp_path / ".export_queue.json"
        queue_data = [
            {
                "timestamp": "2026-03-17T10:00:00",
                "exporter": "slack",
                "entry_data": {"date": "2026-03-17", "project": "test"},
                "error": "timeout",
                "retries": 0,
            }
        ]
        queue_path.write_text(json.dumps(queue_data), encoding="utf-8")

        mock_exporter = MagicMock()
        mock_exporter.export.side_effect = Exception("Network error")
        mock_exporter.validate_config.return_value = True

        with patch("claude_diary.exporters.loader.load_exporters", return_value=[("slack", mock_exporter)]):
            retry_queued({}, str(tmp_path))

        remaining = json.loads(queue_path.read_text(encoding="utf-8"))
        assert len(remaining) == 1
        assert remaining[0]["retries"] == 1

    def test_retry_unknown_exporter_kept_in_queue(self, tmp_path):
        """Items for exporters not in config should remain in queue."""
        queue_path = tmp_path / ".export_queue.json"
        queue_data = [
            {
                "timestamp": "2026-03-17T10:00:00",
                "exporter": "notion",
                "entry_data": {"date": "2026-03-17", "project": "test"},
                "error": "timeout",
                "retries": 0,
            }
        ]
        queue_path.write_text(json.dumps(queue_data), encoding="utf-8")

        # load_exporters returns empty — notion not configured
        with patch("claude_diary.exporters.loader.load_exporters", return_value=[]):
            retry_queued({}, str(tmp_path))

        remaining = json.loads(queue_path.read_text(encoding="utf-8"))
        assert len(remaining) == 1
        assert remaining[0]["exporter"] == "notion"
        assert remaining[0]["retries"] == 0  # not incremented

    def test_retry_mixed_queue(self, tmp_path):
        """Queue with multiple items: success, failure, and max-retry."""
        queue_path = tmp_path / ".export_queue.json"
        queue_data = [
            {
                "timestamp": "2026-03-17T10:00:00",
                "exporter": "slack",
                "entry_data": {"date": "2026-03-17", "project": "test1"},
                "error": "timeout",
                "retries": 0,
            },
            {
                "timestamp": "2026-03-17T11:00:00",
                "exporter": "discord",
                "entry_data": {"date": "2026-03-17", "project": "test2"},
                "error": "500",
                "retries": 3,  # max retries — will be dropped
            },
            {
                "timestamp": "2026-03-17T12:00:00",
                "exporter": "slack",
                "entry_data": {"date": "2026-03-17", "project": "test3"},
                "error": "timeout",
                "retries": 1,
            },
        ]
        queue_path.write_text(json.dumps(queue_data), encoding="utf-8")

        mock_exporter = MagicMock()
        # First call succeeds (test1), second call fails (test3)
        mock_exporter.export.side_effect = [True, False]
        mock_exporter.validate_config.return_value = True

        with patch("claude_diary.exporters.loader.load_exporters", return_value=[("slack", mock_exporter)]):
            retry_queued({}, str(tmp_path))

        remaining = json.loads(queue_path.read_text(encoding="utf-8"))
        # test1 succeeded (removed), discord dropped (max retries), test3 failed (kept with retries=2)
        assert len(remaining) == 1
        assert remaining[0]["entry_data"]["project"] == "test3"
        assert remaining[0]["retries"] == 2

    def test_corrupt_queue_file(self, tmp_path):
        """Corrupt queue file should not raise; function returns silently."""
        queue_path = tmp_path / ".export_queue.json"
        queue_path.write_text("not valid json {{{", encoding="utf-8")

        config = {"exporters": {}}
        retry_queued(config, str(tmp_path))
        # Should not raise


# ── Loader: run_exporters extended tests ───────────────────────────────────

class TestRunExportersExtended:
    def test_export_returns_false_queued(self, tmp_path):
        """When export returns False, it should be added to the failed list and queued."""
        mock_exp = MagicMock()
        mock_exp.export.return_value = False
        result = run_exporters([("slack", mock_exp)], SAMPLE_ENTRY, diary_dir=str(tmp_path))
        assert "slack" in result["failed"]
        assert result["success"] == []
        # Check queue file was created
        queue_path = tmp_path / ".export_queue.json"
        assert queue_path.exists()
        queue = json.loads(queue_path.read_text(encoding="utf-8"))
        assert len(queue) == 1
        assert queue[0]["exporter"] == "slack"

    def test_multiple_exporters_mixed(self, tmp_path):
        """Multiple exporters: one succeeds, one fails."""
        mock_success = MagicMock()
        mock_success.export.return_value = True
        mock_fail = MagicMock()
        mock_fail.export.return_value = False

        result = run_exporters(
            [("slack", mock_success), ("discord", mock_fail)],
            SAMPLE_ENTRY,
            diary_dir=str(tmp_path),
        )
        assert "slack" in result["success"]
        assert "discord" in result["failed"]
