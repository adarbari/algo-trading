"""The ``filings`` task over the recorded SEC payload and synthetic submissions (ADR 0050): one
``events/filing`` row per 8-K and instrument with ``known_from`` by the New York session of the
acceptance time (around 16:00 ET and midnight UTC), the Item 2.02 releases as ``sec_8k``
``events/earnings`` rows (the three ``time`` labels, ``reported``, a key that never collides
with the calendar's), the default ``--since`` per CIK, and the item statuses."""

import json
from datetime import date, datetime, timedelta
from itertools import count
from typing import Any

import pandas as pd

from algotrade.data import StoreReader
from algotrade.data.events import ALL_TIME, read_events
from algotrade.services.events.scope import ScopedName
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.runs import RunStatus
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.events.filings import (
    DEFAULT_SINCE,
    EARNINGS,
    TABLE,
    TASK,
    earnings_rows,
    ingest_filings,
    since_by_cik,
)
from algotrade_ingestion.tasks.framework.run import IngestRun, TaskContext
from algotrade_sources.framework.http import HttpError, RetryPolicy
from algotrade_sources.vendors.sec.submissions import SecFilings
from tests.conftest import REPO_ROOT
from tests.helpers.ingest_fakes import FIXED, http_for, task_ctx
from tests.helpers.stored_frames import stamped

SEC = REPO_ROOT / "tests" / "fixtures" / "sources" / "sec"
MU_MAIN = (SEC / "submissions_CIK0000723125.json").read_bytes()
MU_PAGE = (SEC / "submissions_CIK0000723125-submissions-001.json").read_bytes()
S1, S2 = date(2026, 10, 5), date(2026, 10, 12)
MU, ALPHA = "0000723125", "0001652044"
IDS = {s: f"EQ:{s}" for s in ("MU", "GOOGL", "GOOG", "NOCIK", "GONE", "BAD")}
CIKS = {"MU": "723125", "GOOGL": "1652044", "GOOG": "1652044", "GONE": "999", "BAD": "888"}

# (accession, acceptance UTC, filing date, items, form, report date)
ALPHA_FILINGS = [
    (
        "A1",
        "2026-10-05T13:29:59.000Z",
        "2026-10-05",
        "2.02,9.01",
        "8-K",
        "2026-09-30",
    ),  # 09:29:59 ET
    ("A2", "2026-10-05T13:30:00.000Z", "2026-10-05", "2.02", "8-K", ""),  # 09:30:00 ET
    ("A3", "2026-10-05T19:59:59.000Z", "2026-10-05", "2.02", "8-K", ""),  # 15:59:59 ET
    ("A4", "2026-10-05T20:00:00.000Z", "2026-10-05", "2.02", "8-K", ""),  # 16:00:00 ET
    ("A5", "2026-10-06T00:30:00.000Z", "2026-10-06", "2.02", "8-K", ""),  # 20:30 ET on the 5th
    ("A6", "2026-10-05T14:00:00.000Z", "2026-10-05", "2.02", "8-K/A", ""),  # an amendment
    ("A7", "2026-10-05T15:00:00.000Z", "2026-10-05", "7.01", "8-K", ""),  # no results
    ("A8", "2026-01-15T14:29:00.000Z", "2026-01-15", "2.02", "8-K", ""),  # 09:29 ET (winter)
    ("A9", "2026-01-15T14:30:00.000Z", "2026-01-15", "2.02", "8-K", ""),  # 09:30 ET (winter)
]


def submissions(cik: str, filings: list[tuple[str, str, str, str, str, str]]) -> bytes:
    """A submissions document of 8-K-like rows (newest first, as SEC lists them)."""
    rows = sorted(filings, key=lambda f: f[1], reverse=True)
    recent = {
        "accessionNumber": [f[0] for f in rows],
        "filingDate": [f[2] for f in rows],
        "reportDate": [f[5] for f in rows],
        "acceptanceDateTime": [f[1] for f in rows],
        "form": [f[4] for f in rows],
        "items": [f[3] for f in rows],
        "primaryDocument": [f"{f[0]}.htm" for f in rows],
    }
    return json.dumps({"cik": cik, "filings": {"recent": recent, "files": []}}).encode()


class Feed:
    """SEC answers by CIK; 404 for an unknown one, 500 for ``broken``. A request log."""

    def __init__(self, broken: tuple[str, ...] = ()) -> None:
        self.bodies = {MU: MU_MAIN, ALPHA: submissions(ALPHA, ALPHA_FILINGS)}
        self.broken, self.urls = broken, []
        self.page = MU_PAGE

    def __call__(self, url: str) -> bytes:
        self.urls.append(url)
        if any(f"CIK{cik:0>10}.json" in url for cik in self.broken):
            raise HttpError(500)
        if url.endswith("CIK0000723125-submissions-001.json"):
            return self.page
        for cik, body in self.bodies.items():
            if url.endswith(f"CIK{cik}.json"):
                return body
        raise HttpError(404)


def store() -> StoreWriter:
    writer = StoreWriter(MemoryBackend())
    day = date(2026, 10, 2)
    reference = [
        {"instrument_id": i, "symbol": s, "asset_class": "EQ", "security_type": "COMMON_STOCK",
         "multiplier": 1.0, "status": "ACTIVE"}
        for s, i in IDS.items()
    ]  # fmt: skip
    writer.write_table("instruments/reference", day, "ref", stamped(reference, day, "ref"))
    company = [
        {
            "instrument_id": IDS[s],
            "symbol": s,
            "cik": cik,
            "name": s,
            "sic": "1",
            "sector": "x",
            "fetched_on": day,
        }
        for s, cik in CIKS.items()
        if s in IDS
    ]
    writer.write_table("instruments/company", day, "co", stamped(company, day, "co"))
    return writer


TICKS = count()


def clock() -> datetime:
    return FIXED + timedelta(minutes=next(TICKS))


def context(writer: StoreWriter) -> TaskContext:
    return task_ctx(writer, clock=clock)


def run(
    writer: StoreWriter, feed: Feed, symbols: tuple[str, ...], session: date = S1, **kw: Any
) -> Any:
    source = SecFilings(http_for(feed, RetryPolicy(tries=1)))
    return ingest_filings(context(writer), source, session, symbols, **kw)


def read(writer: StoreWriter, table: str, ids: list[str]) -> pd.DataFrame:
    frame = read_events(StoreReader(writer._backend), table, *ALL_TIME, instruments=ids).frame
    return frame.assign(ts=pd.to_datetime(frame["ts"], utc=True)).reset_index(drop=True)


# ----------------------------------------------------------------------------- the recorded payload


def test_micron_filings_and_results_from_the_recorded_payload() -> None:
    writer, feed = store(), Feed()
    record = run(writer, feed, ("MU",))
    assert record.status is RunStatus.COMPLETE and record.items["0000723125"].startswith(
        "OK: 5 8-K"
    )
    assert len(feed.urls) == 1  # since 2018 is inside the recent block: no older page
    filings = read(writer, TABLE, ["EQ:MU"])
    assert list(filings["accession"]) == [  # by acceptance: the 8-K/A of 2020, then 2026
        "0000723125-20-000012",
        "0001104659-26-071845",
        "0000723125-26-000013",
        "0001104659-26-101067",
        "0000723125-26-000018",
    ]
    assert set(filings["source"]) == {"sec_edgar"} and set(filings["cik"]) == {MU}
    last = filings.iloc[-1]
    assert last["ts"] == pd.Timestamp("2026-09-30 20:02:22", tz="UTC")
    assert (last["form"], last["items"], last["filing_date"]) == (
        "8-K",
        "2.02,9.01",
        date(2026, 9, 30),
    )
    assert last["report_date"] == date(2026, 9, 30) and last["known_from"] == date(2026, 9, 30)
    assert last["primary_document"] == "mu-20260930.htm"
    results = read(writer, EARNINGS, ["EQ:MU"])
    assert list(results["earnings_date"]) == [date(2026, 6, 24), date(2026, 9, 30)]
    assert set(results["source"]) == {"sec_8k"} and results["reported"].all()
    assert list(results["time"]) == ["after_hours", "after_hours"]  # 16:02 New York
    assert results["fiscal_quarter"].isna().all()
    assert results["ts"].iloc[1] == pd.Timestamp("2026-09-30 20:02:22", tz="UTC")  # the instant


def test_a_since_before_the_recent_block_reads_the_older_page() -> None:
    writer, feed = store(), Feed()
    record = run(writer, feed, ("MU",), since=date(2017, 1, 1))
    assert len(feed.urls) == 2 and feed.urls[1].endswith("CIK0000723125-submissions-001.json")
    assert record.stats["filings"] == 8 and record.stats["results"] == 3
    filings = read(writer, TABLE, ["EQ:MU"])
    assert filings["known_from"].min() == date(2017, 6, 28)  # 18:46 UTC: the same New York day
    assert record.stats["since"] == "2017-01-01"


# ----------------------------------------------------------------------------- known_from and time


def test_known_from_is_the_new_york_session_of_the_acceptance() -> None:
    writer = store()
    run(writer, Feed(), ("GOOGL",))
    filings = read(writer, TABLE, ["EQ:GOOGL"]).set_index("accession")
    assert filings.loc["A4", "known_from"] == date(2026, 10, 5)  # 16:00 ET: still that day
    assert filings.loc["A5", "known_from"] == date(2026, 10, 5)  # 00:30 UTC on the 6th is 20:30 ET
    assert filings.loc["A5", "filing_date"] == date(2026, 10, 6)  # SEC dates it the next day
    assert filings.loc["A1", "known_from"] == date(2026, 10, 5)
    assert filings.loc["A8", "known_from"] == date(2026, 1, 15)
    assert filings.loc["A1", "report_date"] == date(2026, 9, 30)
    assert pd.isna(filings.loc["A2", "report_date"])
    assert len(filings) == 9  # every 8-K and the 8-K/A


def test_the_time_label_follows_the_new_york_clock_in_summer_and_winter() -> None:
    writer = store()
    run(writer, Feed(), ("GOOGL",))
    results = read(writer, EARNINGS, ["EQ:GOOGL"])
    labels = {
        (d.isoformat(), label)
        for d, label in zip(results["earnings_date"], results["time"], strict=True)
    }
    assert labels == {
        ("2026-10-05", "pre_market"),  # A1 09:29:59
        ("2026-10-05", "intraday"),  # A2 09:30:00 and A3 15:59:59
        (
            "2026-10-05",
            "after_hours",
        ),  # A4 16:00:00 and A5 20:30 (its date is the 5th, not UTC's 6th)
        ("2026-01-15", "pre_market"),  # A8: 14:29 UTC is 09:29 EST
        ("2026-01-15", "intraday"),  # A9: 14:30 UTC is 09:30 EST
    }
    by_ts = read(writer, EARNINGS, ["EQ:GOOGL"]).set_index("ts")
    late = by_ts.loc[pd.Timestamp("2026-10-06 00:30", tz="UTC")]
    assert late["earnings_date"] == date(2026, 10, 5) and late["known_from"] == date(2026, 10, 5)


def test_only_original_8ks_with_item_202_become_earnings_rows() -> None:
    writer = store()
    record = run(writer, Feed(), ("GOOGL",))
    results = read(writer, EARNINGS, ["EQ:GOOGL"])
    assert record.stats["results"] == len(results) == 7  # A1-A5, A8, A9: not the 8-K/A, not 7.01
    assert results["reported"].all() and set(results["source"]) == {"sec_8k"}
    assert set(results["symbol"]) == {"GOOGL"}
    assert (results["known_from"] == results["earnings_date"]).all()
    assert results["fiscal_quarter"].isna().all()  # the calendar's label is a quarter end, not ours


def test_an_8k_row_never_collides_with_the_calendars_row_of_the_day() -> None:
    writer = store()
    midnight = pd.Timestamp("2026-10-05", tz="UTC")
    calendar = [
        {"instrument_id": "EQ:GOOGL", "ts": midnight, "symbol": "GOOGL", "time": "unknown",
         "reported": False, "known_from": date(2026, 10, 2)}
    ]  # fmt: skip
    day = date(2026, 10, 2)
    writer.write_table(EARNINGS, day, "cal", stamped(calendar, day, "cal"))
    run(writer, Feed(), ("GOOGL",))
    stored = read(writer, EARNINGS, ["EQ:GOOGL"])
    assert len(stored) == 8 and stored["ts"].is_unique  # the calendar's row and the seven 8-K rows
    assert (stored["source"] == "sec_8k").sum() == 7 and (stored["ts"] == midnight).sum() == 1


# ----------------------------------------------------------------------------- instruments and CIKs


def test_share_classes_of_one_cik_each_get_the_rows_from_one_request() -> None:
    writer, feed = store(), Feed()
    record = run(writer, feed, ("GOOGL", "GOOG"))
    assert len(feed.urls) == 1 and record.stats["ciks"] == 1 and record.stats["names"] == 2
    filings = read(writer, TABLE, ["EQ:GOOGL", "EQ:GOOG"])
    assert dict(filings["instrument_id"].value_counts()) == {"EQ:GOOGL": 9, "EQ:GOOG": 9}
    assert record.stats["results"] == 14


def test_item_statuses_for_missing_unknown_and_failing_names() -> None:
    writer, feed = store(), Feed(broken=("888",))
    record = run(writer, feed, ("MU", "NOCIK", "GONE", "BAD", "NOPE"))
    assert record.status is RunStatus.PARTIAL
    assert record.items["sym:NOPE"].startswith("UNKNOWN")  # not in the reference: never fetched
    assert record.items["cik:NOCIK"].startswith("NO_CIK")
    assert record.items["0000000999"].startswith("NO_DATA")  # SEC 404
    assert record.items["0000723125"].startswith("OK")
    assert record.items["0000000888"].startswith("FETCH_ERROR")
    s = record.stats
    assert (s["ciks"], s["ciks_failed"], s["without_cik"], s["unknown_symbols"]) == (
        3,
        1,
        ["NOCIK"],
        ["NOPE"],
    )


def test_a_failing_cik_is_counted_and_the_others_are_stored() -> None:
    writer, feed = store(), Feed(broken=("1652044",))
    record = run(writer, feed, ("MU", "GOOGL"))
    assert record.status is RunStatus.PARTIAL
    assert record.items["0001652044"].startswith("FETCH_ERROR")
    assert (record.stats["ciks"], record.stats["ciks_failed"]) == (2, 1)
    assert len(read(writer, TABLE, ["EQ:MU"])) == 5 and read(writer, TABLE, ["EQ:GOOGL"]).empty


# ----------------------------------------------------------------------------- since


def test_the_default_since_is_the_latest_stored_acceptance_else_2018() -> None:
    writer = store()
    with IngestRun(context(writer), TASK, S1) as first:
        ciks = {MU: [ScopedName("EQ:MU", "MU", ())], ALPHA: [ScopedName("EQ:GOOGL", "GOOGL", ())]}
        assert since_by_cik(first, ciks, None) == {MU: DEFAULT_SINCE, ALPHA: DEFAULT_SINCE}
        assert since_by_cik(first, ciks, date(2020, 5, 1)) == {
            MU: date(2020, 5, 1),
            ALPHA: date(2020, 5, 1),
        }
    run(writer, Feed(), ("MU", "GOOGL"))
    with IngestRun(context(writer), TASK, S2) as second:
        found = since_by_cik(second, {**ciks, "0000000001": [ScopedName("EQ:X", "X", ())]}, None)
    assert found == {
        MU: date(2026, 9, 30),  # 20:02 UTC: that day in New York
        ALPHA: date(2026, 10, 5),  # the 00:30 UTC acceptance of the 6th is the 5th in New York
        "0000000001": DEFAULT_SINCE,
    }
    with IngestRun(context(writer), TASK, S2) as third:  # a share class newly in scope
        two = {MU: [ScopedName("EQ:MU", "MU", ()), ScopedName("EQ:MU2", "MU2", ())]}
        assert since_by_cik(third, two, None) == {MU: DEFAULT_SINCE}


def test_a_later_run_reads_from_the_latest_stored_filing_and_changes_nothing_stored() -> None:
    writer, feed = store(), Feed()
    first = run(writer, feed, ("GOOGL",))
    before = read(writer, TABLE, ["EQ:GOOGL"])
    second = run(writer, feed, ("GOOGL",), session=S2)
    # From 2026-10-05: A1-A7 (filed the 5th) and A5 (the 6th); not the January ones.
    assert first.stats["filings"] == 9 and second.stats["filings"] == 7
    after = read(writer, TABLE, ["EQ:GOOGL"])
    assert len(after) == 9 and list(after["accession"]) == list(before["accession"])
    assert list(after["known_from"]) == list(before["known_from"])  # a rewrite moves nothing later
    assert len(read(writer, EARNINGS, ["EQ:GOOGL"])) == 7


def test_an_acceptance_at_midnight_utc_is_written_one_second_later() -> None:
    """20:00:00 EDT is midnight UTC, the calendar row's key: the 8-K row steps off it."""
    filings = pd.DataFrame(
        {
            "form": ["8-K", "8-K"],
            "items": ["2.02,9.01", "2.02"],
            "acceptance_ts": [
                pd.Timestamp("2026-10-06 00:00:00", tz="UTC"),
                pd.Timestamp("2026-10-06 00:00:30", tz="UTC"),
            ],
            "report_date": [None, None],
        }
    )
    rows = earnings_rows(filings, ScopedName("EQ:X", "X", ()))
    assert list(rows["ts"]) == [
        pd.Timestamp("2026-10-06 00:00:01", tz="UTC"),
        pd.Timestamp("2026-10-06 00:00:30", tz="UTC"),
    ]
    assert list(rows["earnings_date"]) == [date(2026, 10, 5), date(2026, 10, 5)]
