"""Base exporter interface — all exporters must inherit from this."""


class BaseExporter:
    """Base class for diary exporters.

    entry_data contains:
        date, time, project, categories, user_prompts,
        files_created, files_modified, commands_run, summary_hints,
        git_info, code_stats, secrets_masked

    NOTE: Original transcript is NOT accessible (security).
    """

    TRUST_LEVEL = "custom"  # "official", "community", "custom"

    def __init__(self, config):
        self.config = config

    def export(self, entry_data):
        """Export entry_data to external service.
        Returns True on success.
        """
        raise NotImplementedError

    def validate_config(self):
        """Validate configuration values.
        Returns True if config is valid.
        """
        raise NotImplementedError
