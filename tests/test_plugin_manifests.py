"""The Claude Code plugin manifests must match what the README tells people to run.

This is the same failure the 4.8.1 fix was about: an instruction in the docs
that does not work on the reader's machine. The README said

    /plugin marketplace add solzip/agent-diary
    /plugin install agent-diary@solzip

while the repository had no `marketplace.json` at all, so the first line failed
outright, and `plugin.json` carried a `dependencies` object where the schema
wants an array — a wrong type on a recognised field, which makes the plugin
fail to load rather than warn. Both distribution paths this project advertises,
and one of them was broken end to end.

`claude plugin validate --strict` is the real check, but it needs Claude Code
installed and CI has only Python. These assertions cover the specific things
that were wrong, plus the drift that would break the instructions again: the
README naming a marketplace or plugin that the manifests do not define.
"""

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / ".claude-plugin" / "plugin.json"
MARKETPLACE = ROOT / ".claude-plugin" / "marketplace.json"
KEBAB = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def _load(path):
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture
def plugin():
    return _load(PLUGIN)


@pytest.fixture
def marketplace():
    return _load(MARKETPLACE)


class TestTheMarketplaceExists:
    """`/plugin marketplace add <repo>` reads `.claude-plugin/marketplace.json`
    from the repository root. Without it the command fails on line one."""

    def test_the_file_is_there(self):
        assert MARKETPLACE.is_file(), (
            "README documents `/plugin marketplace add`, which requires this file"
        )

    def test_it_has_the_required_fields(self, marketplace):
        for field in ("name", "owner", "plugins"):
            assert field in marketplace, "marketplace.json is missing %r" % field
        assert marketplace["owner"].get("name"), "owner.name is required"
        assert marketplace["plugins"], "a marketplace with no plugins lists nothing"

    def test_the_name_is_kebab_case(self, marketplace):
        assert KEBAB.match(marketplace["name"])

    def test_every_entry_has_a_name_and_a_source(self, marketplace):
        for entry in marketplace["plugins"]:
            assert KEBAB.match(entry.get("name", "")), entry
            assert entry.get("source"), entry

    def test_relative_sources_resolve(self, marketplace):
        """Paths resolve against the marketplace root — the directory holding
        `.claude-plugin/`, not `.claude-plugin/` itself."""
        for entry in marketplace["plugins"]:
            source = entry["source"]
            if isinstance(source, str):
                assert source.startswith("./"), "a relative source must start with ./"
                assert (ROOT / source).is_dir(), "source %s does not exist" % source


class TestTheHooksFileIsWhereTheManifestSaysItIs:
    """The path that made the plugin fail to load: `hooks.json` resolves from
    the plugin root, and the file lives one directory down."""

    def _hook_paths(self, manifest):
        hooks = manifest.get("hooks")
        return [hooks] if isinstance(hooks, str) else []

    def test_the_plugin_manifest_points_at_a_real_file(self, plugin):
        for path in self._hook_paths(plugin):
            assert (ROOT / path).is_file(), "hooks path %s does not exist" % path

    def test_the_marketplace_entry_points_at_a_real_file(self, marketplace):
        for entry in marketplace["plugins"]:
            for path in self._hook_paths(entry):
                assert (ROOT / path).is_file(), "hooks path %s does not exist" % path

    def test_the_hook_actually_registers_a_stop_hook(self, plugin):
        hooks = _load(ROOT / plugin["hooks"])
        assert "Stop" in hooks.get("hooks", {}), (
            "the plugin exists to install the Stop Hook"
        )


class TestTypesTheRuntimeRefusesToLoad:
    """A recognised field with the wrong type is a load failure, not a warning."""

    def test_dependencies_is_a_list_if_present(self, plugin):
        deps = plugin.get("dependencies")
        assert deps is None or isinstance(deps, list), (
            "`dependencies` takes plugin names, not a runtime map like "
            '{"python": ">=3.8"} — that shape stops the plugin loading'
        )

    def test_keywords_is_a_list(self, plugin):
        assert isinstance(plugin.get("keywords", []), list)

    def test_the_plugin_name_is_kebab_case(self, plugin):
        assert KEBAB.match(plugin["name"])


class TestTheReadmeInstructionsMatchTheManifests:
    """The drift that would break the documented path again."""

    @pytest.fixture(params=["README.md", "README.ko.md"])
    def readme(self, request):
        return (ROOT / request.param).read_text(encoding="utf-8")

    def test_the_install_command_names_a_plugin_the_marketplace_defines(
        self, readme, marketplace
    ):
        commands = re.findall(r"/plugin install (\S+)", readme)
        assert commands, "the README no longer documents an install command"
        defined = {e["name"] for e in marketplace["plugins"]}
        for command in commands:
            name, _, market = command.partition("@")
            assert name in defined, "README installs %r, not in marketplace.json" % name
            if market:
                assert market == marketplace["name"], (
                    "README installs from %r but the marketplace is named %r"
                    % (market, marketplace["name"])
                )

    def test_the_marketplace_command_points_at_this_repository(self, readme):
        adds = re.findall(r"/plugin marketplace add (\S+)", readme)
        assert adds, "the README no longer documents adding the marketplace"
        for target in adds:
            assert "solzip/agent-diary" in target, target


class TestTheVersionsAgree:
    """`claude plugin tag` refuses to tag when plugin.json and the marketplace
    entry disagree, and a stale version in either is invisible until then."""

    def _pyproject_version(self):
        text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        return re.search(r'^version = "([^"]+)"', text, re.M).group(1)

    def test_plugin_matches_pyproject(self, plugin):
        assert plugin["version"] == self._pyproject_version()

    def test_marketplace_entry_matches_plugin(self, plugin, marketplace):
        entry = next(e for e in marketplace["plugins"] if e["name"] == plugin["name"])
        assert entry.get("version") == plugin["version"]
