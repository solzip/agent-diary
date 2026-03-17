"""Tests for i18n.py — get_label Korean/English, missing keys."""

from claude_diary.i18n import get_label, LABELS


class TestGetLabelKorean:
    """Test Korean label retrieval."""

    def test_title_korean(self):
        assert get_label("title", "ko") == "작업일지"

    def test_task_requests_korean(self):
        assert get_label("task_requests", "ko") == "작업 요청"

    def test_files_created_korean(self):
        assert get_label("files_created", "ko") == "생성된 파일"

    def test_files_modified_korean(self):
        assert get_label("files_modified", "ko") == "수정된 파일"

    def test_summary_korean(self):
        assert get_label("summary", "ko") == "작업 요약"

    def test_weekdays_korean_is_list(self):
        result = get_label("weekdays", "ko")
        assert isinstance(result, list)
        assert len(result) == 7
        assert result[0] == "월"

    def test_cli_message_korean(self):
        assert "결과" in get_label("cli_no_results", "ko")


class TestGetLabelEnglish:
    """Test English label retrieval."""

    def test_title_english(self):
        assert get_label("title", "en") == "Work Diary"

    def test_task_requests_english(self):
        assert get_label("task_requests", "en") == "Task Requests"

    def test_files_created_english(self):
        assert get_label("files_created", "en") == "Files Created"

    def test_files_modified_english(self):
        assert get_label("files_modified", "en") == "Files Modified"

    def test_summary_english(self):
        assert get_label("summary", "en") == "Work Summary"

    def test_weekdays_english_is_list(self):
        result = get_label("weekdays", "en")
        assert isinstance(result, list)
        assert len(result) == 7
        assert result[0] == "Mon"

    def test_cli_message_english(self):
        assert "No results" in get_label("cli_no_results", "en")


class TestGetLabelMissingKey:
    """Test behavior with missing/unknown keys."""

    def test_missing_key_returns_key_itself(self):
        result = get_label("nonexistent_key", "ko")
        assert result == "nonexistent_key"

    def test_missing_key_english(self):
        result = get_label("totally_unknown", "en")
        assert result == "totally_unknown"

    def test_empty_string_key(self):
        result = get_label("", "ko")
        assert result == ""

    def test_missing_key_with_special_chars(self):
        result = get_label("key-with-dashes", "ko")
        assert result == "key-with-dashes"

    def test_missing_key_returns_same_for_both_langs(self):
        assert get_label("xyz", "ko") == get_label("xyz", "en") == "xyz"


class TestGetLabelFallback:
    """Test language fallback behavior."""

    def test_unknown_language_falls_back_to_korean(self):
        result = get_label("title", "ja")
        assert result == "작업일지"

    def test_none_language_falls_back_to_korean(self):
        result = get_label("title", None)
        assert result == "작업일지"

    def test_empty_language_falls_back_to_korean(self):
        result = get_label("title", "")
        assert result == "작업일지"

    def test_default_language_is_korean(self):
        result = get_label("title")
        assert result == "작업일지"

    def test_unsupported_lang_code(self):
        result = get_label("files_modified", "fr")
        assert result == "수정된 파일"  # Falls back to Korean


class TestLabelsStructure:
    """Test LABELS dict structure integrity."""

    def test_both_languages_present(self):
        assert "ko" in LABELS
        assert "en" in LABELS

    def test_same_keys_in_both_languages(self):
        ko_keys = set(LABELS["ko"].keys())
        en_keys = set(LABELS["en"].keys())
        assert ko_keys == en_keys, f"Key mismatch: ko-only={ko_keys - en_keys}, en-only={en_keys - ko_keys}"

    def test_no_empty_values_in_korean(self):
        for key, value in LABELS["ko"].items():
            if isinstance(value, str):
                assert len(value) > 0, f"Empty value for ko.{key}"

    def test_no_empty_values_in_english(self):
        for key, value in LABELS["en"].items():
            if isinstance(value, str):
                # weekday_suffix is allowed to be empty in English
                if key == "weekday_suffix":
                    continue
                assert len(value) > 0, f"Empty value for en.{key}"

    def test_weekdays_length_consistent(self):
        assert len(LABELS["ko"]["weekdays"]) == len(LABELS["en"]["weekdays"]) == 7
