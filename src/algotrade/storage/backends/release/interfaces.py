"""The release store protocol, its value types and errors (ADR 0077)."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING, Protocol

import pandas as pd
import pyarrow as pa

if TYPE_CHECKING:
    from algotrade.storage.backends.release.manifest import Manifest


class ReleaseError(Exception):
    """Base of the release store's errors; a reader treats any of them as "no release"."""


class ReleaseInvalidError(ReleaseError):
    """The build cannot become a release: an input past its sequence, a destructive operation
    since it began, the size ceiling, or too little free disk."""


class ReleaseNotFoundError(ReleaseError):
    """No sealed release has that id (never sealed, or pruned)."""


class ReleaseCorruptError(ReleaseError):
    """A manifest, table file or CURRENT does not match the hash it is named by."""


@dataclass(frozen=True)
class InputPartitions:
    """The partitions of one stored table a release was built from, each with its
    ``partition_seq`` as the build read it."""

    table: str
    partitions: Mapping[date, int]


@dataclass(frozen=True)
class Draft:
    """A release being built: pinned at ``seq`` from ``begin`` until it is sealed, aborted or
    pruned. ``epoch`` is the store's ``destructive_epoch`` at ``begin``."""

    release_id: str
    session: date
    seq: int
    fmt: int
    epoch: int
    token: str


@dataclass(frozen=True)
class ReleaseReport:
    """What ``make status`` and ``make doctor`` show: the current release, every sealed one, the
    pins on the store and the disk the versions they retain hold (``pinned_bytes``)."""

    current: str | None
    releases: tuple[str, ...]
    pins: dict[str, int] = field(default_factory=dict)
    pinned_bytes: int | None = None  # None: never measured (the serve job's prune records it)


class Release(Protocol):
    """A sealed release opened for reading."""

    @property
    def manifest(self) -> "Manifest": ...

    def read(self, name: str) -> pa.Table:
        """One table, verified against the manifest's SHA-256 (``ReleaseCorruptError``);
        ``KeyError`` for a name the release does not hold."""
        ...


class ReleaseStore(Protocol):
    """Every mutator (``begin``, ``write``, ``seal``, ``abort``, ``promote``, ``prune``) runs only
    under the serve job's ``exclusive_run("serve")``; readers need no lock."""

    def begin(self, session: date, seq: int, fmt: int) -> Draft:
        """Start a build at commit sequence ``seq``: refuses without the free-space floor
        (``ReleaseInvalidError``), then pins ``seq`` (``release-<id>``) so every version the
        build reads survives, and records the epoch."""
        ...

    def write(self, draft: Draft, name: str, table: pa.Table) -> None:
        """Add a table to the draft (``name``: lowercase letters, digits, ``_``); invisible."""
        ...

    def write_frame(self, draft: Draft, name: str, frame: pd.DataFrame) -> None:
        """``write`` for a caller that holds a frame, not an Arrow table."""
        ...

    def seal(self, draft: Draft, inputs: Sequence[InputPartitions], code_sha: str) -> "Manifest":
        """Make the draft a release: raises ``ReleaseInvalidError`` when an input's sequence is
        above the draft's, the epoch moved, or it is over the ceiling; otherwise the files are
        fsynced and the release appears whole. Sealing the id of an identical release returns
        that one. A failure leaves nothing visible."""
        ...

    def abort(self, draft: Draft) -> None:
        """Delete an unsealed draft and unpin it (a sealed release of the same id keeps its pin)."""
        ...

    def promote(self, release_id: str) -> None:
        """Make a sealed release the one served: ``ReleaseNotFoundError`` for an unknown id,
        ``ReleaseInvalidError`` when the store's epoch is not the release's; then one atomic
        replacement of CURRENT (temp file, fsync, rename, directory fsync)."""
        ...

    def current(self) -> tuple[str, str] | None:
        """``(release_id, manifest_hash)`` as CURRENT names them, ``None`` before any promote."""
        ...

    def current_release(self) -> Release | None:
        """The current release, opened and checked against CURRENT's hash
        (``ReleaseCorruptError``); ``None`` when there is none or it was pruned."""
        ...

    def open(self, release_id: str) -> Release | None:
        """A sealed release (its manifest verified), ``None`` when there is no such release."""
        ...

    def releases(self) -> list[str]:
        """Every sealed release id, oldest first (session, then sequence)."""
        ...

    def prune(self, keep: int) -> int:
        """Delete all but the ``keep`` newest releases and the current one; delete drafts older
        than their TTL (a build that died); unpin every ``release-*`` pin that no kept release or
        live draft holds. -> releases deleted."""
        ...

    def free_bytes(self) -> int:
        """Bytes free on the volume releases live on."""
        ...

    def report(self, with_bytes: bool = False) -> ReleaseReport:
        """Current release, releases, pins and ``pinned_bytes`` as the last prune recorded it
        (``with_bytes``: measured now: reads every partition index of the store)."""
        ...
