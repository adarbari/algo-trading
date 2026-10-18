"""``futures-curves``: the nightly curve snapshot per configured root (front contracts, prices
and open interest), a root without data a NO_DATA item, an unreachable gateway a skip."""

import math
from dataclasses import replace
from datetime import UTC, date, datetime

import pandas as pd
import pytest

from algotrade.config.site.ibkr import FuturesRoot
from algotrade.config.site.settings import IbkrSettings, SourcesSettings
from algotrade.core.time.calendar import EXCHANGE_TZ
from algotrade.data import StoreReader
from algotrade.data.futures.curves import curve_of, futures_curve
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.runs import RunRecord, RunStatus
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.framework.run import TaskContext
from algotrade_ingestion.tasks.market.futures_curves import (
    nightly_curves,
    settle_cutoff,
)
from tests.helpers.fake_ib import FakeIB
from tests.helpers.ibkr_store import SESSION, ibkr_source
from tests.helpers.ingest_fakes import task_ctx

ROOTS = (
    FuturesRoot("CL", "NYMEX", "CL"),
    FuturesRoot("ZN", "CBOT", "ZN"),
    FuturesRoot("VX", "CFE", "VX"),
)
NAN = float("nan")
# IB tradingHours, in each contract's time zone: a segment's end date is its trade date. Friday
# 2026-10-02's session is followed by the Sunday evening one (CME 17:00 Chicago = 18:00 New York).
CME = ("20261001:1700-20261002:1600;20261003:CLOSED;20261004:1700-20261005:1600;"
       "20261005:1700-20261006:1600", "America/Chicago")  # fmt: skip
GRAINS = ("20261001:1900-20261002:1320;20261003:CLOSED;20261004:1900-20261005:1320;"
          "20261005:1900-20261006:1320", "America/Chicago")  # fmt: skip
SUGAR = ("20261002:0330-20261002:1300;20261003:CLOSED;20261005:0330-20261005:1300;"
         "20261006:0330-20261006:1300", "America/New_York")  # fmt: skip
# Labor Day 2026-09-07: Friday 09-04's next session opens Sunday 17:00 Chicago (the NYSE
# calendar's next session is Tuesday), and Monday's holiday session settles by 12:00 New York.
LABOR_DAY = ("20260903:1700-20260904:1600;20260905:CLOSED;20260906:1700-20260907:1200;"
             "20260907:1700-20260908:1600", "America/Chicago")  # fmt: skip


def fake() -> FakeIB:
    return FakeIB(
        futures={
            "CL": [("20261022", "CL"), ("20261120", "CL"), ("20261218", "CL"), ("20270120", "CL")],
            "ZN": [("20261219", "ZN"), ("20270319", "ZN")],  # listed, but no price arrives
        },
        fut_hours={"CL": CME, "ZN": CME},
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
    # FIXED (18:00 New York on the Friday) is before Globex reopens: `last`, no trade in month 2
    assert frame["price"].iloc[0] == 70.0 and pd.isna(frame["price"].iloc[1])
    assert frame["price_kind"].iloc[0] == "last" and frame["price"].iloc[2] == 71.0
    assert list(frame["open_interest"]) == [4000.0, 3000.0, 2000.0]
    assert frame["knowledge_ts"].notna().all() and frame["ts"].notna().all()
    assert record.items["root:CL"] == "OK: 2/3 last"
    assert record.items["root:ZN"].startswith("NO_DATA: 2 contracts listed, none with a price")
    assert record.items["root:VX"].startswith("NO_DATA: IBKR lists no VX")
    assert record.stats["roots"] == 3 and record.stats["served"] == 1 and record.stats["rows"] == 3


def test_the_curve_rebuilds_basis_and_roll_yield() -> None:
    ctx, reader = market()
    nightly_curves(ctx, ibkr_source(fake(), stream_wait_s=0.05), SESSION)
    curve = curve_of(futures_curve(reader, SESSION, SESSION), "CL", SESSION)
    assert list(curve["days"]) == [20.0, 77.0]  # the unpriced month is not on the curve
    assert curve["roll_yield"].iloc[0] == 0.0
    expected = math.log(70.0 / 71.0) / (57 / 365)  # contango: negative
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


def at(year: int, month: int, day: int, hour: int, minute: int = 0) -> datetime:
    """A New York wall time."""
    return datetime(year, month, day, hour, minute, tzinfo=EXCHANGE_TZ)


QUOTES = {  # (last, close, volume, open interest): `last` is S+1's trade once its session opened
    ("CL", "20261022"): (70.0, 69.0, 1.0, 1.0),
    ("ZC", "20261214"): (450.0, 449.0, 1.0, 1.0),
    ("SB", "20261030"): (15.0, 14.5, 1.0, 1.0),
}


def exchanges(hours: dict[str, tuple[str, str]]) -> FakeIB:
    return FakeIB(
        futures={
            "CL": [("20261022", "CL")],
            "ZC": [("20261214", "ZC")],
            "SB": [("20261030", "SB")],
        },
        fut_hours=hours,
        fut_quotes=QUOTES,
    )


def run_at(now: datetime, ib: FakeIB, session: date = SESSION) -> tuple[RunRecord, StoreReader]:
    backend = MemoryBackend()
    writer, reader = StoreWriter(backend), StoreReader(backend)
    roots = tuple(FuturesRoot(r, "X", r) for r in ("CL", "ZC", "SB"))
    ibkr = replace(IbkrSettings(), futures_roots=roots, futures_front=1, stream_wait_s=0.05)
    ctx = task_ctx(
        writer, reader, clock=lambda: now.astimezone(UTC), settings=SourcesSettings(ibkr=ibkr)
    )
    return nightly_curves(ctx, ibkr_source(ib, stream_wait_s=0.05), session), reader


def kinds(record: RunRecord) -> dict[str, str]:
    """root -> ``price_kind`` stored (or ``NO_DATA``) from the run's items."""
    return {
        k[5:]: v.split()[-1] if v.startswith("OK") else "NO_DATA" for k, v in record.items.items()
    }


HOURS = {"CL": CME, "ZC": GRAINS, "SB": SUGAR}


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (at(2026, 10, 2, 16, 30), {"CL": "last", "ZC": "last", "SB": "last"}),  # earliest start
        (at(2026, 10, 3, 12), {"CL": "last", "ZC": "last", "SB": "last"}),  # Saturday
        (at(2026, 10, 4, 17, 59), {"CL": "last", "ZC": "last", "SB": "last"}),
        # Sunday 18:05: CME reopened (its close rolled), the grains (20:00) and sugar did not
        (at(2026, 10, 4, 18, 5), {"CL": "settle", "ZC": "last", "SB": "last"}),
        (at(2026, 10, 4, 20, 5), {"CL": "settle", "ZC": "settle", "SB": "last"}),
        (at(2026, 10, 5, 3, 35), {"CL": "settle", "ZC": "settle", "SB": "settle"}),
        (at(2026, 10, 5, 11, 59), {"CL": "settle", "ZC": "settle", "SB": "settle"}),
        (at(2026, 10, 5, 12, 0), {"CL": "NO_DATA", "ZC": "NO_DATA", "SB": "NO_DATA"}),
    ],
)
def test_each_contracts_kind_follows_its_own_next_open(
    now: datetime, expected: dict[str, str]
) -> None:
    record, reader = run_at(now, exchanges(HOURS))
    assert kinds(record) == expected
    frame = futures_curve(reader, SESSION, SESSION)
    for root, kind in expected.items():
        if kind == "NO_DATA":
            assert root not in set(frame["root"])
            continue
        [row] = frame[frame["root"] == root].to_dict("records")
        assert row["price_kind"] == kind
        assert row["price"] == (row["last"] if kind == "last" else row["close"])
        assert row["next_open"].tzinfo is not None


def test_a_read_after_the_bound_does_not_open_the_gateway() -> None:
    ib = exchanges(HOURS)
    record, reader = run_at(at(2026, 10, 5, 12, 0), ib)
    assert record.status is RunStatus.PARTIAL and "reqContractDetails" not in ib.calls
    assert futures_curve(reader, SESSION, SESSION).empty
    assert all(v.startswith("NO_DATA: read after 2026-10-05 12:00") for v in record.items.values())
    assert settle_cutoff(SESSION) == at(2026, 10, 5, 12)  # Friday -> Monday


def test_a_holiday_monday_opens_on_sunday_and_settles_before_noon_that_day() -> None:
    session = date(2026, 9, 4)
    ib = exchanges({"CL": LABOR_DAY, "ZC": LABOR_DAY, "SB": LABOR_DAY})
    sunday, monday = at(2026, 9, 6, 18, 5), at(2026, 9, 7, 11, 59)
    assert kinds(run_at(sunday, ib, session)[0])["CL"] == "settle"  # not next_session based
    assert kinds(run_at(monday, ib, session)[0])["CL"] == "settle"
    assert settle_cutoff(session) == at(2026, 9, 7, 12)  # Monday, though the NYSE is shut
    friday = run_at(at(2026, 9, 4, 16, 30), ib, session)[0]
    assert kinds(friday)["CL"] == "last"


@pytest.mark.parametrize(
    "hours",
    [
        ("", ""),
        ("garbage", "America/Chicago"),
        (CME[0], "Nowhere/Land"),
        (CME[0].split(";")[0], CME[1]),
    ],
)
def test_missing_or_unparsable_trading_hours_fail_closed(hours: tuple[str, str]) -> None:
    record, reader = run_at(
        at(2026, 10, 2, 16, 30), exchanges({"CL": hours, "ZC": GRAINS, "SB": SUGAR})
    )
    assert record.items["root:CL"].startswith("NO_DATA: tradingHours missing or unparsable")
    assert set(futures_curve(reader, SESSION, SESSION)["root"]) == {"ZC", "SB"}  # others stored


def test_the_id_is_built_from_the_delivery_month_not_the_last_trade_month() -> None:
    ctx, reader = market()
    ib = FakeIB(futures={"CL": [("20261120", "CL", "202612")]}, fut_hours={"CL": CME},
                fut_quotes={("CL", "20261120"): (70.0, 69.0, 1.0, 1.0)})  # fmt: skip
    nightly_curves(ctx, ibkr_source(ib, stream_wait_s=0.05), SESSION, ["CL"])
    [row] = futures_curve(reader, SESSION, SESSION).to_dict("records")
    assert (row["instrument_id"], row["contract_month"]) == ("FUT:CL:2026-12", "2026-12")
    assert row["expiry"] == date(2026, 11, 20)
