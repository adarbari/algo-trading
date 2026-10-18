"""The ``filing-text`` task (edge build D10) over synthetic submissions and the two trimmed filing
fixtures: one row set per instrument (share classes share one fetch, no funds), ``known_from`` the
acceptance SESSION (after the close, a weekend), a rerun that asks for nothing, a parser bump that
changes one item (revised from the FETCH's session, the identical items keeping their stamp), the
reader's as-of view across the bump, a failing document (the other filings stored, the item
failed), a headerless document (a null-item row), the 10-K/A as its own filing, and the nightly."""

import json
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
from algotrade_ingestion.tasks.events.filings import Listed
from algotrade_ingestion.tasks.framework.run import TaskContext
from algotrade_sources.framework.http import HttpError, RetryPolicy
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
ALPHA, BETA = "0001652044", "0000723125"
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
        self.lists = {ALPHA: submissions(ALPHA, alpha), BETA: submissions(BETA, [MU_Q])}
        self.documents, self.broken = dict(documents), broken
        self.urls: list[str] = []

    def __call__(self, url: str) -> bytes:
        self.urls.append(url)
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


DOCUMENTS = {"k1.htm": TEN_K, "ka.htm": TEN_K, "q1.htm": TEN_Q, "q2.htm": TEN_Q, "mu.htm": TEN_Q}


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
    ctx: TaskContext = task_ctx(writer, clock=clock, settings=SourcesSettings())
    kw.setdefault("since", date(2026, 1, 1))
    return task.ingest_filing_text(ctx, listing, text, session, **kw)


def rows(writer: StoreWriter, ids: list[str] | None = None) -> pd.DataFrame:
    frame = stored_filing_text(StoreReader(writer._backend), ids or list(IDS.values()), COLUMNS)
    return frame.sort_values(
        ["instrument_id", "accession", "item"], na_position="first"
    ).reset_index(drop=True)


def bumped(monkeypatch: pytest.MonkeyPatch, version: int = 2) -> None:
    """A new parser version, as a release would make it (one constant, imported twice)."""
    monkeypatch.setattr(filing_items, "PARSER_VERSION", version)
    monkeypatch.setattr(task, "PARSER_VERSION", version)


# ------------------------------------------------------------------------------ rows and stamps


def test_a_backfill_stores_the_items_of_each_periodic_filing_per_share_class() -> None:
    writer, sec = store(), feed()
    record = run(writer, sec, requested_symbols=("GOOGL", "GOOG"))
    assert record.status is RunStatus.COMPLETE, record.stats
    assert record.items["0001652044"].startswith("OK: 2026-01-01..2026-10-02 (4 filings)")
    frame = rows(writer)
    assert set(frame["instrument_id"]) == set(SHARES)  # no fund, no name without a CIK
    assert set(frame["accession"]) == {K1[0], Q1[0], Q2[0], KA[0]}  # the 8-K is not a report
    one = frame[frame["instrument_id"] == "EQ:GOOGL"]
    assert sorted(one.loc[one["accession"] == K1[0], "item"]) == ["1", "1A", "3", "7", "7A", "9A"]
    assert sorted(one.loc[one["accession"] == Q1[0], "item"]) == ["I-2", "I-3", "II-1", "II-1A"]
    assert len(sec.document_urls) == 4  # one request a filing, share classes share it
    assert len(frame) == 2 * (6 + 4 + 4 + 6) and record.stats["rows"] == len(frame)


def test_known_from_is_the_acceptance_session_not_the_filing_date_or_the_fetch_day() -> None:
    writer = store()
    run(writer, feed(), requested_symbols=("GOOGL",))
    frame = rows(writer, ["EQ:GOOGL"]).drop_duplicates("accession").set_index("accession")
    known = {a: pd.Timestamp(k).date() for a, k in frame["known_from"].items()}
    assert known[K1[0]] == date(2026, 2, 11)  # 16:30 ET: after the close, the next session
    assert known[Q1[0]] == date(2026, 5, 4)  # a Saturday: Monday
    assert known[Q2[0]] == date(2026, 8, 5)  # 08:00 ET: that session
    assert known[KA[0]] == date(2026, 3, 2)  # a Sunday: Monday; the 10-K/A is its own filing
    assert all(date.fromisoformat(f) == pd.Timestamp(f).date() for f in ("2026-02-10",))
    stored = StoreReader(writer._backend).table_range(TABLE, date(2000, 1, 1), SESSION)
    assert stored is not None
    session = pd.to_datetime(stored["session_date"]).dt.date
    assert (session == pd.to_datetime(stored["known_from"]).dt.date).all()  # partitioned by it
    assert not (
        pd.to_datetime(stored["known_from"]).dt.date == SESSION
    ).any()  # never the fetch day


def test_the_stored_row_carries_no_html_and_the_columns_the_reader_names() -> None:
    writer = store()
    run(writer, feed(), requested_symbols=("GOOGL",))
    frame = rows(writer, ["EQ:GOOGL"])
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
    frame = rows(writer, ["EQ:GOOGL"])
    assert len(frame) == 1 and frame["item"].isna().all() and frame["text"].isna().all()
    assert frame.loc[0, "quality"] == "NO_ITEMS" and frame.loc[0, "reason"]
    seen = filing_text(StoreReader(writer._backend), ["EQ:GOOGL"], date(2026, 3, 2))
    assert len(seen) == 1 and seen["quality"].iloc[0] == "NO_ITEMS"
    assert (
        run(writer, feed([KA]), requested_symbols=("GOOGL",), since=date(2026, 1, 1)).stats["rows"]
        == 0
    )


def test_items_narrow_the_kept_sections_and_a_new_item_list_is_a_new_read() -> None:
    writer = store()
    run(writer, feed([K1]), requested_symbols=("GOOGL",), items=("1A", "7"))
    assert sorted(rows(writer, ["EQ:GOOGL"])["item"]) == ["1A", "7"]
    wider = feed([K1])
    second = run(writer, wider, requested_symbols=("GOOGL",))  # the default list: another tag
    assert len(wider.document_urls) == 1
    frame = rows(writer, ["EQ:GOOGL"])
    assert (
        sorted(frame["item"]) == ["1", "1A", "3", "7", "7A", "9A"] and second.stats["revised"] == 4
    )


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
    frame = rows(writer, ["EQ:GOOGL"])
    risk = frame[frame["item"] == "1A"].sort_values("parser_version")
    assert risk["parser_version"].tolist() == [1, 2]  # both versions stay
    assert pd.Timestamp(risk["known_from"].iloc[0]).date() == date(2026, 2, 11)
    assert pd.Timestamp(risk["known_from"].iloc[1]).date() == LEARNED  # never the acceptance
    business = frame[frame["item"] == "1"].sort_values("parser_version")
    assert business["known_from"].nunique() == 1  # identical text: the stored stamp stands
    assert business["text"].nunique() == 1


def test_the_reader_sees_the_old_text_until_the_revision_is_known(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    writer = store()
    run(writer, feed([K1]), requested_symbols=("GOOGL",))
    bumped(monkeypatch)
    run(writer, Feed([K1], {**DOCUMENTS, "k1.htm": changed(TEN_K)}), requested_symbols=("GOOGL",))
    reader = StoreReader(writer._backend)

    def risk(on: date) -> str:
        found = filing_text(reader, ["EQ:GOOGL"], on, items=["1A"])
        assert len(found) == 1
        return str(found["text"].iloc[0])

    assert filing_text(reader, ["EQ:GOOGL"], date(2026, 2, 10)).empty  # not accepted yet
    assert "faces competition" in risk(date(2026, 2, 11))
    assert "faces competition" in risk(date(2026, 10, 2))  # the day before the revision is known
    assert "faces intense competition" in risk(LEARNED)
    assert filing_text(reader, ["EQ:GOOGL"], LEARNED, items=["1A"], forms=["10-Q"]).empty


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
    assert rows(writer, ["EQ:GOOGL"])["quality"].tolist() == ["NO_ITEMS"]
    bumped(monkeypatch)
    run(writer, feed([K1]), requested_symbols=("GOOGL",))
    reader = StoreReader(writer._backend)
    before = filing_text(reader, ["EQ:GOOGL"], date(2026, 10, 2))
    assert before["quality"].tolist() == ["NO_ITEMS"]  # known then: nothing found
    after = filing_text(reader, ["EQ:GOOGL"], LEARNED)
    assert sorted(after["item"]) == ["1", "1A", "3", "7", "7A", "9A"]  # the null row is dropped
    first = rows(writer, ["EQ:GOOGL"])
    assert (pd.to_datetime(first[first["item"].notna()]["known_from"]).dt.date == LEARNED).all()


def test_force_rewrites_an_identical_filing_with_its_stored_stamp() -> None:
    writer = store()
    run(writer, feed([K1]), requested_symbols=("GOOGL",))
    once = rows(writer, ["EQ:GOOGL"])
    again = feed([K1])
    record = run(writer, again, requested_symbols=("GOOGL",), force=True)
    assert len(again.document_urls) == 1 and record.stats["revised"] == 0
    twice = rows(writer, ["EQ:GOOGL"])
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


def test_the_nightly_asks_only_the_ciks_due_a_report_over_the_last_fortnight() -> None:
    writer = store()
    run(writer, feed([K1]), requested_symbols=("GOOGL", "MU"), since=date(2026, 1, 1))
    new = ("0001652044-26-000099", "2026-09-30T13:00:00.000Z", "2026-09-30", "10-Q", "new.htm")
    sec = Feed([K1, new], {**DOCUMENTS, "new.htm": TEN_Q})
    record = run(writer, sec, session=date(2026, 10, 2), since=None)
    assert record.status is RunStatus.COMPLETE and record.stats["mode"] == "nightly"
    assert record.stats["window"] == "2026-09-18..2026-10-02"
    assert record.stats["ciks"] == 1  # MU's 10-Q is 57 days old: not due yet
    assert [u.rsplit("/", 1)[-1] for u in sec.document_urls] == ["new.htm"]
    accessions = set(rows(writer)["accession"])
    assert "0001652044-26-000099" in accessions and K1[0] in accessions
    due = task.due_ciks({"A": [Listed("EQ:GOOGL", "GOOGL")]}, pd.DataFrame(), SESSION)
    assert due == {}


def test_due_ciks_orders_oldest_first_and_skips_a_recent_filer() -> None:
    names = {c: [Listed(f"EQ:{c}", c)] for c in ("OLD", "OLDER", "FRESH", "NEVER")}
    ts = {"EQ:OLD": "2026-06-01", "EQ:OLDER": "2026-03-01", "EQ:FRESH": "2026-09-20"}
    stored = pd.DataFrame(
        {"instrument_id": list(ts), "ts": [pd.Timestamp(d, tz=UTC) for d in ts.values()]}
    )
    assert list(task.due_ciks(names, stored, SESSION)) == ["OLDER", "OLD"]


def test_a_fund_and_an_unknown_ticker_are_never_fetched() -> None:
    writer, sec = store(), feed()
    record = run(writer, sec, requested_symbols=("SPYX", "NOPE"))
    assert sec.urls == [] and record.items["sym:NOPE"].startswith("UNKNOWN")
    assert record.stats["ciks"] == 0


def test_a_window_that_ends_before_it_starts_is_refused() -> None:
    with pytest.raises(ValueError):
        run(store(), feed(), since=date(2026, 5, 1), until=date(2026, 4, 1))
