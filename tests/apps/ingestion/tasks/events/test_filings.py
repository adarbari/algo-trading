"""The ``filings`` task over the recorded SEC payloads and synthetic submissions (ADR 0050): the
universe's operating companies (no funds), one ``events/filing`` row per 8-K and instrument with
``known_from`` by the New York session of the acceptance time (around 16:00 ET and midnight
UTC), the Item 2.02 releases as ``sec_8k`` ``events/earnings`` rows (the three ``time`` labels,
``reported``, a key that never collides with the calendar's), the per-CIK ``--since`` (resumable,
``--limit``), the nightly from the daily form index (only the CIKs that filed, an unpublished
day read again, a failing day stopping the walk) and the item statuses."""

import json
import re
from datetime import date, datetime, timedelta
from itertools import count
from typing import Any

import pandas as pd
import pytest

from algotrade.config.site.settings import SourcesSettings
from algotrade.core.model.errors import MissingDataError
from algotrade.data import StoreReader
from algotrade.data.events import ALL_TIME, read_events
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.runs import RunStatus
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.events.filings import (
    COLUMNS,
    DEFAULT_SINCE,
    EARNINGS,
    EARNINGS_COLUMNS,
    TABLE,
    TASK,
    Listed,
    earnings_rows,
    ingest_filings,
    since_by_cik,
    stored_filings,
)
from algotrade_ingestion.tasks.framework.run import IngestRun, TaskContext
from algotrade_sources.framework.http import HttpError, RetryPolicy
from algotrade_sources.vendors.sec.daily_index import SecDailyIndex, missing_index
from algotrade_sources.vendors.sec.submissions import SecFilings
from tests.conftest import REPO_ROOT
from tests.helpers.ingest_fakes import FIXED, http_for, task_ctx
from tests.helpers.stored_frames import stamped

SEC = REPO_ROOT / "tests" / "fixtures" / "sources" / "sec"
MU_MAIN = (SEC / "submissions_CIK0000723125.json").read_bytes()
MU_PAGE = (SEC / "submissions_CIK0000723125-submissions-001.json").read_bytes()
S1, S2 = date(2026, 10, 5), date(2026, 10, 12)
MU, ALPHA = "0000723125", "0001652044"
IDS = {s: f"EQ:{s}" for s in ("MU", "GOOGL", "GOOG", "NOCIK", "GONE", "BAD", "SPYX")}
CIKS = {"MU": "723125", "GOOGL": "1652044", "GOOG": "1652044", "GONE": "999", "BAD": "888",
        "SPYX": "777"}  # fmt: skip
TYPES = {"SPYX": "ETF"}  # every other name is a common stock
INDEX = (SEC / "daily_index_form_20260930_trimmed.idx").read_bytes()
DENIED = b"<Error><Code>AccessDenied</Code><Message>Access Denied</Message></Error>"

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

    def __init__(self, broken: tuple[str, ...] = (), alpha: list[Any] | None = None) -> None:
        self.bodies = {MU: MU_MAIN, ALPHA: submissions(ALPHA, alpha or ALPHA_FILINGS)}
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
    universe = [
        {"instrument_id": i, "symbol": s, "security_type": TYPES.get(s, "COMMON_STOCK"),
         "optionable": True, "status": "ACTIVE", "universe_version": "v1"}
        for s, i in IDS.items()
    ]  # fmt: skip
    writer.write_table("universe", day, "uni", stamped(universe, day, "uni"))
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


def context(writer: StoreWriter, **settings: Any) -> TaskContext:
    return task_ctx(writer, clock=clock, settings=SourcesSettings(**settings))


def run(
    writer: StoreWriter, feed: Feed, symbols: tuple[str, ...], session: date = S1, **kw: Any
) -> Any:
    source = SecFilings(http_for(feed, RetryPolicy(tries=1)))
    return ingest_filings(context(writer), source, session, symbols, **kw)


class IndexFeed:
    """Daily form indexes by day; S3's 403 AccessDenied for a day not in ``days`` (a weekend, a
    holiday or not yet published), a 500 for ``broken``. A request log of the days asked."""

    def __init__(self, days: dict[date, bytes], broken: tuple[date, ...] = ()) -> None:
        self.days, self.broken, self.asked = days, broken, []

    def __call__(self, url: str) -> bytes:
        found = re.search(r"form\.(\d{4})(\d{2})(\d{2})\.idx", url)
        assert found, url
        day = date(*(int(g) for g in found.groups()))
        self.asked.append(day)
        if day in self.broken:
            raise HttpError(500)
        if day in self.days:
            return self.days[day]
        raise HttpError(403, body=DENIED)


def index_text(day: date, filers: list[tuple[str, str, str]]) -> bytes:
    """A form index of ``(form, cik, accession)`` lines in the recorded layout."""
    header = b"".join(INDEX.splitlines(keepends=True)[:11])
    lines = [
        f"{form:<17}{'SOME CO':<62}{cik:<12}{day:%Y%m%d}    edgar/data/{cik}/{accession}.txt\n"
        for form, cik, accession in filers
    ]
    return header + "".join(lines).encode()


def nightly(
    writer: StoreWriter, feed: Feed, index: IndexFeed, session: date, backfill: int = 0, **kw: Any
) -> Any:
    """The task as the nightly runs it: both sources, no ``--since``; ``backfill`` is
    ``[quality] filings_backfill_per_night`` (0: the days alone)."""
    source = SecFilings(http_for(feed, RetryPolicy(tries=1)))
    daily = SecDailyIndex(http_for(index, RetryPolicy(tries=1, not_found=missing_index)))
    ctx = context(writer, filings_backfill_per_night=backfill)
    return ingest_filings(ctx, source, session, (), index=daily, **kw)


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
    assert record.items["sym:NOPE"].startswith("UNKNOWN")  # not in the universe: never fetched
    assert "cik:NOCIK" not in record.items  # a name without a CIK is counted, not an item
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
        ciks = {MU: [Listed("EQ:MU", "MU")], ALPHA: [Listed("EQ:GOOGL", "GOOGL")]}
        nothing = stored_filings(first)
        assert since_by_cik(ciks, nothing, None) == {MU: DEFAULT_SINCE, ALPHA: DEFAULT_SINCE}
        assert since_by_cik(ciks, nothing, date(2020, 5, 1)) == {
            MU: date(2020, 5, 1),
            ALPHA: date(2020, 5, 1),
        }
    run(writer, Feed(), ("MU", "GOOGL"))
    with IngestRun(context(writer), TASK, S2) as second:
        both = {**ciks, "0000000001": [Listed("EQ:X", "X")]}
        found = since_by_cik(both, stored_filings(second), None)
    assert found == {
        MU: date(2026, 9, 30),  # 20:02 UTC: that day in New York
        ALPHA: date(2026, 10, 5),  # the 00:30 UTC acceptance of the 6th is the 5th in New York
        "0000000001": DEFAULT_SINCE,
    }
    with IngestRun(context(writer), TASK, S2) as third:  # a share class newly in scope
        two = {MU: [Listed("EQ:MU", "MU"), Listed("EQ:MU2", "MU2")]}
        assert since_by_cik(two, stored_filings(third), None) == {MU: DEFAULT_SINCE}


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
    rows = earnings_rows(filings, Listed("EQ:X", "X"))
    assert list(rows["ts"]) == [
        pd.Timestamp("2026-10-06 00:00:01", tz="UTC"),
        pd.Timestamp("2026-10-06 00:00:30", tz="UTC"),
    ]
    assert list(rows["earnings_date"]) == [date(2026, 10, 5), date(2026, 10, 5)]


# ----------------------------------------------------------------------------- the universe


def test_the_whole_universe_is_covered_without_funds() -> None:
    writer, feed = store(), Feed()
    record = run(writer, feed, ())
    s = record.stats
    assert (s["names"], s["funds_excluded"], s["with_cik"]) == (6, 1, 5)  # SPYX is an ETF
    assert s["without_cik"] == ["NOCIK"] and s["mode"] == "per_cik"
    assert s["ciks"] == 4  # MU, the one Alphabet CIK for two classes, GONE, BAD
    assert not any("777" in url for url in feed.urls)  # the fund's CIK is never asked
    stored = set(read(writer, TABLE, list(IDS.values()))["instrument_id"])
    assert stored == {"EQ:MU", "EQ:GOOGL", "EQ:GOOG"}


def test_a_run_without_a_universe_snapshot_fails() -> None:
    writer = StoreWriter(MemoryBackend())
    with pytest.raises(MissingDataError):
        run(writer, Feed(), ())
    assert StoreReader(writer._backend).runs(TASK)[-1].status is RunStatus.FAILED


# ----------------------------------------------------------------------------- the backfill


def test_a_backfill_skips_ciks_it_already_reaches_and_asks_never_stored_ones_first() -> None:
    writer = store()
    run(writer, Feed(), ("GOOGL",), since=date(2026, 1, 15))  # one Alphabet class, back to 01-15
    second = Feed()
    record = run(writer, second, (), since=date(2026, 1, 15))
    assert record.stats["skipped_covered"] == 1  # the Alphabet CIK was read from 01-15 already
    assert [u.rsplit("/", 1)[1] for u in second.urls] == [
        "CIK0000723125.json", "CIK0000000999.json", "CIK0000000888.json"
    ]  # fmt: skip


def test_a_cik_with_no_filings_since_the_start_is_not_asked_again() -> None:
    """Micron's first filing in the fixture is after 2026-01-15, and SEC has none for GONE:
    neither is stored back to the start, but both were read OK / NO_DATA from it."""
    writer = store()
    run(writer, Feed(), (), since=date(2026, 1, 15))
    again = Feed()
    record = run(writer, again, (), since=date(2026, 1, 15))
    assert again.urls == [] and record.stats["skipped_covered"] == 4
    earlier = Feed()
    run(writer, earlier, (), since=date(2025, 1, 1))  # an earlier start reads them again
    assert len(earlier.urls) == 4


def test_a_cik_that_failed_is_not_covered() -> None:
    writer = store()
    run(writer, Feed(broken=("888",)), (), since=date(2026, 1, 15))
    again = Feed()
    run(writer, again, (), since=date(2026, 1, 15))
    assert [u.rsplit("/", 1)[1] for u in again.urls] == ["CIK0000000888.json"]


def test_the_limit_caps_the_ciks_of_a_run() -> None:
    writer, feed = store(), Feed()
    record = run(writer, feed, (), since=DEFAULT_SINCE, limit=2)
    assert record.stats["ciks"] == len(feed.urls) == 2  # MU, then the Alphabet CIK
    again = Feed()
    run(writer, again, (), since=DEFAULT_SINCE, limit=2)
    # Alphabet's first stored filing (2026-01) does not reach 2018: it is asked again, but the
    # CIKs never stored come first, so repeated runs make progress through the universe.
    assert [u.rsplit("/", 1)[1] for u in again.urls] == ["CIK0000000999.json", "CIK0000000888.json"]


# ----------------------------------------------------------------------------- the nightly


EXTRA = ("A10", "2026-10-07T14:00:00.000Z", "2026-10-07", "7.01", "8-K", "")  # a new 8-K
LATER = ("A11", "2026-10-08T14:00:00.000Z", "2026-10-08", "2.02", "8-K", "")  # not indexed yet


def seeded() -> StoreWriter:
    """A store whose latest stored filing is Alphabet's of 2026-10-06 (A5, accepted 00:30 UTC)."""
    writer = store()
    run(writer, Feed(), ("GOOGL",))
    return writer


def test_the_nightly_asks_only_the_ciks_the_index_shows_and_stops_at_the_last_day() -> None:
    writer = seeded()
    feed = Feed(alpha=[*ALPHA_FILINGS, EXTRA, LATER])
    index = IndexFeed(
        {
            date(2026, 10, 7): index_text(
                date(2026, 10, 7),
                [("8-K", "1652044", "A10"), ("8-K", "55555", "X1"), ("10-K", "723125", "X2")],
            )
        }
    )
    record = nightly(writer, feed, index, date(2026, 10, 8))
    assert record.status is RunStatus.COMPLETE
    assert index.asked == [date(2026, 10, 6), date(2026, 10, 7), date(2026, 10, 8)]
    assert [u.rsplit("/", 1)[1] for u in feed.urls] == ["CIK0001652044.json"]  # not MU, not 55555
    items = record.items
    assert items["idx:2026-10-06"].startswith("NO_DATA") and "holiday" in items["idx:2026-10-06"]
    assert items["idx:2026-10-07"] == "OK: 2 CIKs with an 8-K"  # the 10-K line is no filer
    assert items["idx:2026-10-08"].startswith("NO_DATA: not published yet")
    assert items["0001652044"].startswith("OK")
    stored = read(writer, TABLE, ["EQ:GOOGL", "EQ:GOOG"]).set_index("accession")
    assert "A10" in stored.index and "A11" not in stored.index  # past the last day read: not yet
    assert set(stored["instrument_id"]) == {"EQ:GOOGL", "EQ:GOOG"}
    s = record.stats
    assert (s["mode"], s["days"], s["days_failed"], s["ciks"], s["ciks_failed"]) == (
        "daily_index", 3, 0, 1, 0,
    )  # fmt: skip
    assert (s["since"], s["until"]) == ("2026-10-07", "2026-10-07")
    assert read(writer, EARNINGS, ["EQ:GOOGL"])["earnings_date"].max() == date(2026, 10, 5)


def test_an_unpublished_day_is_read_again_the_next_night() -> None:
    writer = seeded()
    feed = Feed(alpha=[*ALPHA_FILINGS, EXTRA, LATER])
    first = nightly(writer, feed, IndexFeed({}), date(2026, 10, 7))
    assert first.status is RunStatus.COMPLETE and first.stats["ciks"] == 0
    assert len(read(writer, TABLE, ["EQ:GOOGL"])) == 9  # nothing new stored, no progress
    published = {
        date(2026, 10, 7): index_text(date(2026, 10, 7), [("8-K", "1652044", "A10")]),
        date(2026, 10, 8): index_text(date(2026, 10, 8), [("8-K/A", "1652044", "A11")]),
    }
    again = Feed(alpha=[*ALPHA_FILINGS, EXTRA, LATER])
    second = nightly(writer, again, IndexFeed(published), date(2026, 10, 9))
    assert second.stats["until"] == "2026-10-08" and second.status is RunStatus.COMPLETE
    assert {"A10", "A11"} <= set(read(writer, TABLE, ["EQ:GOOGL"])["accession"])


def test_a_day_whose_index_is_over_seven_business_days_missing_is_a_fetch_error() -> None:
    writer = seeded()
    index = IndexFeed({})
    record = nightly(writer, Feed(), index, date(2026, 10, 20))
    # From 10-06: the 6th to the 8th are more than seven business days before the 20th, the 9th
    # (seven) and later are not.
    stale = [k for k, v in record.items.items() if v.startswith("FETCH_ERROR")]
    assert stale == [f"idx:2026-10-{d:02d}" for d in (6, 7, 8)]
    assert record.items["idx:2026-10-09"].startswith("NO_DATA: not published yet")
    assert record.status is RunStatus.PARTIAL and record.stats["days_failed"] == 3


def test_a_failing_day_stops_the_walk_so_later_days_are_never_stored_over_it() -> None:
    writer = seeded()
    feed = Feed(alpha=[*ALPHA_FILINGS, EXTRA, LATER])
    index = IndexFeed(
        {
            date(2026, 10, 6): index_text(date(2026, 10, 6), [("8-K", "1652044", "A5")]),
            date(2026, 10, 8): index_text(date(2026, 10, 8), [("8-K", "1652044", "A11")]),
        },
        broken=(date(2026, 10, 7),),
    )
    record = nightly(writer, feed, index, date(2026, 10, 8))
    assert record.items["idx:2026-10-07"].startswith("FETCH_ERROR")
    assert date(2026, 10, 8) not in index.asked and record.status is RunStatus.PARTIAL
    accessions = set(read(writer, TABLE, ["EQ:GOOGL"])["accession"])
    assert "A11" not in accessions and "A10" not in accessions  # 10-07 is still to read
    assert record.stats["until"] == "2026-10-06" and record.stats["days_failed"] == 1


def test_an_explicit_since_or_an_empty_store_reads_per_cik_even_with_the_index() -> None:
    index = IndexFeed({})
    fresh, feed = store(), Feed()
    record = nightly(fresh, feed, index, S1, limit=1)  # nothing stored: per CIK, capped
    assert record.stats["mode"] == "per_cik" and record.stats["ciks"] == 1 and index.asked == []
    backfill = nightly(seeded(), Feed(), index, S2, since=date(2026, 1, 1))
    assert backfill.stats["mode"] == "per_cik" and index.asked == []


def test_both_paths_store_the_same_rows_for_a_recorded_day() -> None:
    """Micron's 8-K of 2026-09-30: the per-CIK read and the daily index read agree."""
    per_cik = store()
    run(per_cik, Feed(), ("MU",), since=date(2026, 9, 29))
    old = ("O1", "2026-09-29T13:00:00.000Z", "2026-09-29", "7.01", "8-K", "")  # Alphabet, a day on
    through_index = store()
    run(through_index, Feed(alpha=[old]), ("GOOGL",), since=date(2026, 9, 29))
    index = IndexFeed({date(2026, 9, 30): INDEX})  # the recorded form index of that day
    record = nightly(through_index, Feed(alpha=[old]), index, S1)
    assert record.stats["mode"] == "daily_index" and record.stats["ciks"] == 1  # MU only
    assert record.items["idx:2026-09-30"].startswith("OK")
    for table, columns in ((TABLE, COLUMNS), (EARNINGS, EARNINGS_COLUMNS)):
        want = read(per_cik, table, ["EQ:MU"])
        got = read(through_index, table, ["EQ:MU"])
        assert len(want) >= 1
        pd.testing.assert_frame_equal(want[[*columns, "source"]], got[[*columns, "source"]])


# ----------------------------------------------------------------------------- nightly start


def walked(writer: StoreWriter, feed: Feed, published: dict[date, bytes], session: date) -> Any:
    return nightly(writer, feed, IndexFeed(published), session)


def test_the_walk_restarts_from_the_last_clean_walk_not_the_latest_stored_filing() -> None:
    """A per-CIK run (here --symbols) stores filings up to today; the nightly must still read
    the days between its last walk and then."""
    writer = seeded()  # latest stored filing day: 2026-10-06
    first = walked(writer, Feed(), {date(2026, 10, 6): index_text(date(2026, 10, 6), [])}, S2)
    assert first.stats["walked_to"] == "2026-10-06"
    feed = Feed(alpha=[*ALPHA_FILINGS, EXTRA])
    run(writer, feed, ("GOOGL",), session=date(2026, 10, 13))
    assert "A10" in set(read(writer, TABLE, ["EQ:GOOGL"])["accession"])  # stored out of the walk
    index = IndexFeed({date(2026, 10, 7): index_text(date(2026, 10, 7), [("8-K", "723125", "M1")])})
    record = nightly(writer, Feed(), index, date(2026, 10, 14))
    assert index.asked[0] == date(2026, 10, 6)  # not 2026-10-07, the latest stored filing day
    assert record.items["0000723125"].startswith("OK") and record.stats["walked_to"] == "2026-10-07"


def test_a_walk_with_a_failed_cik_or_day_is_read_again() -> None:
    writer = seeded()
    day7 = index_text(date(2026, 10, 7), [("8-K", "1652044", "A10")])
    bad = nightly(writer, Feed(broken=("1652044",)), IndexFeed({date(2026, 10, 7): day7}), S2)
    assert bad.items["0001652044"].startswith("FETCH_ERROR") and bad.stats["walked_to"] is None
    index = IndexFeed({date(2026, 10, 7): day7})
    nightly(writer, Feed(alpha=[*ALPHA_FILINGS, EXTRA]), index, date(2026, 10, 13))
    assert index.asked[0] == date(2026, 10, 6)  # still from the stored latest: no clean walk
    cut = nightly(writer, Feed(), IndexFeed({date(2026, 10, 7): day7}, broken=(date(2026, 10, 8),)),
                  date(2026, 10, 14))  # fmt: skip
    assert cut.stats["walked_to"] is None


def test_the_nightly_reads_in_full_the_ciks_it_never_read_up_to_the_cap() -> None:
    writer = seeded()  # only Alphabet's GOOGL class is stored
    feed = Feed()
    first = nightly(writer, feed, IndexFeed({}), S2, backfill=2)
    # MU and GONE are the first two unread CIKs, in universe order; Alphabet has a stored
    # GOOGL and a new GOOG class, so it is unread too, but past the cap.
    assert [u.rsplit("/", 1)[1] for u in feed.urls] == ["CIK0000723125.json", "CIK0001652044.json"]
    assert first.stats["backfilled"] == [MU, ALPHA] and first.stats["mode"] == "daily_index"
    again = Feed()
    second = nightly(writer, again, IndexFeed({}), date(2026, 10, 13), backfill=2)
    # Read and stored (MU, Alphabet) or read with nothing to show (never): GONE and BAD are next.
    assert [u.rsplit("/", 1)[1] for u in again.urls] == ["CIK0000000999.json", "CIK0000000888.json"]
    third = Feed()
    nightly(writer, third, IndexFeed({}), date(2026, 10, 14), backfill=2)
    assert third.urls == [] and second.stats["backfilled"] == ["0000000999", "0000000888"]
    assert (
        set(read(writer, TABLE, ["EQ:MU"])["accession"])
        and len(read(writer, TABLE, ["EQ:GOOG"])) == 9
    )
