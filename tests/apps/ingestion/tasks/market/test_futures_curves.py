"""``futures-curves``: the nightly curve snapshot per configured root (front contracts, prices
and open interest), a root without data a NO_DATA item, an unreachable gateway a skip."""

import math
from dataclasses import replace
from datetime import date

import pytest

from algotrade.config.site.ibkr import FuturesRoot
from algotrade.config.site.settings import IbkrSettings, SourcesSettings
from algotrade.data import StoreReader
from algotrade.data.futures.curves import curve_of, futures_curve
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.runs import RunStatus
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.framework.run import TaskContext
from algotrade_ingestion.tasks.market.futures_curves import nightly_curves
from tests.helpers.fake_ib import FakeIB
from tests.helpers.ibkr_store import SESSION, ibkr_source
from tests.helpers.ingest_fakes import task_ctx

ROOTS = (
    FuturesRoot("CL", "NYMEX", "CL"),
    FuturesRoot("ZN", "CBOT", "ZN"),
    FuturesRoot("VX", "CFE", "VX"),
)
NAN = float("nan")


def fake() -> FakeIB:
    return FakeIB(
        futures={
            "CL": [("20261022", "CL"), ("20261120", "CL"), ("20261218", "CL"), ("20270120", "CL")],
            "ZN": [("20261219", "ZN"), ("20270319", "ZN")],  # listed, but no price arrives
        },
        fut_quotes={
            ("CL", "20261022"): (70.0, 69.0, 900.0, 4000.0),
            ("CL", "20261120"): (NAN, 70.5, 500.0, 3000.0),  # no trade yet: IB's close
            ("CL", "20261218"): (71.0, 70.8, 300.0, 2000.0),
        },
    )


def market(front: int = 3) -> tuple[TaskContext, StoreReader]:
    backend = MemoryBackend()
    writer, reader = StoreWriter(backend), StoreReader(backend)
    ibkr = replace(IbkrSettings(), futures_roots=ROOTS, futures_front=front, stream_wait_s=0.05)
    return task_ctx(writer, reader, settings=SourcesSettings(ibkr=ibkr)), reader


def test_stores_the_front_contracts_per_root_with_ids_prices_and_open_interest() -> None:
    ctx, reader = market()
    record = nightly_curves(ctx, ibkr_source(fake(), stream_wait_s=0.05), SESSION)
    frame = futures_curve(reader, SESSION, SESSION)
    assert record.status is RunStatus.COMPLETE, record.stats
    assert set(frame["root"]) == {"CL"} and len(frame) == 3  # the front 3, not the 4th month
    assert list(frame["instrument_id"]) == ["FUT:CL:2026-10", "FUT:CL:2026-11", "FUT:CL:2026-12"]
    assert set(frame["parent_id"]) == {"FUT:CL"} and set(frame["source"]) == {"ibkr"}
    assert list(frame["expiry"]) == [date(2026, 10, 22), date(2026, 11, 20), date(2026, 12, 18)]
    assert list(frame["price"]) == [70.0, 70.5, 71.0]
    assert list(frame["price_kind"]) == ["last", "close", "last"]
    assert list(frame["open_interest"]) == [4000.0, 3000.0, 2000.0]
    assert frame["knowledge_ts"].notna().all() and frame["ts"].notna().all()
    assert record.items["root:CL"] == "OK: 3/3"
    assert record.items["root:ZN"].startswith("NO_DATA: 2 contracts listed, none with a price")
    assert record.items["root:VX"].startswith("NO_DATA: IBKR lists no VX")
    assert record.stats["roots"] == 3 and record.stats["served"] == 1 and record.stats["rows"] == 3


def test_the_curve_rebuilds_basis_and_roll_yield() -> None:
    ctx, reader = market()
    nightly_curves(ctx, ibkr_source(fake(), stream_wait_s=0.05), SESSION)
    curve = curve_of(futures_curve(reader, SESSION, SESSION), "CL", SESSION)
    assert list(curve["days"]) == [20.0, 49.0, 77.0]
    assert curve["roll_yield"].iloc[0] == 0.0
    expected = math.log(70.0 / 70.5) / (29 / 365)  # contango: negative
    assert curve["roll_yield"].iloc[1] == pytest.approx(expected) and expected < 0
    assert curve_of(futures_curve(reader, SESSION, SESSION), "CL", date(2026, 10, 3)).empty


def test_only_the_named_roots_are_asked() -> None:
    ctx, reader = market()
    ib = fake()
    nightly_curves(ctx, ibkr_source(ib, stream_wait_s=0.05), SESSION, ["CL"])
    assert [r["symbol"] for r in ib.requests] == ["CL"]
    assert futures_curve(reader, SESSION, SESSION, ["CL"]).shape[0] == 3
    assert futures_curve(reader, SESSION, SESSION, ["NG"]).empty


def test_an_unreachable_gateway_is_a_skip_never_complete() -> None:
    ctx, reader = market()
    down = FakeIB(connect_error=ConnectionRefusedError("refused"))
    record = nightly_curves(ctx, ibkr_source(down), SESSION)
    assert record.stats["skipped"].startswith("WARN: IB Gateway not reachable")
    assert record.status is RunStatus.PARTIAL and futures_curve(reader, SESSION, SESSION).empty


def test_it_never_calls_an_order_or_account_api() -> None:
    ctx, _ = market()
    ib = fake()
    nightly_curves(ctx, ibkr_source(ib, stream_wait_s=0.05), SESSION)
    assert not {"placeOrder", "reqPositions", "accountValues", "IB.connect"} & set(ib.calls)
    assert "reqHistoricalData" not in ib.calls  # live streams only: no historical pacing
