"""The drift summary rides on the command that actually runs.

`diary-notion ops` computes all of this already. Measured on one real diary it
had been run a handful of times against 2,286 pushes, so the numbers existed
and nobody saw them — the same shape as the other failures found in this tool,
where the check was present and unopened rather than absent.

Two properties matter more than the formatting. It must never break a push,
because the rows are written before it runs. And it must stay quiet when there
is nothing to say, because a block that prints on every push and always looks
the same is a block that stops being read.
"""

from claude_diary.cli.notion_push.drift import (
    print_project_drift,
    print_pushed_projects_drift,
)


def _row(project, status="Implementation", review=None, done=False,
         next_action="do the thing", blocked=False, date="2026-08-01",
         task_group="a-group"):
    """A row shaped the way `_row_to_item` reads it.

    Two details that are easy to get wrong and were: finished work is
    `Deployed` rather than `Done`, and `Blocked` is a checkbox with the reason
    in a separate `Block Reason` field.
    """
    props = {
        "Name": {"type": "title", "title": [{"plain_text": "t"}]},
        "Project": {"type": "select", "select": {"name": project}},
        "Status": {"type": "select", "select": {"name": "Deployed" if done else status}},
        "Date": {"type": "date", "date": {"start": date}},
        "Next Action": {"type": "rich_text",
                        "rich_text": [{"plain_text": next_action}] if next_action else []},
        "Blocked": {"type": "checkbox", "checkbox": bool(blocked)},
        "Task Group": {"type": "select",
                       "select": {"name": task_group} if task_group else None},
    }
    if review:
        props["Review Status"] = {"type": "select", "select": {"name": review}}
    return {"archived": False, "properties": props, "url": "https://example/x"}


class FakeExporter:
    """Records the filter it was asked for; returns canned rows."""

    def __init__(self, rows, raises=False):
        self.rows = rows
        self.raises = raises
        self.filters = []

    def query_database_rows(self, db_id, page_size=100, row_filter=None):
        self.filters.append(row_filter)
        if self.raises:
            raise RuntimeError("Notion is down")
        wanted = (row_filter or {}).get("select", {}).get("equals")
        return [r for r in self.rows
                if not wanted
                or r["properties"]["Project"]["select"]["name"] == wanted]


class TestItNeverBreaksThePush:
    """The rows are already in Notion by the time this runs."""

    def test_a_failed_query_is_swallowed(self, capsys):
        exporter = FakeExporter([], raises=True)
        assert print_project_drift(exporter, "db", "proj", "2026-08-13") is None

    def test_a_project_with_no_rows_prints_nothing(self, capsys):
        exporter = FakeExporter([_row("other")])
        print_project_drift(exporter, "db", "proj", "2026-08-13")
        assert capsys.readouterr().out == ""

    def test_a_task_index_out_of_range_is_ignored(self, capsys):
        exporter = FakeExporter([_row("proj")])
        print_pushed_projects_drift(exporter, "db", [], [(7, "gone")], None, "2026-08-13")
        assert capsys.readouterr().out == ""


class TestItAsksForOneProject:
    def test_the_query_is_filtered(self):
        """Unfiltered, this is six paginated requests after every push."""
        exporter = FakeExporter([_row("proj")])
        print_project_drift(exporter, "db", "proj", "2026-08-13")
        assert exporter.filters == [
            {"property": "Project", "select": {"equals": "proj"}}
        ]

    def test_each_pushed_project_is_summarised_once(self, capsys):
        rows = [_row("a"), _row("b")]
        exporter = FakeExporter(rows)
        tasks = [{"project": "a"}, {"project": "b"}, {"project": "a"}]
        pushed = [(0, "one"), (1, "two"), (2, "three")]
        print_pushed_projects_drift(exporter, "db", tasks, pushed, None, "2026-08-13")
        out = capsys.readouterr().out
        assert out.count("Open work in a:") == 1
        assert out.count("Open work in b:") == 1


class TestItSaysOnlyWhatIsTrue:
    def test_signals_that_are_zero_are_not_printed(self, capsys):
        """A column of zeroes trains the reader to skip the block."""
        exporter = FakeExporter([_row("proj", date="2026-08-13")])
        print_project_drift(exporter, "db", "proj", "2026-08-13")
        out = capsys.readouterr().out
        assert "blocked" not in out
        assert "awaiting review" not in out

    def test_the_open_count_and_the_total_are_both_shown(self, capsys):
        rows = [_row("proj") for _ in range(3)] + [_row("proj", done=True)]
        exporter = FakeExporter(rows)
        print_project_drift(exporter, "db", "proj", "2026-08-13")
        out = capsys.readouterr().out
        assert "3 of 4 rows" in out
        assert "1 closed (25%)" in out

    def test_blocked_rows_are_surfaced(self, capsys):
        rows = [_row("proj", blocked=True)]
        exporter = FakeExporter(rows)
        print_project_drift(exporter, "db", "proj", "2026-08-13")
        assert "blocked" in capsys.readouterr().out


class TestItShowsWhetherWorkIsLinkable:
    """`Task Group` is what joins work done on different days. Measured on one
    real database only 38% of rows carried one, which makes most of the
    project history unlinkable — and nothing in the push path said so."""

    def test_ungrouped_rows_are_counted(self, capsys):
        rows = [_row("proj", task_group="") for _ in range(3)] + [_row("proj")]
        exporter = FakeExporter(rows)
        print_project_drift(exporter, "db", "proj", "2026-08-13")
        assert "no task group          3 of 4 rows" in capsys.readouterr().out

    def test_a_fully_grouped_project_says_nothing_about_it(self, capsys):
        exporter = FakeExporter([_row("proj"), _row("proj")])
        print_project_drift(exporter, "db", "proj", "2026-08-13")
        assert "no task group" not in capsys.readouterr().out

    def test_the_names_already_in_use_are_offered(self, capsys):
        """A continuation filed under a new name is not a continuation, so the
        next push needs to see the vocabulary before inventing one."""
        rows = [_row("proj", task_group=""), _row("proj", task_group="alpha"),
                _row("proj", task_group="beta")]
        exporter = FakeExporter(rows)
        print_project_drift(exporter, "db", "proj", "2026-08-13")
        out = capsys.readouterr().out
        assert "groups in use" in out
        assert "alpha" in out and "beta" in out

    def test_the_names_are_not_offered_when_nothing_is_ungrouped(self, capsys):
        exporter = FakeExporter([_row("proj", task_group="alpha")])
        print_project_drift(exporter, "db", "proj", "2026-08-13")
        assert "groups in use" not in capsys.readouterr().out

    def test_mostly_ungrouped_earns_the_hint(self, capsys):
        rows = [_row("proj", task_group="") for _ in range(3)] + [_row("proj")]
        exporter = FakeExporter(rows)
        print_project_drift(exporter, "db", "proj", "2026-08-13")
        assert "cannot be linked" in capsys.readouterr().out


class TestTheHintIsRare:
    """It prints after every push, so a hint that shows most of the time is a
    hint nobody reads."""

    def test_a_healthy_project_gets_no_hint(self, capsys):
        rows = [_row("proj", done=True) for _ in range(6)] + [
            _row("proj", date="2026-08-13") for _ in range(2)
        ]
        exporter = FakeExporter(rows)
        print_project_drift(exporter, "db", "proj", "2026-08-13")
        assert "->" not in capsys.readouterr().out

    def test_a_large_pile_of_open_work_gets_one(self, capsys):
        rows = [_row("proj") for _ in range(25)] + [_row("proj", done=True)]
        exporter = FakeExporter(rows)
        print_project_drift(exporter, "db", "proj", "2026-08-13")
        out = capsys.readouterr().out
        assert out.count("->") == 1
        assert "ops" in out

    def test_blocked_work_gets_one_even_when_the_project_is_small(self, capsys):
        rows = [_row("proj", blocked=True), _row("proj", done=True)]
        exporter = FakeExporter(rows)
        print_project_drift(exporter, "db", "proj", "2026-08-13")
        out = capsys.readouterr().out
        assert out.count("->") == 1
        assert "blocked" in out

    def test_a_review_backlog_points_at_the_review_command(self, capsys):
        rows = [_row("proj", review="Needs Review", date="2026-08-13")
                for _ in range(12)]
        exporter = FakeExporter(rows)
        print_project_drift(exporter, "db", "proj", "2026-08-13")
        assert "review" in capsys.readouterr().out


class TestThePushActuallyCallsIt:
    """Every test above calls the summary directly, and that is how it shipped
    broken: the call site read a `db_id` that only exists on the --force path,
    so an ordinary push raised NameError into a `except Exception` that logs at
    debug. The summary never printed for anybody and no test noticed.
    """

    def _run_push(self, tmp_path, force):
        import json
        import os
        from unittest.mock import MagicMock, patch

        from claude_diary.cli.notion_push import cmd_notion_push

        input_path = tmp_path / "in.json"
        with open(str(input_path), "w", encoding="utf-8") as f:
            json.dump({
                "session_id": "s1",
                "tasks": [{"title": "작업", "project": "proj"}],
            }, f)

        mock_exp = MagicMock()
        mock_exp.ensure_database.return_value = "db_x"
        mock_exp.find_existing_row.return_value = None
        mock_exp.create_row.return_value = "row_a"
        mock_exp.archive_rows_for_session.return_value = 0
        mock_exp.get_task_group_session_ids.return_value = set()
        mock_exp._cache = {"rows": {}, "years": {}, "databases": {}, "root_page_id": "p"}
        mock_exp.query_database_rows.side_effect = (
            lambda db_id, page_size=100, row_filter=None: [
                _row("proj", blocked=True), _row("proj", done=True),
            ]
        )

        args = MagicMock()
        args.input = str(input_path)
        args.force = force
        args.dry_run = False
        args.preview_file = ""
        args.artifact_dir = ""
        args.no_artifacts = True

        config = {"exporters": {"notion_hierarchical": {"api_token": "t", "root_page_id": "p"}}}
        with patch.dict(os.environ, {}, clear=True), \
             patch("claude_diary.cli.notion_push.load_config", return_value=config), \
             patch("claude_diary.cli.notion_push.NotionHierarchicalExporter", return_value=mock_exp), \
             patch("claude_diary.cli.notion_push.get_head_branch", return_value="main"), \
             patch("claude_diary.cli.notion_push.os.getcwd", return_value=str(tmp_path)):
            try:
                cmd_notion_push(args)
            except SystemExit:
                pass

    def test_an_ordinary_push_prints_the_summary(self, tmp_path, capsys):
        self._run_push(tmp_path, force=False)
        assert "Open work in proj:" in capsys.readouterr().out

    def test_a_forced_push_prints_it_too(self, tmp_path, capsys):
        self._run_push(tmp_path, force=True)
        assert "Open work in proj:" in capsys.readouterr().out
