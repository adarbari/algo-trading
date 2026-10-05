"""``ibkr-iv``: IB's IV history backfill (one request per underlying, most liquid first,
resumable across runs, capped; a request IB did not answer is retried, then left pending, never
NO_DATA) and the nightly snapshot (streamed ticks, then a capped backfill of names without
history); only names with a resolved contract; an unreachable gateway is a skip, never COMPLETE."""

import itertools
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

import pandas as pd
import pytest

from algotrade.config.site.settings import IbkrSettings, SourcesSettings
from algotrade.core.time.calendar import sessions_ending
from algotrade.data import StoreReader
from algotrade.data.volatility import ibkr_iv30
from algotrade.storage.runs import RunStatus, start_run
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.framework.run import TaskContext, finished_runs
from algotrade_ingestion.tasks.market.ibkr_iv import (
    HISTORY_TASK,
    NIGHTLY_TASK,
    STOP_AFTER_FAILED,
    backfill_ivs,
    history_done,
    nightly_ivs,
)
from algotrade_ingestion.tasks.reference.ibkr_contracts import resolve_contracts
from algotrade_sources.vendors.ibkr.market_data import IbkrSource
from tests.helpers.fake_ib import Bar, FakeIB
from tests.helpers.ibkr_store import SESSION, coverage_store, ibkr_source
from tests.helpers.ingest_fakes import CountingLimiter, task_ctx
from tests.helpers.stored_frames import stamped

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


def done_ids(ctx: TaskContext) -> set[str]:
    return history_done(finished_runs(ctx.writer, NIGHTLY_TASK, HISTORY_TASK), START)


def test_backfill_one_iv_request_per_name_and_one_partition_per_session() -> None:
    ctx, reader = market(["A", "B"])
    ib = fake(["A", "B"])
    record = backfill_ivs(ctx, ibkr_source(ib), START, SESSION)
    assert record.status is RunStatus.COMPLETE, record.stats
    assert ib.calls.count("reqHistoricalData") == 2  # the IV only, one per name
    assert {r["whatToShow"] for r in ib.requests} == {"OPTION_IMPLIED_VOLATILITY"}
    assert all(r["durationStr"] == f"{(SESSION - START).days + 1} D" for r in ib.requests)
    assert "qualifyContracts" not in ib.calls  # the stored conid is used
    frame = ibkr_iv30(reader, START, SESSION)
    assert len(frame) == 10 and set(frame["source_kind"]) == {"history"}
    a = frame[frame["instrument_id"] == "EQ:A"]
    assert list(a["iv30_ibkr"]) == [0.2, 0.21, 0.22, 0.23, 0.24]
    assert a["hv30_ibkr"].isna().all()  # HV comes from the nightly snapshot only
    assert record.items["hist:EQ:A"] == f"OK: {START.isoformat()}"
    assert record.stats["sessions_written"] == 5 and record.stats["backfill_pending"] == 0
    assert "placeOrder" not in ib.calls and "IB.connect" not in ib.calls


def test_backfill_resumes_across_runs_and_respects_the_limit() -> None:
    ctx, reader = market(["A", "B", "C"])
    first = backfill_ivs(ctx, ibkr_source(fake(["A", "B", "C"])), START, SESSION, limit=2)
    assert set(first.items) == {"hist:EQ:A", "hist:EQ:B"}
    assert first.stats["backfill_pending"] == 1
    assert first.stats["backfill_eta_h"] == round(1 * 10.0 / 3600, 1)
    ib = fake(["A", "B", "C"])
    second = backfill_ivs(ctx, ibkr_source(ib), START, SESSION)
    assert set(second.items) == {"hist:EQ:C"}  # A and B were done by the first run
    assert ib.calls.count("reqHistoricalData") == 1
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


# ---------------------------------------------------------------- unanswered is not empty


@pytest.mark.parametrize("fault", ["timeout", "pacing", "1100"])
def test_a_request_ib_did_not_answer_is_retried_then_pending_never_no_data(fault: str) -> None:
    ctx, reader = market(["A", "B"])
    ib = fake(["A", "B"])
    ib.faults = {"B": [fault] * 3}
    held = CountingLimiter()
    record = backfill_ivs(ctx, ibkr_source(ib, historical=held), START, SESSION)
    assert record.items["hist:EQ:A"] == f"OK: {START.isoformat()}"
    assert record.items["hist:EQ:B"].startswith("FETCH_ERROR: ")  # never NO_DATA
    assert [r["symbol"] for r in ib.requests].count("B") == 3  # 3 attempts
    assert held.held == 30.0 + 60.0  # back-off on the shared historical limiter
    assert record.status is RunStatus.PARTIAL
    assert record.stats["backfill_failed"] == 1 and record.stats["backfill_pending"] == 1
    assert done_ids(ctx) == {"EQ:A"}
    assert set(ibkr_iv30(reader, START, SESSION)["instrument_id"]) == {"EQ:A"}


def test_a_retry_that_ib_answers_is_ok_and_a_flap_with_bars_is_ok() -> None:
    ctx, _ = market(["A", "B"])
    ib = fake(["A", "B"])
    ib.faults = {"A": ["pacing"], "B": ["flap"]}  # A: 162 once; B: 1100 / 1102, bars still came
    held = CountingLimiter()
    record = backfill_ivs(ctx, ibkr_source(ib, historical=held), START, SESSION)
    assert record.status is RunStatus.COMPLETE, record.stats
    assert record.items["hist:EQ:A"] == record.items["hist:EQ:B"] == f"OK: {START.isoformat()}"
    assert held.held == 30.0 and len(ib.requests) == 3


@pytest.mark.parametrize("fault", ["no-data", None])
def test_a_genuine_empty_answer_stays_no_data(fault: str | None) -> None:
    ctx, _ = market(["A", "B"])
    ib = fake(["A", "B"])
    ib.iv = {"A": ib.iv["A"]}  # IB has no IV bars for B
    ib.faults = {"B": [fault]} if fault else {}  # IB's 162 "query returned no data", or none
    record = backfill_ivs(ctx, ibkr_source(ib), START, SESSION)
    assert record.status is RunStatus.COMPLETE
    assert record.items["hist:EQ:B"] == f"NO_DATA: {START.isoformat()}"
    assert len(ib.requests) == 2  # answered: no retry


def test_a_name_not_fetched_is_fetched_by_a_later_run_and_a_resume() -> None:
    ctx, reader = market(["A", "B"])
    ib = fake(["A", "B"])
    ib.faults = {"B": ["timeout"] * 3}
    first = backfill_ivs(ctx, ibkr_source(ib), START, SESSION)
    assert first.status is RunStatus.PARTIAL and done_ids(ctx) == {"EQ:A"}
    ib = fake(["A", "B"])
    resumed = backfill_ivs(ctx, ibkr_source(ib), START, SESSION)  # same session: a resume
    assert resumed.run_id == first.run_id and resumed.status is RunStatus.COMPLETE
    assert [r["symbol"] for r in ib.requests] == ["B"]  # only the name not fetched
    assert done_ids(ctx) == {"EQ:A", "EQ:B"}
    # and a later run with another end date fetches a name an earlier run left pending
    later = SESSION + timedelta(days=3)
    ib = fake(["A", "B"])
    ib.faults = {"A": ["timeout"] * 3}
    stuck = backfill_ivs(ctx, ibkr_source(ib), START - timedelta(1), later)
    assert stuck.items["hist:EQ:A"].startswith("FETCH_ERROR")
    ib = fake(["A", "B"])
    again = backfill_ivs(ctx, ibkr_source(ib), START - timedelta(1), later + timedelta(1))
    assert [r["symbol"] for r in ib.requests] == ["A"]
    assert again.items == {"hist:EQ:A": f"OK: {(START - timedelta(1)).isoformat()}"}
    assert set(ibkr_iv30(reader, START, SESSION)["instrument_id"]) == {"EQ:A", "EQ:B"}


def test_the_backfill_stops_after_names_failing_in_a_row() -> None:
    names = [f"N{i}" for i in range(STOP_AFTER_FAILED + 2)]
    ctx, _ = market(names)
    ib = fake(names)
    ib.faults = {n: ["timeout"] * 3 for n in names}
    record = backfill_ivs(ctx, ibkr_source(ib), START, SESSION)
    assert len(record.items) == STOP_AFTER_FAILED  # the rest were not even asked
    assert record.status is RunStatus.PARTIAL
    assert record.stats["partial"][0].startswith(
        f"backfill stopped: IB did not answer {STOP_AFTER_FAILED} names in a row"
    )
    assert record.stats["backfill_pending"] == len(names)
    # names a retry cannot fix (no permissions) are not retried and never stop the run
    ctx, _ = market(names)
    ib = fake(names)
    ib.faults = {n: ["denied"] for n in names}
    denied = backfill_ivs(ctx, ibkr_source(ib), START, SESSION)
    assert len(ib.requests) == len(names) == len(denied.items)  # one request each
    assert all(v.startswith("FETCH_ERROR: ") for v in denied.items.values())
    assert "partial" not in denied.stats


def test_names_earlier_runs_could_not_fetch_go_last() -> None:
    ctx, _ = market(["A", "B", "C"])
    ib = fake(["A", "B", "C"])
    ib.faults = {"A": ["denied"]}
    backfill_ivs(ctx, ibkr_source(ib), START, SESSION, limit=1)  # A fails
    ib = fake(["A", "B", "C"])
    later = backfill_ivs(ctx, ibkr_source(ib), START, SESSION + timedelta(days=3))
    assert [r["symbol"] for r in ib.requests] == ["B", "C", "A"]  # A no longer blocks B, C
    assert later.status is RunStatus.COMPLETE


def test_a_history_row_keeps_the_hv_of_the_snapshot_it_replaces() -> None:
    ctx, reader = market(["A"], iv_backfill_per_night=0)
    day = SESSION
    nightly_ivs(ctx, ibkr_source(fake(["A"], vols={"A": (0.5, 0.33)}), stream_wait_s=0.01), day)
    assert ibkr_iv30(reader, day, day)["hv30_ibkr"].tolist() == [0.33]  # the snapshot
    backfill_ivs(ctx, ibkr_source(fake(["A"])), START, SESSION)
    rows = ibkr_iv30(reader, START, SESSION).set_index("session_date")
    assert set(rows["source_kind"]) == {"history"}  # the history replaced the snapshot
    assert rows.loc[day, "hv30_ibkr"] == 0.33 and rows.loc[day, "iv30_ibkr"] == 0.24
    assert rows["hv30_ibkr"].drop(day).isna().all()  # no snapshot, no HV
    backfill_ivs(ctx, ibkr_source(fake(["A"])), START - timedelta(1), SESSION)  # again
    again = ibkr_iv30(reader, START, SESSION).set_index("session_date")
    assert again.loc[day, "hv30_ibkr"] == 0.33  # a second backfill keeps it too


class CrashOnClose(IbkrSource):
    """A source whose session ends with a crash: the run is FAILED, its staging kept."""

    def close(self) -> None:
        super().close()
        raise RuntimeError("the process died")


def test_a_resume_that_cannot_connect_is_not_complete_and_keeps_what_was_fetched() -> None:
    ctx, reader = market(["A", "B"])
    crashing = CrashOnClose(ibkr_source(fake(["A", "B"]), stream_wait_s=0.01).gateway)
    with pytest.raises(RuntimeError, match="died"):
        backfill_ivs(ctx, crashing, START, SESSION, limit=1)
    failed = ctx.writer.runs_for(HISTORY_TASK, SESSION)[-1]
    assert failed.status is RunStatus.FAILED and failed.items == {"hist:EQ:A": f"OK: {START}"}
    assert ibkr_iv30(reader, START, SESSION).empty  # staged, not published
    down = FakeIB(connect_error=ConnectionRefusedError("refused"))
    skipped = backfill_ivs(ctx, ibkr_source(down), START, SESSION)
    assert skipped.run_id == failed.run_id  # the resume of the crashed run
    assert skipped.stats["skipped"].startswith("WARN: IB Gateway not reachable")
    assert skipped.status is RunStatus.PARTIAL  # never COMPLETE
    # what the crashed run had fetched is published, so its OK item is true
    assert set(ibkr_iv30(reader, START, SESSION)["instrument_id"]) == {"EQ:A"}
    ib = fake(["A", "B"])
    finished = backfill_ivs(ctx, ibkr_source(ib), START, SESSION)
    assert [r["symbol"] for r in ib.requests] == ["B"] and finished.status is RunStatus.COMPLETE


# ---------------------------------------------------------------- order


def write_liquidity(
    writer: StoreWriter, rows: dict[str, tuple[float, str | None, str | None]]
) -> None:
    """``price_stats@v2`` (``adv_usd_20d``) and ``option_liquidity@v1`` (tiers) rows on the
    session before ``SESSION`` (symbol -> (ADV, put tier, call tier); a ``None`` tier: no row)."""
    day = SESSION - timedelta(days=1)
    prices: list[dict[str, object]] = [
        {"instrument_id": f"EQ:{s}", "adv_usd_20d": adv, "close": 50.0}
        for s, (adv, _, _) in rows.items()
    ]
    options: list[dict[str, object]] = [
        {"instrument_id": f"EQ:{s}", "liq_status": "OK", "put_tier": put, "call_tier": call,
         "chain_oi": 100_000, "chain_volume": 10_000}
        for s, (_, put, call) in rows.items() if put is not None
    ]  # fmt: skip
    writer.write_table("rollups/instrument/price_stats@v2", day, "r", stamped(prices, day, "r"))
    if options:  # none: the table has no partition that day
        table = "rollups/instrument/option_liquidity@v1"
        writer.write_table(table, day, "r", stamped(options, day, "r"))


def test_the_backfill_fetches_the_most_liquid_names_first() -> None:
    names = ["AAA", "BIG", "HALF", "LOW", "MID", "RICH", "ZNONE"]
    ctx, _ = market(names)
    write_liquidity(
        ctx.writer,
        {
            "BIG": (2e8, "A", "A"),  # tier A, HIGH
            "MID": (2e7, "B", "B"),  # tier B, MEDIUM
            "HALF": (1e6, "B", "D"),  # one side B is enough
            "RICH": (5e8, None, None),  # no option row: not liquid, however big
            "LOW": (1e7, "D", "D"),
        },
    )  # AAA, ZNONE: no rows at all, alphabetical at the end
    ib = fake(names)
    record = backfill_ivs(ctx, ibkr_source(ib), START, SESSION)
    order = ["BIG", "MID", "HALF", "RICH", "LOW", "AAA", "ZNONE"]
    assert [r["symbol"] for r in ib.requests] == order
    assert record.stats["backfill_liquid"] == 3
    ctx, _ = market(names)  # only price_stats stored that day: tiers unknown, ADV still orders
    write_liquidity(ctx.writer, {"LOW": (1e7, None, None), "BIG": (2e8, None, None)})
    ib = fake(names)
    backfill_ivs(ctx, ibkr_source(ib), START, SESSION)
    assert [r["symbol"] for r in ib.requests][:2] == ["BIG", "LOW"]
    ctx, _ = market(names)  # --limit takes the head of that order, --symbols narrows it
    write_liquidity(ctx.writer, {"BIG": (2e8, "A", "A"), "LOW": (1e7, "D", "D")})
    ib = fake(names)
    backfill_ivs(ctx, ibkr_source(ib), START, SESSION, symbols=["low", "AAA", "BIG"], limit=2)
    assert [r["symbol"] for r in ib.requests] == ["BIG", "LOW"]
