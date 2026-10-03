"""Pick a storage backend from a URL (``ALGOTRADE_DATA_URL``)."""

import os
from pathlib import Path
from urllib.parse import urlparse

from algotrade.core.errors import ConfigurationError
from algotrade.storage.backends.local import LocalBackend
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.interfaces import Backend

ENV_VAR = "ALGOTRADE_DATA_URL"
DEFAULT_URL = "file://./var/data"


def open_backend(url: str | None = None) -> Backend:
    """``file://<path>`` (relative paths allowed) or ``memory://``."""
    url = url or os.environ.get(ENV_VAR, DEFAULT_URL)
    parsed = urlparse(url)
    if parsed.scheme == "memory":
        return MemoryBackend()
    if parsed.scheme == "file":
        return LocalBackend(Path(parsed.netloc + parsed.path).expanduser())
    raise ConfigurationError(f"unsupported storage URL {url!r} (expected file:// or memory://)")
