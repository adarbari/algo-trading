"""The ``rollups`` task runs rollups in dependency order (each reads what the previous one
wrote this run, a materialised expression feature included) and does not compute the
dependents of a rollup that failed. Per entity (ADR 0047): a market group runs only with
``entity="market"``, a backfill writes the rows three nightly runs write, and a market group
that returns anything but its one ``MKT:US`` row fails."""

import dataclasses
from datetime import date

import pandas as pd
import pytest

from algotrade.features.site import site_features
from algotrade.services.features import read_expressions
from algotrade.storage.runs import RunStatus
from algotrade_ingestion.tasks.derived.rollups import SITE, TABLES, compute_rollups
from tests.helpers.ingest_fakes import task_ctx
from tests.helpers.rollup_store import (
    END,
    MARKET_COUNTS,
    chain_rows,
    market_store,
    series,
    store,
    write_bars,
    write_chains,
    write_curve,
    write_dividends,
)

NEAR, FAR = date(2026, 10, 16), date(2026, 11, 20)


def _market() -> tuple[object, object]:
    writer, reader = store()
    write_bars(writer, {"EQ:A": series(260, start=100.0)})
    spot = float(series(260, start=100.0)[-1])
    write_dividends(writer, [("EQ:A", date(2026, 6, 1), spot * 0.02, "recurring")])
    q = 0.02  # the trailing yield div_yield@v1 will compute
    rows = chain_rows("EQ:A", END, spot, {NEAR: 0.3, FAR: 0.3}, 0.04, q, strikes=_strikes(spot))
    write_chains(writer, END, rows, {"EQ:A": spot})
    write_curve(writer, END, 0.04)
    return writer, reader


def _strikes(spot: float) -> tuple[float, ...]:
    base = round(spot)
    return tuple(float(base + k) for k in range(-10, 11, 2))


def test_rollups_read_the_rollups_computed_before_them() -> None:
    writer, reader = _market()
    record = compute_rollups(task_ctx(writer, reader), END)  # type: ignore[arg-type]
    for key in ("div_yield@v1", "iv30@v1", "iv_history@v2"):
        assert record.items[key].startswith("OK"), key
    assert "rollups/instrument/div_yield@v1" in TABLES
    stored = reader.table("rollups/instrument/div_yield@v1", END)  # type: ignore[attr-defined]
    assert stored is not None and str(stored["div_yield"].dtype) == "float32"
    iv = reader.table("rollups/instrument/iv30@v1", END)  # type: ignore[attr-defined]
    assert iv is not None
    a = iv.set_index("instrument_id").loc["EQ:A"]
    assert a["div_yield"] == pytest.approx(0.02)  # the materialised div_yield, this run
    assert a["iv30"] == pytest.approx(0.30, abs=1e-6)  # q = 0.02 recovers the true vol
    hist = reader.table("rollups/instrument/iv_history@v2", END)  # type: ignore[attr-defined]
    assert hist is not None and hist["history_days"].iloc[0] == 1
    assert hist["rank_status"].iloc[0] == "UNKNOWN"
    virtual = read_expressions(reader, ["iv_hv_spread", "liquidity_class"], END)  # type: ignore[arg-type]
    row = virtual.frame.set_index("instrument_id").loc["EQ:A"]
    assert pd.notna(row["iv_hv_spread"]) and row["liquidity_class"] == "LOW"  # $0.1M ADV
    assert virtual.missing == ("rollups/instrument/option_liquidity@v1",)  # no chain status


def test_a_failed_rollup_blocks_its_dependents(monkeypatch: pytest.MonkeyPatch) -> None:
    writer, reader = _market()

    def boom(*args: object) -> pd.DataFrame:
        raise RuntimeError("boom")

    groups = site_features(SITE).groups  # what the task runs (built once per store)
    broken = dataclasses.replace(groups["price_stats@v2"], compute=boom)
    monkeypatch.setitem(groups, "price_stats@v2", broken)
    record = compute_rollups(task_ctx(writer, reader), END)  # type: ignore[arg-type]
    assert record.status is RunStatus.PARTIAL
    assert record.items["price_stats@v2"] == "FETCH_ERROR: boom"
    for key in ("dividends@v2", "fundamentals@v2", "div_yield@v1", "iv30@v1", "iv_history@v2"):
        assert record.items[key] == "FAILED: not computed: price_stats@v2 failed", key
    assert record.items["earnings@v1"] == "NO_INPUT"


STAMPS = ["knowledge_ts", "run_id"]


@pytest.fixture
def with_market(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(site_features(SITE).groups, MARKET_COUNTS.key, MARKET_COUNTS)


@pytest.mark.usefixtures("with_market")
def test_a_market_backfill_writes_the_rows_of_nightly_runs() -> None:
    nightly_writer, nightly, days = market_store()
    for day in days[-3:]:
        record = compute_rollups(task_ctx(nightly_writer), day, entity="market")  # type: ignore[arg-type]
        assert record.job == "market-rollups" and record.items == {
            MARKET_COUNTS.key: "OK: 1 sessions, 1 rows"
        }
    backfill_writer, backfill, _ = market_store()
    record = compute_rollups(  # type: ignore[arg-type]
        task_ctx(backfill_writer), days[-1], start=days[-3], end=days[-1], entity="market"
    )
    assert record.items == {MARKET_COUNTS.key: "OK: 3 sessions, 3 rows"}
    for day in days[-3:]:
        one = nightly.table(MARKET_COUNTS.table, day).drop(columns=STAMPS)  # type: ignore[attr-defined]
        many = backfill.table(MARKET_COUNTS.table, day).drop(columns=STAMPS)  # type: ignore[attr-defined]
        pd.testing.assert_frame_equal(one, many)
        assert list(one["instrument_id"]) == ["MKT:US"]
    last = backfill.table(MARKET_COUNTS.table, days[-1])  # type: ignore[attr-defined]
    assert (last["names"].iloc[0], last["with_bars"].iloc[0]) == (2, 2)
    assert last["spy_close"].iloc[0] == pytest.approx(series(6, seed=3)[-1])


@pytest.mark.usefixtures("with_market")
def test_market_groups_run_only_as_the_market_entity() -> None:
    writer, _, days = market_store()
    with pytest.raises(KeyError, match="unknown rollups"):
        compute_rollups(task_ctx(writer), days[-1], only=[MARKET_COUNTS.key])  # type: ignore[arg-type]


def test_a_market_group_with_two_rows_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    def twice(*args: object) -> pd.DataFrame:
        return pd.DataFrame({"instrument_id": ["MKT:US", "MKT:US"], "names": [1, 2]})

    broken = dataclasses.replace(MARKET_COUNTS, compute=twice)
    monkeypatch.setitem(site_features(SITE).groups, MARKET_COUNTS.key, broken)
    writer, reader, days = market_store()
    record = compute_rollups(task_ctx(writer), days[-1], entity="market")  # type: ignore[arg-type]
    assert record.status is RunStatus.PARTIAL
    assert "returns one MKT:US row, got ['MKT:US', 'MKT:US']" in record.items[MARKET_COUNTS.key]
    assert reader.table(MARKET_COUNTS.table, days[-1]) is None  # type: ignore[attr-defined]
