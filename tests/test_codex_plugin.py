"""Tests for Codex plugin and skill packaging artifacts."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_codex_plugin_manifest_points_to_skills():
    manifest_path = ROOT / ".codex-plugin" / "plugin.json"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert data["name"] == "working-diary"
    assert data["skills"] == "./skills/"
    assert data["interface"]["displayName"] == "Working Diary"
    assert "hooks" not in data


def test_codex_skills_exist_and_cover_diary_workflows():
    diary = ROOT / "skills" / "diary" / "SKILL.md"
    notion = ROOT / "skills" / "diary-notion" / "SKILL.md"

    diary_text = diary.read_text(encoding="utf-8")
    notion_text = notion.read_text(encoding="utf-8")

    assert "working-diary write --input" in diary_text
    assert "claude-diary write --input" in diary_text
    assert "working-diary diary-notion push" in notion_text
    assert '"purpose": "Feature"' in notion_text
    assert '"summary_hints": ["..."]' in notion_text
    assert '"key_changes": ["..."]' in notion_text
    assert '"work_context": ["..."]' in notion_text
    assert '"impact": ["..."]' in notion_text
    assert '"code_change_highlights": ["..."]' in notion_text
    assert '"implementation_notes": ["..."]' in notion_text
    assert '"verification": ["..."]' in notion_text
    assert '"risks": ["..."]' in notion_text
    assert '"support_needed": ["..."]' in notion_text
    assert '"work_period": "2026-06-02"' in notion_text
    assert '"priority": "P1"' in notion_text
    assert '"next_action": "..."' in notion_text
    assert '"blocked": false' in notion_text
    assert '"block_reason": ""' in notion_text
    assert '"carryover": false' in notion_text
    assert '"review_status": "Needs Review"' in notion_text
    assert '"last_reviewed": "2026-06-02"' in notion_text
    assert '"parent_index": null' in notion_text
    assert "Exclude full diffs" in notion_text
    assert "in Korean" in notion_text
    assert "Notion task database record" in notion_text
    assert "Current Implementation Contract" in notion_text
    assert "schema v7" in notion_text
    assert "native sub-items" in notion_text
    assert "Never write `\"unknown\"` as `project`" in notion_text
    assert "Use `Depends On` only for prerequisite links" in notion_text


def test_codex_skill_metadata_exists():
    assert (ROOT / "skills" / "diary" / "agents" / "openai.yaml").exists()
    assert (ROOT / "skills" / "diary-notion" / "agents" / "openai.yaml").exists()
