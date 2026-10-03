"""``rebalance_selection`` on golden data: a rollup threshold flips between months."""

from datetime import UTC, date, datetime
from typing import Any

import numpy as np
import pytest

from algotrade.config.user import UserContext
from algotrade.core.model.errors import MissingDataError
from algotrade.core.model.types import Side
from algotrade.core.time.calendar import sessions_between
from algotrade.data import StoreReader
from algotrade.engines.selection.evaluate import SelectionResult
from algotrade.services.backtests.rebalance import rebalances
from algotrade.services.backtests.run import BacktestOutcome, run_configured_backtest
from algotrade.services.configs import resolve_config
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import MemoryConfigStore
from algotrade.storage.tables.result_writer import ResultWriter
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.sources.framework.registry import fixture_source
from algotrade_ingestion.tasks.maintenance.golden import load_golden
from tests.conftest import GOLDEN_DIR
from tests.ingest_helpers import task_ctx
from tests.storage_helpers import stamped

T0 = datetime(2026, 10, 3, tzinfo=UTC)
LOADED = datetime(2026, 10, 1, tzinfo=UTC)
START, END = date(2020, 1, 1), date(2020, 6, 30)
FLIP = date(2020, 4, 1)  # BULL is liquid before, BEAR from here on; CHOP always
ADV = "rollup.price_stats@v1.adv_usd_20d"
TABLE = "rollups/instrument/price_stats@v1"
APR_2 = date(2020, 4, 2)  # the bar after the April evaluation (lag 1)


def adv(session: date) -> dict[str, float]:
    early = session < FLIP
    return {"EQ:BULL": 2e6 if early else 5e5, "EQ:BEAR": 5e5 if early else 2e6, "EQ:CHOP": 3e6}


def golden(values: Any = adv, sessions: list[date] | None = None) -> MemoryBackend:
    backend = MemoryBackend()
    writer = StoreWriter(backend)
    load_golden(task_ctx(writer, clock=lambda: LOADED), fixture_source("synthetic", GOLDEN_DIR))
    for session in sessions if sessions is not None else [START, *sessions_between(START, END)]:
        rows = [{"instrument_id": i, "adv_usd_20d": v} for i, v in values(session).items()]
        writer.write_table(TABLE, session, f"ps-{session}", stamped(rows, session, f"ps-{session}"))
    return backend


@pytest.fixture(scope="module")
def backend() -> MemoryBackend:
    return golden()


def config(backtest: dict[str, Any] | None = None, liquid: bool = True) -> dict[str, Any]:
    rules: list[dict[str, Any]] = [
        {"field": "instrument.symbol", "op": "in", "value": ["BULL", "BEAR", "CHOP"]}
    ]
    if liquid:
        rules.append({"field": ADV, "op": "gt", "value": 1e6})
    out: dict[str, Any] = {
        "id": "liquid_sma",
        "kind": "strategy",
        "impl": "sma_crossover",
        "params": {"fast": 2, "slow": 5},
        "selection": {"name": "liquid", "where": {"all": rules}},
    }
    if backtest is not None:
        out["backtest"] = backtest
    return out


def run(
    backend: MemoryBackend, doc: dict[str, Any], writer: ResultWriter | None = None
) -> BacktestOutcome:
    store = MemoryConfigStore({("alice", "strategies", "liquid_sma"): doc})
    resolved = resolve_config(store, "liquid_sma", UserContext("alice"))
    return run_configured_backtest(StoreReader(backend), resolved, START, END, writer, T0)


def test_monthly_rebalance_follows_the_rollup_and_exits_removed(backend: MemoryBackend) -> None:
    outcome = run(backend, config({"rebalance_selection": "monthly"}))
    sets = [(r.evaluated, r.selection.instruments, r.effective) for r in outcome.rebalances]
    assert [s for s, _, _ in sets] == [
        START,
        date(2020, 2, 3),
        date(2020, 3, 2),
        FLIP,
        date(2020, 5, 1),
        date(2020, 6, 1),
    ]
    assert sets[0][1] == ("EQ:BULL", "EQ:CHOP") and sets[0][2] == START
    assert sets[3][1] == ("EQ:BEAR", "EQ:CHOP") and sets[3][2] == APR_2
    april = outcome.rebalances[3]
    assert (april.added, april.removed) == (("EQ:BEAR",), ("EQ:BULL",))
    bull = [f for f in outcome.result.fills if f.instrument_id == "EQ:BULL"]
    held = sum(f.signed_quantity for f in bull if f.timestamp.date() <= APR_2)
    assert held == 0 and all(f.timestamp.date() <= APR_2 for f in bull)
    exit_ = bull[-1]  # SMA held BULL into April: closed at the open of the effective bar
    assert (exit_.side, exit_.timestamp.date()) == (Side.SELL, APR_2)
    bear = [f for f in outcome.result.fills if f.instrument_id == "EQ:BEAR"]
    assert all(f.timestamp.date() > APR_2 for f in bear)  # never before it was selected


def test_audit_is_saved_with_the_run(backend: MemoryBackend) -> None:
    doc = config({"rebalance_selection": "monthly", "selection_lag_sessions": 2})
    outcome = run(backend, doc, ResultWriter(backend))
    (record,) = StoreReader(backend).runs("backtest-liquid_sma-alice", END)
    audit = record.stats["rebalance"]
    assert audit["frequency"] == "monthly" and audit["lag_sessions"] == 2
    assert audit["instruments_ever_selected"] == 3
    april = audit["evaluations"][3]
    assert april["evaluated"] == "2020-04-01" and april["effective"] == "2020-04-03"
    assert april["added"] == ["EQ:BEAR"] and april["removed"] == ["EQ:BULL"]
    assert april["selected"] == 2 and april["survivorship_bias"] is False
    assert april["funnel"]["rules"][1]["passed"] == 2  # the per-rule funnel, reused
    assert len(april["members_hash"]) == 16
    assert audit["mean_turnover"] == pytest.approx(0.1)  # one of two names, once in 5
    assert record.stats["survivorship_bias"] is False
    assert outcome.data_stats()["rebalance"] == audit


def test_default_is_unchanged_and_a_constant_selection_matches_it(backend: MemoryBackend) -> None:
    default = run(backend, config(liquid=False))
    explicit = run(backend, config({"rebalance_selection": "none"}, liquid=False))
    monthly = run(backend, config({"rebalance_selection": "monthly"}, liquid=False))
    assert default.rebalances == () and "rebalance" not in default.data_stats()
    assert default.result.metrics == explicit.result.metrics == monthly.result.metrics
    np.testing.assert_array_equal(default.result.equity, monthly.result.equity)
    assert default.result.fills == monthly.result.fills


def test_a_missing_rollup_on_a_rebalance_session_is_an_error() -> None:
    sparse = golden(sessions=[START])  # rollups only for the start
    with pytest.raises(MissingDataError, match="rebalance session 2020-02-03"):
        run(sparse, config({"rebalance_selection": "monthly"}))


def test_future_data_never_changes_past_selections_or_trades(backend: MemoryBackend) -> None:
    def shifted(session: date) -> dict[str, float]:
        return {i: (1.0 if session >= FLIP else v) for i, v in adv(session).items()}

    other = golden(shifted)
    doc = config({"rebalance_selection": "monthly"})
    base, changed = run(backend, doc), run(other, doc)
    before = [r for r in base.rebalances if r.evaluated < FLIP]
    assert before == [r for r in changed.rebalances if r.evaluated < FLIP]
    assert changed.rebalances[3].selection.instruments == ()  # nothing liquid any more
    days = base.result.timestamps.astype("datetime64[D]")
    cut = int(np.searchsorted(days, np.datetime64(APR_2)))  # first bar the April set trades
    np.testing.assert_array_equal(base.result.equity[:cut], changed.result.equity[:cut])
    assert [f for f in base.result.fills if f.timestamp.date() < APR_2] == [
        f for f in changed.result.fills if f.timestamp.date() < APR_2
    ]


def test_effective_bars_respect_the_lag() -> None:
    days = np.array(["2020-01-01", "2020-01-02", "2020-01-03", "2020-01-06"], "datetime64[D]")
    evaluations = [(date(2020, 1, 1), _empty()), (date(2020, 1, 2), _empty())]
    lag1, lag3 = rebalances(evaluations, days, 1), rebalances(evaluations, days, 3)
    assert [r.effective for r in lag1] == [date(2020, 1, 1), date(2020, 1, 3)]
    assert lag3[1].effective is None  # after the last bar: never applies


def _empty() -> SelectionResult:
    return SelectionResult("s", 0, (), 0, 0, ())
