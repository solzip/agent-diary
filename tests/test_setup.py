"""Tests for install/uninstall — Stop hook + slash commands."""

import json
import os
from unittest.mock import patch, MagicMock

from claude_diary.cli.setup import (
    SLASH_COMMANDS,
    CODEX_SKILLS,
    DIARY_SLASH_COMMAND,
    DIARY_NOTION_SLASH_COMMAND,
    cmd_install,
    cmd_uninstall,
    _install_slash_command,
    _uninstall_slash_command,
    _install_all_slash_commands,
    _uninstall_all_slash_commands,
    _install_all_codex_skills,
    _uninstall_all_codex_skills,
)


def _patch_home(tmp_path):
    """Force ~/.claude paths to land under tmp_path."""
    return patch.dict(os.environ, {
        "HOME": str(tmp_path),         # POSIX
        "USERPROFILE": str(tmp_path),  # Windows
    })


class TestSlashCommandRegistry:
    def test_both_commands_registered(self):
        assert "diary.md" in SLASH_COMMANDS
        assert "diary-notion.md" in SLASH_COMMANDS

    def test_each_entry_has_content_and_marker(self):
        for filename, entry in SLASH_COMMANDS.items():
            content, marker = entry
            assert content
            assert marker in content, "Marker %r must be findable in %s" % (marker, filename)


class TestCodexSkillRegistry:
    def test_codex_skills_registered(self):
        assert "diary" in CODEX_SKILLS
        assert "diary-notion" in CODEX_SKILLS

    def test_each_skill_has_content_and_marker(self):
        for skill_name, entry in CODEX_SKILLS.items():
            content, marker = entry
            assert content
            assert marker in content, "Marker %r must be findable in %s" % (marker, skill_name)


class TestDiaryNotionInstructions:
    def test_slash_and_codex_skill_request_rich_body_fields(self):
        fields = [
            "summary_hints",
            "key_changes",
            "work_context",
            "work_scope",
            "approach",
            "outcome",
            "impact",
            "code_change_highlights",
            "decisions",
            "implementation_notes",
            "verification",
            "risks",
            "next_steps",
            "support_needed",
            "work_period",
            "parent_index",
            "depends_on_indices",
        ]
        codex_content = CODEX_SKILLS["diary-notion"][0]

        for field in fields:
            assert field in DIARY_NOTION_SLASH_COMMAND
            assert field in codex_content
        assert "full diff" in DIARY_NOTION_SLASH_COMMAND
        assert "formatting-only" in codex_content
        assert "반드시 한국어로 작성" in DIARY_NOTION_SLASH_COMMAND
        assert "Write `title`, `body_intro`" in codex_content
        assert "in Korean" in codex_content
        assert "Notion task database record" in codex_content


class TestInstallSlashCommandSingle:
    def test_creates_file_when_missing(self, tmp_path):
        path = tmp_path / "new-command.md"
        result = _install_slash_command(str(path), "hello content")
        assert result == "installed"
        assert path.read_text(encoding="utf-8") == "hello content"

    def test_preserves_existing_file(self, tmp_path):
        path = tmp_path / "existing.md"
        path.write_text("user customized", encoding="utf-8")
        result = _install_slash_command(str(path), "default content")
        assert result == "already exists"
        assert path.read_text(encoding="utf-8") == "user customized"

    def test_creates_parent_directory(self, tmp_path):
        path = tmp_path / "subdir" / "deep" / "file.md"
        result = _install_slash_command(str(path), "x")
        assert result == "installed"
        assert path.exists()


class TestUninstallSlashCommandSingle:
    def test_removes_when_marker_present(self, tmp_path):
        path = tmp_path / "x.md"
        path.write_text("---\n...!claude-diary write\n", encoding="utf-8")
        result = _uninstall_slash_command(str(path), "claude-diary write")
        assert result == "removed"
        assert not path.exists()

    def test_preserves_when_user_modified(self, tmp_path):
        path = tmp_path / "x.md"
        path.write_text("my custom content", encoding="utf-8")
        result = _uninstall_slash_command(str(path), "claude-diary write")
        assert result == "skipped (modified by user)"
        assert path.exists()

    def test_returns_not_present_when_missing(self, tmp_path):
        path = tmp_path / "nonexistent.md"
        result = _uninstall_slash_command(str(path), "marker")
        assert result == "not present"


class TestInstallForce:
    def test_force_overwrites_when_marker_present(self, tmp_path):
        path = tmp_path / "x.md"
        path.write_text("---\nold content with claude-diary write\n", encoding="utf-8")
        result = _install_slash_command(str(path), "new content with claude-diary write",
                                        marker="claude-diary write", force=True)
        assert result == "overwritten"
        assert "new content" in path.read_text(encoding="utf-8")

    def test_force_preserves_user_modified(self, tmp_path):
        path = tmp_path / "x.md"
        path.write_text("totally custom — no marker", encoding="utf-8")
        result = _install_slash_command(str(path), "new content",
                                        marker="claude-diary write", force=True)
        assert result == "skipped (modified by user)"
        # Original content preserved
        assert path.read_text(encoding="utf-8") == "totally custom — no marker"

    def test_force_creates_when_missing(self, tmp_path):
        path = tmp_path / "new.md"
        result = _install_slash_command(str(path), "fresh", marker="marker", force=True)
        assert result == "installed"

    def test_cmd_install_with_force_refreshes_diary_notion(self, tmp_path):
        commands_dir = tmp_path / ".claude" / "commands"
        commands_dir.mkdir(parents=True)
        (commands_dir / "diary-notion.md").write_text(
            "---\nold instructions claude-diary diary-notion push\n", encoding="utf-8"
        )
        args = MagicMock()
        args.force = True
        with _patch_home(tmp_path):
            cmd_install(args)
        # File overwritten with the new bundled DIARY_NOTION_SLASH_COMMAND
        content = (commands_dir / "diary-notion.md").read_text(encoding="utf-8")
        assert "depends_on_indices" in content


class TestInstallAll:
    def test_installs_both_commands(self, tmp_path):
        with _patch_home(tmp_path):
            results = _install_all_slash_commands()
        assert "diary.md" in results
        assert "diary-notion.md" in results
        # Both files created
        diary = tmp_path / ".claude" / "commands" / "diary.md"
        diary_notion = tmp_path / ".claude" / "commands" / "diary-notion.md"
        assert diary.exists()
        assert diary_notion.exists()
        assert "claude-diary write" in diary.read_text(encoding="utf-8")
        assert "claude-diary diary-notion push" in diary_notion.read_text(encoding="utf-8")

    def test_upgrade_path_keeps_existing_diary(self, tmp_path):
        """If user already has /diary from old install, /diary-notion still gets added."""
        commands_dir = tmp_path / ".claude" / "commands"
        commands_dir.mkdir(parents=True)
        existing_diary = commands_dir / "diary.md"
        existing_diary.write_text("user-customized content", encoding="utf-8")

        with _patch_home(tmp_path):
            results = _install_all_slash_commands()
        assert results["diary.md"][1] == "already exists"
        assert results["diary-notion.md"][1] == "installed"
        # User's diary.md is untouched
        assert existing_diary.read_text(encoding="utf-8") == "user-customized content"


class TestInstallAllCodexSkills:
    def test_installs_codex_skills(self, tmp_path):
        with _patch_home(tmp_path):
            results = _install_all_codex_skills()
        assert "diary" in results
        assert "diary-notion" in results
        diary = tmp_path / ".codex" / "skills" / "diary" / "SKILL.md"
        notion = tmp_path / ".codex" / "skills" / "diary-notion" / "SKILL.md"
        assert diary.exists()
        assert notion.exists()
        assert "working-diary write --input" in diary.read_text(encoding="utf-8")
        assert "working-diary diary-notion push" in notion.read_text(encoding="utf-8")


class TestUninstallAll:
    def test_removes_only_unmodified_files(self, tmp_path):
        commands_dir = tmp_path / ".claude" / "commands"
        commands_dir.mkdir(parents=True)
        ours = commands_dir / "diary.md"
        ours.write_text(DIARY_SLASH_COMMAND, encoding="utf-8")
        notion_modified = commands_dir / "diary-notion.md"
        notion_modified.write_text("totally custom — no marker", encoding="utf-8")

        with _patch_home(tmp_path):
            results = _uninstall_all_slash_commands()

        assert results["diary.md"][1] == "removed"
        assert results["diary-notion.md"][1] == "skipped (modified by user)"
        assert not ours.exists()
        assert notion_modified.exists()

    def test_uninstalls_codex_skills(self, tmp_path):
        with _patch_home(tmp_path):
            _install_all_codex_skills()
            results = _uninstall_all_codex_skills()

        assert results["diary"][1] == "removed"
        assert results["diary-notion"][1] == "removed"
        assert not (tmp_path / ".codex" / "skills" / "diary" / "SKILL.md").exists()


class TestCmdInstall:
    def test_writes_hook_and_both_slashes_into_empty_settings(self, tmp_path, capsys):
        settings_path = tmp_path / ".claude" / "settings.json"
        with _patch_home(tmp_path):
            cmd_install(MagicMock())

        # Hook registered
        assert settings_path.exists()
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
        stop_hooks = settings["hooks"]["Stop"]
        assert any(
            "claude_diary.hook" in h["command"]
            for group in stop_hooks for h in group["hooks"]
        )
        # Both slash commands present
        assert (tmp_path / ".claude" / "commands" / "diary.md").exists()
        assert (tmp_path / ".claude" / "commands" / "diary-notion.md").exists()

    def test_install_with_codex_writes_skills(self, tmp_path):
        args = MagicMock()
        args.force = False
        args.codex = True
        with _patch_home(tmp_path):
            cmd_install(args)

        assert (tmp_path / ".codex" / "skills" / "diary" / "SKILL.md").exists()
        assert (tmp_path / ".codex" / "skills" / "diary-notion" / "SKILL.md").exists()

    def test_idempotent_when_hook_already_present(self, tmp_path):
        settings_path = tmp_path / ".claude" / "settings.json"
        settings_path.parent.mkdir(parents=True)
        settings_path.write_text(json.dumps({
            "hooks": {"Stop": [{"hooks": [{"type": "command",
                                            "command": "python -m claude_diary.hook"}]}]}
        }), encoding="utf-8")

        with _patch_home(tmp_path):
            cmd_install(MagicMock())

        after = json.loads(settings_path.read_text(encoding="utf-8"))
        # No duplicate group added
        stop = after["hooks"]["Stop"]
        diary_hooks = [
            h for group in stop for h in group["hooks"]
            if "claude_diary.hook" in h["command"]
        ]
        assert len(diary_hooks) == 1


class TestCmdUninstall:
    def test_removes_hook_and_both_slashes(self, tmp_path):
        # Set up an installed state
        with _patch_home(tmp_path):
            cmd_install(MagicMock())

        # Now uninstall
        with _patch_home(tmp_path):
            cmd_uninstall(MagicMock())

        settings_path = tmp_path / ".claude" / "settings.json"
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
        assert "hooks" not in settings  # cleaned up
        assert not (tmp_path / ".claude" / "commands" / "diary.md").exists()
        assert not (tmp_path / ".claude" / "commands" / "diary-notion.md").exists()

    def test_no_hook_still_cleans_unmodified_slashes(self, tmp_path):
        commands_dir = tmp_path / ".claude" / "commands"
        commands_dir.mkdir(parents=True)
        (commands_dir / "diary.md").write_text(DIARY_SLASH_COMMAND, encoding="utf-8")

        with _patch_home(tmp_path):
            cmd_uninstall(MagicMock())
        # Still gets cleaned up
        assert not (commands_dir / "diary.md").exists()

    def test_uninstall_with_codex_removes_skills(self, tmp_path):
        args = MagicMock()
        args.force = False
        args.codex = True
        with _patch_home(tmp_path):
            cmd_install(args)
            cmd_uninstall(args)

        assert not (tmp_path / ".codex" / "skills" / "diary" / "SKILL.md").exists()
        assert not (tmp_path / ".codex" / "skills" / "diary-notion" / "SKILL.md").exists()
