"""``run_selection``: the versions a commit keeps (``retained``) and which reads can still be
answered from them (``visible_entries``), with pins (ADR 0077)."""

from contextlib import nullcontext

import pandas as pd
import pytest

from algotrade.storage.backends.run_selection import (
    RunEntry,
    StaleSnapshotError,
    chain,
    committed,
    read_at,
    seq_at,
    trimmed,
    visible_entries,
)

K = pd.Timestamp("2026-10-01", tz="UTC")


def commit(previous: RunEntry | None, seq: int, *pins: int) -> RunEntry:
    return committed(K, False, K.to_pydatetime(), seq, f"v{seq}", previous, pins)


def history(*seqs: int, pins: tuple[int, ...] = ()) -> RunEntry:
    entry: RunEntry | None = None
    for seq in seqs:
        entry = commit(entry, seq, *pins)
    assert entry is not None
    return entry


def seen(entry: RunEntry, upto: int) -> str | None:
    found = visible_entries({"r": entry}, upto).get("r")
    return None if found is None else found.ref


def test_without_pins_a_commit_keeps_one_older_version_as_before() -> None:
    entry = history(1, 2, 3, 4)
    assert [e.ref for e in chain(entry)] == ["v4", "v3"]
    assert entry.prev is not None and entry.prev.gap == 1
    assert seen(entry, 3) == "v3"
    with pytest.raises(StaleSnapshotError):
        seen(entry, 2)
    with pytest.raises(StaleSnapshotError):
        seen(entry, 1)


def test_a_first_commit_has_no_chain_and_a_second_does_not_drop() -> None:
    assert history(1).prev is None
    second = history(1, 2)
    assert second.prev is not None and not second.prev.dropped
    assert seen(second, 0) is None  # not yet committed at 0: hidden, not stale


def test_a_pin_keeps_the_newest_version_at_or_below_it_and_marks_the_hole() -> None:
    entry = history(1, 2, 3, 4, 5, 6, pins=(2,))
    assert [e.ref for e in chain(entry)] == ["v6", "v5", "v2"]
    assert seen(entry, 2) == "v2"
    assert seen(entry, 5) == "v5"
    for lost in (3, 4):  # discarded between the pin and the one in flight
        with pytest.raises(StaleSnapshotError):
            seen(entry, lost)
    with pytest.raises(StaleSnapshotError):
        seen(entry, 1)  # older than the pinned version: gone


def test_a_pin_between_two_versions_keeps_the_lower_one() -> None:
    entry = history(1, 2, 5, 6, 7, pins=(4,))
    assert seen(entry, 4) == "v2"  # the newest at or below the pin


def test_two_pins_on_the_same_version_keep_it_once() -> None:
    entry = history(1, 2, 3, 4, 5, pins=(1, 1))
    assert [e.ref for e in chain(entry)] == ["v5", "v4", "v1"]


def test_the_chain_is_never_longer_than_pins_plus_two() -> None:
    entry = history(*range(1, 30), pins=(3, 11, 20))
    assert len(list(chain(entry))) <= 5
    assert {seen(entry, p) for p in (3, 11, 20)} == {"v3", "v11", "v20"}


def test_a_later_commit_without_the_pin_discards_what_only_it_kept() -> None:
    pinned = history(1, 2, 3, 4, pins=(1,))
    unpinned = commit(pinned, 5)
    assert [e.ref for e in chain(unpinned)] == ["v5", "v4"]
    with pytest.raises(StaleSnapshotError):
        seen(unpinned, 1)


def test_recommitting_the_same_sequence_is_idempotent() -> None:
    entry = history(1, 2, 3, pins=(1,))
    assert commit(entry, 3, 1) is entry


def test_seq_at_is_the_highest_visible_sequence_or_none() -> None:
    entry = history(1, 2, 3, 4, pins=(2,))
    assert seq_at({"r": entry}, 2) == 2
    assert seq_at({"r": history(5)}, 2) is None
    assert seq_at({"r": entry, "s": history(1)}, 4) == 4


def test_read_at_reads_once_at_a_named_sequence_and_retries_without_one() -> None:
    calls: list[int] = []

    def read(seq: int) -> str:
        calls.append(seq)
        if seq == 5:
            raise StaleSnapshotError("discarded")
        return f"read at {seq}"

    with pytest.raises(StaleSnapshotError):
        read_at(read, lambda: 9, nullcontext, 5)
    assert calls == [5]  # a pinned reader gets the error, not an answer at sequence 9
    assert read_at(read, lambda: 9, nullcontext, None) == "read at 9"


def test_a_run_born_after_the_pin_is_hidden_from_it_however_often_it_was_recommitted() -> None:
    entry = history(5, 6, 7, 8, pins=(2,))
    assert seen(entry, 2) is None
    assert seen(entry, 4) is None
    with pytest.raises(StaleSnapshotError):
        seen(entry, 5)  # the version at 5 is gone


def test_trimmed_forgets_older_versions_unless_a_pin_may_read_them() -> None:
    old = RunEntry(pd.Timestamp("2026-10-01", tz="UTC"), seq=2)
    entry = RunEntry(pd.Timestamp("2026-10-01", tz="UTC"), seq=5, prev=old)
    gone = trimmed(entry, [6, 9])
    assert gone is not None and gone.prev is None and gone.dropped  # a read on it retries
    assert trimmed(entry, [3]) is None  # a pin below the commit reads the older version
    assert trimmed(gone, []) is None  # nothing left to trim
