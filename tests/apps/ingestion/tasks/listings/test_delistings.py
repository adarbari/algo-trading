"""The delistings task on synthetic stores (ADR 0087 decisions 4 and 5): a row per delisted id with
its reason, last close and terminal basis, the OTC window of 10 sessions, an id with two
listings, the point-in-time reads and the run's acceptance and stats."""

from collections.abc import Sequence
from datetime import UTC, date, datetime, time
from typing import Any

import numpy as np
import pandas as pd
import pytest

from algotrade.core.model.errors import MissingDataError
from algotrade.core.time.calendar import sessions_ending
from algotrade.data.listings.delistings import TABLE, known_by, read_delistings
from algotrade.storage.runs import RunRecord, RunStatus
from algotrade.storage.tables.readers import StoreReader
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.listings.delistings import ingest_delistings
from tests.helpers.ingest_fakes import task_ctx
from tests.helpers.rollup_store import END, store, write_bars, write_rows

N = 60
DAYS = sessions_ending(END, N)
LAST = 30  # index of the default last trading day
DAY = DAYS[LAST]
HISTORY = "instruments/listing_history"


def listing(
    iid: str | None, end: date | None, exchange: str = "NYSE", cik: str | None = "0001"
) -> dict[str, Any]:
    return {
        "instrument_id": iid, "ticker": (iid or "NOID")[-4:], "exchange": exchange,
        "asset_type": "Stock", "price_currency": "USD", "perma_ticker": "",
        "start_date": date(2000, 1, 3), "end_date": end, "security_type": "COMMON_STOCK",
        "cik": cik, "source": "tiingo", "ts": pd.Timestamp("2026-10-05", tz="UTC"),
    }  # fmt: skip


def filing(
    iid: str, form: str, items: str = "", day: date = DAY, hour: int = 14, n: int = 1
) -> dict[str, Any]:
    return {
        "instrument_id": iid, "ts": datetime.combine(day, time(hour), UTC),
        "known_from": day, "cik": "0001", "form": form, "accession": f"0001-{iid}-{n}",
        "filing_date": day, "items": items,
    }  # fmt: skip


def closes(last: int, otc: int | None = None, otc_close: float = 4.0) -> np.ndarray:
    """Close 10.0 through ``last``, then no bar; one OTC print at index ``otc``."""
    out = np.full(N, np.nan)
    out[: last + 1] = 10.0
    if otc is not None:
        out[otc] = otc_close
    return out


def world(
    specs: dict[str, np.ndarray],
    listings: list[dict[str, Any]],
    filings: Sequence[dict[str, Any]] = (),
) -> StoreWriter:
    writer, _ = store()
    skip = {i: [k for k in range(N) if np.isnan(c[k])] for i, c in specs.items()}
    write_bars(writer, {i: np.nan_to_num(c, nan=1.0) for i, c in specs.items()}, skip=skip)
    write_rows(writer, HISTORY, DAY, listings)  # the history is written the last day delisted
    if filings:
        write_rows(writer, "events/filing", DAY, list(filings))
    return writer


def run(writer: StoreWriter, session: date = END) -> tuple[RunRecord, StoreReader]:
    ctx = task_ctx(writer, clock=lambda: datetime.combine(session, time(22), UTC))
    return ingest_delistings(ctx, session), ctx.reader


def stored(reader: StoreReader, session: date = END) -> pd.DataFrame:
    frame = reader.table(TABLE, session)
    assert frame is not None
    return frame.set_index("instrument_id")


def test_every_reason_and_its_terminal_convention() -> None:
    ids = {r: f"EQ:{r}" for r in ("BK", "BKN", "AQ", "ST", "VOL", "UNK")}
    specs = {i: closes(LAST) for i in ids.values()}
    listings = [listing(i, DAY, "NASDAQ" if r == "BKN" else "NYSE") for r, i in ids.items()]
    filings = [
        filing(ids["BK"], "8-K", "1.03"), filing(ids["BKN"], "8-K", "1.03"),
        filing(ids["AQ"], "8-K", "2.01"), filing(ids["ST"], "8-K", "3.01"),
        filing(ids["VOL"], "25"), filing(ids["UNK"], "8-K", "7.01"),
    ]  # fmt: skip
    record, reader = run(world(specs, listings, filings))
    got = stored(reader)
    assert record.status is RunStatus.COMPLETE
    expect = {
        "BK": ("BANKRUPTCY", "REPLACEMENT", -0.30), "BKN": ("BANKRUPTCY", "REPLACEMENT", -0.55),
        "AQ": ("ACQUIRED", "ZERO_ACQUIRED", 0.0), "ST": ("STANDARDS", "REPLACEMENT", -0.30),
        "VOL": ("VOLUNTARY", "ZERO_UNKNOWN", 0.0), "UNK": ("UNKNOWN", "ZERO_UNKNOWN", 0.0),
    }  # fmt: skip
    for key, (reason, basis, ret) in expect.items():
        row = got.loc[ids[key]]
        assert (row["reason"], row["terminal_basis"]) == (reason, basis), key
        assert row["delisting_return"] == ret and row["last_close"] == 10.0
        assert pd.isna(row["terminal_close"]) and pd.isna(row["terminal_session"])
        assert row["last_session"] == DAY
        assert pd.Timestamp(row["knowledge_ts"]) == pd.Timestamp(END, tz="UTC").replace(hour=22)
    assert got.loc[ids["BK"], "reason_source"] == "0001-EQ:BK-1 8-K 1.03"
    assert got.loc[ids["BK"], "known_from"] == DAYS[LAST + 1]
    stats = record.stats
    assert stats["delisted"] == stats["rows"] == 6 and stats["no_last_bar"] == 0
    assert stats["by_reason"]["UNKNOWN"] == 1 and stats["by_basis"]["REPLACEMENT"] == 3
    assert stats["unknown_share"] == round(1 / 6, 4)


def test_an_otc_print_within_ten_sessions_is_the_terminal_close() -> None:
    specs = {"EQ:A": closes(LAST, LAST + 10), "EQ:B": closes(LAST, LAST + 11)}
    writer = world(
        specs,
        [listing("EQ:A", DAY), listing("EQ:B", DAY)],
        [filing("EQ:A", "8-K", "1.03"), filing("EQ:B", "8-K", "1.03")],
    )
    record, reader = run(writer)
    got = stored(reader)
    a, b = got.loc["EQ:A"], got.loc["EQ:B"]
    assert (a["terminal_basis"], a["terminal_close"], a["terminal_session"]) == (
        "OTC_CLOSE", 4.0, DAYS[LAST + 10],
    )  # fmt: skip
    assert abs(a["delisting_return"] - (4.0 / 10.0 - 1)) < 1e-12
    # the print 11 sessions out is ignored: the bankruptcy convention applies
    assert (b["terminal_basis"], b["delisting_return"]) == ("REPLACEMENT", -0.30)
    assert pd.isna(b["terminal_close"])
    assert record.stats["by_basis"]["OTC_CLOSE"] == 1


def test_known_from_follows_the_form_25_acceptance_else_the_last_session() -> None:
    form_25 = filing("EQ:A", "25", day=DAYS[LAST - 3], hour=22)  # after the close: rolls a session
    writer = world(
        {"EQ:A": closes(LAST), "EQ:B": closes(LAST)},
        [listing("EQ:A", DAY), listing("EQ:B", DAY)],
        [form_25],
    )
    _, reader = run(writer)
    got = stored(reader)
    assert got.loc["EQ:A", "known_from"] == DAYS[LAST - 1]
    assert got.loc["EQ:B", "known_from"] == DAYS[LAST + 1]


def test_an_id_with_two_listings_is_delisted_only_once_both_have_ended() -> None:
    first = listing("EQ:FB", DAYS[10], exchange="NASDAQ")
    record, reader = run(world({"EQ:FB": closes(LAST)}, [first, listing("EQ:FB", None, "NASDAQ")]))
    assert record.stats["delisted"] == 0 and record.stats["rows"] == 0
    assert (
        record.status is RunStatus.FAILED and reader.dates(TABLE) == []
    )  # never an empty snapshot
    both = [first, listing("EQ:FB", DAY, exchange="NYSE", cik="0002")]
    _, reader = run(world({"EQ:FB": closes(LAST)}, both))
    row = stored(reader).loc["EQ:FB"]
    assert row["last_session"] == DAY and row["exchange"] == "NYSE" and row["cik"] == "0002"


def test_a_name_with_no_bar_is_counted_and_a_missing_cik_and_filings_are_visible() -> None:
    writer = world(
        {"EQ:A": closes(LAST)},
        [listing("EQ:A", DAY, cik=None), listing("EQ:GONE", DAYS[5], cik="0009")],
    )
    record, reader = run(writer)
    assert list(stored(reader).index) == ["EQ:A"]
    stats = record.stats
    assert (stats["delisted"], stats["no_last_bar"], stats["no_cik"]) == (2, 1, 1)
    assert stats["no_filings"] == 2 and stats["by_reason"]["UNKNOWN"] == 1


def test_no_listing_history_fails_the_run_and_writes_nothing() -> None:
    writer, _ = store()
    record, reader = run(writer)
    assert record.status is RunStatus.FAILED
    assert reader.dates(TABLE) == []


def test_a_later_snapshot_changes_a_reason_and_an_older_one_is_still_read() -> None:
    writer = world({"EQ:A": closes(LAST)}, [listing("EQ:A", DAY)])
    early = DAYS[LAST + 5]
    run(writer, early)  # no filings stored yet: UNKNOWN
    write_rows(writer, "events/filing", DAY, [filing("EQ:A", "8-K", "1.03")])
    _, reader = run(writer, END)
    old, old_day = read_delistings(reader, early)
    new, new_day = read_delistings(reader)
    assert (old_day, new_day) == (early, END)
    assert list(old["reason"]) == ["UNKNOWN"] and list(new["reason"]) == ["BANKRUPTCY"]
    assert read_delistings(reader, DAYS[LAST + 7])[1] == early  # the latest on or before


def test_a_feature_reads_a_delisting_only_from_its_known_from() -> None:
    _, reader = run(world({"EQ:A": closes(LAST)}, [listing("EQ:A", DAY)]))
    frame, _ = read_delistings(reader)
    assert known_by(frame, DAY).empty
    assert list(known_by(frame, DAYS[LAST + 1])["instrument_id"]) == ["EQ:A"]
    assert len(frame) == 1  # the outcome label reads the frame as stored, whatever its known_from


def test_a_session_before_the_listing_history_was_written_is_refused() -> None:
    writer = world({"EQ:A": closes(LAST)}, [listing("EQ:A", DAY)])
    record, reader = run(writer, DAYS[LAST - 1])  # the history was written on DAYS[LAST]
    assert record.status is RunStatus.FAILED and reader.dates(TABLE) == []
    assert "written after the session" in record.stats["failed_because"][0]


def test_a_replay_before_the_write_does_not_see_the_snapshot() -> None:
    writer = world({"EQ:A": closes(LAST)}, [listing("EQ:A", DAY)])
    _, reader = run(writer)  # written at END 22:00 UTC
    before = datetime.combine(END, time(21), UTC)
    after = datetime.combine(END, time(23), UTC)
    assert read_delistings(reader, as_of=after)[1] == END
    with pytest.raises(MissingDataError):
        read_delistings(reader, as_of=before)


def test_a_relisted_id_gets_a_row_for_each_gap() -> None:
    bars = np.full(N, np.nan)
    bars[:6] = 10.0  # the first stretch, delisted on DAYS[5]
    bars[20 : LAST + 1] = 10.0  # relisted on DAYS[20], delisted again on DAY
    first = listing("EQ:R", DAYS[5])
    second = dict(listing("EQ:R", DAY), start_date=DAYS[20])
    record, reader = run(world({"EQ:R": bars}, [first, second]))
    got = stored(reader)
    assert sorted(got["last_session"]) == [DAYS[5], DAY]
    assert record.stats["rows"] == 2 and record.stats["delisted"] == 2
