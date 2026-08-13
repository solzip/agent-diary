"""A missing task group is worth saying and not worth refusing a push over.

`Task Group` is what joins work done on different days into one thread. It was
documented as being for "multi-session work", which defers the decision to a
moment when the answer is not yet known: whether a piece of work continues is
knowable after the second session, and by then the first row is already filed
without a group and can never be joined to its own follow-up. 62% of rows on
one real database have none.

The fix is a warning rather than a validation error. Rejecting the push would
discard the record entirely, and an unlinked row beats no row — that is the
same trade this project has made every time it has had to choose.
"""

from claude_diary.cli.notion_push.validate import (
    _validate_push_data,
    collect_push_warnings,
    print_push_warnings,
)


def _task(title="t", **kw):
    task = {"title": title}
    task.update(kw)
    return task


class TestItNoticesUngroupedWork:
    def test_a_task_without_a_group_is_reported(self):
        warnings = collect_push_warnings([_task()])
        assert len(warnings) == 1
        assert "task_group" in warnings[0]

    def test_a_blank_group_counts_as_missing(self):
        assert collect_push_warnings([_task(task_group="   ")])

    def test_a_grouped_task_is_not_reported(self):
        assert collect_push_warnings([_task(task_group="a-thread")]) == []

    def test_the_count_and_the_positions_are_given(self):
        tasks = [_task(task_group="x"), _task(), _task()]
        warning = collect_push_warnings(tasks)[0]
        assert "2 of 3" in warning
        assert "tasks[1]" in warning and "tasks[2]" in warning

    def test_a_long_list_is_truncated(self):
        warning = collect_push_warnings([_task() for _ in range(9)])[0]
        assert "..." in warning

    def test_it_survives_a_malformed_task(self):
        assert collect_push_warnings(["not a dict", _task(task_group="x")]) == []


class TestItDoesNotBlockThePush:
    def test_validation_still_passes_without_a_group(self):
        """The push has to go through. An unlinked row beats no row."""
        data = {"tasks": [_task()]}
        assert _validate_push_data(data) == []

    def test_the_warning_goes_to_stdout_with_the_command_prefix(self, capsys):
        print_push_warnings(["something to say"])
        out = capsys.readouterr().out
        assert out.startswith("[agent-diary diary-notion push] warning:")
        assert "something to say" in out

    def test_no_warnings_prints_nothing(self, capsys):
        print_push_warnings([])
        assert capsys.readouterr().out == ""
