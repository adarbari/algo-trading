"""``ibkr-contracts``: conids for the optionable coverage through the read-only facade; new and
renamed names at once, the rest once per refresh window (spread by key); full snapshots with
rows carried forward; unknown names NOT_FOUND; an unreachable gateway is a skip."""

from dataclasses import replace
from datetime import date, timedelta

import pandas as pd

from algotrade.config.site.settings import IbkrSettings, SourcesSettings
from algotrade.data.reference import ibkr_contracts
from algotrade.storage.runs import RunStatus
from algotrade_ingestion.tasks.market.option_chains import Underlying
from algotrade_ingestion.tasks.reference.ibkr_contracts import plan, resolve_contracts
from tests.helpers.fake_ib import FakeIB
from tests.helpers.ibkr_store import SESSION, coverage_store, ibkr_source, write_coverage
from tests.helpers.ingest_fakes import task_ctx

BAR = (SESSION, 1.0, 1.0, 1.0, 1.0, 0.0)


def fake(*symbols: str) -> FakeIB:
    return FakeIB(bars={s: [BAR] for s in symbols})


def settings(batch: int = 2, refresh: int = 30) -> SourcesSettings:
    ibkr = replace(IbkrSettings(), contracts_batch=batch, contracts_refresh_days=refresh)
    return SourcesSettings(ibkr=ibkr)


def stored(rows: list[tuple[str, str, int, date]]) -> pd.DataFrame:
    return pd.DataFrame(
        [{"instrument_id": i, "symbol": s, "conid": c, "resolved_at": d} for i, s, c, d in rows]
    )


def test_plan_new_and_renamed_first_then_by_slot_day() -> None:
    names = [Underlying("EQ:A", "A"), Underlying("EQ:B", "B2"), Underlying("EQ:C", "C")]
    old = stored([("EQ:B", "B", 1, SESSION), ("EQ:C", "C", 2, SESSION), ("EQ:X", "X", 3, SESSION)])
    p = plan(names, old, SESSION, IbkrSettings())
    assert [u.instrument_id for u in p.due] == ["EQ:A", "EQ:B"]  # new, renamed (B -> B2)
    assert list(p.carried["instrument_id"]) == ["EQ:C"]  # EQ:X left the coverage: dropped
    later = plan(names, old, SESSION + timedelta(days=31), IbkrSettings())
    assert {u.instrument_id for u in later.due} == {"EQ:A", "EQ:B", "EQ:C"}  # past the window
    capped = plan(names, None, SESSION, IbkrSettings(), limit=1)
    assert len(capped.due) == 1 and capped.deferred == 2
    named = plan(names, old, SESSION, IbkrSettings(), wanted={"EQ:C"})
    assert [u.instrument_id for u in named.due] == ["EQ:C"]  # named names are always due
    assert set(named.carried["instrument_id"]) == set()  # B renamed: not carried as is


def test_resolves_in_batches_and_writes_a_full_snapshot() -> None:
    writer, reader = coverage_store(["A", "BB", "ZZZ"])
    ib = fake("A", "BB")
    ctx = task_ctx(writer, reader, sources={}, settings=settings(batch=2))
    record = resolve_contracts(ctx, ibkr_source(ib), SESSION)
    assert record.status is RunStatus.COMPLETE, record.stats
    assert record.items == {"EQ:A": "OK", "EQ:BB": "OK", "EQ:ZZZ": "NOT_FOUND"}
    assert ib.calls.count("qualifyContracts") == 2  # two batches
    assert "placeOrder" not in ib.calls and "IB.connect" not in ib.calls
    assert ib.calls[-1] == "disconnect"
    frame = ibkr_contracts(reader, SESSION)
    assert frame is not None
    rows = {r.instrument_id: (r.conid, r.primary_exchange) for r in frame.itertuples()}
    assert rows == {"EQ:A": (1001, "NASDAQ"), "EQ:BB": (1002, "NASDAQ")}
    assert record.stats["resolved"] == 2 and record.stats["not_found"] == 1
    assert record.stats["coverage_pct"] == 66.7


def test_the_next_run_carries_rows_and_resolves_only_new_names() -> None:
    writer, reader = coverage_store(["A", "B"])
    ctx = task_ctx(writer, reader, settings=settings())
    resolve_contracts(ctx, ibkr_source(fake("A", "B")), SESSION)
    nxt = SESSION + timedelta(days=1)
    write_coverage(writer, ["A", "B", "C"], nxt)
    ib = fake("A", "B", "C")
    record = resolve_contracts(ctx, ibkr_source(ib), nxt)
    assert record.items == {"EQ:C": "OK"}
    frame = ibkr_contracts(reader, nxt)
    assert frame is not None and sorted(frame["instrument_id"]) == ["EQ:A", "EQ:B", "EQ:C"]
    resolved = dict(zip(frame["instrument_id"], frame["resolved_at"], strict=True))
    assert pd.Timestamp(resolved["EQ:A"]).date() == SESSION  # carried as resolved then
    assert ibkr_contracts(reader, SESSION - timedelta(days=1)) is None  # never a later one


def test_a_failed_batch_is_a_fetch_error_and_the_run_partial() -> None:
    writer, reader = coverage_store(["A"])
    ib = fake("A")

    def broken(*contracts: object) -> list[object]:
        raise TimeoutError("no answer")

    ib.qualifyContracts = broken  # type: ignore[method-assign]
    record = resolve_contracts(
        task_ctx(writer, reader, settings=settings()), ibkr_source(ib), SESSION
    )
    assert record.status is RunStatus.PARTIAL
    assert record.items["EQ:A"].startswith("FETCH_ERROR")


def test_an_unreachable_gateway_is_a_skip() -> None:
    writer, reader = coverage_store(["A"])
    ib = FakeIB(connect_error=ConnectionRefusedError("refused"))
    record = resolve_contracts(task_ctx(writer, reader), ibkr_source(ib), SESSION)
    assert record.stats["skipped"].startswith("WARN: IB Gateway not reachable")
    assert ibkr_contracts(reader, SESSION) is None
