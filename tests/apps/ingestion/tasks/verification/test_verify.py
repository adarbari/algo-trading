"""The ``verify`` task end to end against a fake IB Gateway: our stored session (bars, rollups,
chains) compared with IBKR answers built from the same data PASS; a drifted close FAILs; a
missing contract is a FETCH_ERROR; an unreachable gateway is a skip, never a failure."""

import functools
from datetime import date
from typing import Any

import pytest

from algotrade.config.site.settings import VerificationSettings
from algotrade.data import StoreReader
from algotrade.data.prices import raw_bars
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.runs import RunStatus
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.derived.rollups import compute_rollups
from algotrade_ingestion.tasks.verification.verify import TABLE, load_ours, verify
from algotrade_ingestion.workflows.nightly.steps import StepStatus, from_record
from algotrade_sources.vendors.ibkr.gateway import GatewayConfig, IbkrMarketData
from algotrade_sources.vendors.ibkr.market_data import IbkrSource
from tests.helpers.fake_ib import Bar, FakeIB
from tests.helpers.ingest_fakes import task_ctx
from tests.helpers.rollup_store import (
    END,
    chain_rows,
    series,
    store,
    write_bars,
    write_chains,
    write_curve,
    write_dividends,
)
from tests.helpers.stored_frames import stamped, write_reference

NEAR, FAR = date(2026, 10, 16), date(2026, 11, 20)
SETTINGS = VerificationSettings(core_symbols=("A",), rotating=0, option_symbols=("A",))


@functools.cache
def _built() -> tuple[MemoryBackend, float]:
    """The stored session, built once (rollups take a while). Tests share it: verify only
    adds runs, and each test reads the run it just made (the latest wins)."""
    writer, reader = store()
    write_reference(writer, date(2025, 1, 2), {"A": "EQ:A"})
    write_bars(writer, {"EQ:A": series(260, start=100.0)})
    spot = float(series(260, start=100.0)[-1])
    write_dividends(writer, [("EQ:A", date(2026, 6, 1), spot * 0.02, "recurring")])
    strikes = tuple(float(round(spot) + k) for k in range(-10, 11, 2))
    rows = chain_rows("EQ:A", END, spot, {NEAR: 0.3, FAR: 0.3}, 0.04, 0.02, strikes=strikes)
    write_chains(writer, END, rows, {"EQ:A": spot}, cboe_iv30=30.0)
    write_curve(writer, END, 0.04)
    compute_rollups(task_ctx(writer, reader), END)
    return writer._backend, spot


def market() -> tuple[StoreWriter, StoreReader, float]:
    backend, spot = _built()
    return StoreWriter(backend), StoreReader(backend), spot


def ibkr_from_store(reader: StoreReader, spot: float, drift: float = 0.0) -> FakeIB:
    """What IBKR would say if our data were right (``drift`` moves the last close)."""
    bars = reader.table_range("bars/1d", date(2025, 1, 1), END)
    assert bars is not None
    bars = bars.sort_values("session_date")
    rows: list[Bar] = [
        (r.session_date, r.open, r.high, r.low, r.close, r.volume) for r in bars.itertuples()
    ]
    last = rows[-1]
    rows[-1] = (*last[:4], last[4] * (1 + drift), last[5])
    iv = reader.table("rollups/instrument/iv30@v1", END)
    assert iv is not None
    iv30 = float(iv["iv30"].iloc[0])
    options = reader.table("chains/option_quotes", END)
    assert options is not None
    quotes = {
        (f"{r.expiry:%Y%m%d}", float(r.strike), r.right): (r.bid, r.ask)
        for r in options.itertuples()
    }
    return FakeIB(
        bars={"A": rows},
        iv={"A": [(END, iv30, iv30, iv30, iv30, 0.0)]},
        dividends={"A": (spot * 0.02, spot)},
        expirations=[f"{NEAR:%Y%m%d}", f"{FAR:%Y%m%d}"],
        strikes=sorted({float(r.strike) for r in options.itertuples()}),
        quotes=quotes,
    )


def source(fake: FakeIB) -> IbkrSource:
    config = GatewayConfig("127.0.0.1", 4002, 1)
    return IbkrSource(IbkrMarketData(config, ib_factory=lambda: fake), sessions=260)


def run(writer: StoreWriter, reader: StoreReader, fake: FakeIB, **kw: Any) -> Any:
    ctx = task_ctx(writer, reader, sources={"ibkr": source(fake)})
    return verify(ctx, END, settings=kw.pop("settings", SETTINGS), **kw)


def checks(reader: StoreReader) -> dict[tuple[str, str], str]:
    frame = reader.table(TABLE, END)
    assert frame is not None
    return {(str(r.instrument_id), str(r.check)): str(r.status) for r in frame.itertuples()}


def test_matching_data_passes_every_check_and_saves_raw_json() -> None:
    writer, reader, spot = market()
    fake = ibkr_from_store(reader, spot)
    record = run(writer, reader, fake)
    assert record.status is RunStatus.COMPLETE, record.stats
    graded = checks(reader)
    a = {check: status for (iid, check), status in graded.items() if iid == "EQ:A"}
    assert a == dict.fromkeys(
        ["close", "high", "low", "bars_missing", "hv20", "high_52w", "low_52w", "div_yield",
         "iv30", "iv30_cboe"], "PASS",
    )  # fmt: skip
    options = {check: s for (iid, check), s in graded.items() if iid.startswith("OPT:")}
    assert options == {"option_listed": "PASS", "option_mid": "PASS"}
    assert len([k for k in graded if k[0].startswith("OPT:")]) == 4  # the ATM call and put
    assert record.stats["checks"]["PASS"] == len(graded) and record.stats["failing"] == []
    assert record.stats["sample"] == {"core": 1}
    raw = writer.raw.get("ibkr", "market_data", END, record.run_id, "bars__A")
    assert raw is not None and b'"key": "bars__A"' in raw
    assert fake.calls[-1] == "disconnect"  # the session is always closed
    assert "placeOrder" not in fake.calls and "IB.connect" not in fake.calls


def test_a_drifted_close_fails_and_is_an_example() -> None:
    writer, reader, spot = market()
    record = run(writer, reader, ibkr_from_store(reader, spot, drift=0.01))
    assert checks(reader)[("EQ:A", "close")] == "FAIL"
    assert record.stats["failing"][0]["check"] == "close"
    assert record.stats["checks"]["FAIL"] >= 1


def test_an_unknown_contract_is_a_fetch_error_and_the_run_partial() -> None:
    writer, reader, spot = market()
    settings = VerificationSettings(core_symbols=("A", "ZZZZ"), rotating=0, option_symbols=())
    record = run(writer, reader, ibkr_from_store(reader, spot), settings=settings)
    assert record.status is RunStatus.PARTIAL
    assert record.items["EQ:ZZZZ"].startswith("FETCH_ERROR") and record.items["EQ:A"] == "OK"


def test_requested_symbols_only() -> None:
    writer, reader, spot = market()
    record = run(writer, reader, ibkr_from_store(reader, spot), symbols=["a"])
    assert record.stats["sample"] == {"requested": 1} and set(record.items) == {
        "EQ:A",
        "EQ:A#options",
    }


def test_an_unreachable_gateway_is_a_skip_not_a_failure() -> None:
    writer, reader, _ = market()
    record = run(writer, reader, FakeIB(connect_error=ConnectionRefusedError("refused")))
    assert record.status is RunStatus.COMPLETE and "rows" not in record.stats
    assert record.stats["skipped"].startswith("WARN: IB Gateway not reachable on 127.0.0.1:4002")
    outcome = from_record(record)
    assert outcome.status is StepStatus.SKIPPED and "not reachable" in (outcome.reason or "")


def test_a_session_without_a_chain_is_na_for_options() -> None:
    writer, reader, spot = market()
    fake = ibkr_from_store(reader, spot)
    settings = VerificationSettings(core_symbols=("A",), rotating=0, option_symbols=("A",),
                                    options_per_symbol=0)  # fmt: skip
    run(writer, reader, fake, settings=settings)
    assert checks(reader)[("EQ:A", "option_mid")] == "NA"


def test_needs_a_session_source() -> None:
    writer, reader, _ = market()
    ctx = task_ctx(writer, reader, sources={"ibkr": "not a source"})  # type: ignore[dict-item]
    with pytest.raises(TypeError, match="SessionSource"):
        verify(ctx, END, settings=SETTINGS)


def test_a_flagged_bar_is_left_out_of_the_comparison_not_the_whole_sample() -> None:
    writer, reader, _ = market()
    stored = raw_bars(reader, "1d", END, END, ["EQ:A"])
    flag = [{"instrument_id": "EQ:A", "ts": stored["ts"].iloc[0], "reason": "BAD_OHLC",
             "detail": "d", "status": "FLAGGED"}]  # fmt: skip
    writer.write_table("events/bar_flag", END, "flag", stamped(flag, END, "flag"))
    ours = load_ours(reader, END, ["EQ:A"], 20)
    assert "EQ:A" in ours.bars and END not in set(ours.bars["EQ:A"]["date"])
