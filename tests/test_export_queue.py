"""`.export_queue.json` holds work that has not been delivered anywhere yet.

It is the fifth state file kept beside the diary and the only one that never
got what the other four have: a lock, an atomic write, and a refusal to
replace an unreadable file with an empty one. Measured before the fix, a
truncated queue of twenty came back holding one entry, and forty concurrent
hooks landed twenty-three.
"""

import json
import os
import subprocess
import sys

from claude_diary.exporters.loader import (
    _load_queue,
    _queue_failed,
    _write_queue,
    queue_path_for,
    retry_queued,
)


def _write_raw(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _items(n, exporter="notion"):
    return [{"timestamp": "2026-08-13T10:00:0%d" % i, "exporter": exporter,
             "entry_data": {}, "error": "boom", "retries": 0} for i in range(n)]


class TestAnUnreadableQueueIsNotDeleted:
    def test_a_truncated_queue_is_kept_alongside(self, tmp_path):
        qp = queue_path_for(str(tmp_path))
        raw = json.dumps(_items(20), indent=2)
        _write_raw(qp, raw[: len(raw) // 2])

        _queue_failed(str(tmp_path), "notion", {"date": "2026-08-13"}, "boom")

        preserved = list(tmp_path.glob("*.corrupt"))
        assert preserved, "the only copy of twenty queued exports was overwritten"
        assert preserved[0].read_text(encoding="utf-8") == raw[: len(raw) // 2]

    def test_it_says_so(self, tmp_path, caplog):
        qp = queue_path_for(str(tmp_path))
        _write_raw(qp, "{not json")
        _load_queue(qp)
        assert any("unreadable" in r.message.lower() for r in caplog.records)

    def test_the_new_export_is_still_recorded(self, tmp_path):
        """Preserving the old file must not cost the entry being written."""
        qp = queue_path_for(str(tmp_path))
        _write_raw(qp, "{not json")
        _queue_failed(str(tmp_path), "notion", {"date": "2026-08-13"}, "boom")
        assert len(json.load(open(qp, encoding="utf-8"))) == 1

    def test_a_queue_of_the_wrong_shape_is_also_kept(self, tmp_path):
        """`json.load` succeeds on a dict, so parsing is not the only way this
        file can be wrong, and a dict is no less someone's data than a
        truncated list is. The search index already draws the line here."""
        qp = queue_path_for(str(tmp_path))
        _write_raw(qp, '{"exporter": "notion"}')
        _queue_failed(str(tmp_path), "notion", {"date": "2026-08-13"}, "boom")
        assert list(tmp_path.glob("*.corrupt"))
        assert len(json.load(open(qp, encoding="utf-8"))) == 1

    def test_a_readable_queue_is_left_alone(self, tmp_path):
        qp = queue_path_for(str(tmp_path))
        _write_queue(qp, _items(3))
        _queue_failed(str(tmp_path), "notion", {"date": "2026-08-13"}, "boom")
        assert len(json.load(open(qp, encoding="utf-8"))) == 4
        assert not list(tmp_path.glob("*.corrupt"))


class TestTheWriteIsAtomic:
    def test_a_failed_write_leaves_the_old_queue_intact(self, tmp_path, monkeypatch):
        """The truncation the test above recovers from is what this prevents."""
        qp = queue_path_for(str(tmp_path))
        _write_queue(qp, _items(5))
        before = open(qp, encoding="utf-8").read()

        def refuse(src, dst):
            raise OSError("no")

        monkeypatch.setattr(os, "replace", refuse)
        _write_queue(qp, _items(9))

        assert open(qp, encoding="utf-8").read() == before

    def test_the_temp_file_is_cleaned_up(self, tmp_path, monkeypatch):
        qp = queue_path_for(str(tmp_path))
        monkeypatch.setattr(os, "replace", lambda s, d: (_ for _ in ()).throw(OSError("no")))
        _write_queue(qp, _items(2))
        assert not list(tmp_path.glob("*.tmp*"))


class TestConcurrentHooks:
    """Two sessions ending together is the normal case for this tool."""

    def test_every_queued_export_arrives(self, tmp_path):
        worker = tmp_path / "w.py"
        worker.write_text(
            "import sys\n"
            "from claude_diary.exporters.loader import _queue_failed\n"
            "_queue_failed(sys.argv[1], 'notion', {'project': sys.argv[2]}, 'boom')\n",
            encoding="utf-8",
        )
        n = 12
        procs = [subprocess.Popen([sys.executable, str(worker), str(tmp_path), str(i)],
                                  stderr=subprocess.DEVNULL) for i in range(n)]
        for p in procs:
            p.wait()

        queue = json.load(open(queue_path_for(str(tmp_path)), encoding="utf-8"))
        assert len(queue) == n

    def test_it_uses_a_lock(self, tmp_path, monkeypatch):
        """Separate processes, not threads: threads share a file object and
        pass a test the real thing fails.  This one guards the wiring so the
        expensive test above is not the only thing holding it.
        """
        import claude_diary.exporters.loader as loader

        locked = []
        real = loader.FileLock

        class Watched(real):
            def __enter__(self):
                locked.append(self.lock_path)
                return super().__enter__()

        monkeypatch.setattr(loader, "FileLock", Watched)
        _queue_failed(str(tmp_path), "notion", {"date": "2026-08-13"}, "boom")
        assert locked == [queue_path_for(str(tmp_path)) + ".lock"]


class TestRetryDoesNotDropWhatArrivedMeanwhile:
    def test_an_export_queued_during_a_retry_survives(self, tmp_path, monkeypatch):
        """The exporters run without the lock held, because one slow retry
        must not stall a hook that only wants to add a line. So the write back
        has to merge rather than replace.
        """
        diary = str(tmp_path)
        qp = queue_path_for(diary)
        _write_queue(qp, _items(1))

        class Slow:
            def export(self, entry_data):
                # A hook lands while this retry is in flight.
                _queue_failed(diary, "notion", {"project": "late"}, "boom")
                return True

        monkeypatch.setattr(
            "claude_diary.exporters.loader.load_exporters",
            lambda config: [("notion", Slow())],
        )
        retry_queued({}, diary)

        remaining = json.load(open(qp, encoding="utf-8"))
        projects = [i["entry_data"].get("project") for i in remaining]
        assert "late" in projects, "the export queued mid-retry was dropped"

    def test_a_fully_drained_queue_is_removed(self, tmp_path, monkeypatch):
        diary = str(tmp_path)
        qp = queue_path_for(diary)
        _write_queue(qp, _items(2))

        class Ok:
            def export(self, entry_data):
                return True

        monkeypatch.setattr(
            "claude_diary.exporters.loader.load_exporters",
            lambda config: [("notion", Ok())],
        )
        retry_queued({}, diary)
        assert not os.path.exists(qp)

    def test_a_corrupt_queue_does_not_stall_retries_forever(self, tmp_path, monkeypatch):
        """Returning early left the bad file in place, so every later session
        took the same early return and nothing was ever retried again."""
        diary = str(tmp_path)
        qp = queue_path_for(diary)
        _write_raw(qp, "{not json")

        monkeypatch.setattr(
            "claude_diary.exporters.loader.load_exporters", lambda config: []
        )
        retry_queued({}, diary)

        assert list(tmp_path.glob("*.corrupt")), "the bad queue was left to block every session"
