"""Gitmoji on commit lines — opt-in, and only on commit lines."""

from claude_diary.formatter import GITMOJI, commit_gitmoji, format_entry


def _entry(message):
    return {
        "time": "14:30:15",
        "project": "my-app",
        "categories": ["docs"],
        "user_prompts": ["write it up"],
        "commands_run": ["pytest -q"],
        "summary_hints": ["did the thing"],
        "git_info": {"branch": "main", "commits": [{"hash": "a1b2c3d", "message": message}]},
        "session_id": "s-1",
    }


class TestCommitGitmoji:
    def test_every_type_in_the_reference_maps(self):
        for kind, emoji in GITMOJI.items():
            assert commit_gitmoji("%s: subject" % kind) == emoji

    def test_scope_and_breaking_marker_are_tolerated(self):
        assert commit_gitmoji("feat(notion): add push") == "✨"
        assert commit_gitmoji("fix(cli)!: drop the flag") == "🐛"
        assert commit_gitmoji("refactor!: split it") == "♻️"

    def test_unknown_type_gets_nothing(self):
        assert commit_gitmoji("wip: halfway") == ""
        assert commit_gitmoji("Merge pull request #12") == ""
        assert commit_gitmoji("just a sentence") == ""

    def test_a_message_that_already_leads_with_an_emoji_is_left_alone(self):
        """`ai-commit` and friends may have put one there; two in a row reads
        like a bug."""
        assert commit_gitmoji("✨ feat: add push") == ""

    def test_empty_and_whitespace(self):
        assert commit_gitmoji("") == ""
        assert commit_gitmoji("   ") == ""
        assert commit_gitmoji(None) == ""


class TestFormatEntry:
    def test_off_by_default(self):
        """The diary is a permanent record; opinionated formatting has to be
        asked for."""
        out = format_entry(_entry("feat: add login"))
        assert "`a1b2c3d` feat: add login" in out
        assert "✨" not in out

    def test_on_when_asked(self):
        out = format_entry(_entry("feat: add login"), gitmoji=True)
        assert "`a1b2c3d` ✨ feat: add login" in out

    def test_a_commit_with_no_recognised_type_is_unchanged(self):
        out = format_entry(_entry("Merge pull request #12"), gitmoji=True)
        assert "`a1b2c3d` Merge pull request #12" in out

    def test_headings_never_gain_gitmoji(self):
        """The reason category headings were left out: 📝, ⚡ and 🔒 already
        mean Work Summary, Key Commands and secrets-masked in an entry, and
        gitmoji would give each of them a second meaning in the same entry."""
        entry = _entry("docs: write it up")
        entry["secrets_masked"] = 1
        out = format_entry(entry, gitmoji=True)

        # the commit line carries the docs gitmoji
        assert "`a1b2c3d` 📝 docs: write it up" in out
        # and 📝 still appears exactly once more, as the Work Summary heading
        assert out.count("📝") == 2
        # the category is still plain text, not decorated
        assert "`docs`" in out
        assert "✨ `docs`" not in out


class TestConfigDefault:
    def test_default_config_ships_it_off(self):
        from claude_diary.config import DEFAULT_CONFIG
        assert DEFAULT_CONFIG["formatting"]["gitmoji"] is False
