"""The ``insider`` task over a hand-built quarterly set, submissions and Form 4 XML (EB D6): ids
as of the filing date, ``known_from`` from SEC's acceptance time (a backfill in 2026 of a filing
accepted in September is known from September, a restated line or a 4/A over a stored original
from the fetch's next session), the quarters read once, the nightly walk of the daily index (only
new filings read, a failure keeping the walk where it was, the cap resuming the next night)."""

import json
import re
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pandas as pd
import pytest

from algotrade.config.site.settings import SourcesSettings
from algotrade.data import StoreReader
from algotrade.data.insiders.reading import read_insider_transactions
from algotrade.data.listings.resolvers import listing_resolver
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.runs import RunStatus
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.events import insider
from algotrade_ingestion.tasks.events.insider import TABLE, Sources, ingest_insider, quarter_labels
from algotrade_ingestion.tasks.framework.run import TaskContext
from algotrade_sources.framework.http import HttpError, RetryPolicy
from algotrade_sources.vendors.sec.daily_index import SecDailyIndex, missing_index
from algotrade_sources.vendors.sec.form4_xml import SecForm4Xml
from algotrade_sources.vendors.sec.form345_bulk import SecForm345Bulk, parse_bulk
from algotrade_sources.vendors.sec.submissions import SecFilings
from tests.conftest import REPO_ROOT
from tests.helpers.ingest_fakes import http_for
from tests.helpers.payloads import sec as payloads
from tests.helpers.stored_frames import stamped

SEC = REPO_ROOT / "tests" / "fixtures" / "sources" / "sec"
XML = (SEC / "form4_hand_built_purchase.xml").read_bytes()
INDEX = (SEC / "daily_index_form_20260930_trimmed.idx").read_bytes()
DENIED = b"<Error><Code>AccessDenied</Code><Message>Access Denied</Message></Error>"
CIK = "0000999001"
FIRST, AMENDED, NEW, NEWER = (f"0000999001-26-{n:06d}" for n in (1, 2, 10, 11))
S1, S2, S3 = date(2026, 10, 5), date(2026, 10, 12), date(2026, 10, 14)
# (accession, form, acceptance UTC, filing date): the submissions of the issuer
FILINGS = [
    (FIRST, "4", "2026-09-30T20:30:00.000Z", "2026-09-30"),  # 16:30 ET: after the close, S+1
    (AMENDED, "4/A", "2026-10-02T14:00:00.000Z", "2026-10-02"),
]


def submissions(filings: list[tuple[str, str, str, str]]) -> bytes:
    rows = sorted(filings, key=lambda f: f[2], reverse=True)
    recent = {
        "accessionNumber": [f[0] for f in rows],
        "form": [f[1] for f in rows],
        "acceptanceDateTime": [f[2] for f in rows],
        "filingDate": [f[3] for f in rows],
        "reportDate": ["2026-09-28"] * len(rows),
        "items": [""] * len(rows),
        "primaryDocument": [f"xslF345X05/{f[0]}.xml" for f in rows],
    }
    return json.dumps({"cik": CIK, "filings": {"recent": recent, "files": []}}).encode()


class Feeds:
    """What SEC answers, by URL, with request logs."""

    def __init__(self, filings: list[tuple[str, str, str, str]] | None = None) -> None:
        self.filings = filings or list(FILINGS)
        self.quarters = {"2026q3": payloads.example_quarter()}
        self.days: dict[date, bytes] = {}
        self.broken_xml: set[str] = set()
        self.submission_urls: list[str] = []
        self.bulk_urls: list[str] = []
        self.xml_urls: list[str] = []
        self.index_days: list[date] = []

    def submissions(self, url: str) -> bytes:
        self.submission_urls.append(url)
        if url.endswith(f"CIK{CIK}.json"):
            return submissions(self.filings)
        raise HttpError(404)

    def bulk(self, url: str) -> bytes:
        self.bulk_urls.append(url)
        label = re.search(r"/(\d{4}q\d)_form345", url)
        assert label
        if label[1] in self.quarters:
            return self.quarters[label[1]]
        raise HttpError(404)

    def xml(self, url: str) -> bytes:
        self.xml_urls.append(url)
        if any(accession.replace("-", "") in url for accession in self.broken_xml):
            raise HttpError(500)
        return XML

    def index(self, url: str) -> bytes:
        found = re.search(r"form\.(\d{4})(\d{2})(\d{2})\.idx", url)
        assert found
        day = date(*(int(g) for g in found.groups()))
        self.index_days.append(day)
        if day in self.days:
            return self.days[day]
        raise HttpError(403, body=DENIED)

    def sources(self) -> Sources:
        once = RetryPolicy(tries=1)
        return Sources(
            SecFilings(http_for(self.submissions, once)),
            SecForm345Bulk(http_for(self.bulk, once)),
            SecForm4Xml(http_for(self.xml, once)),
            SecDailyIndex(http_for(self.index, RetryPolicy(tries=1, not_found=missing_index))),
        )


def index_text(day: date, filers: list[tuple[str, str, str]]) -> bytes:
    """A form index of ``(form, cik, accession)`` lines in the recorded layout."""
    header = b"".join(INDEX.splitlines(keepends=True)[:11])
    lines = [
        f"{form:<17}{'SOME CO':<62}{cik:<12}{day:%Y%m%d}    edgar/data/{cik}/{accession}.txt\n"
        for form, cik, accession in filers
    ]
    return header + "".join(lines).encode()


def store() -> StoreWriter:
    writer = StoreWriter(MemoryBackend())
    day = date(2026, 10, 2)
    now = pd.Timestamp(day, tz="UTC")
    listings = pd.DataFrame(
        [("EQ:EXMP", "EXMP", date(2010, 1, 4), None), ("EQ:OTHER", "OTHR", date(2001, 1, 2), None)],
        columns=["instrument_id", "ticker", "start_date", "end_date"],
    ).assign(exchange="NYSE", asset_type="Stock", price_currency="USD", perma_ticker="", ts=now,
             knowledge_ts=now, session_date=day, source="tiingo", run_id="r")  # fmt: skip
    writer.write_table("instruments/listing_history", day, "r", listings)
    universe = [
        {"instrument_id": "EQ:EXMP", "symbol": "EXMP", "security_type": "COMMON_STOCK",
         "optionable": True, "status": "ACTIVE", "universe_version": "v1"}
    ]  # fmt: skip
    writer.write_table("universe", day, "uni", stamped(universe, day, "uni"))
    company = [
        {"instrument_id": "EQ:EXMP", "symbol": "EXMP", "cik": "999001", "name": "Example",
         "sic": "1", "sector": "x", "fetched_on": day}
    ]  # fmt: skip
    writer.write_table("instruments/company", day, "co", stamped(company, day, "co"))
    return writer


class Clock:
    """A clock that moves a minute a call, from ``start`` (the fetch's time)."""

    def __init__(self, start: datetime) -> None:
        self.now = start

    def __call__(self) -> datetime:
        self.now += timedelta(minutes=1)
        return self.now


def run(
    writer: StoreWriter, feeds: Feeds, session: date = S1, at: datetime | None = None, **kw: Any
):
    clock = Clock(at or datetime(2026, 10, 5, 22, tzinfo=UTC))
    ctx = TaskContext(StoreReader(writer._backend), writer, {}, SourcesSettings(), clock=clock)
    return ingest_insider(ctx, feeds.sources(), session, **kw)


def stored(writer: StoreWriter) -> pd.DataFrame:
    """Every stored row, whatever a session may see."""
    found = StoreReader(writer._backend).table_range(TABLE, date(1900, 1, 1), date(9999, 12, 31))
    return found if found is not None else pd.DataFrame(columns=["accession"])


def seen(writer: StoreWriter, through: date | None = None) -> pd.DataFrame:
    return read_insider_transactions(StoreReader(writer._backend), through=through)


# ----------------------------------------------------------------------------- the backfill


def test_a_backfill_stores_the_lines_with_ids_and_the_real_acceptance_sessions() -> None:
    writer, feeds = store(), Feeds()
    record = run(writer, feeds, since=date(2026, 7, 1))
    assert record.status is RunStatus.COMPLETE
    assert record.items["q:2026q3"] == "OK: 4 lines" and record.items["q:2026q4"].startswith(
        "NO_DATA"
    )
    stats = record.stats
    assert (stats["mode"], stats["rows"], stats["quarters"]) == ("bulk", 4, ["2026q3", "2026q4"])
    assert (stats["unresolved"], stats["no_acceptance"], stats["restated"]) == (1, 0, 0)  # ZZZZ
    rows = stored(writer).set_index(["accession", "line"])
    assert set(rows["instrument_id"]) == {"EQ:EXMP"} and len(rows) == 4
    # the run's fetch was on 2026-10-05, the acceptances in September and early October
    assert rows.loc[(FIRST, 1), "known_from"] == date(2026, 10, 1)  # accepted after the 30th close
    assert rows.loc[(AMENDED, 1), "known_from"] == date(2026, 10, 2)
    assert rows.loc[(FIRST, 1), "ts"] == pd.Timestamp("2026-09-30T20:30:00Z")
    assert rows.loc[(FIRST, 1), "filing_date"] == date(2026, 9, 30)  # SEC's (submissions) date
    assert (
        rows.loc[(FIRST, 1), "transaction_code"] == "P" and rows.loc[(FIRST, 1), "shares"] == 1000
    )
    assert len(feeds.submission_urls) == 1 and feeds.submission_urls[0].endswith(f"CIK{CIK}.json")
    assert feeds.bulk_urls[0].endswith("2026q3_form345.zip")  # ZZZZ's CIK was never asked


def test_a_session_sees_the_original_until_its_amendment_is_known() -> None:
    writer = store()
    run(writer, Feeds(), since=date(2026, 7, 1))
    assert seen(writer, date(2026, 9, 29)).empty
    assert seen(writer, date(2026, 9, 30)).empty  # accepted 16:30 on the 30th: not in that close
    on_the_1st = seen(writer, date(2026, 10, 1))
    assert on_the_1st["accession"].tolist() == [FIRST] * 3
    on_the_2nd = seen(writer, date(2026, 10, 2))  # the 4/A is known: it replaces its original
    assert on_the_2nd["accession"].tolist() == [AMENDED]


def test_a_line_whose_filing_the_submissions_do_not_list_is_counted_and_not_stored() -> None:
    writer, feeds = store(), Feeds([FILINGS[0]])
    record = run(writer, feeds, since=date(2026, 7, 1))
    assert record.stats["no_acceptance"] == 1
    assert stored(writer)["accession"].unique().tolist() == [FIRST]


def test_a_quarter_read_once_is_skipped_and_force_rereads_it_without_changing_a_stamp() -> None:
    writer, feeds = store(), Feeds()
    run(writer, feeds, since=date(2026, 7, 1))
    second = run(
        writer, feeds, session=S2, since=date(2026, 7, 1), at=datetime(2026, 10, 12, 22, tzinfo=UTC)
    )
    assert len(feeds.bulk_urls) == 3  # the first run: 2026q3 and 2026q4; the second: q4 again
    assert "q:2026q3" not in second.items and second.items["q:2026q4"].startswith("NO_DATA")
    forced = run(writer, feeds, session=S3, since=date(2026, 7, 1), force=True,
                 at=datetime(2026, 10, 14, 22, tzinfo=UTC))  # fmt: skip
    assert forced.items["q:2026q3"] == "OK: 4 lines" and forced.stats["restated"] == 0
    rows = stored(writer)  # the rerun is a second copy of the same keys in its own partition
    keys = ["accession", "line", "owner_cik", "known_from"]
    assert len(rows) == 8 and len(rows.drop_duplicates(keys)) == 4
    assert set(rows[rows["accession"] == FIRST]["known_from"]) == {date(2026, 10, 1)}


def test_limit_caps_the_quarters_a_run_reads() -> None:
    feeds = Feeds()
    record = run(store(), feeds, since=date(2026, 1, 1), limit=1)
    assert record.stats["quarters"] == ["2026q1"] and list(record.items) == ["q:2026q1"]
    assert quarter_labels(date(2025, 11, 3), date(2026, 2, 1)) == ["2025q4", "2026q1"]


# ----------------------------------------------------------------------------- restatements


def test_a_line_that_changed_is_known_from_the_fetchs_next_session() -> None:
    writer, feeds = store(), Feeds()
    run(writer, feeds, since=date(2026, 7, 1))
    feeds.quarters["2026q3"] = payloads.example_quarter(price="12.0")
    second = run(writer, feeds, session=S2, since=date(2026, 7, 1), force=True,
                 at=datetime(2026, 10, 12, 22, tzinfo=UTC))  # fmt: skip
    assert second.stats["restated"] == 2  # the purchase of the original and of the amendment
    floor = date(2026, 10, 13)  # fetched on Monday the 12th (a market holiday does not matter)
    old = seen(writer, date(2026, 10, 12))
    new = seen(writer, floor)
    assert old[old["transaction_code"] == "P"]["price"].tolist() == [12.5]
    assert new[new["transaction_code"] == "P"]["price"].tolist() == [12.0]
    assert seen(writer, date(2026, 10, 1))["price"].tolist() == [12.5, 13.0, 0.0]  # as first known


def test_a_4a_is_known_from_its_own_acceptance_even_when_its_original_is_stored() -> None:
    writer, feeds = store(), Feeds()
    feeds.quarters["2026q3"] = payloads.example_quarter(amend=False)
    run(writer, feeds, since=date(2026, 7, 1))
    assert stored(writer)["accession"].unique().tolist() == [FIRST]
    feeds.quarters["2026q3"] = payloads.example_quarter()
    second = run(writer, feeds, session=S2, since=date(2026, 7, 1), force=True,
                 at=datetime(2026, 10, 12, 22, tzinfo=UTC))  # fmt: skip
    assert second.stats["restated"] == 0  # its own filing, its own keys: no floor
    rows = stored(writer).set_index("accession")
    assert rows.loc[AMENDED, "known_from"] == date(2026, 10, 2)  # its acceptance, not the fetch
    assert set(seen(writer, date(2026, 10, 1))["accession"]) == {FIRST}
    assert set(seen(writer, date(2026, 10, 2))["accession"]) == {AMENDED}


def test_no_submissions_for_an_issuer_fails_the_quarter_and_it_is_read_again() -> None:
    writer, feeds = store(), Feeds()
    working = feeds.submissions

    def gone(url: str) -> bytes:
        raise HttpError(404)

    feeds.submissions = gone  # type: ignore[method-assign]
    bad = run(writer, feeds, since=date(2026, 7, 1))
    assert bad.items["q:2026q3"].startswith("FETCH_ERROR") and stored(writer).empty
    feeds.submissions = working  # type: ignore[method-assign]
    good = run(writer, feeds, session=S2, since=date(2026, 7, 1),
               at=datetime(2026, 10, 12, 22, tzinfo=UTC))  # fmt: skip
    assert good.items["q:2026q3"] == "OK: 4 lines"  # a failed quarter is not a read one


def test_an_accession_the_other_source_stored_is_skipped_not_keyed_twice() -> None:
    writer = store()
    run(writer, Feeds(), since=date(2026, 7, 1))  # the bulk stores FIRST and AMENDED
    parsed = parse_bulk(payloads.example_quarter())
    parsed = parsed[parsed["issuer_symbol"] == "EXMP"]
    accepted = pd.DataFrame(
        {
            "accession": [FIRST, AMENDED],
            "acceptance_ts": pd.to_datetime(
                ["2026-09-30T20:30:00Z", "2026-10-02T14:00:00Z"], utc=True
            ),
            "filing_date": pd.to_datetime(["2026-09-30", "2026-10-02"]),
        }
    )
    ctx_reader = StoreReader(writer._backend)
    resolver_on = listing_resolver(ctx_reader)
    tally = dict.fromkeys(
        ("no_acceptance", "unresolved", "bad_rows", "restated", "other_source"), 0
    )
    held = stored(writer)
    args = (parsed, accepted, resolver_on, held, date(2026, 10, 13), tally)
    assert len(insider.build_rows(*args, "form4_xml")) == 0  # the bulk rows are the bulk's
    assert tally["other_source"] == 4
    assert len(insider.build_rows(*args, "form345_bulk")) == 4  # its own: a rerun


def test_a_row_without_an_acceptance_instant_is_dropped_and_counted() -> None:
    writer = store()
    run(writer, Feeds(), since=date(2026, 7, 1))
    parsed = parse_bulk(payloads.example_quarter())
    parsed = parsed[parsed["accession"] == FIRST]
    accepted = pd.DataFrame(
        {
            "accession": [FIRST],
            "acceptance_ts": [pd.NaT],
            "filing_date": pd.to_datetime(["2026-09-30"]),
        }
    )
    tally = dict.fromkeys(
        ("no_acceptance", "unresolved", "bad_rows", "restated", "other_source"), 0
    )
    rows = insider.build_rows(
        parsed, accepted, listing_resolver(StoreReader(writer._backend)),
        stored(writer).iloc[0:0], date(2026, 10, 13), tally, "form345_bulk",
    )  # fmt: skip
    assert rows.empty and tally["bad_rows"] == 3


# ----------------------------------------------------------------------------- the nightly walk


def nightly_feeds() -> tuple[StoreWriter, Feeds]:
    """A store with the backfilled quarter and a feed with a new filing on 2026-10-05."""
    writer, feeds = store(), Feeds()
    run(writer, feeds, since=date(2026, 7, 1))
    feeds.filings = [*FILINGS, (NEW, "4", "2026-10-05T14:00:00.000Z", "2026-10-05")]
    feeds.days = {
        date(2026, 10, 2): index_text(date(2026, 10, 2), [("4/A", CIK[3:], AMENDED)]),
        date(2026, 10, 5): index_text(
            date(2026, 10, 5),
            [("4", CIK[3:], NEW), ("4", "888001", NEW), ("4", "999777", "0000999777-26-000001")],
        ),
    }
    return writer, feeds


def test_the_nightly_reads_only_the_filings_it_has_not_stored() -> None:
    writer, feeds = nightly_feeds()
    record = run(writer, feeds, session=S2, at=datetime(2026, 10, 12, 22, tzinfo=UTC))
    assert record.status is RunStatus.COMPLETE and record.stats["mode"] == "daily_index"
    assert len(feeds.xml_urls) == 1 and feeds.xml_urls[0].endswith(
        "/data/999001/000099900126000010/0000999001-26-000010.xml"  # the raw XML, no xsl directory
    )
    assert record.items[f"acc:{NEW}"] == "OK: 3 lines" and record.stats["rows"] == 3
    assert record.stats["walked_to"] == "2026-10-05"
    assert feeds.index_days[0] == date(2026, 10, 2)  # from the latest stored filing day
    rows = stored(writer).set_index("accession")
    assert set(rows.loc[NEW, "instrument_id"]) == {"EQ:EXMP"}
    assert set(rows.loc[NEW, "known_from"]) == {date(2026, 10, 5)}  # 10:00 ET that day
    assert set(rows.loc[NEW, "filing_date"]) == {date(2026, 10, 5)}  # from the submissions
    assert (feeds.submission_urls.count(feeds.submission_urls[-1])) >= 1


def test_the_next_night_starts_at_the_last_clean_day_and_reads_nothing_twice() -> None:
    writer, feeds = nightly_feeds()
    run(writer, feeds, session=S2, at=datetime(2026, 10, 12, 22, tzinfo=UTC))
    feeds.xml_urls.clear()
    feeds.index_days.clear()
    again = run(writer, feeds, session=S3, at=datetime(2026, 10, 14, 22, tzinfo=UTC))
    assert feeds.index_days[0] == date(2026, 10, 5) and feeds.xml_urls == []
    assert again.stats["rows"] == 0 and again.stats["walked_to"] == "2026-10-05"


def test_a_failed_filing_keeps_the_walk_where_it_was_and_is_read_again() -> None:
    writer, feeds = nightly_feeds()
    feeds.broken_xml = {NEW}
    bad = run(writer, feeds, session=S2, at=datetime(2026, 10, 12, 22, tzinfo=UTC))
    assert bad.items[f"acc:{NEW}"].startswith("FETCH_ERROR") and bad.stats["walked_to"] is None
    feeds.broken_xml = set()
    good = run(writer, feeds, session=S3, at=datetime(2026, 10, 14, 22, tzinfo=UTC))
    assert good.items[f"acc:{NEW}"] == "OK: 3 lines" and good.stats["walked_to"] == "2026-10-05"
    assert NEW in set(seen(writer)["accession"])


def test_a_night_stops_after_the_day_that_fills_the_cap_and_the_next_goes_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(insider, "XML_PER_RUN", 1)
    writer, feeds = nightly_feeds()
    feeds.filings.append((NEWER, "4", "2026-10-06T14:00:00.000Z", "2026-10-06"))
    feeds.days[date(2026, 10, 6)] = index_text(date(2026, 10, 6), [("4", CIK[3:], NEWER)])
    first = run(writer, feeds, session=S2, at=datetime(2026, 10, 12, 22, tzinfo=UTC))
    assert first.stats["walked_to"] == "2026-10-05" and NEWER not in set(seen(writer)["accession"])
    second = run(writer, feeds, session=S3, at=datetime(2026, 10, 14, 22, tzinfo=UTC))
    assert second.stats["walked_to"] == "2026-10-06" and NEWER in set(seen(writer)["accession"])


def test_the_first_nightly_with_nothing_stored_reads_only_a_week_back() -> None:
    writer, feeds = store(), Feeds()
    record = run(writer, feeds, session=S1, at=datetime(2026, 10, 5, 22, tzinfo=UTC))
    assert record.stats["mode"] == "daily_index" and feeds.bulk_urls == []
    assert feeds.index_days[0] == date(2026, 9, 28)
