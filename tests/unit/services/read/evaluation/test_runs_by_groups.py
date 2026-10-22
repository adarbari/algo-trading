"""``rows_of_record`` / ``draws_of_record`` over a stored (local Parquet) run: the rows are those
of decoding the whole partition and filtering after, in the same order, whether the file was
written clustered or before clustering; a clustered file's random-only row groups are never
decoded for the screener rows (and nothing else for the draws)."""

from pathlib import Path
from typing import Any

import pyarrow.parquet as pq
import pytest

from algotrade.services.read.context import run_partition
from algotrade.services.read.evaluation import runs as runs_module
from algotrade.services.read.evaluation.edges import load_edge
from algotrade.services.read.evaluation.runs import (
    Draw,
    draws_of_record,
    load_canonical_run,
    rows_of_record,
)
from algotrade.storage.backends import local
from algotrade.storage.backends.arrow import parquet_bytes
from algotrade.storage.backends.local import LocalBackend
from algotrade.storage.tables.schemas import result_table
from tests.unit.services.read.evaluation.conftest import FROZEN, row, stores, write_run


def _fill(backend: Any) -> None:
    """Draws interleaved with screener frozen rows, an exploratory row, an in-sample row, and a
    restated run of the same range end beside the first."""
    draws = [
        row("random", "draw", 0.4, FROZEN, role="random", slice_value=str(i), lift=0.1 * i)
        for i in range(8)
    ]
    extra = [
        *draws[:4],
        row("momo", "frozen", 0.3, FROZEN, exploratory=True, slice_value="x"),
        *draws[4:],
        row("momo", "in_sample", 0.2, FROZEN, in_sample=True),
        row("momo", "year", 0.5, FROZEN),
    ]
    write_run(backend, "first", FROZEN, 0.6, minutes=10, extra=extra)
    write_run(backend, "canon", FROZEN, 0.66, minutes=20, extra=extra[::-1])


def _everything(ctx: Any, record: Any) -> list[Any]:
    frame = run_partition(ctx, result_table(runs_module.EDGE_EVAL), record)
    assert frame is not None
    return [runs_module._row({str(k): v for k, v in r.items()}) for r in frame.to_dict("records")]


def _check(backend: LocalBackend) -> None:
    ctx = stores(backend)  # type: ignore[arg-type]
    for run_id in ("first", "canon"):
        record = ctx.reader.run(run_id)
        assert record is not None
        every = _everything(ctx, record)
        rest = tuple(r for r in every if r.role != "random")
        assert rows_of_record(ctx, record) == rest
        assert draws_of_record(ctx, record) == tuple(
            Draw(r.edge_variant, r.variant, r.horizon_sessions, r.lift)
            for r in every
            if r.role == "random"
        )
        kinds = ("frozen", "year")
        assert rows_of_record(ctx, record, kinds) == tuple(r for r in rest if r.slice_kind in kinds)
        assert len(rest) == 5 and len(draws_of_record(ctx, record)) == 8


def test_a_clustered_run_serves_the_rows_decoding_the_whole_partition_gives(
    tmp_path: Path,
) -> None:
    backend = LocalBackend(tmp_path / "data")
    _fill(backend)
    _check(backend)


def test_a_run_written_before_clustering_serves_the_same_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(local, "table_parquet_bytes", lambda _t, data: parquet_bytes(data))
    backend = LocalBackend(tmp_path / "data")
    _fill(backend)
    _check(backend)


def test_the_screener_rows_of_a_run_decode_no_random_only_row_group(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    backend = LocalBackend(tmp_path / "data")
    _fill(backend)
    ctx = stores(backend)  # type: ignore[arg-type]
    edge = load_edge(ctx, "drift")
    assert edge is not None
    run = load_canonical_run(ctx, edge).run
    assert run is not None
    record = ctx.reader.run(run.run_id)
    assert record is not None
    opened: list[tuple[int, str]] = []
    real = pq.ParquetFile.read_row_groups

    def spy(self: pq.ParquetFile, groups: list[int], *a: object, **k: object) -> object:
        meta = self.metadata
        for g in groups:
            stats = meta.row_group(g).column(self.schema_arrow.names.index("role")).statistics
            opened.append((meta.row_group(g).num_rows, str(stats.min if stats else None)))
        return real(self, groups, *a, **k)

    monkeypatch.setattr(pq.ParquetFile, "read_row_groups", spy)
    rows = rows_of_record(ctx, record)
    assert len(rows) == 5
    assert all(role != "random" for _, role in opened) and sum(n for n, _ in opened) == 5
    opened.clear()
    assert len(draws_of_record(ctx, record)) == 8
    assert opened == [(8, "random")]
