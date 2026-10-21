"""The per-user config generation (ADR 0077 decisions 14-15): a durable counter that moves with
every user config write, so a cached answer keyed on it is never served from before the write.

A seqlock: made odd before the first file of a write changes and even after the last is durably
in place. A key reads it before the answer is computed and caches only an even value; an odd one
(a write in flight, or one that crashed) means *do not cache*, so a half-written config is slow,
never stale. Writes of one user are serialised by a lock file, so two writers never overlap and
the parity is exact. The file is ``users/<user>/.generation`` (written only here, a fitness
test)."""

import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from algotrade.storage.locks import FileLock, held

GENERATION_FILE = ".generation"
LOCK_FILE = ".generation.lock"


def is_stable(generation: int) -> bool:
    """Whether no write is in flight (or crashed) at ``generation``: only then may an answer be
    cached under it."""
    return generation % 2 == 0


def read_generation(user_dir: Path) -> int:
    """The counter under ``user_dir``; 0 when the user has never written."""
    try:
        return int((user_dir / GENERATION_FILE).read_text().strip() or "0")
    except (FileNotFoundError, ValueError):
        return 0


def _store(user_dir: Path, value: int) -> None:
    fd, name = tempfile.mkstemp(dir=user_dir, prefix=f"{GENERATION_FILE}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(str(value))
            fh.flush()
            os.fsync(fh.fileno())
        Path(name).replace(user_dir / GENERATION_FILE)
    finally:
        Path(name).unlink(missing_ok=True)


@contextmanager
def writing(user_dir: Path) -> Iterator[None]:
    """Hold the user's write lock and keep the counter odd for the body, even after it (also
    when the body raises: its files are each atomic, and a stuck odd value would stop caching).
    The lock is a ``flock`` per open file, so it also excludes the threads of this process."""
    user_dir.mkdir(parents=True, exist_ok=True)
    with held(FileLock(user_dir / LOCK_FILE)):
        before = read_generation(user_dir)
        odd = before + 1 if is_stable(before) else before + 2  # a crash left it odd
        _store(user_dir, odd)
        try:
            yield
        finally:
            _store(user_dir, odd + 1)
