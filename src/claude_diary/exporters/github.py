"""GitHub exporter — pushes diary entries to a GitHub repository.

Supports three modes:
- repo: Auto-commit to a diary-dedicated repo
- wiki: Add to project Wiki (placeholder)
- issue: Add as issue comment (placeholder)

Uses 'gh' CLI for authentication (no token storage needed if gh is logged in).
"""

import os
import subprocess
import sys

from claude_diary.exporters.base import BaseExporter


class GithubExporter(BaseExporter):
    TRUST_LEVEL = "official"

    def validate_config(self):
        mode = self.config.get("mode", "repo")
        if mode == "repo":
            return bool(self.config.get("repo")) or bool(self.config.get("local_path"))
        return bool(self.config.get("repo"))

    def export(self, entry_data):
        mode = self.config.get("mode", "repo")

        if mode == "repo":
            return self._export_repo(entry_data)
        elif mode == "wiki":
            return self._export_wiki(entry_data)
        elif mode == "issue":
            return self._export_issue(entry_data)
        return False

    def _export_repo(self, entry_data):
        """Commit diary entry to a local git repo and push."""
        local_path = self.config.get("local_path", "")
        if not local_path:
            # Clone repo if not yet cloned
            return False

        local_path = os.path.expanduser(local_path)
        if not os.path.isdir(local_path):
            return False

        date = entry_data.get("date", "")
        project = entry_data.get("project", "unknown")

        # Determine member subdirectory
        member = self.config.get("member_name", "default")
        member_dir = os.path.join(local_path, "members", member)
        os.makedirs(member_dir, exist_ok=True)

        # Build entry content
        from claude_diary.formatter import format_entry
        from claude_diary.config import load_config
        config = load_config()
        lang = config.get("lang", "ko")
        entry_text = format_entry(entry_data, lang)

        # Append to daily file
        diary_file = os.path.join(member_dir, "%s.md" % date)
        mode = "a" if os.path.exists(diary_file) else "w"
        with open(diary_file, mode, encoding="utf-8") as f:
            if mode == "w":
                from claude_diary.formatter import format_daily_header
                f.write(format_daily_header(date, lang))
            f.write(entry_text)

        # Git add + commit + push
        try:
            subprocess.run(
                ["git", "add", diary_file],
                cwd=local_path, capture_output=True, timeout=10
            )
            subprocess.run(
                ["git", "commit", "-m", "diary: %s %s (%s)" % (date, project, member)],
                cwd=local_path, capture_output=True, timeout=10
            )
            result = subprocess.run(
                ["git", "push"],
                cwd=local_path, capture_output=True, timeout=30
            )
            return result.returncode == 0
        except Exception as e:
            sys.stderr.write("[diary] GitHub repo push failed: %s\n" % str(e))
            return False

    def _export_wiki(self, entry_data):
        """Placeholder for GitHub Wiki export."""
        sys.stderr.write("[diary] GitHub Wiki export not yet implemented\n")
        return False

    def _export_issue(self, entry_data):
        """Placeholder for GitHub Issue comment export."""
        sys.stderr.write("[diary] GitHub Issue export not yet implemented\n")
        return False
