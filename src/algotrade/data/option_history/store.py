"""Open the option-history store (ADR 0084): its own root, marked by a sentinel file.

The local backend's lock creates missing directories, so a path whose drive is not mounted would
quietly fill the boot disk. A history root therefore has to exist and hold ``SENTINEL`` before
the backend opens; ``init_root`` writes it (the owner's one explicit act) after probing that the
drive can take a file lock and an atomic rename (ADR 0022).
"""

import os
from pathlib import Path
from urllib.parse import urlparse

from algotrade.core.model.errors import ConfigurationError
from algotrade.storage.factory import open_backend
from algotrade.storage.locks import FileLock
from algotrade.storage.tables.interfaces import Backend

SENTINEL = ".algotrade-option-history"


class HistoryUnavailableError(ConfigurationError):
    """The option history is not there: no URL, a directory that is not mounted, or no sentinel."""


def root_path(url: str | None) -> Path | None:
    """The directory of a ``file://`` URL (``None`` for any other scheme, e.g. ``memory://``)."""
    if not url:
        raise HistoryUnavailableError(
            "ALGOTRADE_OPTION_HISTORY_URL is not set: point it at the history drive, "
            "e.g. file:///Volumes/<drive>/option-history"
        )
    parsed = urlparse(url)
    if parsed.scheme != "file":
        return None
    return Path(parsed.netloc + parsed.path).expanduser()


def open_history(url: str | None) -> Backend:
    """The history backend at ``url``; ``HistoryUnavailableError`` unless its directory exists
    and holds the sentinel (a ``memory://`` store, for tests, needs neither)."""
    path = root_path(url)
    if path is not None:
        if not path.is_dir():
            raise HistoryUnavailableError(f"{path} does not exist: is the drive mounted?")
        if not (path / SENTINEL).is_file():
            raise HistoryUnavailableError(
                f"{path} has no {SENTINEL}: run `option-history-import --init` once for a new drive"
            )
    assert url is not None
    return open_backend(url)


def init_root(url: str | None) -> Path:
    """Mark an existing directory as the history root, after proving it takes a file lock and an
    atomic rename. The directory is never created: a missing mount fails here."""
    path = root_path(url)
    if path is None:
        raise HistoryUnavailableError("only a file:// root can be initialised")
    if not path.is_dir():
        raise HistoryUnavailableError(f"{path} does not exist: is the drive mounted?")
    probe, moved = path / ".probe", path / ".probe-moved"
    lock = FileLock(path / ".probe.lock")
    if not lock.acquire(wait=False):
        raise HistoryUnavailableError(f"{path} does not take a file lock")
    try:
        with probe.open("wb") as handle:
            handle.write(b"x")
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        lock.release()
    (path / ".probe.lock").unlink(missing_ok=True)
    probe.replace(moved)
    moved.unlink()
    (path / SENTINEL).write_text("ALGOTRADE option history (ADR 0084)\n")
    return path
