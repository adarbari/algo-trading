"""The shares task: CIK -> instruments (every class), incremental by refresh slot, markers for
CIKs without facts, only new facts stored, carry to a new class, limit, force, resume."""

import json
from datetime import UTC, date, datetime, timedelta

import pandas as pd

from algotrade.data import StoreReader
from algotrade.data.shares import TABLE, share_facts, stored_shares
from algotrade.data.statements.reading import TABLE as STATEMENTS
from algotrade.data.statements.reading import statement_facts, stored_statements
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.runs import RunStatus
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.reference.shares import (
    SharesSources,
    Standing,
    _due,
    _rows,
    ingest_shares,
    priority_order,
)
from algotrade_sources.framework.http import HttpError, RetryPolicy
from algotrade_sources.vendors.sec import company_facts
from algotrade_sources.vendors.sec.company_facts import SecCompanyFacts, parse_statements
from tests.helpers.ingest_fakes import http_for, task_ctx
from tests.helpers.stored_frames import stamped
from tests.libs.sources.vendors.sec.test_company_facts import PAYLOAD
from tests.libs.sources.vendors.sec.test_statement_concepts import AAPL as AAPL_STATEMENTS

DAY = date(2026, 10, 2)
PRICE_STATS = "rollups/instrument/price_stats@v2"
CLOCK = lambda: datetime(2026, 10, 2, 22, tzinfo=UTC)  # noqa: E731
GOOGL_CIK = "0001652044"
GOOGL_FACTS = (
    b'{"cik": 1652044, "facts": {"us-gaap": {"WeightedAverageNumberOfSharesOutstandingBasic":'
    b' {"units": {"shares": [{"start": "2026-04-01", "end": "2026-06-30", "val": 12151000000,'
    b' "accn": "0001652044-26-000071", "fy": 2026, "fp": "Q2", "form": "10-Q",'
    b' "filed": "2026-07-23"}]}}}}}'
)


class FakeFacts:
    def __init__(self, broken: set[str] | None = None, aapl: bytes = PAYLOAD) -> None:
        self.urls: list[str] = []
        self.broken = broken or set()
        self.aapl = aapl

    def __call__(self, url: str) -> bytes:
        self.urls.append(url)
        cik = url.rsplit("CIK", 1)[1].removesuffix(".json")
        if cik in self.broken:
            raise HttpError(500)
        if cik == "0000320193":
            return self.aapl
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


def test_the_writer_keeps_every_tag_of_a_period_and_collapses_a_same_tag_amendment() -> None:
    base = {"concept": "revenue", "unit": "usd", "period_start": "2026-04-01",
            "period_end": "2026-06-30", "filed": "2026-08-04"}  # fmt: skip
    facts = pd.DataFrame(
        [
            {**base, "tag": "us-gaap:Revenues", "value": 100.0},
            {**base, "tag": "us-gaap:SalesRevenueNet", "value": 101.0},
            {**base, "tag": "us-gaap:SalesRevenueNet", "value": 102.0},  # a same-day amendment
        ]
    )
    members = pd.DataFrame([{"instrument_id": "EQ:A", "symbol": "A", "cik": "0000000001"}])
    rows = _rows(facts, members, DAY)
    revenue = rows[rows["concept"] == "revenue"]
    assert sorted(revenue["value"]) == [100.0, 102.0]
    assert set(revenue["tag"]) == {"us-gaap:Revenues", "us-gaap:SalesRevenueNet"}
    assert list(rows[rows["concept"] == "checked"]["tag"]) == [None]


def test_one_fetch_writes_the_shares_and_the_statements() -> None:
    writer, reader = store()
    feed = FakeFacts(aapl=AAPL_STATEMENTS)
    record = ingest_shares(task_ctx(writer, reader, CLOCK), sources(feed), DAY)
    assert record.status is RunStatus.COMPLETE
    assert sorted(u.rsplit("CIK", 1)[1][:10] for u in feed.urls) == sorted(
        {"0000320193", GOOGL_CIK, "0000884394"}
    )  # the document of each CIK is fetched once, for both tables
    expected = len(parse_statements(AAPL_STATEMENTS))
    facts = statement_facts(reader, DAY)
    assert len(facts) == expected > 0 and set(facts["instrument_id"]) == {"EQ:AAPL"}
    assert record.stats["statement_rows"] == expected + 4  # + a marker per instrument of each CIK
    stored = stored_statements(reader)
    assert set(stored[stored["concept"] == "checked"]["instrument_id"]) == {
        "EQ:AAPL", "EQ:GOOGL", "EQ:GOOG", "EQ:SPY",
    }  # fmt: skip
    assert len(share_facts(reader)) > 0  # the same document's share counts
    assert writer.raw.get("sec_edgar", "companyfacts", DAY, record.run_id, "0000320193") == (
        AAPL_STATEMENTS
    )


def test_a_statements_failure_after_the_shares_stored_leaves_the_statements_due() -> None:
    """Fails if a CIK's due date came from the shares table alone: its marker there is fresh,
    so the CIK would wait 30 days for statements that were never stored."""
    writer, reader = store()
    put = writer.staging.put

    def put_unless_statements(run_id: str, table: str, key: str, frame: pd.DataFrame) -> None:
        if table == STATEMENTS and key == "0000320193":
            raise OSError("disk full")
        put(run_id, table, key, frame)

    writer.staging.put = put_unless_statements  # type: ignore[method-assign]
    first = ingest_shares(
        task_ctx(writer, reader, CLOCK), sources(FakeFacts(aapl=AAPL_STATEMENTS)), DAY
    )
    assert first.status is RunStatus.PARTIAL and first.stats["failed"][0].startswith("0000320193")
    shares = stored_shares(reader)
    assert "EQ:AAPL" in set(shares[shares["concept"] == "checked"]["instrument_id"])
    stored = stored_statements(reader)
    assert "EQ:AAPL" not in set(stored["instrument_id"])  # no statements, and no marker
    writer.staging.put = put  # type: ignore[method-assign]
    nxt = DAY + timedelta(days=1)  # far from the 30-day slot of the shares marker
    feed = FakeFacts(aapl=AAPL_STATEMENTS)
    second = ingest_shares(task_ctx(writer, reader, CLOCK), sources(feed), nxt)
    assert "0000320193" in {u.rsplit("CIK", 1)[1][:10] for u in feed.urls}
    assert second.status is RunStatus.COMPLETE
    again = statement_facts(reader, nxt)
    assert len(again) == len(parse_statements(AAPL_STATEMENTS))


def test_a_new_class_gets_the_statements_of_its_ciks_stored_facts_too() -> None:
    writer, reader = store()
    kwargs = {"refresh_days": 100000}  # nothing is due again on the next day
    ingest_shares(
        task_ctx(writer, reader, CLOCK), sources(FakeFacts(aapl=AAPL_STATEMENTS), **kwargs), DAY
    )
    nxt = DAY + timedelta(days=1)
    reference = reader.table("instruments/reference", DAY)
    assert reference is not None
    row = reference[reference["symbol"] == "AAPL"].assign(instrument_id="EQ:AAPL2", symbol="AAPL2")
    writer.write_table("instruments/reference", nxt, "u2", pd.concat([reference, row]))
    feed = FakeFacts(aapl=AAPL_STATEMENTS)
    record = ingest_shares(task_ctx(writer, reader, CLOCK), sources(feed, **kwargs), nxt)
    assert record.stats["requested"] == 0 and not feed.urls
    expected = len(parse_statements(AAPL_STATEMENTS))
    assert record.stats["statements_carried"] == expected
    facts = statement_facts(reader, nxt)
    assert len(facts[facts["instrument_id"] == "EQ:AAPL2"]) == expected
    assert len(facts[facts["instrument_id"] == "EQ:AAPL"]) == expected


def test_the_statements_backlog_is_fetched_a_few_ciks_a_night() -> None:
    """Three CIKs have share counts and no statements (stored before the table existed): with
    a cap of one, one is fetched each night, never one twice, and the deferred are counted."""
    writer, reader = store()
    markers = [
        {"instrument_id": f"EQ:{sym}", "symbol": sym, "cik": cik, "concept": "checked",
         "tag": None, "period_start": None, "period_end": None, "filed": None, "fetched_on": DAY}
        for sym, cik in (("AAPL", "0000320193"), ("GOOGL", GOOGL_CIK), ("GOOG", GOOGL_CIK),
                         ("SPY", "0000884394"))
    ]  # fmt: skip
    writer.write_table(TABLE, DAY, "old", stamped(markers, DAY, "old"))
    assert stored_statements(reader).empty
    seen: list[str] = []
    for night, deferred in ((1, 2), (2, 1), (3, 0), (4, 0)):
        feed = FakeFacts(aapl=AAPL_STATEMENTS)
        capped = SharesSources(sources(feed, 100000).facts, 100000, backfill_per_night=1)
        record = ingest_shares(task_ctx(writer, reader, CLOCK), capped, DAY + timedelta(days=night))
        seen += [u.rsplit("CIK", 1)[1][:10] for u in feed.urls]
        assert record.stats["deferred_by_limit"] == deferred
    assert len(seen) == len(set(seen)) == 3  # each CIK once, the rest of the nights idle
    last = stored_statements(reader)
    assert set(last[last["concept"] == "checked"]["instrument_id"]) == {
        "EQ:AAPL", "EQ:GOOGL", "EQ:GOOG", "EQ:SPY",
    }  # fmt: skip


def test_a_new_cik_is_never_capped_by_the_backlog_limit() -> None:
    writer, reader = store()
    capped = SharesSources(sources(FakeFacts()).facts, 30, backfill_per_night=1)
    record = ingest_shares(task_ctx(writer, reader, CLOCK), capped, DAY)
    assert record.stats["requested"] == 3 and record.stats["deferred_by_limit"] == 0


def test_a_statements_parse_error_keeps_the_shares_and_the_cik_due(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Fails if the shares were lost with the statements, or if the missing table wrote a
    marker (the CIK would then wait 30 days)."""
    writer, reader = store()
    with monkeypatch.context() as broken:
        broken.setattr(company_facts, "_statement_rows", lambda doc, cik: 1 / 0)
        first = ingest_shares(
            task_ctx(writer, reader, CLOCK), sources(FakeFacts(aapl=AAPL_STATEMENTS)), DAY
        )
    assert first.status is RunStatus.PARTIAL
    assert {f.split(":")[0] for f in first.stats["failed"]} >= {"0000320193"}
    assert len(share_facts(reader)) > 0  # the share counts of the same document are stored
    # no statements and no marker for a CIK whose document did not parse (the fund's 404 has one)
    assert set(stored_statements(reader)["instrument_id"]) == {"EQ:SPY"}
    feed = FakeFacts(aapl=AAPL_STATEMENTS)
    ingest_shares(task_ctx(writer, reader, CLOCK), sources(feed), DAY + timedelta(days=1))
    assert "0000320193" in {u.rsplit("CIK", 1)[1][:10] for u in feed.urls}
    assert len(statement_facts(reader, DAY + timedelta(days=1))) > 0


def test_a_restatement_filed_after_a_session_does_not_change_what_that_session_read() -> None:
    writer, reader = store()
    ingest_shares(task_ctx(writer, reader, CLOCK), sources(FakeFacts(aapl=AAPL_STATEMENTS)), DAY)
    before = statement_facts(reader, DAY)
    doc = json.loads(AAPL_STATEMENTS)
    assets = doc["facts"]["us-gaap"]["Assets"]["units"]["USD"]
    latest = max(assets, key=lambda r: r["filed"])
    assets.append({**latest, "val": latest["val"] * 2, "filed": "2026-12-01", "form": "10-Q/A",
                   "accn": "0000320193-26-000099"})  # fmt: skip
    later = DAY + timedelta(days=2)
    ingest_shares(
        task_ctx(writer, reader, CLOCK),
        sources(FakeFacts(aapl=json.dumps(doc).encode())),
        later,
        force=True,
    )
    pd.testing.assert_frame_equal(statement_facts(reader, DAY), before)
    after = statement_facts(reader, date(2026, 12, 1))
    assert len(after) == len(before) + 1
    assert after.iloc[-1]["value"] == latest["val"] * 2


def _order(scope=(), sp500=(), standing=None):  # type: ignore[no-untyped-def]
    ids = {"A": "1", "B": "2", "C": "3", "D": "4", "E": "5"}
    return priority_order(sorted(ids.values()), set(scope), set(sp500), standing or {}, ids)


def test_priority_scope_then_sp500_then_the_rest_by_market_cap() -> None:
    standing = {"C": Standing(market_cap=5.0), "D": Standing(market_cap=9.0)}
    assert _order(scope={"E"}, sp500={"B"}, standing=standing) == ["5", "2", "4", "3", "1"]


def test_priority_inside_the_sp500_optionable_liquid_names_come_first() -> None:
    standing = {
        "A": Standing(optionable=False, adv_usd=9e9),
        "B": Standing(optionable=True, adv_usd=1e6),
        "C": Standing(optionable=True, adv_usd=5e7),
    }
    assert _order(sp500={"A", "B", "C"}, standing=standing)[:3] == ["3", "2", "1"]


def test_priority_scope_names_stay_first_whatever_their_liquidity() -> None:
    standing = {"A": Standing(optionable=False), "B": Standing(optionable=True, adv_usd=9e9)}
    assert _order(scope={"A"}, sp500={"B"}, standing=standing)[:2] == ["1", "2"]


def test_priority_missing_inputs_degrade_to_cik_order_and_a_cik_takes_its_best_instrument() -> None:
    assert _order() == ["1", "2", "3", "4", "5"] == _order()  # deterministic
    ids = {"A1": "9", "A2": "9", "B": "1"}
    got = priority_order(["1", "9"], set(), {"A2"}, {}, ids)
    assert got == ["9", "1"]  # CIK 9 holds an S&P 500 class


def test_the_cap_defers_the_lowest_priority_backlog_ciks() -> None:
    day = date(2026, 1, 5)
    fetched = [dict.fromkeys("123", day), {}]
    src = SharesSources(None, 30, backfill_per_night=1)  # type: ignore[arg-type]
    due, deferred = _due(list("123"), fetched, day, src, False, ["3", "1", "2"])
    assert due == ["3"] and deferred == 2
    assert _due(list("123"), fetched, day, src, False)[0] == ["1"]  # default: CIK order
    # a CIK new to both is never deferred, and --limit style slicing takes the highest first
    fresh = _due(list("123"), [{"1": day}, {}], day, src, False, ["3", "2", "1"])
    assert fresh == (["3", "2", "1"], 0)  # new to both are never deferred; priority order


def test_priority_never_changes_what_is_due_or_exempt() -> None:
    """Fails if the order changed the due set or which CIKs the cap exempts (new to both,
    shares-due, stale): only the order of the new part may differ."""
    day = date(2026, 3, 1)
    old, recent = date(2026, 1, 1), date(2026, 2, 28)
    fetched = [
        {"1": old, "2": recent, "3": recent, "4": old, "5": recent},  # shares
        {"1": old, "4": old, "5": recent},  # statements: 2, 3 are backlog; 6 new to both
    ]
    ciks = ["1", "2", "3", "4", "5", "6"]
    for cap, force in ((0, False), (1, False), (3, False), (1, True)):
        src = SharesSources(None, 30, backfill_per_night=cap)  # type: ignore[arg-type]
        plain = _due(ciks, fetched, day, src, force)
        ranked = _due(ciks, fetched, day, src, force, ["6", "3", "2", "5", "4", "1"])
        backlog = {"2", "3"}
        assert set(plain[0]) - backlog == set(ranked[0]) - backlog  # exempt CIKs: the same
        assert len(plain[0]) == len(ranked[0]) and plain[1] == ranked[1]
        if cap == 0 or force or cap >= 2:
            assert sorted(plain[0]) == sorted(ranked[0])  # nothing deferred: the same due set
        else:
            assert "3" in ranked[0] and "2" not in ranked[0]  # the cap defers the lowest


def _priced_store() -> tuple[StoreWriter, StoreReader]:
    """The shares store with a flagged S&P 500 name: GOOGL in the S&P 500, AAPL optionable."""
    writer = StoreWriter(MemoryBackend())
    rows = [("AAPL", "0000320193", False, True), ("GOOGL", GOOGL_CIK, True, False),
            ("SPY", "0000884394", False, False)]  # fmt: skip
    reference = [
        {"instrument_id": f"EQ:{s}", "symbol": s, "asset_class": "equity", "multiplier": 1.0,
         "security_type": "COMMON_STOCK", "status": "ACTIVE", "cik": cik, "in_sp500": sp,
         "optionable": opt}
        for s, cik, sp, opt in rows
    ]  # fmt: skip
    writer.write_table("instruments/reference", DAY, "u", stamped(reference, DAY, "u"))
    return writer, StoreReader(writer._backend)


def _stats(writer: StoreWriter, day: date, adv: float, run: str) -> None:
    frame = [{"instrument_id": "EQ:AAPL", "symbol": "AAPL", "close": 100.0, "adv_usd_20d": adv}]
    writer.write_table(PRICE_STATS, day, run, stamped(frame, day, run))


def test_limit_takes_the_sp500_first_then_the_liquid_optionable() -> None:
    writer, reader = _priced_store()
    _stats(writer, DAY - timedelta(days=1), 5e7, "p")
    feed = FakeFacts()
    ingest_shares(task_ctx(writer, reader, CLOCK), sources(feed), DAY, limit=2)
    fetched = [u.rsplit("CIK", 1)[1][:10] for u in feed.urls]
    assert fetched == [GOOGL_CIK, "0000320193"]  # S&P 500 first; then optionable and liquid


def test_a_rerun_after_tonights_rollups_keeps_the_same_order() -> None:
    """Fails if an input was read on the session itself: the roll-ups written after the first
    attempt would reorder (and the cap pick other CIKs)."""
    writer, reader = _priced_store()
    first, second = FakeFacts(), FakeFacts()
    ingest_shares(task_ctx(writer, reader, CLOCK), sources(first), DAY, limit=3)
    _stats(writer, DAY, 5e7, "same-day")  # tonight's price_stats, written after
    ingest_shares(task_ctx(writer, reader, CLOCK), sources(second), DAY, force=True, limit=3)
    order = [u.rsplit("CIK", 1)[1][:10] for u in first.urls]
    assert order == [u.rsplit("CIK", 1)[1][:10] for u in second.urls]
