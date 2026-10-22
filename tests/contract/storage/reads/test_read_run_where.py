"""Storage contract, ``read_run(where=...)``: the rows passing the filters are exactly those of
filtering the whole read, whichever backend and however the file was written (clustered by
``TableSpec.cluster_by``, or an older file whose groups mix the values); a clustered local file
never decodes the row groups the footer statistics rule out."""

from collections.abc import Iterator
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
import pytest

from algotrade.storage.backends import local
from algotrade.storage.backends.arrow import parquet_bytes
from algotrade.storage.backends.local import LocalBackend
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.interfaces import Backend, RowFilter
from tests.helpers.stored_frames import T0, stamped

DAY = date(2026, 10, 1)
TABLE = "results/edge_eval"
AT = T0 + timedelta(minutes=30)
RANDOM = RowFilter("role", frozenset({"random"}))
NOT_RANDOM = RowFilter("role", frozenset({"random"}), keep=False)


@pytest.fixture(params=["memory", "local"])
def backend(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[Backend]:
    yield MemoryBackend() if request.param == "memory" else LocalBackend(tmp_path / "data")


def eval_row(role: str | None, kind: str, value: str, lift: float) -> dict[str, object]:
    return {
        "edge_id": "e", "user_id": "u", "variant": "v", "horizon_sessions": 20,
        "slice_kind": kind, "slice_value": value, "range_from": DAY, "role": role, "lift": lift,
    }  # fmt: skip


def mixed_rows() -> list[dict[str, object]]:
    """Draws interleaved with the screener rows, a null role and two slice kinds."""
    return [
        eval_row("screener", "all", "all", 1.0),
        *(eval_row("random", "draw", str(i), 0.1 * i) for i in range(6)),
        eval_row("screener", "frozen", "frozen", 2.0),
        eval_row("baseline", "all", "all", 3.0),
        eval_row(None, "all", "x", 4.0),
        eval_row("screener", "year", "2025", 5.0),
    ]


def publish(backend: Backend, run: str, rows: list[dict[str, object]]) -> None:
    backend.tables.write(TABLE, DAY, run, stamped(rows, DAY, run, T0), pending=True)
    backend.tables.commit_run(run, AT)


def cases() -> list[list[RowFilter]]:
    return [
        [RANDOM],
        [NOT_RANDOM],
        [NOT_RANDOM, RowFilter("slice_kind", frozenset({"frozen", "year"}))],
        [RANDOM, RowFilter("slice_kind", frozenset({"frozen"}))],  # matches none
        [RowFilter("role", frozenset({"nothing"}))],
        [RowFilter("no_such_column", frozenset({"a"}))],
        [RowFilter("no_such_column", frozenset({"a"}), keep=False)],
    ]


def expected(whole: pd.DataFrame, where: list[RowFilter]) -> list[tuple[object, ...]]:
    keep = pd.Series(True, index=whole.index)
    for one in where:
        found = (
            whole[one.column].isin(set(one.values))
            if one.column in whole
            else pd.Series(False, index=whole.index)
        )
        keep &= found if one.keep else ~found
    return list(zip(whole[keep]["slice_kind"], whole[keep]["slice_value"], strict=True))


def asked(backend: Backend, where: list[RowFilter]) -> list[tuple[object, ...]] | None:
    got = backend.tables.read_run(TABLE, DAY, "r1", where=where)
    return None if got is None else list(zip(got["slice_kind"], got["slice_value"], strict=True))


def test_where_serves_the_rows_filtering_the_whole_read_gives(backend: Backend) -> None:
    publish(backend, "r1", mixed_rows())
    publish(backend, "r2", [eval_row("random", "draw", "other", 9.0)])  # another run, same day
    whole = backend.tables.read_run(TABLE, DAY, "r1")
    assert whole is not None
    for where in cases():
        want = expected(whole, where)
        got = asked(backend, where)
        assert got == (want or None), where


def test_an_unclustered_older_file_serves_the_same_rows(
    backend: Backend, monkeypatch: pytest.MonkeyPatch
) -> None:
    if not isinstance(backend, LocalBackend):
        pytest.skip("a file layout is the local backend's")
    monkeypatch.setattr(local, "table_parquet_bytes", lambda _t, data: parquet_bytes(data))
    publish(backend, "r1", mixed_rows())
    whole = backend.tables.read_run(TABLE, DAY, "r1")
    assert whole is not None
    for where in cases():
        assert asked(backend, where) == (expected(whole, where) or None), where


def file_of(backend: LocalBackend) -> Path:
    (found,) = (backend.tables.root / TABLE / f"date={DAY.isoformat()}").glob("*.parquet")
    return found


def decoded_rows(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """The rows of every row group a read decodes."""
    seen: list[int] = []
    real = pq.ParquetFile.read_row_groups

    def spy(self: pq.ParquetFile, groups: list[int], *a: object, **k: object) -> object:
        seen.extend(self.metadata.row_group(g).num_rows for g in groups)
        return real(self, groups, *a, **k)

    monkeypatch.setattr(pq.ParquetFile, "read_row_groups", spy)
    return seen


def test_a_clustered_file_decodes_only_the_groups_that_can_hold_the_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    backend = LocalBackend(tmp_path / "data")
    publish(backend, "r1", mixed_rows())
    meta = pq.ParquetFile(file_of(backend)).metadata
    assert meta.num_row_groups == 6  # (null role last), baseline, random, 3 x screener kinds
    seen = decoded_rows(monkeypatch)
    rest = asked(backend, [NOT_RANDOM])
    assert rest is not None and len(rest) == 5 and sum(seen) == 5  # no draw was decoded
    seen.clear()
    draws = asked(backend, [RANDOM])
    assert draws is not None and len(draws) == 6 and sum(seen) == 6
    seen.clear()
    frozen = asked(backend, [NOT_RANDOM, RowFilter("slice_kind", frozenset({"frozen"}))])
    assert frozen == [("frozen", "frozen")] and sum(seen) == 1


def test_an_unclustered_file_reads_whole_and_the_rows_are_cut_exactly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    backend = LocalBackend(tmp_path / "data")
    monkeypatch.setattr(local, "table_parquet_bytes", lambda _t, data: parquet_bytes(data))
    publish(backend, "r1", mixed_rows())
    seen = decoded_rows(monkeypatch)
    rest = asked(backend, [NOT_RANDOM])
    assert rest is not None and len(rest) == 5 and sum(seen) == 11  # one mixed group, read whole


def test_clustering_is_deterministic_and_keeps_each_groups_order(tmp_path: Path) -> None:
    first, second = (LocalBackend(tmp_path / n) for n in ("a", "b"))
    for one in (first, second):
        publish(one, "r1", mixed_rows())
    assert file_of(first).read_bytes() == file_of(second).read_bytes()
    got = pq.read_table(file_of(first)).to_pandas()
    draws = got[got["role"] == "random"]["slice_value"]
    assert list(draws) == [str(i) for i in range(6)]  # the stable sort kept the stored order
