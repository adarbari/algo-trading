"""The ``ipo-lockups`` task over synthetic EDGAR answers (edge build D8): the search by month, the
acceptance from the issuer's submissions, the facts of the document, ``known_from`` (the real
acceptance session, a backfill included; a changed re-extraction the session after the fetch's own
clock, never ``--until``), the instrument id (only the CIK's universe instrument, filled later
without a fetch), the failure modes stored as rows, resumability (``--limit``) and item statuses."""

import json
import re
from datetime import date, datetime, timedelta
from itertools import count
from typing import Any
from urllib.parse import parse_qs, urlparse

import pandas as pd
import pytest

from algotrade.config.site.settings import SourcesSettings
from algotrade.data import StoreReader
from algotrade.data.events import latest_versions
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.runs import RunStatus
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.events import ipo_lockups, lockup_rows
from algotrade_ingestion.tasks.events.ipo_lockups import (
    KEY,
    TABLE,
    ingest_ipo_lockups,
    months_between,
)
from algotrade_ingestion.tasks.framework.run import TaskContext
from algotrade_sources.framework.http import HttpError, RetryPolicy
from algotrade_sources.vendors.sec.submissions import SecFilings
from algotrade_sources.vendors.sec_prospectus.prospectus import SecProspectus
from algotrade_sources.vendors.sec_prospectus.prospectus_search import SecProspectusSearch
from tests.helpers.ingest_fakes import FIXED, http_for, task_ctx
from tests.helpers.payloads import sec as payloads
from tests.helpers.stored_frames import stamped

SESSION = date(2026, 10, 5)
ABC, DEF, GHI = "0001111111", "0002222222", "0003333333"
ACC1, ACC2, ACC3 = "0001193125-26-100001", "0001193125-26-100002", "0001193125-26-100003"
IDS = {"ABCD": "EQ:ABCD", "GOOA": "EQ:GOOA", "GOOB": "EQ:GOOB"}
CIKS = {"ABCD": ABC, "GOOA": GHI, "GOOB": GHI}  # GHI has two share classes
TICKS = count()


def clock() -> datetime:
    return FIXED + timedelta(minutes=next(TICKS))  # 2026-10-02 18:00 New York and later


def snapshot(writer: StoreWriter, day: date, universe: tuple[str, ...]) -> None:
    """A universe and company-details snapshot of ``universe`` on ``day``."""
    rows = [
        {"instrument_id": IDS[s], "symbol": s, "security_type": "COMMON_STOCK",
         "optionable": True, "status": "ACTIVE", "universe_version": "v1"}
        for s in universe
    ]  # fmt: skip
    writer.write_table("universe", day, f"uni{day}", stamped(rows, day, f"uni{day}"))
    company = [
        {"instrument_id": IDS[s], "symbol": s, "cik": CIKS[s], "name": s, "sic": "1",
         "sector": "x", "fetched_on": day}
        for s in universe
    ]  # fmt: skip
    writer.write_table("instruments/company", day, f"co{day}", stamped(company, day, f"co{day}"))


def store(universe: tuple[str, ...] = ("ABCD", "GOOA", "GOOB")) -> StoreWriter:
    writer = StoreWriter(MemoryBackend())
    day = date(2026, 10, 2)
    reference = [
        {"instrument_id": IDS[s], "symbol": s, "asset_class": "EQ", "security_type": "COMMON_STOCK",
         "multiplier": 1.0, "status": "ACTIVE"}
        for s in IDS
    ]  # fmt: skip
    writer.write_table("instruments/reference", day, "ref", stamped(reference, day, "ref"))
    snapshot(writer, day, universe)
    return writer


class Filing:
    """One 424B4 of the fake EDGAR: its hit, acceptance and document."""

    def __init__(self, accession: str, cik: str, filed: str, accepted: str, document: bytes | None,
                 name: str = "Issuer Inc") -> None:  # fmt: skip
        self.accession, self.cik, self.filed, self.accepted = accession, cik, filed, accepted
        self.document, self.name, self.listed, self.in_submissions = document, name, True, True


class Edge:
    """EDGAR as three URL shapes (search, submissions, document) with a request log."""

    def __init__(self, filings: list[Filing]) -> None:
        self.filings, self.urls, self.broken_months = filings, [], set()

    def __call__(self, url: str) -> bytes:
        self.urls.append(url)
        if "efts.sec.gov" in url:
            return self.search(parse_qs(urlparse(url).query))
        if "/submissions/CIK" in url:
            return self.submissions(re.search(r"CIK(\d{10})\.json", url)[1])  # type: ignore[index]
        found = re.search(r"/data/(\d+)/(\d{18})/(.+)$", url)
        for f in self.filings:
            if found and f.accession.replace("-", "") == found[2] and f.document is not None:
                return f.document
        raise HttpError(404)

    def search(self, query: dict[str, list[str]]) -> bytes:
        start, end = query["startdt"][0], query["enddt"][0]
        if start[:7] in self.broken_months:
            raise HttpError(500)
        hits = [
            (f.accession, f.cik.lstrip("0"), f.filed, f.name)
            for f in self.filings
            if f.listed and start <= f.filed <= end
        ]
        return payloads.search_page(hits)

    def submissions(self, cik: str) -> bytes:
        mine = [f for f in self.filings if f.cik == cik and f.in_submissions]
        if not mine:
            raise HttpError(404)
        recent = {
            "accessionNumber": [f.accession for f in mine],
            "filingDate": [f.filed for f in mine],
            "reportDate": ["" for _ in mine],
            "acceptanceDateTime": [f.accepted for f in mine],
            "form": ["424B4" for _ in mine],
            "items": ["" for _ in mine],
            "primaryDocument": [f"{f.accession}.htm" for f in mine],
        }
        return json.dumps({"cik": cik, "filings": {"recent": recent, "files": []}}).encode()

    def documents(self) -> list[str]:
        return [u for u in self.urls if "/Archives/edgar/data/" in u]


def ipo(accession: str = ACC1, cik: str = ABC, **kw: Any) -> Filing:
    """A standard IPO priced Friday 2026-06-12 and accepted 17:30 New York (21:30 UTC)."""
    document = kw.pop("document", payloads.prospectus())
    accepted = kw.pop("accepted", "2026-06-12T21:30:00.000Z")
    return Filing(accession, cik, kw.pop("filed", "2026-06-15"), accepted, document, **kw)


def run(writer: StoreWriter, edge: Edge, **kw: Any) -> Any:
    retry = RetryPolicy(tries=1)
    ctx: TaskContext = task_ctx(writer, clock=clock, settings=SourcesSettings())
    kw.setdefault("since", date(2026, 6, 1))
    return ingest_ipo_lockups(
        ctx,
        SESSION,
        SecProspectusSearch(http_for(edge, retry)),
        SecFilings(http_for(edge, retry)),
        SecProspectus(http_for(edge, retry)),
        **kw,
    )


def rows(writer: StoreWriter, through: date | None = None) -> pd.DataFrame:
    return latest_versions(StoreReader(writer._backend), TABLE, KEY, through)


def test_an_ipo_row_has_the_facts_the_expiry_and_the_acceptance_session() -> None:
    writer = store()
    record = run(writer, Edge([ipo()]))
    assert record.status is RunStatus.COMPLETE and record.items[f"acc:{ACC1}"] == "OK: EXTRACTED"
    row = rows(writer).iloc[0]
    assert pd.isna(row["instrument_id"])  # a first version never carries today's universe id
    assert row["cik"] == ABC and row["accession"] == ACC1
    assert bool(row["is_ipo"]) and row["extraction"] == "EXTRACTED" and pd.isna(row["reason"])
    assert row["prospectus_date"] == date(2026, 6, 12) and row["offer_price"] == 18.0
    assert row["lockup_days"] == 180 and row["lockup_expiry"] == date(2026, 12, 10)
    assert row["ticker"] == "ABCD" and row["exchange"] == "NASDAQ" and not row["early_release"]
    assert pd.Timestamp(row["ts"]) == pd.Timestamp("2026-06-12T21:30:00Z")
    assert row["issuer_name"] == "Issuer Inc" and row["rules_version"] == lockup_rows.RULES_VERSION


def test_a_backfilled_row_is_known_from_its_acceptance_not_the_fetch() -> None:
    writer = store()
    run(writer, Edge([ipo()]))  # the run is on 2026-10-05, the acceptance on 2026-06-12 17:30 ET
    # after the 16:00 close: known from the next session, the Monday
    assert rows(writer).iloc[0]["known_from"] == date(2026, 6, 15)
    assert rows(writer, through=date(2026, 6, 12)).empty  # not known the session before
    assert len(rows(writer, through=date(2026, 6, 15))) == 1


def test_a_backfilled_row_has_no_instrument_id_at_its_acceptance_session() -> None:
    """Today's universe must not date a 2026-06 row: the id is its own, later version."""
    writer = store()  # ABCD is in today's universe
    run(writer, Edge([ipo()]))
    at_acceptance = rows(writer, through=date(2026, 6, 15))
    assert pd.isna(at_acceptance.iloc[0]["instrument_id"])
    run(writer, Edge([ipo()]))  # the next run stages the id, known from the fetch's next session
    assert rows(writer, through=date(2026, 10, 2)).iloc[0]["instrument_id"] is None or pd.isna(
        rows(writer, through=date(2026, 10, 2)).iloc[0]["instrument_id"]
    )
    assert rows(writer).iloc[0]["instrument_id"] == "EQ:ABCD"
    assert rows(writer).iloc[0]["known_from"] == date(2026, 10, 5)


def test_an_after_close_acceptance_counts_from_the_next_session_and_so_does_the_expiry_base() -> (
    None
):
    late = ipo(accepted="2026-06-13T03:30:00.000Z")  # 23:30 New York on Friday the 12th
    early = ipo(ACC2, DEF, accepted="2026-06-12T19:59:00.000Z")  # 15:59: before the close
    writer = store()
    run(writer, Edge([late, early]))
    got = rows(writer).set_index("accession")
    assert got.loc[ACC1, "known_from"] == date(2026, 6, 15)
    assert got.loc[ACC2, "known_from"] == date(2026, 6, 12)
    assert got.loc[ACC1, "lockup_expiry"] == date(2026, 12, 10)  # the prospectus date rules it


def test_a_not_ipo_and_a_no_lockup_prospectus_are_stored_with_a_reason_and_no_date() -> None:
    follow_on = ipo(ACC1, ABC, document=b"<p>We are offering shares. Lock-up of 90 days after the "
                    b"date of this prospectus.</p>")  # fmt: skip
    silent = ipo(ACC2, DEF, document=payloads.prospectus(repeat=0))
    writer = store()
    record = run(writer, Edge([follow_on, silent]))
    got = rows(writer).set_index("accession")
    assert got.loc[ACC1, "extraction"] == "NOT_IPO" and not got.loc[ACC1, "is_ipo"]
    assert (
        got.loc[ACC2, "extraction"] == "NO_LOCKUP" and "no lock-up term" in got.loc[ACC2, "reason"]
    )
    for accession in (ACC1, ACC2):
        assert pd.isna(got.loc[accession, "lockup_days"]) and pd.isna(
            got.loc[accession, "lockup_expiry"]
        )
    assert record.items[f"acc:{ACC2}"] == "OK: NO_LOCKUP"


def test_a_term_in_months_ends_on_the_calendar_month_and_an_undated_text_has_no_expiry() -> None:
    months = ipo(document=payloads.prospectus(terms=("six months",), dated="August 31, 2025"))
    undated = ipo(ACC2, DEF, document=payloads.prospectus(dated="no date here"))
    writer = store()
    run(writer, Edge([months, undated]))
    got = rows(writer).set_index("accession")
    assert got.loc[ACC1, "lockup_days"] == 181  # 2025-08-31 + 6 months = 2026-02-28
    assert got.loc[ACC1, "lockup_expiry"] == date(2026, 3, 2)  # Sunday the 1st is no session
    assert got.loc[ACC2, "lockup_days"] == 180 and pd.isna(got.loc[ACC2, "lockup_expiry"])
    assert "no prospectus date" in got.loc[ACC2, "reason"]


def test_a_stored_prospectus_is_not_read_again_and_writes_nothing() -> None:
    writer, edge = store(), Edge([ipo()])
    run(writer, edge)
    edge.urls.clear()
    record = run(writer, edge)
    assert edge.documents() == [] and record.stats["skipped_stored"] == 1
    assert record.stats["instruments_filled"] == 1  # the id version, no fetch
    third = run(writer, edge)
    assert third.stats["rows"] == 0 and len(rows(writer)) == 1  # nothing left to write


def new_rules(monkeypatch: pytest.MonkeyPatch) -> None:
    """The extraction rules moved to version v3 (the task and the row builder both read it)."""
    monkeypatch.setattr(ipo_lockups, "RULES_VERSION", "v3")
    monkeypatch.setattr(lockup_rows, "RULES_VERSION", "v3")


def test_a_changed_reextraction_is_a_new_version_known_from_the_fetch_not_the_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    writer = store()
    run(writer, Edge([ipo()]))
    new_rules(monkeypatch)
    # the document now reads another term; --until far in the future must not date the version
    newer = Edge([ipo(document=payloads.prospectus(terms=("90 days",)))])
    record = run(writer, newer, until=date(2027, 1, 1))
    assert record.items[f"acc:{ACC1}"] == "OK: EXTRACTED (changed)"
    # the clock reads 2026-10-02 18:00 New York (a Friday): the next session is Monday the 5th
    now, before = rows(writer), rows(writer, through=date(2026, 10, 2))
    assert now.iloc[0]["lockup_days"] == 90 and now.iloc[0]["known_from"] == date(2026, 10, 5)
    assert now.iloc[0]["rules_version"] == "v3"
    assert before.iloc[0]["lockup_days"] == 180 and before.iloc[0]["known_from"] == date(
        2026, 6, 15
    )


def test_only_the_rules_version_moving_is_restaged_under_the_same_known_from(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    writer, edge = store(), Edge([ipo()])
    run(writer, edge)
    new_rules(monkeypatch)
    record = run(writer, edge)
    assert record.items[f"acc:{ACC1}"] == "OK: EXTRACTED (rules)"
    assert rows(writer).iloc[0]["known_from"] == date(2026, 6, 15)  # no restatement
    assert rows(writer).iloc[0]["rules_version"] == "v3"
    assert run(writer, edge).stats["read"] == 0  # not read again


def test_the_instrument_is_filled_as_its_own_version_without_a_fetch() -> None:
    writer = store(universe=("GOOA", "GOOB"))  # ABCD is in no universe yet
    edge = Edge([ipo(ACC1, ABC), ipo(ACC2, GHI, document=payloads.prospectus(ticker="GOOB"))])
    run(writer, edge)
    assert rows(writer)["instrument_id"].isna().all()  # first versions carry no id
    edge.urls.clear()
    run(writer, edge)  # the fill: two share classes, the prospectus ticker picks GOOB
    got = rows(writer).set_index("accession")
    assert pd.isna(got.loc[ACC1, "instrument_id"])  # the issuer is in no universe yet
    assert got.loc[ACC2, "instrument_id"] == "EQ:GOOB" and edge.documents() == []
    assert got.loc[ACC2, "known_from"] == date(2026, 10, 5)
    snapshot(writer, date(2026, 10, 3), ("ABCD", "GOOA", "GOOB"))  # a later snapshot holds ABCD
    record = run(writer, edge)
    assert edge.documents() == [] and record.items["ids"] == "OK: 1"
    after = rows(writer).set_index("accession")
    assert after.loc[ACC1, "instrument_id"] == "EQ:ABCD"
    assert after.loc[ACC1, "known_from"] == date(2026, 10, 5)
    early = rows(writer, through=date(2026, 10, 2)).set_index("accession")
    assert pd.isna(early.loc[ACC1, "instrument_id"])


def test_the_gap_against_d1s_424b4_rows_is_in_the_stats() -> None:
    writer = store()
    day = date(2026, 10, 2)
    d1 = [
        {"instrument_id": "EQ:ABCD", "ts": pd.Timestamp("2026-06-12T21:30:00Z"), "cik": ABC,
         "form": "424B4", "accession": a, "filing_date": date(2026, 6, 15), "items": "",
         "known_from": date(2026, 6, 15)}
        for a in (ACC1, ACC3)
    ]  # fmt: skip
    writer.write_table("events/filing", day, "d1", stamped(d1, day, "d1"))
    record = run(writer, Edge([ipo(ACC1, ABC)]))  # the search lists only ACC1
    assert record.stats["filing_424b4_in_window"] == 2
    assert record.stats["filing_424b4_not_listed"] == 1
    assert record.stats["filing_424b4_not_listed_sample"] == [ACC3]


def test_without_a_universe_the_facts_are_stored_with_a_null_instrument() -> None:
    writer = StoreWriter(MemoryBackend())
    record = run(writer, Edge([ipo()]))
    assert record.stats["universe_available"] is False
    assert (
        pd.isna(rows(writer).iloc[0]["instrument_id"])
        and rows(writer).iloc[0]["lockup_days"] == 180
    )


def test_a_failed_month_is_an_item_and_the_other_months_still_run() -> None:
    march = ipo(ACC2, DEF, filed="2026-07-15", accepted="2026-07-14T21:00:00.000Z")
    edge = Edge([ipo(), march])
    edge.broken_months = {"2026-06"}
    writer = store()
    record = run(writer, edge)
    assert record.status is RunStatus.PARTIAL
    assert record.items["win:2026-06"].startswith("FETCH_ERROR")
    assert record.items["win:2026-07"] == "OK: 1 hits"
    assert [r["accession"] for _, r in rows(writer).iterrows()] == [ACC2]
    assert record.stats["windows_failed"] == 1 and record.stats["windows"] == 5


def test_a_prospectus_the_submissions_or_the_server_lack_is_no_data_not_a_row() -> None:
    lost = ipo(ACC1, ABC)
    lost.in_submissions = False  # the search lists it, the issuer's submissions do not (yet)
    gone = ipo(ACC2, DEF, document=None)
    record = run(store(), Edge([lost, gone]))
    assert record.items[f"acc:{ACC1}"].startswith("NO_DATA: the issuer's submissions")
    assert record.items[f"acc:{ACC2}"].startswith("NO_DATA: the prospectus document")
    assert record.status is RunStatus.COMPLETE and record.stats["rows"] == 0


def test_limit_reads_the_oldest_first_and_a_rerun_resumes() -> None:
    second = ipo(ACC2, DEF, filed="2026-07-15", accepted="2026-07-14T21:00:00.000Z")
    third = ipo(ACC3, GHI, filed="2026-08-17", accepted="2026-08-14T20:00:00.000Z")
    writer, edge = store(), Edge([third, second, ipo()])
    first_run = run(writer, edge, limit=1)
    assert first_run.stats["read"] == 1 and rows(writer)["accession"].tolist() == [ACC1]
    edge.urls.clear()
    run(writer, edge, limit=1)
    assert rows(writer)["accession"].tolist() == [ACC1, ACC2]
    assert len(edge.documents()) == 1  # the stored one is not read again
    run(writer, edge)
    assert rows(writer)["accession"].tolist() == [ACC1, ACC2, ACC3]


def test_the_default_window_is_the_thirty_days_before_the_session() -> None:
    edge = Edge([])
    ctx = task_ctx(store(), clock=clock)
    retry = RetryPolicy(tries=1)
    record = ingest_ipo_lockups(
        ctx,
        SESSION,
        SecProspectusSearch(http_for(edge, retry)),
        SecFilings(http_for(edge, retry)),
        SecProspectus(http_for(edge, retry)),
    )
    assert record.stats["since"] == "2026-09-05" and record.stats["until"] == "2026-10-05"
    assert set(record.items) == {"win:2026-09", "win:2026-10"}


def test_months_between_clips_to_the_window() -> None:
    assert months_between(date(2025, 12, 20), date(2026, 2, 3)) == [
        (date(2025, 12, 20), date(2025, 12, 31)),
        (date(2026, 1, 1), date(2026, 1, 31)),
        (date(2026, 2, 1), date(2026, 2, 3)),
    ]
    assert months_between(date(2026, 3, 5), date(2026, 3, 5)) == [
        (date(2026, 3, 5), date(2026, 3, 5))
    ]
    assert months_between(date(2026, 3, 6), date(2026, 3, 5)) == []
