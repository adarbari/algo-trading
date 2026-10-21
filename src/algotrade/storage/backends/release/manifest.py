"""A release's manifest: what it holds and what it was built from, canonical and hashed.

The manifest is JSON with sorted keys and no spaces, so two builds of the same inputs give the
same bytes. ``content_hash`` is the SHA-256 of that JSON without the ``content_hash`` field;
CURRENT names it and readers verify it. ``built_at`` is a fact of the run record, never of the
manifest (it would make two builds differ).
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from algotrade.storage.backends.release.interfaces import InputPartitions, ReleaseCorruptError

MAX_RELEASE_BYTES = 300 * 1024 * 1024  # ADR 0077 decision 6: the size ceiling
MIN_FREE_BYTES = 5 * 1024**3  # decision 6: the free-space floor is this or 3x the last release
FLOOR_FACTOR = 3


@dataclass(frozen=True)
class TableInfo:
    """One table file of a release: its rows, the SHA-256 of its bytes and their count."""

    rows: int
    sha256: str
    bytes: int


@dataclass(frozen=True)
class Manifest:
    format: int
    release_id: str
    session: str
    seq: int
    destructive_epoch: int
    code_sha: str
    inputs: tuple[InputPartitions, ...]
    tables: dict[str, TableInfo] = field(default_factory=dict)
    content_hash: str = ""

    def body(self) -> dict[str, Any]:
        """Every field but ``content_hash``, as plain JSON values in canonical order."""
        return {
            "format": self.format,
            "release_id": self.release_id,
            "session": self.session,
            "seq": self.seq,
            "destructive_epoch": self.destructive_epoch,
            "code_sha": self.code_sha,
            "inputs": [
                {
                    "table": i.table,
                    "partitions": {d.isoformat(): n for d, n in sorted(i.partitions.items())},
                }
                for i in sorted(self.inputs, key=lambda i: i.table)
            ],
            "tables": {
                name: {"rows": t.rows, "sha256": t.sha256, "bytes": t.bytes}
                for name, t in sorted(self.tables.items())
            },
        }

    def computed_hash(self) -> str:
        return hashlib.sha256(_canonical(self.body())).hexdigest()

    def sealed(self) -> "Manifest":
        """This manifest with its ``content_hash`` filled in."""
        return Manifest(**{**self.__dict__, "content_hash": self.computed_hash()})

    def to_json(self) -> bytes:
        return _canonical({**self.body(), "content_hash": self.content_hash})

    @property
    def total_bytes(self) -> int:
        return sum(t.bytes for t in self.tables.values())

    @classmethod
    def from_json(cls, data: bytes) -> "Manifest":
        """Parse and verify: ``ReleaseCorruptError`` when the hash does not match the content."""
        try:
            raw = json.loads(data)
            manifest = cls(
                format=int(raw["format"]),
                release_id=str(raw["release_id"]),
                session=str(raw["session"]),
                seq=int(raw["seq"]),
                destructive_epoch=int(raw["destructive_epoch"]),
                code_sha=str(raw["code_sha"]),
                inputs=tuple(
                    InputPartitions(
                        i["table"],
                        {date.fromisoformat(d): int(n) for d, n in i["partitions"].items()},
                    )
                    for i in raw["inputs"]
                ),
                tables={
                    name: TableInfo(int(t["rows"]), str(t["sha256"]), int(t["bytes"]))
                    for name, t in raw["tables"].items()
                },
                content_hash=str(raw["content_hash"]),
            )
        except (KeyError, ValueError, TypeError) as exc:
            raise ReleaseCorruptError(f"manifest unreadable: {exc}") from exc
        if manifest.content_hash != manifest.computed_hash():
            raise ReleaseCorruptError(f"manifest of {manifest.release_id} does not match its hash")
        return manifest


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def release_id(session: date, seq: int, fmt: int) -> str:
    return f"{session.isoformat()}.{seq}.f{fmt}"


def room_needed(last_release_bytes: int) -> int:
    """The free bytes a build needs before it starts: ``max(5 GB, 3 x the last release)``."""
    return max(MIN_FREE_BYTES, FLOOR_FACTOR * last_release_bytes)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
