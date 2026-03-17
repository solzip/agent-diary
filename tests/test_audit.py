"""Tests for audit log system."""

import json
import os

from claude_diary.lib.audit import log_entry, read_audit_log, verify_checksum


class TestAuditLog:
    def test_log_creates_file(self, tmp_path):
        diary_dir = str(tmp_path)
        log_entry(diary_dir, "session-001", "/tmp/transcript.jsonl", ["/tmp/diary.md"])
        audit_file = tmp_path / ".audit.jsonl"
        assert audit_file.exists()

    def test_log_content(self, tmp_path):
        diary_dir = str(tmp_path)
        log_entry(diary_dir, "session-001", "/tmp/t.jsonl", ["/tmp/d.md"], secrets_masked=3)
        entries = read_audit_log(diary_dir)
        assert len(entries) == 1
        assert entries[0]["session_id"] == "session-001"
        assert entries[0]["secrets_masked"] == 3
        assert entries[0]["checksum"].startswith("sha256:")

    def test_multiple_entries(self, tmp_path):
        diary_dir = str(tmp_path)
        log_entry(diary_dir, "s1", "", [], secrets_masked=0)
        log_entry(diary_dir, "s2", "", [], secrets_masked=1)
        log_entry(diary_dir, "s3", "", [], secrets_masked=2)
        entries = read_audit_log(diary_dir, limit=2)
        assert len(entries) == 2
        assert entries[0]["session_id"] == "s3"  # newest first

    def test_read_empty(self, tmp_path):
        entries = read_audit_log(str(tmp_path))
        assert entries == []


class TestVerifyChecksum:
    def test_first_run_valid(self, tmp_path):
        is_valid, current, last = verify_checksum(str(tmp_path))
        assert is_valid is True
        assert current.startswith("sha256:")
        assert last is None

    def test_consistent_checksum(self, tmp_path):
        diary_dir = str(tmp_path)
        log_entry(diary_dir, "s1", "", [])
        is_valid, current, last = verify_checksum(diary_dir)
        assert is_valid is True
        assert current == last
