"""Shapes the pipeline passes around.

These were documented in comments until now, on the grounds that TypedDict
needs Python 3.8. The floor has been 3.8 for some time, and the comments had
already drifted: they omitted `short_hash` from a commit and three keys the
parser produces. A comment cannot fail, which is exactly the problem.

Every dict here is `total=False`. The pipeline builds an entry in stages —
parse, then git enrichment, then categorisation, then the secret scan — and
each stage adds keys. Marking them required would describe a state the data
only reaches at the end.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict


class CommitInfo(TypedDict, total=False):
    """One commit, as `git_info.get_commit_info` returns it."""

    hash: str
    short_hash: str
    message: str


class DiffStat(TypedDict, total=False):
    """Line and file counts for a range of commits.

    `files` counts distinct paths across the range, not the sum per commit.
    """

    added: int
    deleted: int
    files: int


class GitInfo(TypedDict, total=False):
    """Repository state at the time a session ended."""

    branch: str
    commits: List[CommitInfo]
    diff_stat: DiffStat


class ParsedTranscript(TypedDict, total=False):
    """What `lib.parser.parse_transcript` pulls out of a session transcript.

    `files_modified`, `files_created` and `tools_used` are sets while parsing,
    to deduplicate, and are lists by the time they reach `EntryData`.
    """

    user_prompts: List[str]
    files_modified: Any
    files_created: Any
    commands_run: List[str]
    tools_used: Any
    errors_encountered: List[str]
    summary_hints: List[str]
    session_start: Optional[str]
    session_end: Optional[str]


class EntryData(TypedDict, total=False):
    """One diary entry, from `core.process_session` through to the writer.

    This is the value the formatter renders, the secret scanner masks in
    place, and the exporters consume.
    """

    session_id: str
    date: str
    time: str
    project: str
    cwd: str

    user_prompts: List[str]
    files_created: List[str]
    files_modified: List[str]
    commands_run: List[str]
    summary_hints: List[str]
    errors_encountered: List[str]

    categories: List[str]
    git_info: Optional[GitInfo]
    code_stats: Optional[DiffStat]
    secrets_masked: int


class EnrichmentConfig(TypedDict, total=False):
    """Which enrichment stages run. Every stage defaults to on."""

    git_info: bool
    auto_category: bool
    code_stats: bool
    session_time: bool


class FormattingConfig(TypedDict, total=False):
    """Rendering choices that are taste rather than correctness."""

    gitmoji: bool


class Config(TypedDict, total=False):
    """User configuration, merged from defaults, environment and config.json.

    Precedence is not uniform: `config.json` wins for these keys, while the
    two Notion credentials are read from the environment first. See README
    section 5.
    """

    lang: str
    timezone_offset: int
    diary_dir: str
    manual_diary_dir: str
    max_transcript_lines: Optional[int]
    enrichment: EnrichmentConfig
    formatting: FormattingConfig
    exporters: Dict[str, Dict[str, Any]]
    custom_categories: Dict[str, List[str]]


def make_empty_entry_data() -> EntryData:
    """Create an EntryData with every list present and every scalar zeroed.

    Callers can then append without checking whether a key exists.
    """
    return EntryData(
        session_id="unknown",
        date="",
        time="",
        project="unknown",
        cwd="",
        user_prompts=[],
        files_created=[],
        files_modified=[],
        commands_run=[],
        summary_hints=[],
        errors_encountered=[],
        categories=[],
        git_info=None,
        code_stats=None,
        secrets_masked=0,
    )
