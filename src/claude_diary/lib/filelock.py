"""A small cross-platform file lock, standard library only.

The Stop Hook runs once per session ending, as its own process. Two sessions
finishing at the same moment means two processes writing the same day file,
and measured on twelve concurrent writers that lost three entries outright
and left the session count reading four.

`fcntl` and `msvcrt` would each work on one platform and behave differently
on the other. A lock file created with `O_CREAT | O_EXCL` is one syscall,
identical everywhere, and needs nothing outside the standard library — which
matters here, because the core ships with no dependencies.

The failure mode a lock file has that an advisory lock does not is the stale
lock: a process dies holding it and everyone after waits forever. So the
lock records its pid and creation time, and a lock older than
`STALE_AFTER_SECONDS` is broken rather than waited on. Losing an entry is
the thing being fixed; hanging the hook forever would be worse.
"""

from __future__ import annotations

import errno
import os
import time
from typing import Optional

from claude_diary.log import get_logger

logger = get_logger("claude_diary.lib.filelock")

# Long enough for a slow disk, short enough that a crashed hook does not
# block the next session for a noticeable time.
STALE_AFTER_SECONDS = 30.0
ACQUIRE_TIMEOUT_SECONDS = 10.0
_POLL_SECONDS = 0.01

# Outcomes of one acquisition attempt. `_HELD` is worth waiting on;
# `_UNAVAILABLE` is not, and telling them apart is the difference between a
# hook that pauses briefly and one that pauses for the whole timeout.
_ACQUIRED = "acquired"
_HELD = "held"
_UNAVAILABLE = "unavailable"


class FileLock:
    """Exclusive lock keyed on a path. Use as a context manager.

    Never raises on failure to acquire: the diary is best-effort, and a
    missed lock must degrade to the previous unlocked behaviour rather than
    lose the entry to an exception. `acquired` says which happened.
    """

    def __init__(self, target_path: str, timeout: float = ACQUIRE_TIMEOUT_SECONDS):
        self.lock_path = "%s.lock" % target_path
        self.timeout = timeout
        self.acquired = False

    def __enter__(self) -> "FileLock":
        deadline = time.monotonic() + self.timeout
        while True:
            state = self._try_acquire()
            if state is _ACQUIRED:
                self.acquired = True
                return self
            if state is _UNAVAILABLE:
                # The directory will not accept a lock file at all, so no
                # amount of waiting changes the answer. Waiting anyway cost
                # the full timeout per lock — measured at 20s of a Stop Hook
                # holding up the end of a session, on a diary directory that
                # had simply lost its write permission.
                logger.warning(
                    "Cannot create %s (directory not writable); "
                    "continuing without the lock", self.lock_path,
                )
                return self
            if self._break_if_stale():
                continue
            if time.monotonic() >= deadline:
                logger.warning(
                    "Could not lock %s within %.0fs; writing without it",
                    self.lock_path, self.timeout,
                )
                return self
            time.sleep(_POLL_SECONDS)

    def __exit__(self, exc_type, exc, tb) -> None:
        if not self.acquired:
            return
        try:
            os.unlink(self.lock_path)
        except OSError:
            pass
        self.acquired = False

    def _try_acquire(self) -> str:
        """Returns one of the three module-level states."""
        try:
            fd = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except OSError as e:
            if e.errno == errno.EEXIST:
                # Somebody holds it. That clears on its own, so wait.
                return _HELD
            if e.errno in (errno.EACCES, errno.EPERM):
                # We cannot create the file at all. Waiting cannot fix this.
                return _UNAVAILABLE
            raise
        try:
            os.write(fd, ("%d %f" % (os.getpid(), time.time())).encode("utf-8"))
        finally:
            os.close(fd)
        return _ACQUIRED

    def _break_if_stale(self) -> bool:
        """Remove a lock left behind by a process that died holding it."""
        age = self._age()
        if age is None or age < STALE_AFTER_SECONDS:
            return False
        try:
            os.unlink(self.lock_path)
            logger.warning("Broke stale lock %s (%.0fs old)", self.lock_path, age)
            return True
        except OSError:
            return False

    def _age(self) -> Optional[float]:
        try:
            return max(0.0, time.time() - os.path.getmtime(self.lock_path))
        except OSError:
            return None
