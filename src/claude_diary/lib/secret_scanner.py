"""Secret scanner — detect and mask sensitive information before writing diary."""

import re

BASIC_PATTERNS = [
    (r'(?i)(password|passwd|pwd)\s*[=:]\s*\S+', r'\1=****'),
    (r'(?i)(api[_-]?key|apikey)\s*[=:]\s*\S+', r'\1=****'),
    (r'(?i)(secret|token)\s*[=:]\s*\S+', r'\1=****'),
    (r'sk-[a-zA-Z0-9]{20,}', '****'),
    (r'ghp_[a-zA-Z0-9]{36,}', '****'),
    (r'gho_[a-zA-Z0-9]{36,}', '****'),
    (r'xoxb-[a-zA-Z0-9\-]+', '****'),
    (r'AKIA[A-Z0-9]{16}', '****'),
    (r'(?i)bearer\s+[a-zA-Z0-9\-._~+/]+=*', 'Bearer ****'),
]


def scan_and_mask(text, additional_patterns=None):
    """Scan text for secret patterns and mask them.

    Args:
        text: Text to scan
        additional_patterns: Optional list of extra regex patterns to mask

    Returns:
        (masked_text, mask_count)
    """
    if not text:
        return text, 0

    # Skip already-masked text
    if text == "****" or text.count("****") > 2:
        return text, 0

    count = 0
    all_patterns = list(BASIC_PATTERNS)
    if additional_patterns:
        for p in additional_patterns:
            all_patterns.append((p, "****"))

    for pattern, replacement in all_patterns:
        new_text, n = re.subn(pattern, replacement, text)
        count += n
        text = new_text

    return text, count


def scan_entry_data(entry_data, additional_patterns=None):
    """Scan and mask secrets in all text fields of entry_data.

    Args:
        entry_data: Entry data dict (modified in-place)
        additional_patterns: Optional list of extra regex patterns

    Returns total number of secrets masked.
    """
    total = 0

    # Scan user_prompts
    for i, prompt in enumerate(entry_data.get("user_prompts", [])):
        masked, count = scan_and_mask(prompt, additional_patterns)
        if count > 0:
            entry_data["user_prompts"][i] = masked
            total += count

    # Scan summary_hints
    for i, hint in enumerate(entry_data.get("summary_hints", [])):
        masked, count = scan_and_mask(hint, additional_patterns)
        if count > 0:
            entry_data["summary_hints"][i] = masked
            total += count

    # Scan commands
    for i, cmd in enumerate(entry_data.get("commands_run", [])):
        masked, count = scan_and_mask(cmd, additional_patterns)
        if count > 0:
            entry_data["commands_run"][i] = masked
            total += count

    entry_data["secrets_masked"] = total
    return total
