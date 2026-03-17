"""Obsidian exporter — copies diary entries to an Obsidian vault."""

import os
import shutil

from claude_diary.exporters.base import BaseExporter


class ObsidianExporter(BaseExporter):
    TRUST_LEVEL = "official"

    def validate_config(self):
        vault_path = self.config.get("vault_path", "")
        return bool(vault_path) and os.path.isdir(os.path.expanduser(vault_path))

    def export(self, entry_data):
        vault_path = os.path.expanduser(self.config["vault_path"])
        diary_subdir = self.config.get("subfolder", "claude-diary")

        target_dir = os.path.join(vault_path, diary_subdir)
        os.makedirs(target_dir, exist_ok=True)

        date = entry_data.get("date", "")
        if not date:
            return False

        # Build Obsidian-flavored markdown with YAML frontmatter
        project = entry_data.get("project", "unknown")
        categories = entry_data.get("categories", [])
        hints = entry_data.get("summary_hints", [])

        frontmatter = [
            "---",
            "date: %s" % date,
            "project: %s" % project,
            "categories: [%s]" % ", ".join(categories),
            "tags: [claude-diary, %s]" % project,
            "---",
            "",
        ]

        body_lines = []
        body_lines.append("## %s | %s" % (entry_data.get("time", ""), project))
        body_lines.append("")

        if categories:
            body_lines.append("**Categories:** %s" % " ".join("#%s" % c for c in categories))
            body_lines.append("")

        prompts = entry_data.get("user_prompts", [])
        if prompts:
            body_lines.append("### Tasks")
            for p in prompts[:5]:
                short = p.replace("\n", " ").strip()[:150]
                body_lines.append("- %s" % short)
            body_lines.append("")

        if hints:
            body_lines.append("### Summary")
            for h in hints[:5]:
                body_lines.append("- %s" % h)
            body_lines.append("")

        files = entry_data.get("files_created", []) + entry_data.get("files_modified", [])
        if files:
            body_lines.append("### Files")
            for f in files[:15]:
                body_lines.append("- `%s`" % f)
            body_lines.append("")

        content = "\n".join(frontmatter + body_lines)

        # Append to daily note or create new
        target_file = os.path.join(target_dir, "%s.md" % date)
        mode = "a" if os.path.exists(target_file) else "w"
        with open(target_file, mode, encoding="utf-8") as f:
            if mode == "a":
                f.write("\n---\n\n")
            f.write(content)

        return True
