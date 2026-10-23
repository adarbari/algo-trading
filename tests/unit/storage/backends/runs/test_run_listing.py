"""``find_many`` over one cached directory listing: the same records as the per-job globs it
replaced, one directory scan for any number of calls, a fresh listing after a write; ``find``
through the per-job index equals the full scan and decodes no names per call."""

from __future__ import annotations

import glob
import threading
import time
from datetime import date, timedelta
from pathlib import Path

import pytest

from algotrade.storage.backends.local import LocalBackend, LocalRuns, safe
from algotrade.storage.backends.runs import run_listing
from algotrade.storage.runs import RunRecord, job_of_name, run_session, start_run
from tests.helpers.stored_frames import T0

D1 = date(2026, 3, 2)
JOBS = ["screen", "screen-wide", "edge", "ingest"]
SPAN = (D1, D1 + timedelta(3))


def _old_find_many(runs: LocalRuns, jobs: list[str], first: date, last: date) -> list[RunRecord]:
    """The implementation before the listing: one glob per job."""
    paths = {
        p
        for job in jobs
        for p in runs.root.glob(f"{glob.escape(safe(job))}-*.json")
        if (day := run_session(p.stem)) is not None and first <= day <= last
    }
    records = [r for p in sorted(paths) if (r := runs._record(p.name)) is not None]
    return sorted((r for r in records if r.job in jobs), key=lambda r: r.started_at)


def _fixture(tmp_path: Path) -> LocalRuns:
    runs = LocalBackend(tmp_path).runs
    n = 0
    for job in JOBS:  # "screen" is a prefix of "screen-wide": shared stems
        for d in range(4):
            runs.save(start_run(job, D1 + timedelta(d), T0 + timedelta(seconds=n)))
            n += 1
    runs.save(RunRecord("job-screen-0123456789abcdef", "job:screen", D1, T0))
    (runs.root / "notes.txt").write_text("x")
    return runs


def test_find_many_equals_the_per_job_globs_it_replaced(tmp_path: Path) -> None:
    runs = _fixture(tmp_path)
    spans = [SPAN, (D1 + timedelta(1), D1 + timedelta(2)), (D1 - timedelta(9), D1 - timedelta(5))]
    for jobs in (["screen"], ["screen-wide"], ["screen", "screen-wide"], JOBS, ["job:screen"], []):
        for first, last in spans:
            assert runs.find_many(jobs, first, last) == _old_find_many(runs, jobs, first, last)
    assert len(runs.find_many(JOBS, *SPAN)) == 16


def test_find_many_calls_scan_the_directory_once_and_see_a_new_write(tmp_path: Path) -> None:
    runs = _fixture(tmp_path)
    for _ in range(20):
        runs.find_many(JOBS, *SPAN)
    runs.find("edge")
    assert runs._listing.scans == 1
    before = len(runs.find_many(["edge"], D1, D1 + timedelta(9)))
    time.sleep(0.01)
    runs.save(start_run("edge", D1 + timedelta(5), T0 + timedelta(99)))
    assert len(runs.find_many(["edge"], D1, D1 + timedelta(9))) == before + 1
    assert runs._listing.scans == 2


def test_find_many_drops_a_deleted_record_after_the_directory_changes(tmp_path: Path) -> None:
    runs = _fixture(tmp_path)
    assert len(runs.find_many(["edge"], *SPAN)) == 4
    time.sleep(0.01)
    next(runs.root.glob("edge-*.json")).unlink()
    assert len(runs.find_many(["edge"], *SPAN)) == 3


def test_concurrent_find_many_and_a_save_agree_with_the_listing(tmp_path: Path) -> None:
    runs = _fixture(tmp_path)
    results: list[int] = []

    def read() -> None:
        results.append(len(runs.find_many(["ingest"], D1, D1 + timedelta(9))))

    threads = [threading.Thread(target=read) for _ in range(4)]
    for t in threads[:2]:
        t.start()
    time.sleep(0.01)
    runs.save(start_run("ingest", D1 + timedelta(6), T0 + timedelta(77)))
    for t in threads[2:]:
        t.start()
    for t in threads:
        t.join()
    assert set(results) <= {4, 5} and len(results) == 4
    assert len(runs.find_many(["ingest"], D1, D1 + timedelta(9))) == 5


def _old_find(runs: LocalRuns, job: str, session_date: date | None = None) -> list[RunRecord]:
    """``find`` before the per-job index: a scan of every stem, decoding each name."""
    prefix = f"{safe(job)}-"
    names = [
        f"{stem}.json"
        for stem, day in runs._listing.all()
        if (
            (stem.startswith(prefix) and session_date in (None, day))
            if day is not None
            else (implied := job_of_name(stem)) is None or implied == job
        )
    ]
    records = [r for name in names if (r := runs._record(name)) is not None]
    hits = [r for r in records if r.job == job and session_date in (None, r.session_date)]
    return sorted(hits, key=lambda r: r.started_at)


def _job_fixture(tmp_path: Path) -> LocalRuns:
    runs = _fixture(tmp_path)
    runs.save(RunRecord("job-edge-0123456789abcdef", "job:edge", D1, T0))
    runs.save(RunRecord("job-edge-eval-0123456789abcdef", "job:edge-eval", D1, T0))
    runs.save(RunRecord("job-screen-fedcba9876543210", "job:screen", D1 + timedelta(1), T0))
    runs.save(RunRecord("oddly-named", "screen", D1, T0 + timedelta(1)))  # implies no job
    return runs


def test_find_equals_the_full_scan_it_replaced(tmp_path: Path) -> None:
    runs = _job_fixture(tmp_path)
    jobs = [*JOBS, "job:screen", "job:edge", "job:edge-eval", "job:none", "screen-", "oddly"]
    for job in jobs:
        for day in (None, D1, D1 + timedelta(1), D1 + timedelta(30)):
            assert runs.find(job, day) == _old_find(runs, job, day), (job, day)
    assert len(runs.find("screen")) == 5  # four dated, the odd name (opened, job matches)
    assert len(runs.find("job:screen")) == 2


def test_find_decodes_no_job_name_per_call(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The call budget: the stems' jobs are decoded once per listing, never per ``find``."""
    runs = LocalBackend(tmp_path).runs
    for n in range(300):  # many session-less job records and many dated runs
        runs.save(RunRecord(f"job-kind{n % 20}-{n:016x}", f"job:kind{n % 20}", D1, T0))
        runs.save(start_run(f"j{n % 40}", D1 + timedelta(n % 5), T0 + timedelta(n)))
    calls = []
    real = job_of_name
    monkeypatch.setattr(run_listing, "job_of_name", lambda s: calls.append(s) or real(s))
    runs.find("j1")  # the listing is built: one decode per undated stem
    built = len(calls)
    assert built == 300
    for _ in range(50):
        runs.find("j1")
        runs.find("job:kind3")
    assert len(calls) == built
