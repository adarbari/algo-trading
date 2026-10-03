"""``ibkr-iv``: IB's IV / HV history backfill (one request per series per underlying, resumable
across runs, capped) and the nightly snapshot (streamed ticks, then a capped backfill of names
without history); only names with a resolved contract; an unreachable gateway is a skip."""

import itertools
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

import pandas as pd

from algotrade.config.site.settings import IbkrSettings, SourcesSettings
from algotrade.core.time.calendar import sessions_ending
from algotrade.data import StoreReader
from algotrade.data.volatility import ibkr_iv30
from algotrade.storage.runs import RunStatus, start_run
from algotrade_ingestion.tasks.framework.run import TaskContext
from algotrade_ingestion.tasks.market.ibkr_iv import backfill_ivs, history_done, nightly_ivs
from algotrade_ingestion.tasks.reference.ibkr_contracts import resolve_contracts
from tests.helpers.fake_ib import Bar, FakeIB
from tests.helpers.ibkr_store import SESSION, coverage_store, ibkr_source
from tests.helpers.ingest_fakes import task_ctx

DAYS = sessions_ending(SESSION, 5)
START = DAYS[0]


def bars(values: list[float]) -> list[Bar]:
    return [(d, v, v, v, v, 0.0) for d, v in zip(DAYS, values, strict=True)]


def fake(names: list[str], vols: dict[str, tuple[float, float]] | None = None) -> FakeIB:
    return FakeIB(
        bars={s: bars([1.0] * 5) for s in names},
        iv={s: bars([0.2, 0.21, 0.22, 0.23, 0.24]) for s in names},
        hv={s: bars([0.15] * 5) for s in names},
        vols=vols or {},
    )


def settings(**ibkr: object) -> SourcesSettings:
    return SourcesSettings(ibkr=replace(IbkrSettings(), **ibkr))  # type: ignore[arg-type]


def ticking() -> Callable[[], datetime]:
    """A clock one minute later at each call: every run gets its own run id."""
    times = itertools.count()
    return lambda: datetime(2026, 10, 2, 22, tzinfo=UTC) + timedelta(minutes=next(times))


def market(names: list[str], **ibkr: object) -> tuple[TaskContext, StoreReader]:
    """A store with the coverage and resolved contracts for ``names``."""
    writer, reader = coverage_store(names)
    ctx = task_ctx(writer, reader, clock=ticking(), settings=settings(**ibkr))
    resolve_contracts(ctx, ibkr_source(fake(names)), SESSION)
    return ctx, reader


def test_backfill_one_request_per_series_and_one_partition_per_session() -> None:
    ctx, reader = market(["A", "B"])
    ib = fake(["A", "B"])
    record = backfill_ivs(ctx, ibkr_source(ib), START, SESSION)
    assert record.status is RunStatus.COMPLETE, record.stats
    assert ib.calls.count("reqHistoricalData") == 4  # (IV, HV) x 2 names
    assert {r["whatToShow"] for r in ib.requests} == {
        "OPTION_IMPLIED_VOLATILITY",
        "HISTORICAL_VOLATILITY",
    }
    assert all(r["durationStr"] == f"{(SESSION - START).days + 1} D" for r in ib.requests)
    assert "qualifyContracts" not in ib.calls  # the stored conid is used
    frame = ibkr_iv30(reader, START, SESSION)
    assert len(frame) == 10 and set(frame["source_kind"]) == {"history"}
    a = frame[frame["instrument_id"] == "EQ:A"]
    assert list(a["iv30_ibkr"]) == [0.2, 0.21, 0.22, 0.23, 0.24]
    assert list(a["hv30_ibkr"]) == [0.15] * 5
    assert record.items["hist:EQ:A"] == f"OK: {START.isoformat()}"
    assert record.stats["sessions_written"] == 5 and record.stats["backfill_pending"] == 0
    assert "placeOrder" not in ib.calls and "IB.connect" not in ib.calls


def test_backfill_resumes_across_runs_and_respects_the_limit() -> None:
    ctx, reader = market(["A", "B", "C"])
    first = backfill_ivs(ctx, ibkr_source(fake(["A", "B", "C"])), START, SESSION, limit=2)
    assert set(first.items) == {"hist:EQ:A", "hist:EQ:B"}
    assert first.stats["backfill_pending"] == 1
    assert first.stats["backfill_eta_h"] == round(2 * 10.0 / 3600, 1)
    ib = fake(["A", "B", "C"])
    second = backfill_ivs(ctx, ibkr_source(ib), START, SESSION)
    assert set(second.items) == {"hist:EQ:C"}  # A and B were done by the first run
    assert ib.calls.count("reqHistoricalData") == 2
    earlier = backfill_ivs(ctx, ibkr_source(fake(["A", "B", "C"])), START - timedelta(1), SESSION)
    assert len(earlier.items) == 3  # an earlier start needs the history again
    assert set(ibkr_iv30(reader, START, SESSION)["instrument_id"]) == {"EQ:A", "EQ:B", "EQ:C"}


def test_history_done_reads_ok_and_no_data_items_from_an_earlier_start() -> None:
    record = start_run("ibkr_iv_history", SESSION, pd.Timestamp("2026-10-02", tz="UTC"))
    record.items = {"hist:EQ:A": "OK: 2024-10-01", "hist:EQ:B": "NO_DATA: 2024-10-01",
                    "hist:EQ:C": "FETCH_ERROR: x", "snap:EQ:A": "OK: 1/1"}  # fmt: skip
    assert history_done([record], date(2024, 10, 1)) == {"EQ:A", "EQ:B"}
    assert history_done([record], date(2024, 9, 30)) == set()


def test_a_name_without_history_is_no_data_not_a_failure() -> None:
    ctx, _ = market(["A", "B"])
    ib = fake(["A", "B"])
    ib.iv = {"A": ib.iv["A"]}
    ib.hv = {"A": ib.hv["A"]}
    record = backfill_ivs(ctx, ibkr_source(ib), START, SESSION)
    assert record.status is RunStatus.COMPLETE
    assert record.items["hist:EQ:B"] == f"NO_DATA: {START.isoformat()}"


def test_nightly_snapshot_then_a_capped_backfill_of_names_without_history() -> None:
    ctx, reader = market(["A", "B", "C"], iv_batch=2, iv_backfill_per_night=1)
    ib = fake(["A", "B", "C"], vols={"A": (0.31, 0.25), "B": (0.4, float("nan"))})
    record = nightly_ivs(ctx, ibkr_source(ib, stream_wait_s=0.01), SESSION)
    assert record.status is RunStatus.COMPLETE, record.stats
    today = ibkr_iv30(reader, SESSION, SESSION)
    snap = today[today["source_kind"] == "snapshot"].set_index("instrument_id")
    assert snap.loc["EQ:A", "iv30_ibkr"] == 0.31 and snap.loc["EQ:A", "hv30_ibkr"] == 0.25
    assert pd.isna(snap.loc["EQ:B", "hv30_ibkr"]) and "EQ:C" not in snap.index  # no ticks
    assert ib.calls.count("reqMktData 104,106") == 3
    assert ib.calls.count("cancelMktData") == 3  # every stream is cancelled
    assert record.stats["with_iv"] == 2 and record.stats["coverage_pct"] == 66.7
    # then the history of ONE name (the cap), up to the session before: no overlap with today
    assert record.stats["backfilled"] == 1 and record.stats["backfill_pending"] == 2
    hist = ibkr_iv30(reader, START, SESSION)
    hist = hist[hist["source_kind"] == "history"]
    assert set(hist["instrument_id"]) == {"EQ:A"} and max(hist["session_date"]) < SESSION


def test_names_without_a_contract_are_left_out() -> None:
    writer, reader = coverage_store(["A", "B"])
    ctx = task_ctx(writer, reader, clock=ticking(), settings=settings(iv_backfill_per_night=0))
    resolve_contracts(ctx, ibkr_source(fake(["A"])), SESSION)  # IB knows A only
    ib = fake(["A", "B"], vols={"A": (0.3, 0.2), "B": (0.3, 0.2)})
    record = nightly_ivs(ctx, ibkr_source(ib, stream_wait_s=0.01), SESSION)
    assert record.stats["underlyings"] == 2 and record.stats["with_contract"] == 1
    assert list(ibkr_iv30(reader, SESSION, SESSION)["instrument_id"]) == ["EQ:A"]


def test_an_unreachable_gateway_is_a_skip() -> None:
    ctx, reader = market(["A"])
    ib = FakeIB(connect_error=ConnectionRefusedError("refused"))
    record = nightly_ivs(ctx, ibkr_source(ib), SESSION)
    assert record.stats["skipped"].startswith("WARN: IB Gateway not reachable")
    assert ibkr_iv30(reader, SESSION, SESSION).empty
