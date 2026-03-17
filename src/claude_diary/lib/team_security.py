"""Team security module — path masking, content filtering, access control, opt-out."""

import fnmatch
import os
import re
import sys


# ── Path Masking ──

def mask_paths(file_list, mask_patterns):
    """Mask sensitive file paths using glob patterns.

    Args:
        file_list: List of file path strings
        mask_patterns: List of glob patterns (e.g., "**/credentials/**", "**/.env*")

    Returns:
        New list with matched paths replaced by "[MASKED]"
    """
    if not mask_patterns:
        return file_list

    masked = []
    for fp in file_list:
        normalized = fp.replace("\\", "/")
        if _path_matches(normalized, mask_patterns):
            masked.append("[MASKED]")
        else:
            masked.append(fp)
    return masked


def _path_matches(path, patterns):
    """Check if path matches any glob pattern."""
    for pattern in patterns:
        # Normalize pattern
        p = pattern.replace("\\", "/")
        # Direct fnmatch
        if fnmatch.fnmatch(path, p):
            return True
        # Check if any path component matches a keyword pattern
        parts = path.lower().split("/")
        p_parts = p.lower().replace("**/", "").replace("/**", "").split("/")
        for keyword in p_parts:
            if not keyword or keyword == "*":
                continue
            for part in parts:
                if fnmatch.fnmatch(part, keyword):
                    return True
    return False


# ── Content Filtering ──

def filter_content(text, filter_keywords, mode="redact"):
    """Filter sensitive content from text.

    Args:
        text: Text to filter
        filter_keywords: List of keywords to detect
        mode: "redact" = replace sentence with [REDACTED], "skip" = return None

    Returns:
        Filtered text, or None if mode=skip and keyword found
    """
    if not text or not filter_keywords:
        return text

    text_lower = text.lower()
    for kw in filter_keywords:
        if kw.lower() in text_lower:
            if mode == "skip":
                return None
            elif mode == "redact":
                # Replace the sentence containing the keyword
                sentences = re.split(r'([.!?\n])', text)
                result = []
                for i in range(0, len(sentences), 2):
                    sent = sentences[i] if i < len(sentences) else ""
                    sep = sentences[i + 1] if i + 1 < len(sentences) else ""
                    if kw.lower() in sent.lower():
                        result.append("[REDACTED]" + sep)
                    else:
                        result.append(sent + sep)
                return "".join(result)

    return text


def filter_entry_data(entry_data, filter_keywords, mode="redact"):
    """Apply content filtering to all text fields of entry_data.

    If mode=skip and keyword found, returns False (skip entire session).
    Otherwise modifies entry_data in-place and returns True.
    """
    if not filter_keywords:
        return True

    # Check if session should be skipped entirely
    if mode == "skip":
        all_text = " ".join(
            entry_data.get("user_prompts", []) +
            entry_data.get("summary_hints", []) +
            entry_data.get("commands_run", [])
        )
        for kw in filter_keywords:
            if kw.lower() in all_text.lower():
                return False

    # Redact mode
    for field in ("user_prompts", "summary_hints", "commands_run"):
        items = entry_data.get(field, [])
        filtered = []
        for item in items:
            result = filter_content(item, filter_keywords, mode)
            if result is not None:
                filtered.append(result)
        entry_data[field] = filtered

    return True


# ── Session Opt-out ──

def should_skip_session(cwd, config):
    """Check if the current session should be skipped.

    Checks:
    1. CLAUDE_DIARY_SKIP=1 environment variable
    2. Project name in config.skip_projects list

    Returns:
        True if session should be skipped
    """
    # Env var check
    if os.environ.get("CLAUDE_DIARY_SKIP", "").strip() in ("1", "true", "yes"):
        return True

    # Project skip list
    skip_projects = config.get("skip_projects", [])
    if skip_projects and cwd:
        project = os.path.basename(cwd.replace("\\", "/").rstrip("/"))
        if project in skip_projects:
            return True

    return False


# ── Access Control ──

ROLE_PERMISSIONS = {
    "member": {"own_diary": "full", "others_diary": "summary", "others_detail": False, "team_stats": True},
    "lead":   {"own_diary": "full", "others_diary": "full", "others_detail": "same_project", "team_stats": True},
    "admin":  {"own_diary": "full", "others_diary": "full", "others_detail": True, "team_stats": True},
}


def check_access(viewer_role, viewer_name, target_name, target_project=None, viewer_projects=None):
    """Check if viewer has access to target's diary.

    Args:
        viewer_role: "member", "lead", or "admin"
        viewer_name: Name of the person viewing
        target_name: Name of the diary owner
        target_project: Project of the diary entry
        viewer_projects: Projects the viewer is involved in

    Returns:
        "full", "summary", or "none"
    """
    if viewer_name == target_name:
        return "full"

    perms = ROLE_PERMISSIONS.get(viewer_role, ROLE_PERMISSIONS["member"])

    if viewer_role == "admin":
        return "full"

    if viewer_role == "lead":
        if target_project and viewer_projects and target_project in viewer_projects:
            return "full"
        return perms["others_diary"]

    # member
    return "summary"


def apply_access_filter(entry_data, access_level):
    """Filter entry_data based on access level.

    "full": no filtering
    "summary": only project, categories, code_stats (no prompts, files, commands)
    "none": empty dict
    """
    if access_level == "full":
        return entry_data

    if access_level == "none":
        return {}

    # summary mode
    return {
        "date": entry_data.get("date", ""),
        "time": entry_data.get("time", ""),
        "project": entry_data.get("project", ""),
        "categories": entry_data.get("categories", []),
        "code_stats": entry_data.get("code_stats"),
        "git_info": {"branch": entry_data.get("git_info", {}).get("branch", "")} if entry_data.get("git_info") else None,
    }
