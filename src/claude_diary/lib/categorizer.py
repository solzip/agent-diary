"""Auto-categorizer — keyword-based work type classification (KO/EN)."""

DEFAULT_RULES = {
    "feature":  ["구현", "추가", "기능", "implement", "add", "feature", "new"],
    "bugfix":   ["수정", "버그", "에러", "fix", "bug", "error", "resolve"],
    "refactor": ["리팩토링", "정리", "개선", "refactor", "clean", "improve"],
    "docs":     ["문서", "README", "주석", "doc", "comment", "readme"],
    "test":     ["테스트", "검증", "test", "verify", "assert"],
    "config":   ["설정", "환경", "config", "setup", "install", "deploy"],
    "style":    ["스타일", "UI", "CSS", "design", "layout", "style"],
}


def categorize(entry_data, custom_rules=None):
    """Categorize work based on user_prompts, summary_hints, and file extensions.

    Args:
        entry_data: dict with user_prompts, summary_hints, files_created, files_modified
        custom_rules: optional dict of {"category": ["keyword1", ...]} to merge

    Returns:
        list of up to 3 category strings, sorted by frequency (descending).
    """
    rules = dict(DEFAULT_RULES)
    if custom_rules:
        for cat, keywords in custom_rules.items():
            if cat in rules:
                rules[cat] = list(set(rules[cat] + keywords))
            else:
                rules[cat] = keywords

    # Build search text from all relevant fields
    texts = []
    texts.extend(entry_data.get("user_prompts", []))
    texts.extend(entry_data.get("summary_hints", []))
    texts.extend(entry_data.get("commands_run", []))
    combined = " ".join(texts).lower()

    # Also check file extensions
    all_files = (
        entry_data.get("files_created", []) +
        entry_data.get("files_modified", [])
    )
    file_text = " ".join(all_files).lower()

    # Score each category
    scores = {}
    for category, keywords in rules.items():
        score = 0
        for kw in keywords:
            score += combined.count(kw.lower())
        # File extension hints (once per category, not per keyword)
        if category == "style" and any(ext in file_text for ext in [".css", ".scss", ".styled"]):
            score += 2
        if category == "test" and any(ext in file_text for ext in ["test_", "_test.", ".test.", "spec."]):
            score += 2
        if category == "docs" and any(ext in file_text for ext in [".md", ".rst", ".txt"]):
            score += 2
        if score > 0:
            scores[category] = score

    # Return top 3 by score
    sorted_cats = sorted(scores.keys(), key=lambda c: scores[c], reverse=True)
    return sorted_cats[:3]
