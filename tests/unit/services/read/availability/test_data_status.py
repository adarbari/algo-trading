"""``load_data_status``: the session's data from run records alone. A missing record is UNKNOWN
with a public NOT_RUN gap (never 0%); each ``DataState`` follows from the session's workflow and
the datasets; a screener is affected when it has no run, a PARTIAL run or a run without a
required table (a gap in an optional table alone does not count)."""

import tomllib
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from typing import Any, cast

import pytest

from algotrade.data import StoreReader
from algotrade.services.read.availability import data_status as module
from algotrade.services.read.availability.cause import CauseLevel, UnavailableKind
from algotrade.services.read.availability.data_status import (
    FUNDAMENTALS_FEATURE,
    PRICES_FEATURE,
    DatasetName,
    DatasetState,
    DataState,
    check_name,
    load_data_status,
    share_status,
)
from algotrade.services.read.context import ReadContext
from algotrade.services.read.session import NewerSession, NewerState, Session
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.runs import start_run
from tests.conftest import REPO_ROOT

DAY = date(2026, 10, 2)
DONE = datetime(2026, 10, 3, 2, tzinfo=UTC)


def _step(
    prices: tuple[int, int] = (1000, 1000),
    shares: tuple[int, int] = (999, 1000),
    rest_ok: bool = True,
    shares_ok: bool = True,
    status: str = "PASS",
) -> Any:
    """A ``rollups`` step with the two coverage checks, as ``judge`` stores them: (covered,
    applicable) split into a core and a rest cell (``ok``: the rule's verdict on the cell)."""

    def check(feature: str, covered: int, applicable: int, ok: bool) -> dict[str, Any]:
        cells = [
            {"tier": "core", "applicable": 100, "covered": min(covered, 100), "ok": True},
            {
                "tier": "rest",
                "applicable": applicable - 100,
                "covered": max(covered - 100, 0),
                "ok": ok,
            },
        ]
        return {"name": check_name(feature), "status": status, "data": {"cells": cells}}

    return {
        "rollups": {
            "checks": [
                check(PRICES_FEATURE, *prices, rest_ok),
                check(FUNDAMENTALS_FEATURE, *shares, shares_ok),
            ]
        }
    }


def _session(newer: NewerSession | None = None, complete: bool = True) -> Session:
    return Session(
        DAY, None, True, DAY, DAY, False, (), (), complete=complete, newer=newer, cutoff=DONE
    )


def _records(
    chains: dict[str, str] | None = None,
    steps: dict[str, Any] | None = None,
) -> MemoryBackend:
    backend = MemoryBackend()
    if chains is not None:
        run = start_run("option_chains", DAY, DONE - timedelta(hours=1))
        run.items = chains
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
    return _records({"A": "OK", "B": "OK"}, _step())


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
        {"A": "OK", "B": "OK", "C": "STALE_DATA: old", "D": "OK"},
        _step(prices=(500, 1000), rest_ok=False),
    )
    prices, options, fundamentals = _status(backend, monkeypatch=monkeypatch).datasets
    assert (prices.name, prices.status, prices.present, prices.expected) == (
        DatasetName.PRICES,
        DatasetState.PARTIAL,
        500,
        1000,
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


def test_a_dataset_far_below_98_percent_that_passes_its_minimums_is_complete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fundamentals cover about 47% and the rule accepts it: the share is shown, the grade is
    the rule's (a 98% cut would hold the pill at PARTIAL forever)."""
    backend = _records({"A": "OK"}, _step(shares=(470, 1000)))
    fundamentals = _status(backend, monkeypatch=monkeypatch).datasets[2]
    assert (fundamentals.status, fundamentals.share) == (DatasetState.COMPLETE, 0.47)
    assert _status(backend, monkeypatch=monkeypatch).state is DataState.COMPLETE


def test_a_breaching_tier_or_a_warned_check_is_partial(monkeypatch: pytest.MonkeyPatch) -> None:
    for step in (_step(rest_ok=False, shares_ok=False), _step(status="WARN")):
        status = _status(_records({"A": "OK"}, step), monkeypatch=monkeypatch)
        assert [d.status for d in status.datasets[::2]] == [DatasetState.PARTIAL] * 2
        assert status.state is DataState.PARTIAL


def test_a_retry_record_without_the_checks_does_not_hide_the_ones_before(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A retry nightly carries the ``rollups`` step over without its checks (nightly.py
    ``_carry``): the newest record that holds them answers, not the newest record."""
    backend = _records({"A": "OK"}, _step())
    retry = start_run("nightly", DAY, DONE)
    retry.stats = {"steps": {"rollups": {"status": "SUCCEEDED", "origin": "earlier"}}}
    backend.runs.save(retry)
    prices = _status(backend, monkeypatch=monkeypatch).datasets[0]
    assert (prices.status, prices.present, prices.expected) == (DatasetState.COMPLETE, 1000, 1000)


def test_a_check_with_nothing_covered_is_missing_not_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prices = _status(_records(steps=_step(prices=(0, 1000))), monkeypatch=monkeypatch).datasets[0]
    assert (prices.status, prices.present, prices.share) == (DatasetState.MISSING, 0, 0.0)


def test_the_checks_are_named_as_the_ingestion_names_them() -> None:
    """``coverage_<group>.<column>``, and the rules exist in sources.toml."""
    rules = tomllib.loads((REPO_ROOT / "config/site/sources.toml").read_text())["quality"][
        "coverage"
    ]
    for feature in (PRICES_FEATURE, FUNDAMENTALS_FEATURE):
        group, column = feature.split(".")
        assert column in rules[group]
        assert check_name(feature) == f"coverage_{group}.{column}"


@pytest.mark.parametrize(
    ("newer", "complete", "backend", "expected"),
    [
        (None, True, _full, DataState.COMPLETE),
        (None, False, _full, DataState.PARTIAL),
        (None, True, lambda: _records({"A": "OK"}), DataState.PARTIAL),
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
