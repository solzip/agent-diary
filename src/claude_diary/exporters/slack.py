"""Slack exporter — sends diary summary to Slack via Incoming Webhook."""

import json
import urllib.request

from claude_diary.exporters.base import BaseExporter


class SlackExporter(BaseExporter):
    TRUST_LEVEL = "official"

    def validate_config(self):
        url = self.config.get("webhook_url", "")
        return url.startswith("https://hooks.slack.com/")

    def export(self, entry_data):
        url = self.config["webhook_url"]

        project = entry_data.get("project", "unknown")
        categories = entry_data.get("categories", [])
        prompts = entry_data.get("user_prompts", [])
        hints = entry_data.get("summary_hints", [])
        code_stats = entry_data.get("code_stats") or {}
        git_info = entry_data.get("git_info") or {}

        cat_str = ", ".join(categories) if categories else "uncategorized"
        summary = hints[0] if hints else (prompts[0][:100] if prompts else "No summary")

        lines = []
        lines.append("*%s %s* | `%s`" % (
            "\U0001f4d3", project, entry_data.get("date", "")
        ))
        lines.append("\U0001f3f7\ufe0f %s" % cat_str)
        lines.append("\U0001f4cb %s" % summary)

        added = code_stats.get("added", 0)
        deleted = code_stats.get("deleted", 0)
        files = code_stats.get("files", 0)
        if added > 0 or deleted > 0:
            lines.append("\U0001f4ca +%d / -%d lines (%d files)" % (added, deleted, files))

        branch = git_info.get("branch", "")
        commits = git_info.get("commits", [])
        if branch and commits:
            lines.append("\U0001f500 %d commits on `%s`" % (len(commits), branch))

        payload = json.dumps({"text": "\n".join(lines)}).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            resp = urllib.request.urlopen(req, timeout=10)
            return resp.status == 200
        except Exception:
            return False
