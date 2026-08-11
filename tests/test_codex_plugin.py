"""Tests for Codex plugin and skill packaging artifacts."""

import json
import re
from pathlib import Path

import pytest

from claude_diary import __version__
from claude_diary.cli.setup import CODEX_SKILLS, HOOK_COMMAND


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("skill_name", sorted(CODEX_SKILLS))
def test_shipped_skill_matches_the_installed_copy(skill_name):
    """`skills/` and the `setup.py` constants are two copies of one contract.

    The Codex plugin marketplace ships `skills/<name>/SKILL.md`, while
    `agent-diary install --codex-only` writes the embedded constant to
    `~/.codex/skills/`. A change applied to only one of them means two agents
    following two different contracts, with nothing at runtime to notice.
    """
    shipped = (ROOT / "skills" / skill_name / "SKILL.md").read_text(encoding="utf-8")
    installed = CODEX_SKILLS[skill_name][0]
    assert shipped == installed, (
        "skills/%s/SKILL.md is out of sync with setup.py — update both." % skill_name
    )


def _pyproject_version():
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    assert match is not None
    return match.group(1)


def test_codex_plugin_manifest_points_to_skills():
    manifest_path = ROOT / ".codex-plugin" / "plugin.json"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert data["name"] == "agent-diary"
    assert data["homepage"] == "https://github.com/solzip/agent-diary"
    assert data["repository"] == "https://github.com/solzip/agent-diary"
    assert data["skills"] == "./skills/"
    assert data["interface"]["displayName"] == "Agent Diary"
    assert "hooks" not in data


def test_claude_plugin_manifest_uses_current_repository():
    manifest_path = ROOT / ".claude-plugin" / "plugin.json"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert data["name"] == "agent-diary"
    assert data["repository"] == "https://github.com/solzip/agent-diary"
    assert data["hooks"] == "hooks.json"
    assert "claude-code-hooks-diary" not in manifest_path.read_text(encoding="utf-8")


def test_distribution_versions_match_package_version():
    codex = json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
    claude = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))

    assert _pyproject_version() == __version__
    assert codex["version"] == __version__
    assert claude["version"] == __version__


def test_claude_plugin_hook_uses_installer_command():
    hooks_path = ROOT / ".claude-plugin" / "hooks.json"
    data = json.loads(hooks_path.read_text(encoding="utf-8"))
    command = data["hooks"]["Stop"][0]["hooks"][0]["command"]

    assert command == HOOK_COMMAND
    assert "PYTHONIOENCODING=" not in command


def test_english_readme_uses_current_install_flow():
    text = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "working-diary-system" not in text
    assert "install.sh" not in text
    assert "agent-diary init --codex-only" in text
    assert "agent-diary install --force --codex-only" in text
    assert "Apply or refresh Codex setup:\n\n```bash\nagent-diary install --force --codex-only" in text
    assert 'pip install "agent-diary[notion]"' in text
    assert "stores the Notion token and root page ID" in text
    assert "API tokens, webhook URLs, and root page IDs are stored in this local config" in text


def test_korean_readme_uses_codex_only_install_flow():
    text = (ROOT / "README.ko.md").read_text(encoding="utf-8")

    assert "agent-diary init --codex-only" in text
    assert "agent-diary install --force --codex-only" in text
    assert "Codex 적용 또는 갱신:\n\n```bash\nagent-diary install --force --codex-only" in text
    assert "현재 구현에는 Codex만 단독으로 적용하는 별도 명령이 없습니다" not in text


def test_security_policy_matches_current_config_behavior():
    text = (ROOT / "SECURITY.md").read_text(encoding="utf-8")

    assert "Does NOT modify your source code or Claude Code configuration" not in text
    assert "Registers or refreshes Claude Code hook/slash command settings" in text
    assert "Codex-only setup does not modify Claude Code settings" in text
    assert "unless you explicitly enable an exporter" in text
    assert "Stores exporter credentials such as API tokens and webhook URLs in local config" in text
    assert "Does NOT transmit stored exporter credentials except" in text
    assert "Does NOT store or transmit API tokens" not in text


def test_codex_skills_exist_and_cover_diary_workflows():
    diary = ROOT / "skills" / "diary" / "SKILL.md"
    notion = ROOT / "skills" / "diary-notion" / "SKILL.md"

    diary_text = diary.read_text(encoding="utf-8")
    notion_text = notion.read_text(encoding="utf-8")

    assert "agent-diary write --input" in diary_text
    assert "agent-diary write --input" in diary_text
    assert "agent-diary diary-notion push" in notion_text
    assert '"schema_version": 2' in notion_text
    assert '"purpose": "Feature"' in notion_text
    assert '"summary": {' in notion_text
    assert '"outcomes": ["..."]' in notion_text
    assert '"work": {' in notion_text
    assert '"context": "..."' in notion_text
    assert '"appendix": {' in notion_text
    assert '"key_changes": ["..."]' in notion_text
    assert '"implementation_notes": ["..."]' in notion_text
    assert '"verification": ["..."]' in notion_text
    assert '"artifacts": [' in notion_text
    assert '"risks": ["..."]' in notion_text
    assert '"support_needed": ["..."]' in notion_text
    # No concrete work_period in the example: agents copy example dates, and a
    # single-day session is supposed to omit the field entirely.
    assert '"work_period"' not in notion_text
    assert '"priority": "P1"' in notion_text
    assert '"next_action": "..."' in notion_text
    assert '"blocked": false' in notion_text
    assert '"block_reason": ""' in notion_text
    assert '"carryover": false' in notion_text
    assert '"review_status"' not in notion_text
    assert '"last_reviewed"' not in notion_text
    assert '"parent_index": null' in notion_text
    assert "Exclude full diffs" in notion_text
    assert "in Korean" in notion_text
    assert "Notion task database record" in notion_text
    assert "Current Implementation Contract" in notion_text
    assert "schema v8" in notion_text
    assert ".agent-diary/runs" in notion_text
    assert "--preview-file" in notion_text
    assert "native sub-items" in notion_text
    assert "Never write `\"unknown\"` as `project`" in notion_text
    assert "Use `Depends On` only for prerequisite links" in notion_text


def test_codex_skill_metadata_exists():
    assert (ROOT / "skills" / "diary" / "agents" / "openai.yaml").exists()
    assert (ROOT / "skills" / "diary-notion" / "agents" / "openai.yaml").exists()
