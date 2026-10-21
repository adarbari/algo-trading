"""The filing-text fetch pipeline (``filing_text_fetch.py``): documents read ahead of the task's
loop must give the loop exactly what it got reading one at a time (the same stored rows, the same
failures on the same items), a CIK's lookahead is bounded, a request that fails like a block stops
everything not yet started and holds the limiter, and nothing is left running when the run ends."""

import threading
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pandas as pd
import pytest

from algotrade.storage.runs import RunStatus
from algotrade_ingestion.tasks.events import filing_text as task
from algotrade_ingestion.tasks.events import filing_text_fetch as fetch
from algotrade_sources.framework.base import TransientFetchError
from algotrade_sources.framework.http import GaveUpError, HttpError
from algotrade_sources.framework.limiter import StepLimiter
from algotrade_sources.framework.series import FilingTextRequest
from algotrade_sources.vendors.sec_text.filing_text import extract_payload
from tests.apps.ingestion.tasks.events.test_filing_text import (
    ALPHA,
    BETA,
    GONE,
    TEN_K,
    feed,
    rows,
    run,
    store,
)

CIKS = ["0000000001", "0000000002", "0000000003"]


def request(accession: str, cik: str = "0000000001") -> FilingTextRequest:
    return FilingTextRequest(
        key=accession, session_date=date(2026, 10, 2), cik=cik, form="10-K",
        primary_document=f"{accession}.htm",
    )  # fmt: skip


def parse(body: bytes, accession: str, form: str, items: tuple[str, ...]) -> bytes:
    return b"parsed:" + accession.encode() + b":" + body


def blocking(exc: Exception) -> bool:
    return isinstance(exc, TransientFetchError | GaveUpError)


class Fakes:
    """list / body functions over ``docs`` (cik -> accessions) with a log of what ran."""

    def __init__(self, docs: dict[str, list[str]], fail: dict[str, Exception] | None = None):
        self.docs, self.fail = docs, fail or {}
        self.listed: list[str] = []
        self.bodies: list[str] = []
        self.lock = threading.Lock()

    def list_fn(self, cik: str) -> tuple[bytes | None, Sequence[FilingTextRequest]]:
        with self.lock:
            self.listed.append(cik)
        return b"list:" + cik.encode(), [request(a, cik) for a in self.docs.get(cik, [])]

    def body_fn(self, req: FilingTextRequest) -> bytes | None:
        with self.lock:
            self.bodies.append(req.key)
        if req.key in self.fail:
            raise self.fail[req.key]
        return None if req.key == "gone" else b"body-" + req.key.encode()


def pipeline(fakes: Fakes, ciks: Sequence[str], **kw: Any) -> fetch.Prefetch:
    kw.setdefault("on_block", lambda: None)
    return fetch.Prefetch(
        ciks, fakes.list_fn, fakes.body_fn, parse, threads=3, procs=0, blocking=blocking, **kw
    )


def test_the_loop_gets_each_listing_and_document_in_its_own_order() -> None:
    fakes = Fakes({CIKS[0]: ["a1", "a2", "gone"], CIKS[1]: ["b1"], CIKS[2]: []})
    prefetch = pipeline(fakes, CIKS)
    try:
        assert prefetch.listing(CIKS[0]) == b"list:0000000001"
        assert prefetch.document(CIKS[0], "a1") == b"parsed:a1:body-a1"
        assert prefetch.document(CIKS[0], "a2") == b"parsed:a2:body-a2"
        assert prefetch.document(CIKS[0], "gone") is None  # a 404 is None, as ``fetch`` says
        assert prefetch.listing(CIKS[1]) == b"list:0000000002"
        assert prefetch.document(CIKS[1], "b1") == b"parsed:b1:body-b1"
        assert prefetch.listing(CIKS[2]) == b"list:0000000003"
    finally:
        prefetch.close()


def test_a_failing_document_is_raised_when_the_loop_reaches_it_and_not_before() -> None:
    boom = LookupError("one bad document")
    fakes = Fakes({CIKS[0]: ["a1", "bad", "a3"]}, fail={"bad": boom})
    prefetch = pipeline(fakes, CIKS[:1])
    try:
        prefetch.listing(CIKS[0])  # the loop lists a CIK before it asks for its documents
        assert prefetch.document(CIKS[0], "a1") == b"parsed:a1:body-a1"
        with pytest.raises(LookupError, match="one bad document"):
            prefetch.document(CIKS[0], "bad")
        assert prefetch.document(CIKS[0], "a3") == b"parsed:a3:body-a3"  # the others are untouched
    finally:
        prefetch.close()


def test_only_a_few_ciks_are_listed_ahead_of_the_loop() -> None:
    ciks = [f"{n:010d}" for n in range(1, 40)]
    fakes = Fakes({cik: [] for cik in ciks})
    prefetch = pipeline(fakes, ciks)
    try:
        assert prefetch.listing(ciks[0]) is not None
        prefetch.close()  # waits for the running ones
        assert len(fakes.listed) <= fetch.LOOKAHEAD + 1 + fetch.LIST_THREADS
    finally:
        prefetch.close()


def test_a_block_stops_what_has_not_started_holds_the_limiter_and_later_asks_raise() -> None:
    held: list[int] = []
    blocked = GaveUpError("giving up: HTTP 403", 403)
    fakes = Fakes({CIKS[0]: ["a1"], CIKS[1]: ["b1", "b2"]}, fail={"a1": blocked})
    prefetch = pipeline(fakes, CIKS, on_block=lambda: held.append(1))
    try:
        with pytest.raises(GaveUpError):
            prefetch.document(CIKS[0], "a1") if prefetch.listing(CIKS[0]) else None
        for _ in range(200):  # the block has been seen: nothing new starts
            if held:
                break
            threading.Event().wait(0.01)
        assert held == [1]  # the limiter is held once, not once per request in flight
        started = len(fakes.bodies)
        with pytest.raises((TransientFetchError, GaveUpError)):
            prefetch.document(CIKS[1], "b2")
        assert len(fakes.bodies) <= started + 3  # at most what was already running
    finally:
        prefetch.close()


def test_closing_leaves_no_thread_running_and_a_second_close_is_harmless() -> None:
    fakes = Fakes({CIKS[0]: ["a1", "a2"], CIKS[1]: ["b1"]})
    prefetch = pipeline(fakes, CIKS)
    prefetch.listing(CIKS[0])
    prefetch.close()
    prefetch.close()
    assert not [t for t in threading.enumerate() if t.name.startswith("ft-")]


def test_worker_processes_parse_exactly_what_the_task_parses_inline() -> None:
    req = FilingTextRequest(
        key="0001652044-26-000010", session_date=date(2026, 10, 2), cik=ALPHA, form="10-K",
        primary_document="k1.htm", items=("1A", "7"),
    )  # fmt: skip
    fakes = Fakes({ALPHA: [req.key]})
    fakes.body_fn = lambda r: TEN_K  # type: ignore[method-assign]
    fakes.list_fn = lambda cik: (b"x", [req])  # type: ignore[method-assign]
    prefetch = fetch.Prefetch(
        [ALPHA], fakes.list_fn, fakes.body_fn, extract_payload,
        threads=2, procs=2, blocking=blocking,
    )  # fmt: skip
    try:
        prefetch.listing(ALPHA)
        assert prefetch.document(ALPHA, req.key) == extract_payload(
            TEN_K, req.key, "10-K", ("1A", "7")
        )
    finally:
        prefetch.close()


# ------------------------------------------------------------------ the task through the pipeline


@pytest.mark.parametrize("procs", [0, 2])
def test_the_pipeline_stores_exactly_the_rows_of_the_one_at_a_time_loop(procs: int) -> None:
    sequential, piped = store(), store()
    one = run(sequential, feed())
    many = run(piped, feed(), threads=4, procs=procs)
    assert one.status is many.status is RunStatus.COMPLETE, many.stats
    clocked = ["knowledge_ts", "run_id"]  # stamped by the run (the test clock ticks per run)
    pd.testing.assert_frame_equal(
        rows(sequential).drop(columns=clocked), rows(piped).drop(columns=clocked)
    )
    for key in ("rows", "filings_listed", "filings_fetched", "quality", "sessions_written"):
        assert many.stats[key] == one.stats[key], key
    assert many.items == one.items
    assert not [t for t in threading.enumerate() if t.name.startswith("ft-")]


def test_a_rerun_through_the_pipeline_asks_for_nothing() -> None:
    writer = store()
    run(writer, feed(), threads=3, procs=0)
    sec = feed()
    again = run(writer, sec, threads=3, procs=0)
    assert again.stats["rows"] == 0
    assert [u for u in sec.document_urls if "/daily-index/" not in u] == []


def test_blocked_documents_end_the_run_partial_through_the_pipeline_and_leave_nothing_running() -> (
    None
):
    broken = ("k1.htm", "ka.htm", "q1.htm", "q2.htm", "mu.htm", "gone.htm")
    record = run(store(), feed(broken=broken), threads=4, procs=0)
    assert record.status is RunStatus.PARTIAL, record.stats
    assert "failed in a row" in str(record.stats["partial"])
    assert not [t for t in threading.enumerate() if t.name.startswith("ft-")]


def test_live_only_asks_just_the_operating_companies_of_the_universe() -> None:
    writer, sec = store(), feed()
    record = run(writer, sec, live_only=True)
    assert record.status is RunStatus.COMPLETE, record.stats
    assert set(record.items) == {ALPHA, BETA}  # GONE is in no universe: not asked
    assert GONE not in "".join(sec.listing_urls)
    assert record.stats["filers"] == 2 and record.stats["live_only"] is True
    assert record.stats["pending"] == 0


def test_live_only_keeps_the_recorded_filer_list_whole_so_a_wider_run_can_follow() -> None:
    writer = store()
    window = {"since": date(2026, 1, 1), "until": date(2026, 9, 1)}
    run(writer, feed(), live_only=True, **window)
    wide = run(writer, feed(), **window)  # the window's list was recorded with every filer
    assert wide.stats["filers_cached"] is True and wide.stats["filers"] == 3
    assert set(wide.items) == {GONE}  # the live ones are covered by the first run


def test_two_ciks_listing_the_same_accession_each_get_the_document() -> None:
    """A combined filing is listed under a parent and its subsidiaries: both must read it."""
    fakes = Fakes({CIKS[0]: ["shared"], CIKS[1]: ["shared"]})
    prefetch = pipeline(fakes, CIKS[:2])
    try:
        prefetch.listing(CIKS[0])
        prefetch.listing(CIKS[1])
        assert prefetch.document(CIKS[0], "shared") == b"parsed:shared:body-shared"
        assert prefetch.document(CIKS[1], "shared") == b"parsed:shared:body-shared"
    finally:
        prefetch.close()


def test_only_a_block_page_a_403_or_a_429_stops_the_read_ahead() -> None:
    assert task._stops_fetch(TransientFetchError("block page"))
    assert task._stops_fetch(GaveUpError("giving up", 403))
    assert task._stops_fetch(HttpError(429))
    assert not task._stops_fetch(GaveUpError("giving up", 500))  # one bad request fails its CIK
    assert not task._stops_fetch(LookupError("404"))


def test_a_block_holds_the_stepped_limiter_and_counts_as_an_error(tmp_path: Path) -> None:
    now, slept = [1000.0], []

    def sleep(seconds: float) -> None:
        slept.append(seconds)
        now[0] += seconds

    limiter = StepLimiter(
        "sec", 8, 5, directory=tmp_path, sleep=sleep, clock=lambda: now[0]
    )  # the explicit run stores it under "sec_stepped", not "sec"
    ctx = SimpleNamespace(pacing={"sec_stepped": limiter})
    run_ = SimpleNamespace(stats={})
    task._hold_sec(ctx, run_)  # type: ignore[arg-type]
    limiter.wait()
    assert slept and slept[-1] >= task.BLOCK_HOLD_S - 1  # no request for the hold
    assert limiter.rps == 7  # the block page came back as a 200: still one step down
    assert run_.stats["blocked_hold_s"] == task.BLOCK_HOLD_S
