"""A constant that nothing reads is worse than no constant at all.

Three of them were sitting in this codebase: `RICH_TEXT_LIMIT`,
`ACTIVE_STATUSES` and `DEFAULT_VERIFICATION_LIMIT`. None was referenced from
anywhere. The damage is not the dead line — it is what grows next to it. Eight
literal `[:2000]` did the truncating `RICH_TEXT_LIMIT` was named for, in three
modules; the status strings `ACTIVE_STATUSES` enumerated were typed out inline
half a dozen times in the file directly below it. `formatter.py` even documented
that it truncated "to RICH_TEXT_LIMIT" while importing no such name.

That is the shape this project keeps finding: one place was given a name, the
others were written out by hand, and nothing connects them. So the check is not
"is this value duplicated" — that is hard to see — but "does the name anyone
bothered to define actually get used", which is exactly the signal that goes
missing first.

References are counted from the syntax tree, not with a text search: a mention
inside a docstring is how `RICH_TEXT_LIMIT` looked used for as long as it was
not.
"""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: Constants that exist for readers of the module rather than for its code.
#: Anything added here needs a reason on the line, not just a name.
DEFINED_FOR_DOCUMENTATION = {
    # The default `--transcripts` shows this to the user; the code path uses
    # resolve_transcript_root(), which returns it expanded and separator-correct.
    "CLAUDE_TRANSCRIPT_ROOT",
}


def _python_files(*relative):
    for base in relative:
        for path in sorted((ROOT / base).rglob("*.py")):
            if "__pycache__" not in path.parts:
                yield path


def _module_constants():
    """Every module-level UPPER_CASE assignment in the package."""
    found = {}
    for path in _python_files("src"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if not isinstance(node, ast.Assign):
                continue
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.isupper() and len(target.id) > 3:
                    found.setdefault(target.id, []).append(
                        "%s:%d" % (path.relative_to(ROOT).as_posix(), node.lineno))
    return found


def _names_read_anywhere():
    """Names the code actually reads, from src and from the tests.

    Attributes count (`statuses.DONE`), so do imports (`from ... import VALID`),
    and strings do not — which is the whole point.
    """
    read = set()
    for path in _python_files("src", "tests"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        assigned_here = {
            t for node in tree.body if isinstance(node, ast.Assign)
            for t in node.targets if isinstance(t, ast.Name)
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node not in assigned_here:
                read.add(node.id)
            elif isinstance(node, ast.Attribute):
                read.add(node.attr)
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    read.add(alias.name)
                    if alias.asname:
                        read.add(alias.asname)
    return read


class TestEveryNamedConstantIsRead:
    def test_no_constant_is_defined_and_never_used(self):
        read = _names_read_anywhere()
        dead = sorted(
            "%s (%s)" % (name, ", ".join(where))
            for name, where in _module_constants().items()
            if name not in read and name not in DEFINED_FOR_DOCUMENTATION
        )
        assert not dead, (
            "defined and never read. Either use it — the value is probably typed out "
            "by hand somewhere — or delete it: %s" % "; ".join(dead)
        )

    def test_the_scan_sees_the_constants_it_is_meant_to(self):
        """A collector that quietly found nothing would make the check above
        pass while checking nothing."""
        constants = _module_constants()
        assert len(constants) > 50, "only found %d module constants" % len(constants)
        assert "RICH_TEXT_LIMIT" in constants
        assert "DEFAULT_CONFIG" in constants

    def test_a_docstring_mention_does_not_count_as_a_use(self):
        """How `RICH_TEXT_LIMIT` looked used for as long as it was not: named
        in `formatter.py`'s docstring, imported by nobody."""
        tree = ast.parse('"""Mentions ONLY_IN_A_DOCSTRING."""\nX = 1\n')
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        assert "ONLY_IN_A_DOCSTRING" not in names


def _literals(skip):
    """Every string and number the code states outright, by file.

    Literals only — a path named inside a docstring is describing the layout to
    a reader, and rewriting prose to interpolate a constant makes it worse. A
    string the program passes to `expanduser` is a different thing, and that is
    what this sees.
    """
    out = {}
    for path in _python_files("src"):
        if path.name in skip:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        docstrings = {
            ast.get_docstring(n, clean=False)
            for n in ast.walk(tree)
            if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        }
        values = [n.value for n in ast.walk(tree)
                  if isinstance(n, ast.Constant) and n.value not in docstrings]
        out[path.relative_to(ROOT).as_posix()] = values
    return out


class TestTheValuesThatWereConsolidatedStayConsolidated:
    """Each of these had one named home and several handwritten copies."""

    def _stating(self, skip, *values):
        wanted = set(values)
        return [name for name, found in _literals(skip).items() if wanted & set(found)]

    def test_the_diary_dir_default_lives_only_in_config(self):
        offenders = self._stating({"config.py"}, "~/working-diary", "~/working-diary/manual")
        assert not offenders, (
            "DEFAULT_CONFIG states this default; use resolve_diary_dir(config) "
            "or resolve_manual_diary_dir(config): %s" % ", ".join(offenders))

    def test_the_transcript_root_lives_only_in_config(self):
        offenders = self._stating({"config.py"}, "~/.claude/projects")
        assert not offenders, (
            "three spellings of this path disagreed on Windows; use "
            "resolve_transcript_root(): %s" % ", ".join(offenders))

    def test_the_notion_api_facts_live_only_in_notion_api(self):
        offenders = self._stating(
            {"notion_api.py"}, "2022-06-28", "https://api.notion.com/v1", 2000)
        assert not offenders, (
            "import these from claude_diary.lib.notion_api: %s" % ", ".join(offenders))

    def test_the_status_values_live_only_in_statuses(self):
        """Not every mention — `notion_ops` compares against single statuses by
        name and that reads better than a constant would. What must not come
        back is the *enumeration*, which is what drifts when a value is added."""
        for name, found in _literals({"statuses.py"}).items():
            spelled_out = {v for v in found if isinstance(v, str)} >= {
                "Discussion", "Design", "Implementation", "Testing"}
            assert not spelled_out, (
                "%s enumerates the statuses again; import them from "
                "claude_diary.lib.statuses" % name)
