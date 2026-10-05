"""Saved backtest runs over the golden API store: the list (the strategy configs the user and
the site run), one run's detail read as the run left it, and ``None`` for anything that is not
a backtest run."""

import pytest

from algotrade.config.user import UserContext
from algotrade.services.explore.store import ReadStore
from algotrade.services.read.context import (
    ReadContext,
    open_context,
    open_stores,
    run_partition,
)
from algotrade.services.read.ops.backtests import load_backtest, load_backtests
from algotrade.storage.tables.schemas import result_table


@pytest.fixture(scope="module")
def ctx(explore: tuple[ReadStore, dict[str, str]]) -> ReadContext:
    store = explore[0]
    return open_context(store.reader, store.configs, store.user)


def test_the_list_newest_first(ctx: ReadContext, explore: tuple[ReadStore, dict[str, str]]) -> None:
    runs = load_backtests(ctx)
    assert [r.run_id for r in runs] == [explore[1]["backtest"]]
    run = runs[0]
    assert (run.config_id, run.user, run.status, run.start) == (
        "sma_trend", "local", "complete", "2022-01-03",
    )  # fmt: skip
    assert run.metrics == {"sharpe": 1.2} and run.finished_at is not None


def test_the_detail(ctx: ReadContext, explore: tuple[ReadStore, dict[str, str]]) -> None:
    detail = load_backtest(ctx, explore[1]["backtest"])
    assert detail is not None
    assert [p.equity for p in detail.equity] == [100000.0, 101000.0]
    assert [p.gross_exposure for p in detail.equity] == [0.0, 0.9]
    fill = detail.fills[0]
    assert (fill.instrument_id, fill.side, fill.quantity, fill.multiplier) == (
        "EQ:AAA", "BUY", 10.0, 1.0,
    )  # fmt: skip
    assert detail.selection == {"instruments": ["EQ:AAA"]} and detail.rebalances == ()
    assert set(detail.data) == {"as_of", "data_versions", "reference_snapshot", "survivorship_bias"}


def test_not_a_backtest_run_is_none(
    ctx: ReadContext, explore: tuple[ReadStore, dict[str, str]]
) -> None:
    assert load_backtest(ctx, "nope") is None
    assert load_backtest(ctx, ".x") is None
    assert load_backtest(ctx, explore[1]["nightly"]) is None


def test_run_partition_reads_only_session_grain_tables(
    ctx: ReadContext, explore: tuple[ReadStore, dict[str, str]]
) -> None:
    run = ctx.reader.run(explore[1]["backtest"])
    assert run is not None
    with pytest.raises(ValueError, match="grain"):
        run_partition(ctx, "instruments/reference", run)
    assert run_partition(ctx, result_table("nothing_stored"), run) is None


def test_another_users_run_is_not_theirs(explore: tuple[ReadStore, dict[str, str]]) -> None:
    store = explore[0]
    bob = open_stores(store.reader, store.configs, UserContext("bob"))
    assert load_backtests(bob) == ()  # "local" ran it; bob sees only his and the site's
    assert load_backtest(bob, explore[1]["backtest"]) is None
