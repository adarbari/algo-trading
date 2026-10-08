"""Ingestion completeness over the golden store: the window of sessions ending at the session,
each dataset's cells by kind (session, chains, snapshot), and one cell's drill-down."""

from datetime import UTC, date, datetime

import pytest

from algotrade.services.read.context import ReadContext, open_context
from algotrade.services.read.ops.ingestion import (
    Cell,
    load_cell_detail,
    load_completeness,
)
from algotrade_api.deps import ReadStore

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
