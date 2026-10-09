"""The history copy (ADR 0060) is invisible: whatever runs wrote whatever partitions (a later
run superseding or restating one, a partition rewritten or added after the copy was built), a
``read_range`` for any range, instrument filter and column selection returns exactly the frame
the partitions give, whether the copy served it or the read fell back."""

import tempfile
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
from hypothesis import given, settings
from hypothesis import strategies as st
from pandas.testing import assert_frame_equal

from algotrade.storage.backends.local import LocalBackend
from tests.helpers.stored_frames import stamped

TABLES = ("rollups/instrument/prop@v1", "events/prop")
START = date(2025, 12, 1)
IDS = ("EQ:A", "EQ:B", "EQ:C", "EQ:D", "EQ:E")
FUTURE = datetime(2200, 1, 1, tzinfo=UTC)
BASE = datetime(2026, 1, 1, tzinfo=UTC)

type Write = tuple[date, int, list[str], bool, bool]  # day, run, ids in order, restates, x

days = st.integers(0, 70).map(lambda n: START + timedelta(days=n))
id_sets = st.lists(st.sampled_from(IDS), min_size=1, max_size=5, unique=True)
writes = st.tuples(days, st.integers(1, 3), id_sets, st.booleans(), st.booleans())
queries = st.fixed_dictionaries(
    {
        "instruments": st.one_of(st.none(), st.lists(st.sampled_from([*IDS, "EQ:Z"]), max_size=4)),
        "columns": st.one_of(st.none(), st.just(["a"]), st.just(["b", "c"]), st.just(["x"])),
    }
)


def write(backend: LocalBackend, table: str, item: Write) -> None:
    day, run, ids, restates, extra = item
    rows: list[dict[str, Any]] = [
        {"instrument_id": s, "a": float(run * 10 + k), "b": run + k, "c": f"{s}{run}"}
        for k, s in enumerate(ids)
    ]
    frame = stamped(rows, day, f"r{run}", BASE + timedelta(hours=run))
    if extra:  # a column some partitions have and others lack (added mid-year)
        frame = frame.assign(x=float(run))
    if table.startswith("events/"):
        frame = frame.assign(ts=pd.Timestamp(day, tz="UTC"), known_from=day)
    backend.tables.write(table, day, f"r{run}", frame, restates=restates)


@settings(max_examples=40, deadline=None)
@given(
    table=st.sampled_from(TABLES),
    before=st.lists(writes, min_size=1, max_size=14),
    after=st.lists(writes, max_size=3),
    query=queries,
    bounds=st.tuples(days, days),
)
def test_the_copy_read_equals_the_partition_read(
    table: str,
    before: list[Write],
    after: list[Write],
    query: dict[str, Any],
    bounds: tuple[date, date],
) -> None:
    start, end = sorted(bounds)
    with tempfile.TemporaryDirectory() as root:
        backend = LocalBackend(Path(root))
        for item in before:
            write(backend, table, item)
        backend.tables.build_history(table, [2025, 2026])
        for item in after:  # partitions that changed since the copy was built
            write(backend, table, item)
        got = backend.tables.read_range(table, start, end, **query)
        expected = backend.tables.read_range(table, start, end, as_of=FUTURE, **query)
        assert (got is None) == (expected is None)
        if got is not None and expected is not None:
            assert_frame_equal(got, expected)
