"""The ``filing-text`` task (edge builds D10, D10b) over synthetic submissions, daily form indexes
and the two trimmed filing fixtures: filer-first coverage (a delisted filer in no universe is read,
its rows keyed by CIK, no id stored: readers map the CIK), ``known_from`` the acceptance SESSION
(after the close, a weekend), a rerun that asks for nothing, a parser bump that changes one item
(revised from the FETCH's session, the identical items keeping their stamp), the reader's as-of
view across the bump (and the ids it maps at the session), a failing document (the other filings
stored, the item failed), a headerless document (a null-item row), the 10-K/A as its own filing,
SEC holidays in the index walk, and the nightly."""

import json
import re
from datetime import UTC, date, datetime, timedelta
from itertools import count
from typing import Any

import pandas as pd
import pytest

from algotrade.config.site.settings import SourcesSettings
from algotrade.data import StoreReader
from algotrade.data.filing_text.reading import (
    COLUMNS,
    TABLE,
    filing_text,
    stored_filing_text,
)
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.runs import RunRecord, RunStatus
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.events import filing_text as task
from algotrade_ingestion.tasks.events import filing_text_filers as filers
from algotrade_ingestion.tasks.events.filing_text_filers import IndexGapError, sec_holidays
from algotrade_ingestion.tasks.framework.run import TaskContext
from algotrade_sources.framework.http import GaveUpError, HttpError, RetryPolicy
from algotrade_sources.vendors.sec.daily_index import SecDailyIndex, missing_index
from algotrade_sources.vendors.sec.submissions import SecFilings
from algotrade_sources.vendors.sec_text import filing_items
from algotrade_sources.vendors.sec_text.filing_text import SecFilingText
from tests.conftest import REPO_ROOT
from tests.helpers.ingest_fakes import FIXED, http_for, task_ctx
from tests.helpers.stored_frames import stamped

SEC = REPO_ROOT / "tests" / "fixtures" / "sources" / "sec"
TEN_K = (SEC / "10k_items_trimmed.htm").read_bytes()
TEN_Q = (SEC / "10q_items_trimmed.htm").read_bytes()
SESSION = date(2026, 10, 2)  # the run's session; its clock is FIXED: Friday 18:00 New York
LEARNED = date(2026, 10, 5)  # the session after FIXED's exchange date: when a revision is known
ALPHA, BETA, GONE = "0001652044", "0000723125", "0000999999"  # GONE: delisted, in no universe
IDS = {s: f"EQ:{s}" for s in ("GOOGL", "GOOG", "MU", "SPYX", "NOCIK")}
CIKS = {"GOOGL": "1652044", "GOOG": "1652044", "MU": "723125", "SPYX": "777"}
SHARES = ["EQ:GOOGL", "EQ:GOOG"]

# (accession, acceptance UTC, filing date, form, document)
K1 = (
    "0001652044-26-000010",
    "2026-02-10T21:30:00.000Z",
    "2026-02-10",
    "10-K",
    "k1.htm",
)  # 16:30 ET
Q1 = (
    "0001652044-26-000020",
    "2026-05-02T14:00:00.000Z",
    "2026-05-02",
    "10-Q",
    "q1.htm",
)  # a Saturday
Q2 = (
    "0001652044-26-000030",
    "2026-08-05T12:00:00.000Z",
    "2026-08-05",
    "10-Q",
    "q2.htm",
)  # 08:00 ET
KA = (
    "0001652044-26-000040",
    "2026-03-01T15:00:00.000Z",
    "2026-03-01",
    "10-K/A",
    "ka.htm",
)  # Sunday
NOISE = ("0001652044-26-000050", "2026-06-01T15:00:00.000Z", "2026-06-01", "8-K", "n.htm")
MU_Q = ("0000723125-26-000007", "2026-08-06T13:00:00.000Z", "2026-08-06", "10-Q", "mu.htm")
GONE_K = ("0000999999-26-000001", "2026-03-10T14:00:00.000Z", "2026-03-10", "10-K", "gone.htm")
FULL_ITEMS = ("1", "1A", "3", "7", "7A", "9A", "I-2", "I-3", "II-1", "II-1A")
DENIED = b"<Error><Code>AccessDenied</Code><Message>Access Denied</Message></Error>"


def submissions(cik: str, filings: list[tuple[str, str, str, str, str]]) -> bytes:
    rows = sorted(filings, key=lambda f: f[1], reverse=True)
    recent = {
        "accessionNumber": [f[0] for f in rows],
        "filingDate": [f[2] for f in rows],
        "reportDate": ["" for _ in rows],
        "acceptanceDateTime": [f[1] for f in rows],
        "form": [f[3] for f in rows],
        "items": ["" for _ in rows],
        "primaryDocument": [f[4] for f in rows],
    }
    return json.dumps({"cik": cik, "filings": {"recent": recent, "files": []}}).encode()


class Feed:
    """SEC answers: the listing by CIK, a document by file name (``documents``), 500 for the
    names in ``broken``, 404 otherwise. A request log."""

    def __init__(
        self, alpha: list[Any], documents: dict[str, bytes], broken: tuple[str, ...] = ()
    ) -> None:
        self.lists = {
            ALPHA: submissions(ALPHA, alpha),
            BETA: submissions(BETA, [MU_Q]),
            GONE: submissions(GONE, [GONE_K]),
        }
        self.documents, self.broken = dict(documents), broken
        self.urls: list[str] = []
        # the form index by day: the filers of (form, cik, accession); every other weekday is a
        # published, empty index; ``unpublished`` days answer S3's 403, ``down`` days a 500
        self.filers: dict[date, list[tuple[str, str, str]]] = {
            date(2026, 2, 10): [("10-K", ALPHA, K1[0])],
            date(2026, 3, 10): [("10-K", GONE, GONE_K[0])],
            date(2026, 8, 6): [("10-Q", BETA, MU_Q[0])],
        }
        self.unpublished: set[date] = set()
        self.down: set[date] = set()

    def index(self, url: str) -> bytes:
        found = re.search(r"form\.(\d{4})(\d{2})(\d{2})\.idx", url)
        assert found, url
        day = date(*(int(g) for g in found.groups()))
        if day in self.down:
            raise HttpError(500)
        if day in self.unpublished:
            raise HttpError(403, body=DENIED)
        lines = [
            f"{form:<17}{'SOME CO':<62}{cik:<12}{day:%Y%m%d}    edgar/data/{cik}/{acc}.txt\n"
            for form, cik, acc in self.filers.get(day, [])
        ]
        return "".join(lines).encode()

    def __call__(self, url: str) -> bytes:
        self.urls.append(url)
        if "/full-index/" in url:  # the fallback for a day with no daily file: not served here
            raise HttpError(403, body=DENIED)
        if "/daily-index/" in url:
            return self.index(url)
        name = url.rsplit("/", 1)[-1]
        if name in self.broken:
            raise HttpError(500)
        for cik, body in self.lists.items():
            if url.endswith(f"CIK{cik}.json"):
                return body
        if name in self.documents:
            return self.documents[name]
        raise HttpError(404)

    @property
    def document_urls(self) -> list[str]:
        return [u for u in self.urls if "/Archives/" in u]

    @property
    def listing_urls(self) -> list[str]:
        return [u for u in self.urls if "/submissions/" in u]

    @property
    def index_urls(self) -> list[str]:
        return [u for u in self.urls if "/daily-index/" in u]


DOCUMENTS = {
    "k1.htm": TEN_K,
    "ka.htm": TEN_K,
    "q1.htm": TEN_Q,
    "q2.htm": TEN_Q,
    "mu.htm": TEN_Q,
    "gone.htm": TEN_K,
}


def feed(alpha: list[Any] | None = None, **kw: Any) -> Feed:
    return Feed(alpha or [K1, Q1, Q2, KA, NOISE], DOCUMENTS, **kw)


def store() -> StoreWriter:
    writer = StoreWriter(MemoryBackend())
    day = date(2026, 10, 1)
    types = {"SPYX": "ETF"}
    universe = [
        {"instrument_id": i, "symbol": s, "security_type": types.get(s, "COMMON_STOCK"),
         "optionable": True, "status": "ACTIVE", "universe_version": "v1"}
        for s, i in IDS.items()
    ]  # fmt: skip
    writer.write_table("universe", day, "uni", stamped(universe, day, "uni"))
    reference = [
        {"instrument_id": i, "symbol": s, "asset_class": "EQ", "security_type": "COMMON_STOCK",
         "multiplier": 1.0, "status": "ACTIVE"}
        for s, i in IDS.items()
    ]  # fmt: skip
    writer.write_table("instruments/reference", day, "ref", stamped(reference, day, "ref"))
    company = [
        {"instrument_id": IDS[s], "symbol": s, "cik": cik, "name": s, "sic": "1", "sector": "x",
         "fetched_on": day}
        for s, cik in CIKS.items()
    ]  # fmt: skip
    writer.write_table("instruments/company", day, "co", stamped(company, day, "co"))
    return writer


TICKS = count()


def clock() -> datetime:
    return FIXED + timedelta(minutes=next(TICKS))


def run(writer: StoreWriter, sec: Feed, session: date = SESSION, **kw: Any) -> Any:
    listing = SecFilings(http_for(sec, RetryPolicy(tries=1)))
    text = SecFilingText(http_for(sec, RetryPolicy(tries=1)))
    index = SecDailyIndex(http_for(sec, RetryPolicy(tries=1, not_found=missing_index)))
    ctx: TaskContext = task_ctx(writer, clock=clock, settings=SourcesSettings())
    kw.setdefault("since", date(2026, 1, 1))
    kw.setdefault("items", FULL_ITEMS)  # the six + four sections the fixtures hold
    return task.ingest_filing_text(ctx, listing, text, index, session, **kw)


def rows(writer: StoreWriter, ciks: list[str] | None = None) -> pd.DataFrame:
    """Every stored version (the null-id first versions and the id versions)."""
    frame = stored_filing_text(
        StoreReader(writer._backend), None, (*COLUMNS, "text_sha"), ciks=ciks
    )
    return frame.sort_values(
        ["cik", "accession", "item", "known_from"], na_position="first"
    ).reset_index(drop=True)


def first_versions(writer: StoreWriter, cik: str = ALPHA) -> pd.DataFrame:
    """Every stored row of one filer (no id is ever stored)."""
    return rows(writer, [cik])


def once(reader: StoreReader, on: date, **kw: Any) -> pd.DataFrame:
    """The scan on ``on``, a row per (filer, filing, item): the share classes of a filer folded."""
    found = filing_text(reader, None, on, **kw)
    return found.drop_duplicates(["cik", "accession", "item"], ignore_index=True)


def scan(writer: StoreWriter, on: date = date(2027, 1, 1), **kw: Any) -> pd.DataFrame:
    """What the reader shows on ``on``: the latest version of each item of every filer."""
    return once(StoreReader(writer._backend), on, **kw)


def bumped(monkeypatch: pytest.MonkeyPatch, version: int = 2) -> None:
    """A new parser version, as a release would make it (one constant, imported twice)."""
    monkeypatch.setattr(filing_items, "PARSER_VERSION", version)
    monkeypatch.setattr(task, "PARSER_VERSION", version)


# ------------------------------------------------------------------------------ rows and stamps


def test_a_backfill_stores_the_items_of_each_periodic_filing_once_per_filer_with_no_id() -> None:
    writer, sec = store(), feed()
    record = run(writer, sec, requested_symbols=("GOOGL", "GOOG"))
    assert record.status is RunStatus.COMPLETE, record.stats
    assert record.items["0001652044"].startswith("OK: 2026-01-01..2026-10-02 (4 filings)")
    frame = first_versions(writer)
    assert set(frame["accession"]) == {K1[0], Q1[0], Q2[0], KA[0]}  # the 8-K is not a report
    assert frame["cik"].eq(ALPHA).all() and frame["instrument_id"].isna().all()
    k1 = sorted(frame.loc[frame["accession"] == K1[0], "item"])
    assert k1 == ["1", "1A", "3", "7", "7A", "9A"]
    q1 = sorted(frame.loc[frame["accession"] == Q1[0], "item"])
    assert q1 == ["I-2", "I-3", "II-1", "II-1A"]
    assert len(sec.document_urls) == 4  # one request a filing, whatever the share classes
    assert len(frame) == 20 and record.stats["rows"] == 20
    assert frame["text_sha"].notna().equals(frame["text"].notna())  # a hash of every text


def test_known_from_is_the_acceptance_session_not_the_filing_date_or_the_fetch_day() -> None:
    writer = store()
    run(writer, feed(), requested_symbols=("GOOGL",))
    frame = first_versions(writer).drop_duplicates("accession").set_index("accession")
    known = {a: pd.Timestamp(k).date() for a, k in frame["known_from"].items()}
    assert known[K1[0]] == date(2026, 2, 11)  # 16:30 ET: after the close, the next session
    assert known[Q1[0]] == date(2026, 5, 4)  # a Saturday: Monday
    assert known[Q2[0]] == date(2026, 8, 5)  # 08:00 ET: that session
    assert known[KA[0]] == date(2026, 3, 2)  # a Sunday: Monday; the 10-K/A is its own filing
    stored = StoreReader(writer._backend).table_range(TABLE, date(2000, 1, 1), SESSION)
    assert stored is not None
    first = stored[stored["instrument_id"].isna()]
    session = pd.to_datetime(first["session_date"]).dt.date
    assert (session == pd.to_datetime(first["known_from"]).dt.date).all()  # partitioned by it
    assert not (pd.to_datetime(first["known_from"]).dt.date == SESSION).any()  # never the fetch day


def test_the_reader_maps_the_cik_to_instruments_at_the_session_the_row_stores_none() -> None:
    writer = store()
    run(writer, feed([K1]), requested_symbols=("GOOGL",))
    reader = StoreReader(writer._backend)
    seen = filing_text(reader, ["EQ:GOOGL"], LEARNED)
    assert len(seen) == 6 and seen["instrument_id"].eq("EQ:GOOGL").all()
    both = filing_text(reader, ["EQ:GOOGL", "EQ:GOOG"], LEARNED)  # one filer, two share classes
    assert sorted(set(both["instrument_id"])) == ["EQ:GOOG", "EQ:GOOGL"] and len(both) == 12
    scan_ = filing_text(reader, None, LEARNED)
    assert sorted(set(scan_["instrument_id"])) == ["EQ:GOOG", "EQ:GOOGL"]
    assert scan_.attrs["pre_snapshot"] is False
    early = filing_text(reader, ["EQ:GOOGL"], date(2026, 3, 1))  # before the first snapshot
    assert len(early) == 6 and early.attrs["pre_snapshot"] is True  # the earliest stands in


def test_a_filer_in_no_universe_is_read_filer_first_with_a_null_id() -> None:
    writer, sec = store(), feed()
    record = run(writer, sec)  # no symbols: every filer of the window's form indexes
    assert record.status is RunStatus.COMPLETE, record.stats
    assert record.stats["filers"] == 3 and record.stats["filers_cached"] is False
    assert record.stats["index_days"] == len(sec.index_urls) > 190
    assert set(record.items) == {ALPHA, BETA, GONE}  # GONE is in no universe snapshot
    gone = rows(writer, [GONE])
    assert gone["accession"].eq(GONE_K[0]).all() and len(gone) == 6
    assert rows(writer)["instrument_id"].isna().all()  # no id is stored for any filer
    mapped = filing_text(StoreReader(writer._backend), None, date(2027, 1, 1))
    assert set(mapped.loc[mapped["cik"] == BETA, "instrument_id"]) == {"EQ:MU"}
    assert set(mapped.loc[mapped["cik"] == ALPHA, "instrument_id"]) == {"EQ:GOOGL", "EQ:GOOG"}
    seen = scan(writer, forms=["10-K"], ciks=[GONE])
    assert seen["cik"].eq(GONE).all() and len(seen) == 6


def test_the_filers_of_a_past_window_are_read_from_the_run_that_found_them() -> None:
    writer = store()
    window = {"since": date(2026, 1, 1), "until": date(2026, 9, 1), "limit": 1}
    first = run(writer, feed(), **window)
    assert first.stats["filers"] == 3 and first.stats["pending"] == 2
    sec = feed()
    second = run(writer, sec, **window)
    assert sec.index_urls == [] and second.stats["filers_cached"] is True
    assert second.stats["filers"] == 3 and second.stats["skipped_covered"] == 1
    assert second.stats["pending"] == 1 and len(second.items) == 1


def test_a_window_reaching_the_session_is_walked_again() -> None:
    writer = store()
    run(writer, feed(), limit=1)
    sec = feed()
    run(writer, sec, limit=1)  # until = the session: the day's index may not be final
    assert len(sec.index_urls) > 190


def test_sec_holidays_are_the_federal_closures_with_weekend_observance() -> None:
    year = sec_holidays(2026)
    assert {date(2026, 1, 1), date(2026, 1, 19), date(2026, 2, 16), date(2026, 5, 25)} <= year
    assert {date(2026, 6, 19), date(2026, 7, 3), date(2026, 9, 7), date(2026, 10, 12)} <= year
    assert {date(2026, 11, 11), date(2026, 11, 26), date(2026, 12, 25)} <= year  # July 4 is a Sat
    assert date(2026, 7, 4) not in year and date(2026, 4, 3) not in year  # Good Friday is open
    assert date(2021, 12, 31) in sec_holidays(2022)  # New Year 2022 fell on a Saturday
    assert date(2020, 6, 19) not in sec_holidays(2020) and date(2025, 1, 9) in sec_holidays(2025)


SPECIAL = [
    *(date(2010, 2, d) for d in range(8, 12)),
    date(2012, 10, 29), date(2012, 10, 30), date(2012, 12, 24), date(2014, 12, 26),
    date(2015, 12, 24), date(2017, 1, 20), date(2018, 12, 5), date(2018, 12, 24),
    date(2019, 12, 24), date(2020, 12, 24), date(2021, 1, 20), date(2024, 12, 24),
    date(2025, 1, 9), date(2025, 12, 24), date(2025, 12, 26),
]  # fmt: skip


@pytest.fixture(autouse=True)
def no_index_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    """A missing weekday is re-read after a pause (``walk_index``): the tests do not wait."""
    monkeypatch.setattr(filers, "nap", lambda _s: None)


@pytest.mark.parametrize("day", SPECIAL, ids=str)
def test_every_special_closure_is_a_sec_holiday_of_its_year(day: date) -> None:
    assert day in sec_holidays(day.year) and day.isoweekday() < 6


def test_allow_gap_accepts_a_verified_weekday_and_the_error_names_the_date_and_the_flag() -> None:
    gap = feed()
    gap.unpublished = {date(2026, 2, 3)}  # a business day with no index
    with pytest.raises(IndexGapError, match=r"2026-02-03.*--allow-gap 2026-02-03"):
        run(store(), gap)
    record = run(store(), gap, allow_gap=("2026-02-03",))
    assert record.status is RunStatus.COMPLETE
    assert record.stats["index_gaps_allowed"] == ["2026-02-03"]
    assert record.stats["index_holidays"] == 1  # the allowed day is counted with the closures


def test_a_holiday_without_an_index_is_skipped_but_any_other_missing_day_fails_the_run() -> None:
    sec = feed()
    sec.unpublished = {date(2026, 1, 19)}  # Martin Luther King Jr. Day
    record = run(store(), sec)
    assert record.status is RunStatus.COMPLETE and record.stats["index_holidays"] == 1
    normal = feed()
    normal.unpublished = {date(2026, 2, 3)}  # a business day: S3 has not got it
    with pytest.raises(IndexGapError):
        run(store(), normal, until=date(2026, 9, 1))
    down = feed()
    down.down = {date(2026, 2, 3)}
    with pytest.raises(GaveUpError):
        run(store(), down)


def test_the_default_items_are_the_risk_factors_and_the_mda() -> None:
    writer = store()
    run(writer, feed([K1, Q1]), requested_symbols=("GOOGL",), items=())
    frame = rows(writer)
    assert sorted(frame.loc[frame["form"] == "10-K", "item"]) == ["1A", "7"]
    assert sorted(frame.loc[frame["form"] == "10-Q", "item"]) == ["I-2", "II-1A"]


def test_the_stored_row_carries_no_html_and_the_columns_the_reader_names() -> None:
    writer = store()
    run(writer, feed(), requested_symbols=("GOOGL",))
    frame = first_versions(writer)
    assert not frame["text"].dropna().str.contains("<div|<span|ix:header|HIDDEN XBRL").any()
    assert tuple(frame.columns[:3]) == ("instrument_id", "ts", "known_from")
    assert frame["parser_version"].eq(1).all() and frame["cik"].eq("0001652044").all()
    short = frame[(frame["item"] == "3") & (frame["accession"] == K1[0])].iloc[0]
    assert short["quality"] == "SHORT" and short["char_count"] == len(short["text"])


def test_a_rerun_asks_for_nothing_and_writes_nothing() -> None:
    writer, sec = store(), feed()
    first = run(writer, sec, requested_symbols=("GOOGL",))
    before = len(rows(writer))
    again = feed()
    second = run(writer, again, requested_symbols=("GOOGL",))
    assert second.stats["ciks"] == 0 and second.stats["skipped_covered"] == 1  # covered window
    assert again.urls == [] and len(rows(writer)) == before and first.stats["rows"] == before


def test_a_widened_window_reads_the_listing_but_fetches_only_missing_filings() -> None:
    writer = store()
    run(writer, feed(), requested_symbols=("GOOGL",), since=date(2026, 3, 1))
    sec = feed()
    second = run(writer, sec, requested_symbols=("GOOGL",), since=date(2026, 1, 1))
    assert len(sec.listing_urls) == 1  # the window is wider: the CIK is read again
    assert sorted(u.rsplit("/", 1)[-1] for u in sec.document_urls) == ["k1.htm"]
    assert second.stats["filings_already_stored"] == 3 and second.stats["filings_fetched"] == 1


def test_a_failing_document_fails_the_cik_but_keeps_the_others_and_a_rerun_asks_only_for_it() -> (
    None
):
    writer = store()
    sec = feed(broken=("q1.htm",))
    record = run(writer, sec, requested_symbols=("GOOGL",))
    assert record.status is RunStatus.PARTIAL
    status = record.items["0001652044"]
    assert status.startswith("FETCH_ERROR: 1 of 4 filings failed") and Q1[0] in status
    assert set(rows(writer)["accession"]) == {K1[0], Q2[0], KA[0]}  # nothing for the failed one
    again = feed()
    fixed = run(writer, again, requested_symbols=("GOOGL",))
    assert [u.rsplit("/", 1)[-1] for u in again.document_urls] == ["q1.htm"]
    assert fixed.status is RunStatus.COMPLETE and set(rows(writer)["accession"]) >= {Q1[0]}


def test_a_missing_document_is_a_failed_item_never_an_empty_row() -> None:
    writer = store()
    sec = Feed([K1], {})  # every document 404s
    record = run(writer, sec, requested_symbols=("GOOGL",))
    assert record.status is RunStatus.PARTIAL and record.items["0001652044"].startswith(
        "FETCH_ERROR"
    )
    assert rows(writer).empty


def test_a_document_without_item_headers_is_one_null_item_row() -> None:
    page = (
        b"<html><body>"
        + b"<p>Amendment No. 1 adds the exhibits listed below to the report.</p>" * 150
        + b"</body></html>"
    )
    writer = store()
    sec = Feed([KA], {**DOCUMENTS, "ka.htm": page})
    run(writer, sec, requested_symbols=("GOOGL",))
    frame = rows(writer)
    assert len(frame) == 1 and frame["item"].isna().all() and frame["text"].isna().all()
    assert frame["quality"].eq("NO_ITEMS").all() and frame["reason"].notna().all()
    seen = scan(writer, date(2026, 3, 2))
    assert len(seen) == 1 and seen["quality"].iloc[0] == "NO_ITEMS"
    again = run(writer, feed([KA]), requested_symbols=("GOOGL",), since=date(2026, 1, 1))
    assert again.stats["rows"] == 0


def test_items_narrow_the_kept_sections_and_a_new_item_list_is_a_new_read() -> None:
    writer = store()
    run(writer, feed([K1]), requested_symbols=("GOOGL",), items=("1A", "7"))
    assert sorted(scan(writer)["item"]) == ["1A", "7"]
    wider = feed([K1])
    second = run(writer, wider, requested_symbols=("GOOGL",))  # the default list: another tag
    assert len(wider.document_urls) == 1
    frame = scan(writer)
    assert sorted(frame["item"]) == ["1", "1A", "3", "7", "7A", "9A"]
    assert second.stats["revised"] == 4


# ---------------------------------------------------------------------- a parser bump is a revision


def changed(document: bytes) -> bytes:
    return document.replace(b"faces competition", b"faces intense competition and new regulation")


def test_a_parser_bump_that_changes_one_item_is_known_from_the_fetch_not_the_acceptance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    writer = store()
    run(writer, feed([K1]), requested_symbols=("GOOGL",))
    bumped(monkeypatch)
    sec = Feed([K1], {**DOCUMENTS, "k1.htm": changed(TEN_K)})
    record = run(writer, sec, requested_symbols=("GOOGL",), until=date(2026, 9, 1))  # a past --to
    assert record.stats["learned_on"] == LEARNED.isoformat() and record.stats["revised"] == 1
    frame = rows(writer)
    risk = frame[frame["item"] == "1A"].sort_values(["parser_version", "known_from"])
    assert risk["parser_version"].tolist() == [1, 2]  # both versions stay
    known = [pd.Timestamp(k).date() for k in risk["known_from"]]
    assert known == [date(2026, 2, 11), LEARNED]  # v2: never the acceptance
    business = frame[frame["item"] == "1"].sort_values("parser_version")
    assert business["text"].nunique() == 1  # identical text: the stored stamp stands
    assert business["known_from"].nunique() == 1


def test_the_reader_sees_the_old_text_until_the_revision_is_known(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    writer = store()
    run(writer, feed([K1]), requested_symbols=("GOOGL",))
    bumped(monkeypatch)
    run(writer, Feed([K1], {**DOCUMENTS, "k1.htm": changed(TEN_K)}), requested_symbols=("GOOGL",))
    reader = StoreReader(writer._backend)

    def risk(on: date) -> str:
        found = once(reader, on, items=["1A"])
        assert len(found) == 1
        return str(found["text"].iloc[0])

    assert once(reader, date(2026, 2, 10)).empty  # not accepted yet
    assert "faces competition" in risk(date(2026, 2, 11))
    assert "faces competition" in risk(date(2026, 10, 2))  # the day before the revision is known
    assert "faces intense competition" in risk(LEARNED)
    assert once(reader, LEARNED, items=["1A"], forms=["10-Q"]).empty


def test_a_later_parser_that_finds_a_header_an_earlier_one_missed_is_a_revision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headless = (
        b"<html><body>"
        + b"<p>The annual report text follows in full.</p>" * 200
        + b"</body></html>"
    )
    writer = store()
    run(writer, Feed([K1], {**DOCUMENTS, "k1.htm": headless}), requested_symbols=("GOOGL",))
    assert rows(writer)["quality"].tolist() == ["NO_ITEMS"]
    bumped(monkeypatch)
    run(writer, feed([K1]), requested_symbols=("GOOGL",))
    reader = StoreReader(writer._backend)
    before = once(reader, date(2026, 10, 2))
    assert before["quality"].tolist() == ["NO_ITEMS"]  # known then: nothing found
    after = once(reader, LEARNED)
    assert sorted(after["item"]) == ["1", "1A", "3", "7", "7A", "9A"]  # the null row is dropped
    first = rows(writer)
    assert (pd.to_datetime(first[first["item"].notna()]["known_from"]).dt.date == LEARNED).all()


def test_force_rewrites_an_identical_filing_with_its_stored_stamp() -> None:
    writer = store()
    run(writer, feed([K1]), requested_symbols=("GOOGL",))
    once = rows(writer)
    again = feed([K1])
    record = run(writer, again, requested_symbols=("GOOGL",), force=True)
    assert len(again.document_urls) == 1 and record.stats["revised"] == 0
    twice = rows(writer)
    assert twice["known_from"].tolist() == once["known_from"].tolist() and len(twice) == len(once)


# --------------------------------------------------------------------------------- pure helpers


def test_same_is_na_safe() -> None:
    assert task._same(None, float("nan")) and task._same("a", "a")
    assert not task._same(None, "") and not task._same("a", None) and not task._same("a", "b")


def test_read_done_needs_the_same_tag_and_a_covering_window() -> None:
    def record(tag: str, status: str) -> RunRecord:
        out = RunRecord("r", "filing_text", date(2026, 10, 2), FIXED, RunStatus.COMPLETE, FIXED)
        out.items, out.stats = {"C": status}, {"tag": tag}
        return out

    window = "OK: 2026-01-01..2026-12-31 (3 filings)"
    tag = task.run_tag(())
    assert task.read_done([record(tag, window)], tag, date(2026, 3, 1), date(2026, 9, 1)) == {"C"}
    assert not task.read_done([record(tag, window)], tag, date(2025, 12, 1), date(2026, 9, 1))
    assert not task.read_done(
        [record("parser=0|items=default", window)], tag, date(2026, 3, 1), date(2026, 9, 1)
    )
    assert not task.read_done(
        [record(tag, "FETCH_ERROR: 1 of 2 filings failed")], tag, date(2026, 3, 1), date(2026, 9, 1)
    )


# ----------------------------------------------------------------------------------- the nightly


def test_the_nightly_with_nothing_stored_is_a_warn_not_a_failure() -> None:
    writer = store()
    sec = feed()
    record = run(writer, sec, since=None)
    assert record.status is RunStatus.PARTIAL and sec.urls == []
    assert "run the backfill" in record.stats["partial"][0]


def test_the_nightly_asks_only_the_ciks_due_a_report_each_from_its_latest_stored_filing() -> None:
    writer = store()
    run(writer, feed([K1]), requested_symbols=("GOOGL", "GOOG", "MU"), since=date(2026, 1, 1))
    new = ("0001652044-26-000099", "2026-08-20T13:00:00.000Z", "2026-08-20", "10-Q", "new.htm")
    sec = Feed([K1, new], {**DOCUMENTS, "new.htm": TEN_Q})
    # six weeks after the filing: a fixed fortnight window would have lost it
    record = run(writer, sec, session=date(2026, 10, 9), since=None)
    assert record.status is RunStatus.COMPLETE and record.stats["mode"] == "nightly"
    assert record.stats["window"] == "2026-02-10..2026-10-09"
    assert record.stats["ciks"] == 2  # both are over 60 days old; MU's 10-Q is stored already
    assert [u.rsplit("/", 1)[-1] for u in sec.document_urls] == ["new.htm"]
    accessions = set(rows(writer)["accession"])
    assert "0001652044-26-000099" in accessions and K1[0] in accessions


def test_a_cik_checked_within_the_recheck_days_is_not_asked_again() -> None:
    writer = store()
    run(writer, feed([K1]), requested_symbols=("GOOGL",), since=date(2026, 1, 1))
    sec = feed([K1])
    record = run(writer, sec, session=SESSION, since=None)  # the same session: just checked
    assert record.stats["ciks"] == 0 and sec.urls == []


def test_due_ciks_reads_from_the_latest_stored_day_and_the_longest_unchecked_goes_first() -> None:
    ts = {"OLD": "2026-06-01", "OLDER": "2026-03-01", "FRESH": "2026-09-20", "ASKED": "2026-01-05",
          "DEAD": "2024-11-01"}  # fmt: skip
    stored = pd.DataFrame({"cik": list(ts), "ts": [pd.Timestamp(d, tz=UTC) for d in ts.values()]})
    checked = {"OLD": date(2026, 9, 1), "ASKED": SESSION}
    due = task.due_ciks(stored, checked, SESSION)  # NEVER has nothing stored: the backfill's
    assert list(due) == [
        "OLDER",
        "OLD",
    ]  # never checked first; ASKED today; FRESH not due; DEAD silent over 400 days
    assert due["OLDER"] == date(2026, 2, 28) and due["OLD"] == date(2026, 5, 31)  # New York
    assert task.due_ciks(pd.DataFrame(), {}, SESSION) == {}


def test_a_never_filing_cik_does_not_hold_the_head_of_the_line_every_night() -> None:
    ts = {f"C{i}": "2026-01-05" for i in range(3)}
    stored = pd.DataFrame({"cik": list(ts), "ts": [pd.Timestamp(d, tz=UTC) for d in ts.values()]})
    first = task.due_ciks(stored, {}, SESSION)
    asked = {c: SESSION - timedelta(days=10 - i) for i, c in enumerate(["C0", "C1"])}
    later = task.due_ciks(stored, asked, SESSION)
    assert next(iter(later)) == "C2" and next(iter(first)) == "C0"


def test_a_fund_and_an_unknown_ticker_are_never_fetched() -> None:
    writer, sec = store(), feed()
    record = run(writer, sec, requested_symbols=("SPYX", "NOPE"))
    assert sec.urls == [] and record.items["sym:NOPE"].startswith("UNKNOWN")
    assert record.stats["ciks"] == 0


def test_a_window_that_ends_before_it_starts_is_refused() -> None:
    with pytest.raises(ValueError):
        run(store(), feed(), since=date(2026, 5, 1), until=date(2026, 4, 1))


# ------------------------------------------------------------------ bad filings, blocks, disk


def test_a_filing_with_no_primary_document_is_a_no_items_row_not_a_failure() -> None:
    writer = store()
    listing = submissions(ALPHA, [KA]).replace(
        b'"primaryDocument": ["ka.htm"]', b'"primaryDocument": [null]'
    )
    sec = Feed([KA], DOCUMENTS)
    sec.lists[ALPHA] = listing
    record = run(writer, sec, requested_symbols=("GOOGL",))
    assert record.status is RunStatus.COMPLETE and sec.document_urls == []
    frame = first_versions(writer)
    assert (
        frame["quality"].tolist() == ["NO_ITEMS"]
        and "no primary document" in frame["reason"].iloc[0]
    )


def test_an_exhibit_only_amendment_is_a_stored_row_and_the_cik_stays_ok() -> None:
    page = b"<html><body>" + b"<p>Exhibit 31 certification.</p>" * 40 + b"</body></html>"
    writer = store()
    record = run(writer, Feed([KA], {**DOCUMENTS, "ka.htm": page}), requested_symbols=("GOOGL",))
    assert record.items["0001652044"].startswith("OK") and record.status is RunStatus.COMPLETE


def test_missing_documents_never_stop_the_run_but_blocked_ones_do() -> None:
    writer = store()
    names = {}
    # four CIKs would be needed: use the two real ones with every document missing (404): both
    # fail, neither is a block, so the run reaches both
    record = run(writer, Feed([K1], {}), requested_symbols=("GOOGL", "MU"))
    assert sum(s.startswith("FETCH_ERROR") for s in record.items.values()) == 2
    assert "stopped" not in " ".join(record.stats.get("partial", []))
    assert names == {}


def test_a_blocked_listing_counts_toward_the_stop_and_the_run_ends_partial(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    writer = store()
    monkeypatch.setattr(task, "STOP_AFTER_FAILED", 1)

    class Down(Feed):
        def __call__(self, url: str) -> bytes:
            if "/submissions/" in url:
                raise HttpError(500)
            return super().__call__(url)

    record = run(writer, Down([K1], DOCUMENTS), requested_symbols=("GOOGL", "MU"))
    assert any("stopped: 1 CIKs failed in a row" in p for p in record.stats["partial"])
    assert sum(s.startswith("FETCH_ERROR") for s in record.items.values()) == 1


def test_a_cik_that_failed_before_goes_last_in_the_next_backfill() -> None:
    writer = store()
    run(writer, Feed([K1], {}), requested_symbols=("GOOGL",))  # GOOGL's document 404s
    sec = feed([K1])
    record = run(writer, sec, requested_symbols=("GOOGL", "MU"), limit=1)
    assert list(record.items) == ["0000723125"]  # MU first; the failed CIK waits its turn
    assert record.stats["pending"] == 1


def test_the_run_ends_partial_when_the_disk_is_short(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    writer = store()
    monkeypatch.setattr(task, "store_path", lambda ctx: tmp_path)
    monkeypatch.setattr(task, "free_gb", lambda path: 1.0)
    sec = feed()
    record = run(writer, sec, requested_symbols=("GOOGL",))
    assert record.status is RunStatus.PARTIAL and sec.urls == []
    assert "1.0 GB free is under 5 GB" in record.stats["partial"][0]
    monkeypatch.setattr(task, "free_gb", lambda path: 50.0)
    assert run(writer, feed(), requested_symbols=("GOOGL",)).status is RunStatus.COMPLETE


def test_the_disk_floor_is_a_site_setting() -> None:
    assert SourcesSettings().sec_filing_text_min_free_gb == 5.0
