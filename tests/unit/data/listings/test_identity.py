"""``memoised_identity``: the identity of a session is computed once per (reader, published
sequence, session, as_of) and again after a publish; the memo stays small. ``historical_reference``:
a delisted name keeps the security type the listing history stored; only a null type is the
counted proxy (ADR 0087)."""

import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date

import pandas as pd

from algotrade.data.listings import identity
from algotrade.data.listings.identity import (
    HistoricalIdentity,
    historical_reference,
    memoised_identity,
)
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.readers import StoreReader
from algotrade.storage.tables.writers import StoreWriter

S = date(2012, 6, 1)


@dataclass
class _Reader:
    seq: int = 1
    own_run: str | None = None

    def version(self) -> tuple[str, int]:
        return ("live", self.seq)


def _computer(calls: list[int]):  # type: ignore[no-untyped-def]
    def compute() -> HistoricalIdentity | None:
        calls.append(1)
        return HistoricalIdentity(S, pd.DataFrame(), frozenset())

    return compute


def test_one_computation_per_published_sequence_and_session() -> None:
    reader, calls = _Reader(), []
    compute = _computer(calls)
    first = memoised_identity(reader, S, None, compute)  # type: ignore[arg-type]
    assert memoised_identity(reader, S, None, compute) is first  # type: ignore[arg-type]
    assert len(calls) == 1
    memoised_identity(reader, date(2012, 6, 4), None, compute)  # type: ignore[arg-type]
    assert len(calls) == 2  # another session
    reader.seq = 2  # a commit published: the earlier entry is unreachable
    assert memoised_identity(reader, S, None, compute) is not first  # type: ignore[arg-type]
    assert len(calls) == 3
    mine = _Reader(own_run="r")  # pending writes do not move visible_seq: never memoised
    memoised_identity(mine, S, None, compute)  # type: ignore[arg-type]
    memoised_identity(mine, S, None, compute)  # type: ignore[arg-type]
    assert len(calls) == 5


def test_the_memo_is_bounded_and_keeps_none() -> None:
    reader, calls = _Reader(), []
    for k in range(identity._MEMO_SIZE + 3):
        memoised_identity(reader, date(2012, 1, 1 + k), None, _computer(calls))  # type: ignore[arg-type]
    assert len(identity._memo) == identity._MEMO_SIZE
    assert memoised_identity(reader, S, None, lambda: None) is None  # type: ignore[arg-type]
    assert memoised_identity(reader, S, None, _computer(calls)) is None  # type: ignore[arg-type]


def test_the_memo_is_guarded_by_a_lock() -> None:
    assert isinstance(identity._lock, type(threading.Lock()))
    reader, calls = _Reader(), []
    with ThreadPoolExecutor(4) as pool:
        list(
            pool.map(
                lambda k: memoised_identity(
                    reader, date(2012, 1, 1 + k % 5), None, _computer(calls)
                ),
                range(40),
            )
        )  # type: ignore[arg-type]
    assert len(identity._memo) <= identity._MEMO_SIZE


def _store(rows: list[tuple[str, str, str, str | None, str]]) -> StoreReader:
    """Listing rows (id, ticker, asset_type, security_type, source), all NASDAQ and listed
    2005-2015, and an S&P 500 membership snapshot."""
    backend, day = MemoryBackend(), date(2026, 10, 5)
    now = pd.Timestamp(day, tz="UTC")
    listings = pd.DataFrame(
        [
            {"instrument_id": i, "ticker": t, "exchange": "NASDAQ", "asset_type": a,
             "security_type": k, "source": src, "start_date": date(2005, 1, 3),
             "end_date": date(2015, 1, 2)}
            for i, t, a, k, src in rows
        ]
    ).assign(ts=now, session_date=day, knowledge_ts=now, run_id="r")  # fmt: skip
    members = pd.DataFrame(
        {"index_name": ["SP500"], "ticker": ["NONE"], "start_date": [date(2000, 1, 3)],
         "end_date": [None], "ts": [now], "session_date": [day], "knowledge_ts": [now],
         "source": ["x"], "run_id": ["m"]}
    )  # fmt: skip
    writer = StoreWriter(backend)
    writer.write_table("instruments/listing_history", day, "r", listings)
    writer.write_table("instruments/index_membership", day, "m", members)
    return StoreReader(backend)


def test_a_delisted_warrant_is_typed_warrant_and_only_a_null_type_uses_the_proxy() -> None:
    reader = _store(
        [
            ("EQ:W", "WARR", "Stock", "WARRANT", "massive"),  # Massive typed it: kept
            ("EQ:N", "NOTYPE", "Stock", None, "tiingo"),  # no type: the common stock proxy, counted
            ("EQ:E", "ETFNULL", "ETF", None, "tiingo"),  # no type, an ETF row: an ETF, no proxy
            ("EQ:F", "ETFTYPE", "ETF", "ETF", "massive"),
            ("EQ:T", "TODAY", "Stock", "UNIT", "tiingo"),  # alive in today's snapshot: its own row
        ]
    )
    today = pd.DataFrame(
        {"instrument_id": ["EQ:T"], "symbol": ["TODAY"], "security_type": ["COMMON_STOCK"],
         "status": ["ACTIVE"], "optionable": [True], "is_etf": [False]}
    )  # fmt: skip
    found = historical_reference(reader, S, today)
    by = found.frame.set_index("instrument_id")
    assert by.loc["EQ:W", "security_type"] == "WARRANT" and not by.loc["EQ:W", "is_etf"]
    assert by.loc["EQ:N", "security_type"] == "COMMON_STOCK"
    assert by.loc["EQ:E", "security_type"] == "ETF" and by.loc["EQ:E", "is_etf"]
    assert by.loc["EQ:F", "security_type"] == "ETF" and by.loc["EQ:F", "is_etf"]
    assert by.loc["EQ:T", "security_type"] == "COMMON_STOCK"  # today's row, the disclosed tilt
    assert found.type_proxy_ids == frozenset({"EQ:N"})
    assert found.proxy_ids == frozenset({"EQ:W", "EQ:N", "EQ:E", "EQ:F"})  # unchanged meaning
    ids = {"EQ:W", "EQ:N", "EQ:E", "EQ:F", "EQ:T"}
    assert found.paths(ids) == {"today_flag": 1, "proxy": 4}  # paths() is unchanged
    assert found.type_paths(ids) == {"today_flag": 1, "stored_type": 3, "type_proxy": 1}
