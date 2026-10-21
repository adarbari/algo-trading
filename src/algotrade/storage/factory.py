"""Open a storage backend (and the text cache beside it) from a URL, and the config store from
a directory.

Callers pass both explicitly (``algotrade.config.env`` resolves them from the environment);
storage never reads environment variables.
"""

from pathlib import Path
from urllib.parse import urlparse

from algotrade.core.model.errors import ConfigurationError
from algotrade.storage.backends.local import LocalBackend
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.backends.release.interfaces import ReleaseReport, ReleaseStore
from algotrade.storage.backends.release.local import LocalReleaseStore
from algotrade.storage.backends.release.memory import MemoryReleaseStore
from algotrade.storage.backends.text_cache import LocalTextCache, MemoryTextCache
from algotrade.storage.configs.files import FileConfigStore
from algotrade.storage.configs.store import ConfigStore
from algotrade.storage.tables.interfaces import Backend


def open_backend(url: str) -> Backend:
    """``file://<path>`` (relative paths allowed) or ``memory://``."""
    parsed = urlparse(url)
    if parsed.scheme == "memory":
        return MemoryBackend()
    if parsed.scheme == "file":
        return LocalBackend(Path(parsed.netloc + parsed.path).expanduser())
    raise ConfigurationError(f"unsupported storage URL {url!r} (expected file:// or memory://)")


def open_release_store(url: str, backend: Backend) -> ReleaseStore:
    """The serving release store (ADR 0077) of the store at ``url``: ``serving/`` in the data root,
    pinning through ``backend``'s tables (a memory store needs the backend it pins in)."""
    parsed = urlparse(url)
    if parsed.scheme == "memory":
        return MemoryReleaseStore(backend.tables)
    if parsed.scheme == "file":
        return LocalReleaseStore(Path(parsed.netloc + parsed.path).expanduser(), backend.tables)
    raise ConfigurationError(f"unsupported storage URL {url!r} (expected file:// or memory://)")


def release_report(url: str) -> ReleaseReport:
    """The pins, releases and retained-version disk of the store at ``url`` for ``make status`` and
    ``make doctor`` (read-only; a ``file://`` store only: a memory store has nothing durable)."""
    return open_release_store(url, open_backend(url)).report()


def open_text_cache(url: str) -> LocalTextCache | MemoryTextCache:
    """The cache of text answers beside the store at ``url``: ``cache/explanations`` next to
    the data root (``file://./var/data`` -> ``./var/cache/explanations``), or in memory."""
    parsed = urlparse(url)
    if parsed.scheme == "memory":
        return MemoryTextCache()
    if parsed.scheme == "file":
        data_root = Path(parsed.netloc + parsed.path).expanduser()
        return LocalTextCache.beside(data_root)
    raise ConfigurationError(f"unsupported storage URL {url!r} (expected file:// or memory://)")


def open_config_store(directory: str | Path) -> ConfigStore:
    """TOML config files under ``directory`` (``config.env.config_dir()`` by default)."""
    return FileConfigStore(
        Path(directory)
    )  # tests over the repo config build FileConfigStore(..., local=False)
