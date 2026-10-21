"""Local release store: releases on the volume of the data root, beside ``tables/``.

Layout under ``<root>/serving`` (an internal detail)::

    CURRENT                         {"manifest_hash", "release_id"}: the release served
    releases/<release_id>/          manifest.json + <table>.parquet, appears whole at seal
    drafts/<release_id>~<token>/    a build in progress (invisible to every reader)

A seal fsyncs every file and the draft directory, then renames the directory into
``releases/`` (one atomic step) and fsyncs ``releases/``: a crash leaves a draft, never half a
release. ``promote`` writes CURRENT to a temp file, fsyncs it, ``os.replace``s it over the old
one and fsyncs ``serving/``: readers see the old release or the new one.
"""

import json
import os
import secrets
import shutil
import time
from collections.abc import Callable
from pathlib import Path

from algotrade.storage.backends.local_index import atomic_write
from algotrade.storage.backends.release.base import DRAFT_TTL_S, ReleaseStoreBase
from algotrade.storage.backends.release.interfaces import Draft, ReleaseCorruptError
from algotrade.storage.backends.release.manifest import MAX_RELEASE_BYTES, Manifest
from algotrade.storage.tables.interfaces import TableStore

MANIFEST = "manifest.json"
CURRENT = "CURRENT"


def _fsync(path: Path) -> None:
    """Flush a file, or a directory (its entries), to disk."""
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


class LocalReleaseStore(ReleaseStoreBase):
    def __init__(
        self,
        root: Path,
        tables: TableStore,
        max_bytes: int = MAX_RELEASE_BYTES,
        draft_ttl_s: float = DRAFT_TTL_S,
        free: Callable[[], int] | None = None,
    ) -> None:
        super().__init__(tables, max_bytes, draft_ttl_s, free)
        self.root = root / "serving"

    def _folder(self, release: str) -> Path:
        return self.root / "releases" / release

    def _draft_folder(self, release: str, token: str) -> Path:
        return self.root / "drafts" / f"{release}~{token}"

    def _disk_free(self) -> int:
        probe = self.root
        while not probe.exists() and probe != probe.parent:
            probe = probe.parent
        return shutil.disk_usage(probe).free

    def _draft_open(self, draft: Draft) -> None:
        self._draft_folder(draft.release_id, draft.token).mkdir(parents=True, exist_ok=True)

    def _draft_put(self, draft: Draft, name: str, data: bytes) -> None:
        atomic_write(self._draft_folder(draft.release_id, draft.token) / f"{name}.parquet", data)

    def _draft_files(self, draft: Draft) -> dict[str, bytes]:
        folder = self._draft_folder(draft.release_id, draft.token)
        return {p.stem: p.read_bytes() for p in sorted(folder.glob("*.parquet"))}

    def _draft_delete(self, release: str, token: str) -> None:
        shutil.rmtree(self._draft_folder(release, token), ignore_errors=True)

    def _drafts(self) -> list[tuple[str, str, float]]:
        base = self.root / "drafts"
        if not base.exists():
            return []
        now = time.time()
        found = []
        for folder in base.iterdir():
            release, _, token = folder.name.partition("~")
            found.append((release, token, now - folder.stat().st_mtime))
        return found

    def _publish(self, draft: Draft, manifest: Manifest) -> None:
        folder = self._draft_folder(draft.release_id, draft.token)
        atomic_write(folder / MANIFEST, manifest.to_json())
        for path in folder.iterdir():
            _fsync(path)
        _fsync(folder)
        target = self._folder(draft.release_id)
        target.parent.mkdir(parents=True, exist_ok=True)
        folder.rename(target)  # the one step that makes the release appear
        _fsync(target.parent)

    def _delete_release(self, release: str) -> None:
        shutil.rmtree(self._folder(release), ignore_errors=True)

    def _sealed(self) -> tuple[dict[str, Manifest], list[str]]:
        base = self.root / "releases"
        found: dict[str, Manifest] = {}
        bad: list[str] = []
        for folder in sorted(base.iterdir()) if base.exists() else []:
            try:
                found[folder.name] = Manifest.from_json((folder / MANIFEST).read_bytes())
            except (ReleaseCorruptError, FileNotFoundError):
                bad.append(folder.name)
        return found, bad

    def _manifest(self, release: str) -> Manifest | None:
        try:
            return Manifest.from_json((self._folder(release) / MANIFEST).read_bytes())
        except FileNotFoundError:
            return None

    def _loader(self, release: str) -> Callable[[str], bytes]:
        folder = self._folder(release)

        def load(name: str) -> bytes:
            return (folder / f"{name}.parquet").read_bytes()

        return load

    def _read_current(self) -> tuple[str, str] | None:
        try:
            named = json.loads((self.root / CURRENT).read_text())
            return str(named["release_id"]), str(named["manifest_hash"])
        except FileNotFoundError:
            return None
        except (ValueError, KeyError, TypeError) as exc:
            raise ReleaseCorruptError(f"CURRENT is unreadable: {exc}") from exc

    def _write_current(self, release: str, manifest_hash: str) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            {"manifest_hash": manifest_hash, "release_id": release}, sort_keys=True
        ).encode()
        temp = self.root / f".{CURRENT}.{secrets.token_hex(4)}.tmp"
        try:
            with temp.open("wb") as fh:
                fh.write(payload)
                fh.flush()
                os.fsync(fh.fileno())
            temp.replace(self.root / CURRENT)
        except BaseException:
            temp.unlink(missing_ok=True)
            raise
        _fsync(self.root)
