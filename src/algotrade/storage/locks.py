"""Exclusive locks shared across threads and processes (ADR 0019: storage owns locks).

- ``FileLock``: ``fcntl.flock`` on a lock file, so separate processes (two CLI runs, a
  launchd job and a manual run) exclude each other; a thread lock on top makes one
  ``FileLock`` object safe to share between threads too.
- ``ThreadLock``: the in-process equivalent, for backends that live in one process (memory).

Both implement ``Lock``. Backends hand them out by name (``Backend.lock``); where the lock
file lives is the backend's business, like every other path.
"""

import fcntl
import os
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Protocol


class Lock(Protocol):
    def acquire(self, wait: bool = True) -> bool:
        """Take the lock; with ``wait=False`` return ``False`` at once if someone holds it."""
        ...

    def release(self) -> None: ...


class ThreadLock:
    def __init__(self) -> None:
        self._lock = threading.Lock()

    def acquire(self, wait: bool = True) -> bool:
        return self._lock.acquire(blocking=wait)

    def release(self) -> None:
        self._lock.release()


class FileLock:
    """An exclusive ``flock`` on ``path`` (created on first use, never deleted)."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._thread = threading.Lock()
        self._fd: int | None = None

    def acquire(self, wait: bool = True) -> bool:
        if not self._thread.acquire(blocking=wait):
            return False
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o644)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX if wait else fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                os.close(fd)
                self._thread.release()
                return False
        except BaseException:
            self._thread.release()
            raise
        self._fd = fd
        return True

    def release(self) -> None:
        fd, self._fd = self._fd, None
        if fd is not None:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
        self._thread.release()


@contextmanager
def held(lock: Lock, wait: bool = True) -> Iterator[bool]:
    """Hold ``lock`` for the block; yields whether it was taken (``wait=False`` tries once)."""
    taken = lock.acquire(wait=wait)
    try:
        yield taken
    finally:
        if taken:
            lock.release()
