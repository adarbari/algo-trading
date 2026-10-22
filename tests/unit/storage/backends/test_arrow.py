"""Clustered files (``TableSpec.cluster_by``, ``arrow.encode``): a table that declares it is
written sorted by its column in small row groups, the same rows always give the same bytes, a
read of a few values decodes only the groups that can hold them, and a file written before
(one big group, any order) reads the same rows by being read whole and filtered."""

import io
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow.parquet as pq
import pytest

from algotrade.storage.backends.arrow import encode, is_clustered, to_arrow
from algotrade.storage.backends.local import LocalBackend
from algotrade.storage.tables.schemas.results import CLUSTER_ROWS
from tests.helpers.stored_frames import make_unclustered, screen_values_rows, stamped

VALUES = "results/rule_screen_values"
PLAIN = "rollups/market/demo@v1"
DAY = date(2026, 10, 1)
INSTRUMENTS = 4_000  # x 3 rows = 12,000 rows: two row groups of 8,192


def values_frame(run: str = "r1") -> pd.DataFrame:
    return stamped(screen_values_rows(INSTRUMENTS), DAY, run)


def file_of(root: Path, run: str = "r1") -> Path:
    return next((root / "tables" / VALUES / f"date={DAY.isoformat()}").glob(f"run={run}*.parquet"))


def test_a_clustered_table_is_written_sorted_in_declared_row_groups() -> None:
    frame = values_frame()
    parquet = pq.ParquetFile(io.BytesIO(encode(VALUES, to_arrow(VALUES, frame))))
    ids = parquet.read(columns=["instrument_id"]).column(0).to_pylist()
    assert ids == sorted(ids) and len(ids) == INSTRUMENTS * 3
    sizes = [parquet.metadata.row_group(g).num_rows for g in range(parquet.num_row_groups)]
    assert sizes == [CLUSTER_ROWS, INSTRUMENTS * 3 - CLUSTER_ROWS]


def test_the_same_rows_give_the_same_bytes_twice_and_in_either_input_order() -> None:
    frame = values_frame()
    first = encode(VALUES, to_arrow(VALUES, frame))
    assert encode(VALUES, to_arrow(VALUES, frame)) == first
    # the stable sort keeps the order of equal instrument ids, so a frame already sorted by
    # (instrument, criterion) is a fixed point of the writer
    again = pq.read_table(io.BytesIO(first))
    assert encode(VALUES, again) == first


def test_a_table_without_clustering_is_written_as_it_was() -> None:
    frame = stamped([{"instrument_id": f"EQ:{n}", "a": 1.0} for n in (3, 1, 2)], DAY, "r1")
    data = to_arrow(PLAIN, frame)
    ids = pq.read_table(io.BytesIO(encode(PLAIN, data))).column("instrument_id").to_pylist()
    assert ids == ["EQ:3", "EQ:1", "EQ:2"]


def test_the_footer_tells_a_clustered_file_from_one_written_before(tmp_path: Path) -> None:
    backend = LocalBackend(tmp_path / "data")
    backend.tables.write(VALUES, DAY, "r1", values_frame())
    assert backend.tables.run_layouts(VALUES, DAY) == {"r1": True}
    make_unclustered(tmp_path / "data" / "tables" / VALUES / f"date={DAY.isoformat()}")
    assert backend.tables.run_layouts(VALUES, DAY) == {"r1": False}
    assert is_clustered(file_of(tmp_path / "data"), PLAIN)  # a table with no layout: nothing to do


def read_counting(monkeypatch: pytest.MonkeyPatch) -> list[list[int]]:
    """The row groups every ``read_row_groups`` of this test decodes."""
    opened: list[list[int]] = []
    real = pq.ParquetFile.read_row_groups

    def counting(self: Any, row_groups: Any, *args: Any, **kwargs: Any) -> Any:
        opened.append(list(row_groups))
        return real(self, row_groups, *args, **kwargs)

    monkeypatch.setattr(pq.ParquetFile, "read_row_groups", counting)
    return opened


def test_an_instrument_read_opens_only_the_row_groups_that_can_hold_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    backend = LocalBackend(tmp_path / "data")
    frame = values_frame()
    backend.tables.write(VALUES, DAY, "r1", frame)
    opened = read_counting(monkeypatch)
    first, last = "EQ:00001", f"EQ:{INSTRUMENTS - 1:05d}"
    low = backend.tables.read_run(VALUES, DAY, "r1", instruments=[first])
    assert opened == [[0]]  # of two groups, the first
    high = backend.tables.read_run(VALUES, DAY, "r1", instruments=[last])
    assert opened[-1] == [1]
    assert low is not None and high is not None
    assert set(low["instrument_id"]) == {first} and len(low) == 3
    assert set(high["instrument_id"]) == {last} and len(high) == 3


def sorted_rows(frame: pd.DataFrame | None) -> pd.DataFrame:
    assert frame is not None
    keys = ["instrument_id", "criterion_id"]
    return frame.sort_values(keys).reset_index(drop=True)


def test_sorted_and_old_files_read_the_same_rows_for_every_read(tmp_path: Path) -> None:
    """Equivalence: a clustered store and the same store written before give identical rows for a
    whole read, an instrument read and a run read; a mixed store (one run each) reads whole."""
    new, old, mixed = (LocalBackend(tmp_path / n / "data") for n in ("new", "old", "mixed"))
    wanted = ["EQ:00001", "EQ:02000", f"EQ:{INSTRUMENTS - 1:05d}", "EQ:99999"]
    for backend in (new, old, mixed):
        backend.tables.write(VALUES, DAY, "r1", values_frame("r1"))
        backend.tables.write(VALUES, DAY, "r2", values_frame("r2"))
    make_unclustered(tmp_path / "old" / "data" / "tables" / VALUES / f"date={DAY.isoformat()}")
    make_unclustered(tmp_path / "mixed" / "data" / "tables" / VALUES / f"date={DAY.isoformat()}")
    mixed.tables.write(VALUES, DAY, "r2", values_frame("r2"))  # r2 again, now clustered
    assert mixed.tables.run_layouts(VALUES, DAY) == {"r1": False, "r2": True}
    for store in (old, mixed):
        for run in ("r1", "r2"):
            for instruments in (None, wanted):
                got = sorted_rows(store.tables.read_run(VALUES, DAY, run, instruments=instruments))
                ref = sorted_rows(new.tables.read_run(VALUES, DAY, run, instruments=instruments))
                pd.testing.assert_frame_equal(got, ref)
        whole = sorted_rows(store.tables.read(VALUES, DAY))
        pd.testing.assert_frame_equal(whole, sorted_rows(new.tables.read(VALUES, DAY)))
