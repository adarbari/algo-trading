"""The release store's rules, shared by the local and memory stores so they cannot disagree.

A subclass supplies the physical primitives (where draft files, sealed releases and CURRENT
live); everything that decides lives here: the free-space floor at ``begin``, the pin that
protects the build's inputs, the checks at ``seal`` (inputs not past the draft's sequence,
epoch unmoved, size ceiling), idempotent re-sealing, ``promote``'s epoch check, CURRENT's
verification against the manifest hash, and ``prune``'s unpinning of every pin no kept release
or live draft holds. Nothing here knows a path.

**Single writer.** One pin (``release-<id>``) serves every draft of an id, so ``begin``, ``seal``,
``abort``, ``promote`` and ``prune`` run only under the serve job's ``exclusive_run("serve")``
(the build job takes that lock around them); readers (``open``, ``current_release``,
``report``) need none. ``seal`` and ``promote`` still refuse a release whose pin is gone (a
draft pruned mid-build), so a lock slip cannot serve a partial release.
"""

import io
import logging
import re
import secrets
from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from datetime import date

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from algotrade.storage.backends.arrow import parquet_bytes
from algotrade.storage.backends.release.interfaces import (
    Draft,
    InputPartitions,
    Release,
    ReleaseCorruptError,
    ReleaseInvalidError,
    ReleaseNotFoundError,
    ReleaseReport,
    Reservation,
)
from algotrade.storage.backends.release.manifest import (
    MAX_RELEASE_BYTES,
    Manifest,
    TableInfo,
    release_id,
    room_needed,
    sha256,
)
from algotrade.storage.tables.interfaces import TableStore

log = logging.getLogger(__name__)
PIN_PREFIX = "release-"
DRAFT_TTL_S = 6 * 3600.0  # a draft this old is a build that died (the build restarts <= 3 times)
_NAME = re.compile(r"^[a-z][a-z0-9_]*$")


class StoredRelease:
    """A sealed release opened for reading: the manifest and a way to load one file's bytes."""

    def __init__(self, manifest: Manifest, load: Callable[[str], bytes]) -> None:
        self._manifest = manifest
        self._load = load

    @property
    def manifest(self) -> Manifest:
        return self._manifest

    def read(self, name: str) -> pa.Table:
        info = self._manifest.tables[name]  # KeyError: the release holds no such table
        try:
            data = self._load(name)
        except FileNotFoundError as gone:  # a prune deleted the release under an open reader
            raise ReleaseNotFoundError(self._manifest.release_id) from gone
        if sha256(data) != info.sha256:
            raise ReleaseCorruptError(f"{self._manifest.release_id}/{name} does not match its hash")
        return pq.read_table(io.BytesIO(data))


class ReleaseStoreBase(ABC):
    def __init__(
        self,
        tables: TableStore,
        max_bytes: int = MAX_RELEASE_BYTES,
        draft_ttl_s: float = DRAFT_TTL_S,
        free: Callable[[], int] | None = None,
    ) -> None:
        self._tables = tables
        self._max_bytes = max_bytes
        self._draft_ttl_s = draft_ttl_s
        self._free = free

    # ----------------------------------------------------------------- primitives

    @abstractmethod
    def _disk_free(self) -> int: ...

    @abstractmethod
    def _draft_open(self, draft: Draft) -> None: ...

    @abstractmethod
    def _draft_put(self, draft: Draft, name: str, data: bytes) -> None: ...

    @abstractmethod
    def _draft_files(self, draft: Draft) -> dict[str, bytes]: ...

    @abstractmethod
    def _draft_delete(self, release: str, token: str) -> None: ...

    @abstractmethod
    def _drafts(self) -> list[tuple[str, str, float]]:
        """``(release_id, token, age in seconds)`` of every unsealed draft."""

    @abstractmethod
    def _publish(self, draft: Draft, manifest: Manifest) -> None:
        """Make the draft's files and ``manifest`` a sealed release, durably and all at once."""

    @abstractmethod
    def _delete_release(self, release: str) -> None: ...

    @abstractmethod
    def _sealed(self) -> tuple[dict[str, Manifest], list[str]]:
        """The sealed releases' manifests by id, and the ids whose manifest is unreadable."""

    @abstractmethod
    def _manifest(self, release: str) -> Manifest | None:
        """One sealed release's manifest (``ReleaseCorruptError`` when it does not match its
        hash), ``None`` when there is no such release."""

    @abstractmethod
    def _loader(self, release: str) -> Callable[[str], bytes]: ...

    @abstractmethod
    def _read_stats(self) -> dict[str, int] | None:
        """What the last prune recorded (``pinned_bytes``), ``None`` before any."""

    @abstractmethod
    def _write_stats(self, stats: dict[str, int]) -> None: ...

    @abstractmethod
    def _read_current(self) -> tuple[str, str] | None: ...

    @abstractmethod
    def _write_current(self, release: str, manifest_hash: str) -> None: ...

    # ----------------------------------------------------------------- the protocol

    def free_bytes(self) -> int:
        return self._disk_free() if self._free is None else self._free()

    def _order(self, manifests: dict[str, Manifest]) -> list[str]:
        return sorted(manifests, key=lambda r: (manifests[r].session, manifests[r].seq, r))

    def releases(self) -> list[str]:
        return self._order(self._sealed()[0])

    def reserve(self, seq: int) -> Reservation:
        token = secrets.token_hex(4)
        epoch = self._tables.destructive_epoch()  # before the pin and before any read
        self._tables.pin(f"{PIN_PREFIX}pending-{token}", seq)
        return Reservation(token, seq, epoch)

    def drop_reservation(self, reservation: Reservation) -> None:
        self._tables.unpin(f"{PIN_PREFIX}pending-{reservation.token}")

    def begin(
        self, session: date, seq: int, fmt: int, reservation: Reservation | None = None
    ) -> Draft:
        manifests = self._sealed()[0]
        order = self._order(manifests)
        need = room_needed(manifests[order[-1]].total_bytes if order else 0)
        if (free := self.free_bytes()) < need:
            raise ReleaseInvalidError(f"free space {free} B is below the floor of {need} B")
        if reservation is not None and reservation.seq != seq:
            raise ReleaseInvalidError(f"the reservation is at {reservation.seq}, not {seq}")
        rid = release_id(session, seq, fmt)
        epoch = self._tables.destructive_epoch() if reservation is None else reservation.epoch
        draft = Draft(rid, session, seq, fmt, epoch, secrets.token_hex(4))
        self._tables.pin(PIN_PREFIX + rid, seq)  # before any file: a crash leaves a pin prune sees
        if reservation is not None:
            self.drop_reservation(reservation)
        self._draft_open(draft)
        return draft

    def write(self, draft: Draft, name: str, table: pa.Table) -> None:
        if not _NAME.match(name):
            raise ValueError(f"invalid release table name {name!r}")
        self._draft_put(draft, name, parquet_bytes(table))

    def _require_pin(self, release: str, seq: int) -> None:
        if self._tables.pins().get(PIN_PREFIX + release) != seq:
            raise ReleaseInvalidError(f"the pin of {release} is gone (pruned during the build?)")

    def write_frame(self, draft: Draft, name: str, frame: pd.DataFrame) -> None:
        """``write`` of a frame (callers outside storage hold no Arrow): the index is dropped and
        the pandas schema metadata too, so the bytes depend on the values alone."""
        table = pa.Table.from_pandas(frame, preserve_index=False).replace_schema_metadata(None)
        self.write(draft, name, table)

    def seal(self, draft: Draft, inputs: Sequence[InputPartitions], code_sha: str) -> Manifest:
        self._require_pin(draft.release_id, draft.seq)
        for item in inputs:
            for day, seq in item.partitions.items():
                if seq > draft.seq:
                    raise ReleaseInvalidError(
                        f"input {item.table} {day}: sequence {seq} is above the draft's {draft.seq}"
                    )
        if self._tables.destructive_epoch() != draft.epoch:
            raise ReleaseInvalidError("a destructive operation ran since the build began (epoch)")
        files = self._draft_files(draft)
        if not files:
            raise ReleaseInvalidError("a release holds at least one table")
        infos = {
            name: TableInfo(
                pq.ParquetFile(io.BytesIO(data)).metadata.num_rows, sha256(data), len(data)
            )
            for name, data in files.items()
        }
        manifest = Manifest(
            draft.fmt,
            draft.release_id,
            draft.session.isoformat(),
            draft.seq,
            draft.epoch,
            code_sha,
            tuple(inputs),
            infos,
        ).sealed()
        if manifest.total_bytes > self._max_bytes:
            raise ReleaseInvalidError(
                f"{manifest.total_bytes} B is over the ceiling of {self._max_bytes} B"
            )
        existing = self._manifest(draft.release_id)
        if existing is not None:
            if existing.content_hash == manifest.content_hash:  # the same build again
                self._draft_delete(draft.release_id, draft.token)
                return existing
            if existing.destructive_epoch != draft.epoch:
                self._delete_release(draft.release_id)  # built before a destructive operation
            elif existing.code_sha != code_sha:  # a rebuild after a deploy: the old one stands
                log.info("%s exists from code %s: kept over %s", draft.release_id,
                         existing.code_sha, code_sha)  # fmt: skip
                self._draft_delete(draft.release_id, draft.token)
                return existing
            else:  # the same code gave other bytes: a build that is not deterministic
                raise ReleaseInvalidError(f"{draft.release_id} exists with other content")
        self._publish(draft, manifest)
        return manifest

    def abort(self, draft: Draft) -> None:
        self._draft_delete(draft.release_id, draft.token)
        if draft.release_id not in self._sealed()[0]:
            self._tables.unpin(PIN_PREFIX + draft.release_id)

    def promote(self, release: str) -> None:
        manifest = self._manifest(release)
        if manifest is None:
            raise ReleaseNotFoundError(release)
        if manifest.destructive_epoch != self._tables.destructive_epoch():
            raise ReleaseInvalidError(f"{release} was built before a destructive operation (epoch)")
        self._require_pin(release, manifest.seq)
        self._write_current(release, manifest.content_hash)

    def current(self) -> tuple[str, str] | None:
        return self._read_current()

    def current_release(self) -> Release | None:
        named = self.current()
        if named is None:
            return None
        found = self.open(named[0])
        if found is None:  # pruned under a stale CURRENT: read it again once
            again = self.current()
            if again is None or again == named:
                return None
            named, found = again, self.open(again[0])
            if found is None:
                return None
        if found.manifest.content_hash != named[1]:
            raise ReleaseCorruptError(f"CURRENT names another hash than {named[0]}'s manifest")
        return found

    def open(self, release: str) -> Release | None:
        manifest = self._manifest(release)
        return None if manifest is None else StoredRelease(manifest, self._loader(release))

    def prune(self, sessions: int) -> int:
        manifests, unreadable = self._sealed()
        named = self._read_current()
        newest: dict[str, str] = {}  # session -> its newest release (highest sequence)
        for release in self._order(manifests):
            newest[manifests[release].session] = release
        kept = (
            {newest[s] for s in sorted(newest)[len(newest) - sessions :]} if sessions > 0 else set()
        )
        if named is not None:
            kept.add(named[0])
        doomed = [r for r in manifests if r not in kept]
        for release in [*doomed, *[r for r in unreadable if r not in kept]]:
            self._delete_release(release)
        live: set[str] = set()
        for release, token, age in self._drafts():
            if age >= self._draft_ttl_s:
                self._draft_delete(release, token)
            else:
                live.add(release)
        for pin in self._tables.pins():
            if pin.startswith(PIN_PREFIX) and pin[len(PIN_PREFIX) :] not in kept | live:
                self._tables.unpin(pin)
        self._write_stats({"pinned_bytes": self._tables.pinned_bytes()})  # for doctor, not a read
        return len(doomed)

    def report(self, with_bytes: bool = False) -> ReleaseReport:
        """``pinned_bytes``: what the last prune recorded (``None`` before any); ``with_bytes``
        measures it now by walking every partition index (an operator's one-off, never a page)."""
        named = self._read_current()
        stats = self._read_stats()
        pinned = (
            self._tables.pinned_bytes() if with_bytes else stats["pinned_bytes"] if stats else None
        )
        return ReleaseReport(
            named[0] if named else None, tuple(self.releases()), self._tables.pins(), pinned
        )
