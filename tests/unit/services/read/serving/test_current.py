"""``resolve_current``: the release a request follows, or None for the live path."""

from datetime import date
from pathlib import Path

import pyarrow as pa

from algotrade.data import StoreReader
from algotrade.services.read.serving.current import SUPPORTED_FORMATS, resolve_current
from algotrade.storage.backends.local import LocalBackend
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.backends.release.interfaces import InputPartitions
from algotrade.storage.backends.release.local import LocalReleaseStore
from algotrade.storage.backends.release.memory import MemoryReleaseStore

S = date(2026, 10, 2)


def sealed(backend: MemoryBackend, store: MemoryReleaseStore, fmt: int = 1) -> str:
    x = backend.tables.visible_seq()
    draft = store.begin(S, x, fmt)
    store.write(draft, "session", pa.table({"date": [S.isoformat()]}))
    return store.seal(draft, [InputPartitions("bars/1d", {S: x})], "abc").release_id


def test_no_current_release_is_the_live_path() -> None:
    backend = MemoryBackend()
    assert resolve_current(StoreReader(backend), MemoryReleaseStore(backend.tables)) is None


def test_a_promoted_release_resolves_with_its_session_and_sequence() -> None:
    backend = MemoryBackend()
    store = MemoryReleaseStore(backend.tables)
    release_id = sealed(backend, store)
    assert resolve_current(StoreReader(backend), store) is None  # sealed, not promoted
    store.promote(release_id)
    found = resolve_current(StoreReader(backend), store)
    assert found is not None and found.release_id == release_id and found.session == S
    assert found.seq == backend.tables.visible_seq()


def test_an_unsupported_format_is_the_live_path() -> None:
    backend = MemoryBackend()
    store = MemoryReleaseStore(backend.tables)
    other = max(SUPPORTED_FORMATS) + 1
    store.promote(sealed(backend, store, other))
    assert resolve_current(StoreReader(backend), store) is None


def test_a_destructive_operation_since_the_build_is_the_live_path() -> None:
    backend = MemoryBackend()
    store = MemoryReleaseStore(backend.tables)
    store.promote(sealed(backend, store))
    backend.tables.drop("rollups/instrument/other@v1")
    assert resolve_current(StoreReader(backend), store) is None


def test_a_current_naming_a_pruned_or_changed_release_is_the_live_path() -> None:
    backend = MemoryBackend()
    store = MemoryReleaseStore(backend.tables)
    release_id = sealed(backend, store)
    store.promote(release_id)
    store.state.current = (release_id, "not the manifest hash")
    assert resolve_current(StoreReader(backend), store) is None
    store.state.current = ("2020-01-01.1.f1", "x")
    assert resolve_current(StoreReader(backend), store) is None


def test_a_tampered_manifest_never_raises_and_is_the_live_path(tmp_path: Path) -> None:
    backend = LocalBackend(tmp_path / "data")
    store = LocalReleaseStore(tmp_path / "data", backend.tables)
    x = backend.tables.visible_seq()
    draft = store.begin(S, x, 1)
    store.write(draft, "session", pa.table({"date": [S.isoformat()]}))
    release_id = store.seal(draft, [InputPartitions("bars/1d", {S: x})], "abc").release_id
    store.promote(release_id)
    assert resolve_current(StoreReader(backend), store) is not None
    manifest = tmp_path / "data" / "serving" / "releases" / release_id / "manifest.json"
    manifest.write_bytes(manifest.read_bytes().replace(b'"abc"', b'"evil"'))
    assert resolve_current(StoreReader(backend), store) is None
