"""The current serving release as one request sees it (ADR 0077 decisions 5, 23).

``resolve_current`` reads CURRENT once and returns the release the reads of this request follow:
its id, session and the commit sequence ``X`` its tables were built at (a reader pinned there is
the release), or ``None`` for the live path. ``None`` whenever the release cannot be trusted:
no CURRENT, a format this code does not read, a manifest or CURRENT that does not match its
hash, a release pruned under CURRENT, or a destructive operation (purge, remove-runs, drop,
direct write) on the store since it was built (``destructive_epoch``). Never raises for those:
the caller answers live, uncached.
"""

from dataclasses import dataclass
from datetime import date
from urllib.parse import urlparse

from algotrade.data import StoreReader
from algotrade.storage.backends.release.interfaces import ReleaseError, ReleaseStore
from algotrade.storage.backends.runs.run_selection import StaleSnapshotError
from algotrade.storage.factory import open_backend, open_release_store

SUPPORTED_FORMATS = frozenset(
    {1}
)  # the formats this code reads (``services.serving.build.FORMAT``)


@dataclass(frozen=True)
class CurrentRelease:
    """The release a request follows: reads pinned at ``seq`` for ``session``."""

    release_id: str
    session: date
    seq: int
    manifest_hash: str


def resolve_current(reader: StoreReader, releases: ReleaseStore) -> CurrentRelease | None:
    """The current release if it can be trusted now, else ``None`` (see the module docstring)."""
    try:
        current = releases.current_release()
    except ReleaseError:
        return None
    if current is None:
        return None
    manifest = current.manifest
    if manifest.format not in SUPPORTED_FORMATS:
        return None
    if manifest.destructive_epoch != reader.destructive_epoch():
        return None
    return CurrentRelease(
        manifest.release_id,
        date.fromisoformat(manifest.session),
        manifest.seq,
        manifest.content_hash,
    )


def releases_at(data_url: str) -> ReleaseStore | None:
    """The serving release store beside the store at ``data_url`` (a ``file://`` store: the
    ingestion's serve-release job writes it; stateless over the data root), ``None`` for a store
    that has none (``memory://``: a test passes its own)."""
    if urlparse(data_url).scheme != "file":
        return None
    return open_release_store(data_url, open_backend(data_url))


__all__ = [
    "SUPPORTED_FORMATS",
    "CurrentRelease",
    "ReleaseStore",
    "StaleSnapshotError",  # the lost-pin error a pinned read raises, for the API's fallback
    "releases_at",
    "resolve_current",
]
