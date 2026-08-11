"""Helpers shared by the `diary-notion` subcommands that read Notion rows."""

from datetime import datetime, timezone, timedelta


def resolve_year_and_today(config, explicit_year):
    """Return (year, "YYYY-MM-DD") in the configured local timezone."""
    tz_offset = config.get("timezone_offset", 9)
    local_tz = timezone(timedelta(hours=tz_offset))
    now = datetime.now(local_tz)
    year = explicit_year or now.year
    return year, now.strftime("%Y-%m-%d")


def plain_text(item):
    return item.get("plain_text") or ((item.get("text") or {}).get("content")) or ""


def title_value(prop):
    values = (prop or {}).get("title") or []
    text = "".join(plain_text(item) for item in values).strip()
    return text or "(untitled)"


def select_value(prop):
    return ((prop or {}).get("select") or {}).get("name") or ""


def date_start_value(prop):
    return ((prop or {}).get("date") or {}).get("start") or ""
