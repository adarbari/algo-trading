"""Open a storage backend from a URL, and the config store from a directory.

Callers pass both explicitly (``algotrade.config.env`` resolves them from the environment);
storage never reads environment variables.
"""

from pathlib import Path
from urllib.parse import urlparse

from algotrade.core.errors import ConfigurationError
from algotrade.storage.backends.config_files import FileConfigStore
from algotrade.storage.backends.local import LocalBackend
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.config_store import ConfigStore
from algotrade.storage.interfaces import Backend


def open_backend(url: str) -> Backend:
    """``file://<path>`` (relative paths allowed) or ``memory://``."""
    parsed = urlparse(url)
    if parsed.scheme == "memory":
        return MemoryBackend()
    if parsed.scheme == "file":
        return LocalBackend(Path(parsed.netloc + parsed.path).expanduser())
    raise ConfigurationError(f"unsupported storage URL {url!r} (expected file:// or memory://)")


def open_config_store(directory: str | Path) -> ConfigStore:
    """TOML config files under ``directory`` (``config.env.config_dir()`` by default)."""
    return FileConfigStore(Path(directory))
