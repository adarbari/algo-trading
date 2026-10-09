"""The ``outcomes`` task before the first universe snapshot and for the long horizon: the names
are the listing history's alive on S (a delisted name included, never only today's), a name the
listing history says delisted by T is a DELISTED row, and a horizon above ``NIGHTLY_MAX_HORIZON``
is computed only in a backfill."""

from datetime import date

import pandas as pd
import pytest

from algotrade.core.time.calendar import sessions_ending
from algotrade.storage.tables.readers import StoreReader
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.derived import outcomes
from algotrade_ingestion.tasks.derived.outcomes import TABLE, compute_outcomes
from tests.helpers.ingest_fakes import task_ctx
from tests.helpers.rollup_store import END, SPY, series, store, write_bars, write_rows
from tests.helpers.stored_frames import universe_rows

N = 40
Z = "EQ:TIINGO:Z"


def _listing(iid: str | None, ticker: str, asset: str, end: date | None) -> dict[str, object]:
    return {"instrument_id": iid, "ticker": ticker, "exchange": "NASDAQ", "asset_type": asset,
            "price_currency": "USD", "perma_ticker": "", "start_date": date(2000, 1, 3),
            "end_date": end, "ts": pd.Timestamp("2026-10-05", tz="UTC")}  # fmt: skip


def _store() -> tuple[StoreWriter, StoreReader, list[date]]:
    writer, reader = store()
    closes = {"EQ:A": series(N), Z: series(N, seed=2), SPY: series(N, seed=3),
              "EQ:TODAY": series(N, seed=4)}  # fmt: skip
    days = write_bars(writer, closes, skip={Z: [N - 3, N - 2, N - 1]})  # Z's last bar: days[-4]
    ref = [{"instrument_id": i, "symbol": i, "asset_class": "EQ", "security_type": "COMMON_STOCK",
            "multiplier": 1.0, "status": "ACTIVE", "delisted_on": None}
           for i in ("EQ:A", Z, SPY, "EQ:TODAY")]  # fmt: skip
    write_rows(writer, "instruments/reference", days[0], ref)
    # the one universe snapshot is the last session's, so every window start is before it
    write_rows(writer, "universe", days[-1], universe_rows(["A", "TODAY"]))
    write_rows(writer, "universe", days[-1], universe_rows(["SPY"], instrument_id=SPY))
    listings = [_listing("EQ:A", "A", "Stock", None), _listing(Z, "Z", "Stock", days[-4]),
                _listing(SPY, "SPY", "ETF", None), _listing(None, "NOID", "Stock", None)]  # fmt: skip  # noqa: E501
    frame = pd.DataFrame(listings).assign(source="tiingo")
    write_rows(writer, "instruments/listing_history", date(2026, 10, 5), frame.to_dict("records"))
    member = [{"index_name": "SP500", "ticker": "ZZZ", "start_date": date(1999, 1, 4),
               "end_date": None, "ts": pd.Timestamp("2026-10-05", tz="UTC"),
               "source": "sp500_history"}]  # fmt: skip
    write_rows(writer, "instruments/index_membership", date(2026, 10, 5), member)
    return writer, reader, days


def _h6(reader: StoreReader, end: date) -> pd.DataFrame:
    start = sessions_ending(end, 7)[0]
    part = reader.table(TABLE, start)
    assert part is not None
    return part[(part["horizon_sessions"] == 6) & (part["window_end"] == end)]


def test_outcomes_2010_window_uses_listing_universe() -> None:
    writer, reader, _ = _store()
    record = compute_outcomes(task_ctx(writer), END)
    rows = _h6(reader, END)
    assert set(rows["instrument_id"]) == {"EQ:A", Z, SPY}  # not EQ:TODAY, not the id-less listing
    assert record.stats["h6"]["pre_snapshot"] is False  # the listing universe, not survivors


def test_tiingo_delisted_name_is_delisted_row() -> None:
    writer, reader, _ = _store()
    record = compute_outcomes(task_ctx(writer), END)
    z = _h6(reader, END).set_index("instrument_id").loc[Z]
    assert z["outcome_status"] == "DELISTED"
    assert record.stats["h6"]["reasons"] == 0


def test_a_delisting_after_the_window_end_is_not_known_then() -> None:
    writer, reader, days = _store()
    early = days[-7]  # Z has bars through it; its end_date (days[-4]) is after
    compute_outcomes(task_ctx(writer), days[-1], days[-8], days[-1])
    z = _h6(reader, early).set_index("instrument_id").loc[Z]
    assert z["outcome_status"] == "COMPLETE"  # a bar at T; and never marked gone by a later date


def test_a_horizon_above_the_nightly_cap_is_computed_only_in_a_backfill(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(outcomes, "horizons_and_benchmarks", lambda _c=None: ([6, 504], ["SPY"]))
    writer, _, days = _store()
    nightly = compute_outcomes(task_ctx(writer), END)
    assert nightly.items["h504"] == "BACKFILL_ONLY" and nightly.items["h6"].startswith("OK")
    backfill = compute_outcomes(task_ctx(writer), END, days[-3], END)
    assert backfill.items["h504"] == "BEFORE_HISTORY"
