"""The shares task: CIK -> instruments (every class), incremental by refresh slot, markers for
CIKs without facts, only new facts stored, carry to a new class, limit, force, resume."""

import json
from datetime import UTC, date, datetime, timedelta

import pandas as pd

from algotrade.data import StoreReader
from algotrade.data.shares import TABLE, share_facts, stored_shares
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.runs import RunStatus
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.reference.shares import SharesSources, ingest_shares
from algotrade_sources.framework.http import HttpError, RetryPolicy
from algotrade_sources.vendors.sec.company_facts import SecCompanyFacts
from tests.helpers.ingest_fakes import http_for, task_ctx
from tests.helpers.stored_frames import stamped
from tests.libs.sources.vendors.sec.test_company_facts import PAYLOAD

DAY = date(2026, 10, 2)
CLOCK = lambda: datetime(2026, 10, 2, 22, tzinfo=UTC)  # noqa: E731
GOOGL_CIK = "0001652044"
GOOGL_FACTS = (
    b'{"cik": 1652044, "facts": {"us-gaap": {"WeightedAverageNumberOfSharesOutstandingBasic":'
    b' {"units": {"shares": [{"start": "2026-04-01", "end": "2026-06-30", "val": 12151000000,'
    b' "accn": "0001652044-26-000071", "fy": 2026, "fp": "Q2", "form": "10-Q",'
    b' "filed": "2026-07-23"}]}}}}}'
)


class FakeFacts:
    def __init__(self, broken: set[str] | None = None) -> None:
        self.urls: list[str] = []
        self.broken = broken or set()

    def __call__(self, url: str) -> bytes:
        self.urls.append(url)
        cik = url.rsplit("CIK", 1)[1].removesuffix(".json")
        if cik in self.broken:
            raise HttpError(500)
        if cik == "0000320193":
            return PAYLOAD
        if cik == GOOGL_CIK:
            return GOOGL_FACTS
        raise HttpError(404)  # SPY's trust: no XBRL facts


def sources(feed: FakeFacts, refresh_days: int = 30) -> SharesSources:
    return SharesSources(SecCompanyFacts(http_for(feed, RetryPolicy(tries=1))), refresh_days)


def store(extra: tuple[tuple[str, str | None], ...] = ()) -> tuple[StoreWriter, StoreReader]:
    """Reference on DAY: AAPL (CIK in the reference), GOOGL + GOOG (CIK only in
    instruments/company), SPY (a fund CIK), WEIRD (no CIK)."""
    writer = StoreWriter(MemoryBackend())
    rows = [
        ("AAPL", "0000320193"),
        ("GOOGL", None),
        ("GOOG", None),
        ("SPY", "884394"),
        ("WEIRD", None),
        *extra,
    ]
    reference = [
        {"instrument_id": f"EQ:{s}", "symbol": s, "asset_class": "equity", "multiplier": 1.0,
         "security_type": "COMMON_STOCK", "status": "ACTIVE", "cik": cik}
        for s, cik in rows
    ]  # fmt: skip
    writer.write_table("instruments/reference", DAY, "u", stamped(reference, DAY, "u"))
    company = [
        {"instrument_id": f"EQ:{s}", "symbol": s, "cik": GOOGL_CIK, "name": "Alphabet Inc.",
         "sic": "7370", "sector": "Technology", "fetched_on": DAY}
        for s in ("GOOGL", "GOOG")
    ]  # fmt: skip
    writer.write_table("instruments/company", DAY, "c", stamped(company, DAY, "c"))
    return writer, StoreReader(writer._backend)


def test_first_run_maps_facts_to_every_class_and_marks_funds() -> None:
    writer, reader = store()
    feed = FakeFacts()
    record = ingest_shares(task_ctx(writer, reader, CLOCK), sources(feed), DAY)
    assert record.status is RunStatus.COMPLETE
    s = record.stats
    assert (s["instruments"], s["ciks"], s["requested"], s["with_facts"], s["no_facts"]) == (
        4, 3, 3, 2, 1,
    )  # fmt: skip
    facts = share_facts(reader)
    googl = facts[facts["instrument_id"].isin(["EQ:GOOGL", "EQ:GOOG"])]
    assert len(googl) == 2 and set(googl["shares"]) == {12151000000.0}
    assert set(googl["cik"]) == {GOOGL_CIK} and set(googl["concept"]) == {"weighted_basic"}
    aapl = facts[facts["instrument_id"] == "EQ:AAPL"]
    assert len(aapl) == 8 and aapl["filed"].iloc[0] == date(2025, 10, 31)
    assert set(aapl["fy"].dropna()) == {2025, 2026}
    revenue = aapl[aapl["concept"] == "revenue"].iloc[0]
    assert (revenue["value"], revenue["unit"], revenue["period_start"]) == (
        95359000000.0,
        "usd",
        date(2025, 12, 28),
    )
    stored = stored_shares(reader)
    markers = stored[stored["concept"] == "checked"]
    assert set(markers["instrument_id"]) == {"EQ:AAPL", "EQ:GOOGL", "EQ:GOOG", "EQ:SPY"}
    assert set(markers["fetched_on"]) == {DAY}
    assert writer.raw.get("sec_edgar", "companyfacts", DAY, record.run_id, "0000320193") == PAYLOAD


def test_nightly_runs_are_incremental_and_store_only_new_facts() -> None:
    writer, reader = store()
    ingest_shares(task_ctx(writer, reader, CLOCK), sources(FakeFacts()), DAY)
    nxt = DAY + timedelta(days=1)
    again = FakeFacts()
    record = ingest_shares(task_ctx(writer, reader, CLOCK), sources(again), nxt)
    assert record.stats["requested"] == len(again.urls) <= 1  # only a CIK whose slot is today
    later = DAY + timedelta(days=31)
    stale = FakeFacts()
    record = ingest_shares(task_ctx(writer, reader, CLOCK), sources(stale), later)
    assert record.stats["requested"] == 3  # every CIK's slot passed in 31 days
    partition = reader.table(TABLE, later)
    assert partition is not None
    assert set(partition["concept"]) == {"checked"}  # nothing new was filed
    assert len(share_facts(reader)) == 10
    forced = FakeFacts()
    ingest_shares(task_ctx(writer, reader, CLOCK), sources(forced), later, force=True)
    assert len(forced.urls) == 3


def test_limit_defers_and_errors_make_the_run_partial() -> None:
    writer, reader = store()
    feed = FakeFacts(broken={"0000320193"})
    record = ingest_shares(task_ctx(writer, reader, CLOCK), sources(feed), DAY, limit=2)
    assert record.status is RunStatus.PARTIAL
    assert (record.stats["requested"], record.stats["deferred_by_limit"]) == (2, 1)
    assert record.stats["failed"][0].startswith("0000320193")
    # The failed and the deferred CIK are still due next run; the fund was checked.
    retry = FakeFacts()
    ingest_shares(task_ctx(writer, reader, CLOCK), sources(retry), DAY + timedelta(days=1))
    fetched = {u.rsplit("CIK", 1)[1][:10] for u in retry.urls}
    assert fetched >= {GOOGL_CIK, "0000320193"}


def test_a_new_class_gets_its_ciks_stored_facts() -> None:
    writer, reader = store()
    ingest_shares(task_ctx(writer, reader, CLOCK), sources(FakeFacts()), DAY)
    nxt = DAY + timedelta(days=1)
    reference = reader.table("instruments/reference", DAY)
    assert reference is not None
    row = reference[reference["symbol"] == "AAPL"].assign(instrument_id="EQ:AAPL2", symbol="AAPL2")
    writer.write_table("instruments/reference", nxt, "u2", pd.concat([reference, row]))
    record = ingest_shares(task_ctx(writer, reader, CLOCK), sources(FakeFacts()), nxt)
    if record.stats["requested"] == 0:  # AAPL's slot is not today: copied, not fetched
        assert record.stats["carried"] == 8
    facts = share_facts(reader)
    assert len(facts[facts["instrument_id"] == "EQ:AAPL2"]) == 8


def test_resume_skips_ciks_already_fetched() -> None:
    writer, reader = store()
    feed = FakeFacts(broken={GOOGL_CIK})
    first = ingest_shares(task_ctx(writer, reader, CLOCK), sources(feed), DAY)
    assert first.status is RunStatus.PARTIAL
    fixed = FakeFacts()
    second = ingest_shares(task_ctx(writer, reader, CLOCK), sources(fixed), DAY)
    assert second.run_id == first.run_id  # resumed the unfinished run
    assert [u.rsplit("CIK", 1)[1][:10] for u in fixed.urls] == [GOOGL_CIK]
    assert second.status is RunStatus.COMPLETE
    assert len(share_facts(reader)) == 10


def test_a_forced_refetch_adds_only_the_financials_to_an_older_store() -> None:
    """Share counts stored before the financials existed: a refetch stores the new concepts
    (the keys now include the period start) and nothing that is already there."""
    writer, reader = store()
    older = json.loads(PAYLOAD)
    del older["facts"]["us-gaap"]["Revenues"]
    first = FakeFacts()
    first_feed = lambda url: json.dumps(older).encode() if "0000320193" in url else first(url)  # noqa: E731
    ingest_shares(task_ctx(writer, reader, CLOCK), sources(first_feed), DAY)
    assert "revenue" not in set(share_facts(reader)["concept"])
    later = DAY + timedelta(days=1)
    ingest_shares(task_ctx(writer, reader, CLOCK), sources(FakeFacts()), later, force=True)
    partition = reader.table(TABLE, later)
    assert partition is not None
    fresh = partition[partition["concept"] != "checked"]
    assert set(fresh["concept"]) == {"revenue"} and len(fresh) == 1  # AAPL's one revenue fact
