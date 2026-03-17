"""Notion exporter — pushes diary entries to a Notion database.

Requires: pip install requests (optional dependency)
"""

from claude_diary.exporters.base import BaseExporter


class NotionExporter(BaseExporter):
    TRUST_LEVEL = "official"

    def validate_config(self):
        return bool(self.config.get("api_token")) and bool(self.config.get("database_id"))

    def export(self, entry_data):
        try:
            import requests
        except ImportError:
            import sys
            sys.stderr.write("[diary] Notion exporter requires 'requests': pip install requests\n")
            return False

        token = self.config["api_token"]
        db_id = self.config["database_id"]

        # Team mode: add author column
        member_name = self.config.get("member_name", "")

        # Build Notion page properties
        categories = entry_data.get("categories", [])
        prompts = entry_data.get("user_prompts", [])
        hints = entry_data.get("summary_hints", [])
        files_mod = entry_data.get("files_modified", [])
        files_new = entry_data.get("files_created", [])
        git_info = entry_data.get("git_info") or {}
        code_stats = entry_data.get("code_stats") or {}

        properties = {
            "Date": {"date": {"start": entry_data.get("date", "")}},
            "Project": {"select": {"name": entry_data.get("project", "unknown")}},
            "Categories": {"multi_select": [{"name": c} for c in categories[:5]]},
            "Task Requests": {"rich_text": [{"text": {"content": "\n".join(prompts[:3])[:2000]}}]},
            "Files Modified": {"rich_text": [{"text": {"content": "\n".join(files_mod + files_new)[:2000]}}]},
            "Work Summary": {"rich_text": [{"text": {"content": "\n".join(hints[:5])[:2000]}}]},
        }

        # Team mode: add Author column
        if member_name:
            properties["Author"] = {"select": {"name": member_name}}

        # Git info
        commits = git_info.get("commits", [])
        if commits:
            git_text = "Branch: %s\n%s" % (
                git_info.get("branch", ""),
                "\n".join("%s %s" % (c["hash"], c["message"]) for c in commits[:5])
            )
            properties["Git Commits"] = {"rich_text": [{"text": {"content": git_text[:2000]}}]}

        # Code stats
        added = code_stats.get("added", 0)
        deleted = code_stats.get("deleted", 0)
        if added > 0 or deleted > 0:
            properties["Lines Changed"] = {"number": added + deleted}

        resp = requests.post(
            "https://api.notion.com/v1/pages",
            headers={
                "Authorization": "Bearer %s" % token,
                "Content-Type": "application/json",
                "Notion-Version": "2022-06-28",
            },
            json={"parent": {"database_id": db_id}, "properties": properties},
            timeout=10,
        )

        return resp.status_code == 200
