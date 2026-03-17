"""Discord exporter — sends diary summary via Discord Webhook."""

import json
import urllib.request

from claude_diary.exporters.base import BaseExporter


class DiscordExporter(BaseExporter):
    TRUST_LEVEL = "official"

    def validate_config(self):
        url = self.config.get("webhook_url", "")
        return url.startswith("https://discord.com/api/webhooks/")

    def export(self, entry_data):
        url = self.config["webhook_url"]

        project = entry_data.get("project", "unknown")
        date = entry_data.get("date", "")
        categories = entry_data.get("categories", [])
        prompts = entry_data.get("user_prompts", [])
        hints = entry_data.get("summary_hints", [])
        code_stats = entry_data.get("code_stats") or {}
        git_info = entry_data.get("git_info") or {}

        cat_str = ", ".join(categories) if categories else "uncategorized"
        summary = hints[0] if hints else (prompts[0][:100] if prompts else "No summary")

        fields = [
            {"name": "Categories", "value": cat_str, "inline": True},
            {"name": "Summary", "value": summary[:1024], "inline": False},
        ]

        added = code_stats.get("added", 0)
        deleted = code_stats.get("deleted", 0)
        if added > 0 or deleted > 0:
            fields.append({
                "name": "Code Stats",
                "value": "+%d / -%d lines (%d files)" % (added, deleted, code_stats.get("files", 0)),
                "inline": True,
            })

        branch = git_info.get("branch", "")
        commits = git_info.get("commits", [])
        if branch:
            fields.append({
                "name": "Git",
                "value": "%d commits on `%s`" % (len(commits), branch),
                "inline": True,
            })

        embed = {
            "title": "\U0001f4d3 Work Diary — %s" % project,
            "description": date,
            "color": 5814783,  # Blue
            "fields": fields,
        }

        payload = json.dumps({"embeds": [embed]}).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            resp = urllib.request.urlopen(req, timeout=10)
            return resp.status in (200, 204)
        except Exception:
            return False
