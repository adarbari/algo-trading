"""Ingestion completeness over the golden store: the window of sessions ending at the session,
each dataset's cells by kind (session, chains, snapshot), and one cell's drill-down."""

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest

from algotrade.services.read.context import ReadContext, ResultCache, open_context, snapshot_on
from algotrade.services.read.ops import ingestion
from algotrade.services.read.ops.ingestion import (
    Cell,
    load_cell_detail,
    load_completeness,
)
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.readers import StoreReader
from algotrade_api.deps import ReadStore
from tests.helpers.stored_frames import publish

NOW = datetime(2026, 10, 5, 12, tzinfo=UTC)


def _ctx(api_golden: tuple[ReadStore, dict[str, str]], day: date | None = None) -> ReadContext:
    store = api_golden[0]
    return open_context(store.reader, store.configs, store.user, day)


@pytest.fixture(scope="module")
def cells(api_golden: tuple[ReadStore, dict[str, str]]) -> dict[tuple[str, str], Cell]:
    grid = load_completeness(_ctx(api_golden), 3, NOW)
    assert grid.sessions == (date(2022, 11, 21), date(2022, 11, 22), date(2022, 11, 23))
    assert grid.last_closed == date(2026, 10, 2)  # Monday noon: Friday is the last closed
    assert len(grid.cells) == 3 * len(grid.datasets)
    return {(c.dataset, c.session.isoformat()): c for c in grid.cells}


def test_session_datasets_compare_with_the_previous_stored_session(
    cells: dict[tuple[str, str], Cell],
) -> None:
    bars = cells[("bars/1d", "2022-11-23")]
    assert (bars.status, bars.present, bars.expected) == ("COMPLETE", 11, 11)
    assert bars.run_ids
    stats = cells[("rollups/instrument/price_stats@v2", "2022-11-23")]
    assert (stats.status, stats.expected) == ("COMPLETE", 4)
    assert cells[("rollups/instrument/price_stats@v2", "2022-11-21")].status == "MISSING"


def test_chains_against_the_optionable_universe(cells: dict[tuple[str, str], Cell]) -> None:
    chains = cells[("chains/option_quotes", "2022-11-23")]
    assert (chains.status, chains.present, chains.expected) == ("PARTIAL", 1, 4)
    assert cells[("chains/option_quotes", "2022-11-22")].status == "MISSING"


def test_snapshots_built_carried_or_missing(cells: dict[tuple[str, str], Cell]) -> None:
    reference = cells[("instruments/reference", "2022-11-22")]
    assert (reference.status, reference.basis) == ("CARRIED", "snapshot of 2020-01-01")
    assert (
        cells[("universe", "2022-11-22")].status == "CARRIED"
    )  # the golden load writes one (ED3c)
    assert cells[("universe", "2022-11-23")].status == "COMPLETE"


def test_the_window_ends_at_the_session_asked_for(
    api_golden: tuple[ReadStore, dict[str, str]],
) -> None:
    grid = load_completeness(_ctx(api_golden, date(2022, 11, 22)), 0, NOW)
    assert grid.sessions == (date(2022, 11, 22),)  # at least one session


def test_drill_down_chains_groups_underlyings(api_golden: tuple[ReadStore, dict[str, str]]) -> None:
    detail = load_cell_detail(_ctx(api_golden, date(2022, 11, 23)), "chains/option_quotes")
    assert detail is not None
    assert (detail.job, detail.cell.status, detail.groups) == ("option_chains", "PARTIAL", ())
    assert [r.job for r in detail.runs][-1] == "option_chains"


def test_drill_down_groups_run_items(api_golden: tuple[ReadStore, dict[str, str]]) -> None:
    detail = load_cell_detail(_ctx(api_golden, date(2022, 11, 23)), "bars/1d")
    assert detail is not None
    assert detail.job == "daily_bars" and detail.cell.run_ids
    assert {r.run_id for r in detail.runs} >= set(detail.cell.run_ids)


def test_an_unlisted_dataset_is_none(api_golden: tuple[ReadStore, dict[str, str]]) -> None:
    assert load_cell_detail(_ctx(api_golden), "nope") is None


def test_the_grid_lists_each_tables_stored_dates_once(
    api_golden: tuple[ReadStore, dict[str, str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    # listing walks every partition directory of a table (14 000 for a market rollup): the
    # grid asked it for every cell, 35 s for the Admin Ingestion page on the real store
    listed: list[str] = []
    real = ingestion.stored_dates

    def counting(ctx: Any, table: str) -> tuple[date, ...]:
        listed.append(table)
        return real(ctx, table)

    monkeypatch.setattr(ingestion, "stored_dates", counting)
    grid = load_completeness(_ctx(api_golden), 5, NOW)
    assert len(grid.cells) == 5 * len(grid.datasets)
    assert len(listed) == len(set(listed))


def test_the_grid_is_kept_until_the_next_publish(
    api_golden: tuple[ReadStore, dict[str, str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    # the status strip of every page asks for a one-session grid: 430 partitions read a page
    ctx = _ctx(api_golden)
    read: list[str] = []
    real = ingestion.partition_on

    def counting(c: Any, table: str, day: date) -> Any:
        read.append(table)
        return real(c, table, day)

    monkeypatch.setattr(ingestion, "partition_on", counting)
    first = load_completeness(ctx, 2, NOW)
    once = len(read)
    assert once > 0
    assert load_completeness(ctx, 2, NOW).cells == first.cells and len(read) == once
    seq = ctx.reader.visible_seq()
    monkeypatch.setattr(ctx.reader, "visible_seq", lambda: seq + 1)  # a publish
    load_completeness(ctx, 2, NOW)
    assert len(read) == 2 * once


def test_chain_coverage_reads_the_chains_run_records_of_the_session(
    api_golden: tuple[ReadStore, dict[str, str]],
) -> None:
    found = ingestion.load_chain_coverage(_ctx(api_golden, date(2022, 11, 23)))
    assert found is not None and found.session == date(2022, 11, 23)
    assert found.total > 0 and found.ok <= found.total
    assert found.share == found.ok / found.total
    assert sum(s.count for s in found.statuses) == found.total
    assert found.drift == ()  # one night of history: nothing to compare with


def test_a_session_without_a_chains_record_has_no_coverage(
    api_golden: tuple[ReadStore, dict[str, str]],
) -> None:
    assert ingestion.load_chain_coverage(_ctx(api_golden, date(2022, 11, 21))) is None


# ---- the bounded window: the cells are the listing's, without listing a grid table -------------
def _store(*tables: tuple[str, list[date]]) -> tuple[Any, Any]:
    backend = MemoryBackend()
    for n, (table, days) in enumerate(tables):
        for k, day in enumerate(days):
            publish(backend, f"w{n}-{k}", table, day)
    reader = StoreReader(backend)
    return reader, SimpleNamespace(reader=reader, cache=ResultCache())


GRID = [date(2026, 10, 1) + timedelta(days=k) for k in range(5)]  # the window's sessions
DENSE = "rollups/instrument/dense@v1"  # a day before the window, gaps inside it
SPARSE = "rollups/instrument/sparse@v1"  # nothing within 31 days before the window
EMPTY = "rollups/instrument/empty@v1"


def _fixture() -> tuple[Any, Any]:
    dense = [date(2026, 9, 20), GRID[1], GRID[3]]
    sparse = [date(2026, 3, 2), GRID[2]]  # its previous day is months back
    return _store((DENSE, dense), (SPARSE, sparse), (EMPTY, []))


def test_the_windowed_cells_equal_the_listed_ones_for_every_table_and_day() -> None:
    _reader, ctx = _fixture()
    windowed = ingestion._Counts(ctx, GRID)
    for table in (DENSE, SPARSE, EMPTY):
        listed = ingestion._Counts(ctx)  # no window: every question is answered by the listing
        for day in [*GRID, date(2026, 10, 9)]:  # the last is outside the window: listed too
            stored = listed.stored(table)
            before = [s for s in stored if s < day]
            assert windowed.around(table, day) == (day in stored, before[-1] if before else None)


def test_a_grid_cell_never_lists_a_table_that_has_a_day_in_the_lookback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reader, ctx = _fixture()
    counts = ingestion._Counts(ctx, GRID)

    def refuse(table: str) -> list[date]:
        if table == DENSE:
            raise AssertionError("a full dates() listing for a grid cell")
        return real(table)

    real = reader.dates
    monkeypatch.setattr(reader, "dates", refuse)
    assert counts.around(DENSE, GRID[1]) == (True, date(2026, 9, 20))
    assert counts.around(DENSE, GRID[2]) == (False, GRID[1])
    assert counts.around(DENSE, GRID[4]) == (False, GRID[3])
    # the sparse table has no day in the lookback: it falls back to the listing, same answer
    assert counts.around(SPARSE, GRID[2]) == (True, date(2026, 3, 2))
    assert counts.around(EMPTY, GRID[0]) == (False, None)


def test_the_pinned_window_equals_the_pinned_listing() -> None:
    reader, ctx = _fixture()
    pin = reader._backend.tables.visible_seq()
    publish(reader._backend, "late", DENSE, GRID[2])  # committed after the pin
    ctx.reader = reader.pinned(pin)
    counts = ingestion._Counts(ctx, GRID)
    assert counts.around(DENSE, GRID[2]) == (False, GRID[1])
    assert counts.around(DENSE, GRID[4]) == (False, GRID[3])


def test_a_snapshot_from_the_window_agrees_with_the_rule() -> None:
    _reader, ctx = _fixture()
    counts = ingestion._Counts(ctx, GRID)
    for day in (*GRID, date(2026, 10, 20)):
        for table in (DENSE, SPARSE, EMPTY):
            assert counts.carried(table, day) == snapshot_on(ctx, table, day)
