"""``load_data_status``: the session's data from run records alone. A missing record is UNKNOWN
with a public NOT_RUN gap (never 0%); each ``DataState`` follows from the session's workflow and
the datasets; a screener is affected when it has no run, a PARTIAL run or a run without a
required table (a gap in an optional table alone does not count)."""

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from typing import Any, cast

import pytest

from algotrade.data import StoreReader
from algotrade.services.read.availability import data_status as module
from algotrade.services.read.availability.cause import CauseLevel, UnavailableKind
from algotrade.services.read.availability.data_status import (
    DatasetName,
    DatasetState,
    DataState,
    load_data_status,
    share_status,
)
from algotrade.services.read.context import ReadContext
from algotrade.services.read.session import NewerSession, NewerState, Session
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.runs import start_run

DAY = date(2026, 10, 2)
DONE = datetime(2026, 10, 3, 2, tzinfo=UTC)
COVERAGE_STEP = {
    "rollups": {
        "checks": [
            {
                "name": "coverage_next_earnings_date",
                "status": "PASS",
                "detail": "",
                "data": {
                    "cells": [
                        {"tier": "core", "applicable": 100, "covered": 100},
                        {"tier": "rest", "applicable": 900, "covered": 899},
                    ]
                },
            }
        ]
    }
}


def _session(newer: NewerSession | None = None, complete: bool = True) -> Session:
    return Session(
        DAY, None, True, DAY, DAY, False, (), (), complete=complete, newer=newer, cutoff=DONE
    )


def _records(
    bars: dict[str, str] | None = None,
    chains: dict[str, str] | None = None,
    steps: dict[str, Any] | None = None,
) -> MemoryBackend:
    backend = MemoryBackend()
    for job, items in (("daily_bars", bars), ("option_chains", chains)):
        if items is not None:
            run = start_run(job, DAY, DONE - timedelta(hours=1))
            run.items = items
            backend.runs.save(run)
    if steps is not None:
        run = start_run("nightly", DAY, DONE - timedelta(hours=2))
        run.stats = {"steps": steps}
        backend.runs.save(run)
    return backend


def _status(
    backend: MemoryBackend,
    session: Session | None = None,
    screeners: dict[str, Any] | None = None,
    monkeypatch: pytest.MonkeyPatch | None = None,
) -> module.DataStatus:
    found = screeners or {}
    ctx = cast(
        ReadContext, SimpleNamespace(reader=StoreReader(backend), session=session or _session())
    )
    assert monkeypatch is not None
    monkeypatch.setattr(
        module,
        "load_screeners",
        lambda _: tuple(SimpleNamespace(owner="site", id=i) for i in found),
    )
    monkeypatch.setattr(
        module,
        "load_latest_runs",
        lambda _, keys: {k: SimpleNamespace(run=found[k[1]]) for k in keys},
    )
    return load_data_status(ctx)


def _full() -> MemoryBackend:
    return _records({"A": "OK", "B": "OK"}, {"A": "OK", "B": "OK"}, COVERAGE_STEP)


def test_a_missing_record_is_unknown_with_a_public_gap_not_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    status = _status(_records(), monkeypatch=monkeypatch)
    assert [d.status for d in status.datasets] == [DatasetState.UNKNOWN] * 3
    for d in status.datasets:
        assert (d.present, d.expected, d.share) == (None, None, None)
        assert d.unavailable[0].kind is UnavailableKind.NOT_RUN
        assert d.unavailable[0].cause.leaf.level is CauseLevel.RUN  # admin-only chain
    assert status.state is DataState.PARTIAL


def test_the_datasets_are_graded_from_their_records(monkeypatch: pytest.MonkeyPatch) -> None:
    backend = _records(
        {"A": "OK", "B": "FAILED: no data"},
        {"A": "OK", "B": "OK", "C": "STALE_DATA: old", "D": "OK"},
        COVERAGE_STEP,
    )
    prices, options, fundamentals = _status(backend, monkeypatch=monkeypatch).datasets
    assert (prices.name, prices.status, prices.present, prices.expected) == (
        DatasetName.PRICES,
        DatasetState.PARTIAL,
        1,
        2,
    )
    assert (options.name, options.status, options.share) == (
        DatasetName.OPTIONS_CHAINS,
        DatasetState.PARTIAL,
        0.75,
    )
    assert (fundamentals.present, fundamentals.expected, fundamentals.status) == (
        999,
        1000,
        DatasetState.COMPLETE,
    )


def test_a_record_with_nothing_ok_is_missing_not_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    prices = _status(_records({"A": "FAILED: x"}), monkeypatch=monkeypatch).datasets[0]
    assert (prices.status, prices.present, prices.share) == (DatasetState.MISSING, 0, 0.0)


@pytest.mark.parametrize(
    ("newer", "complete", "backend", "expected"),
    [
        (None, True, _full, DataState.COMPLETE),
        (None, False, _full, DataState.PARTIAL),
        (None, True, lambda: _records({"A": "OK"}, {"A": "OK"}), DataState.PARTIAL),
        (
            NewerSession(DAY + timedelta(days=1), NewerState.IN_PROGRESS),
            True,
            _full,
            DataState.NEXT_PROCESSING,
        ),
        (
            NewerSession(DAY + timedelta(days=1), NewerState.PUBLISHING),
            True,
            _full,
            DataState.NEXT_PROCESSING,
        ),
        (
            NewerSession(
                DAY + timedelta(days=1), NewerState.FAILED_RETRYING, UnavailableKind.SYSTEM
            ),
            True,
            _full,
            DataState.NEXT_FAILED_SHOWING_PREVIOUS,
        ),
    ],
)
def test_each_data_state(
    newer: NewerSession | None,
    complete: bool,
    backend: Any,
    expected: DataState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    status = _status(backend(), _session(newer, complete), monkeypatch=monkeypatch)
    assert status.state is expected
    assert status.knowledge_ts == DONE


def test_affected_screeners_count_gaps_but_not_an_optional_table_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ok = SimpleNamespace(coverage="COMPLETE", missing_tables=(), missing_optional_tables=())
    optional_only = SimpleNamespace(
        coverage="COMPLETE",
        missing_tables=(),
        missing_optional_tables=("rollups/instrument/ibkr_iv@v1",),
    )
    partial = SimpleNamespace(coverage="PARTIAL", missing_tables=(), missing_optional_tables=())
    missing = SimpleNamespace(
        coverage="COMPLETE", missing_tables=("chains/status",), missing_optional_tables=()
    )
    found = {
        "ok": ok,
        "optional": optional_only,
        "partial": partial,
        "missing": missing,
        "not_run": None,
    }
    status = _status(_full(), screeners=found, monkeypatch=monkeypatch)
    assert (status.affected_screeners, status.total_screeners) == (3, 5)


def test_no_screeners_is_zero_of_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    status = _status(_full(), monkeypatch=monkeypatch)
    assert (status.affected_screeners, status.total_screeners) == (0, 0)


def test_share_status_is_the_admin_grids_rule() -> None:
    assert [
        share_status(0, 10),
        share_status(9, 10),
        share_status(10, 10),
        share_status(3, None),
    ] == [
        "MISSING",
        "PARTIAL",
        "COMPLETE",
        "COMPLETE",
    ]
