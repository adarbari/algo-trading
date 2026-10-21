"""``Manifest``: canonical JSON, a hash of the content without the hash, and the floor."""

import json
from datetime import date

import pytest

from algotrade.storage.backends.release.interfaces import InputPartitions, ReleaseCorruptError
from algotrade.storage.backends.release.manifest import (
    MIN_FREE_BYTES,
    Manifest,
    TableInfo,
    release_id,
    room_needed,
)

D = date(2026, 10, 2)


def manifest(**over: object) -> Manifest:
    fields: dict[str, object] = {
        "format": 1,
        "release_id": release_id(D, 7, 1),
        "session": D.isoformat(),
        "seq": 7,
        "destructive_epoch": 2,
        "code_sha": "abc",
        "inputs": (InputPartitions("b", {D: 7}), InputPartitions("a", {D: 3})),
        "tables": {"picks": TableInfo(2, "f" * 64, 100), "session": TableInfo(1, "e" * 64, 50)},
    }
    return Manifest(**{**fields, **over}).sealed()  # type: ignore[arg-type]


def test_the_release_id_is_session_sequence_and_format() -> None:
    assert release_id(D, 7, 1) == "2026-10-02.7.f1"


def test_the_json_is_canonical_and_round_trips() -> None:
    m = manifest()
    data = m.to_json()
    assert data == manifest(tables=dict(reversed(m.tables.items()))).to_json()  # order-free
    assert b" " not in data and b"built_at" not in data
    assert Manifest.from_json(data).to_json() == data  # inputs come back sorted
    assert [i["table"] for i in json.loads(data)["inputs"]] == ["a", "b"]


def test_a_changed_field_changes_the_hash_and_a_tampered_file_is_refused() -> None:
    assert manifest().content_hash != manifest(code_sha="abd").content_hash
    data = manifest().to_json()
    with pytest.raises(ReleaseCorruptError):
        Manifest.from_json(data.replace(b'"seq":7', b'"seq":8'))
    with pytest.raises(ReleaseCorruptError):
        Manifest.from_json(b"not json")


def test_the_room_a_build_needs_is_five_gb_or_three_times_the_last_release() -> None:
    assert room_needed(0) == MIN_FREE_BYTES
    assert room_needed(200 * 1024**2) == MIN_FREE_BYTES
    assert room_needed(2 * 1024**3) == 6 * 1024**3
