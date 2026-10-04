from datetime import UTC, date, datetime

import pytest

from algotrade.config.user import UserContext
from algotrade.services.explore.runs import (
    failure_groups,
    nightly_runs,
    quality_checks,
    run_detail,
    run_items,
)
from algotrade.services.explore.store import NotFoundError, store_over
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import MemoryConfigStore
from algotrade.storage.runs import start_run

NOW = datetime(2026, 10, 3, 2, tzinfo=UTC)


def test_failure_groups_largest_first_with_examples_and_statuses() -> None:
    items = {f"T{i:02}": f"STALE_DATA: chain is for 2026-10-0{i % 2 + 1}" for i in range(12)}
    items |= {"A": "OK", "B": "NO_CHAIN", "C": "ERROR: timeout", "D": "SKIPPED: none due"}
    groups = failure_groups(items)
    assert [(g.reason, g.count) for g in groups] == [
        ("STALE_DATA: chain is for <date>", 12),
        ("ERROR: timeout", 1),
        ("NO_CHAIN", 1),
    ]
    assert groups[0].examples[:2] == ["T00", "T01"] and len(groups[0].examples) == 10
    assert groups[0].statuses == [
        "STALE_DATA: chain is for 2026-10-01",
        "STALE_DATA: chain is for 2026-10-02",
    ]


def test_a_nightly_run_that_failed_early_shows_its_items_as_steps() -> None:
    backend = MemoryBackend()
    run = start_run("nightly", date(2026, 10, 2), NOW)
    run.items = {"universe-build": "FAILED"}
    run.stats = {"failed": ["no step succeeded"]}
    backend.runs.save(run)  # RUNNING: no finish time, no duration
    store = store_over(backend, MemoryConfigStore({}), UserContext("local"))
    [summary] = nightly_runs(store, limit=0)
    assert [(s.name, s.status) for s in summary.steps] == [("universe-build", "FAILED")]
    assert (summary.duration_s, summary.problems) == (None, ["no step succeeded"])
    assert run_detail(store, run.run_id).duration_s is None


def test_quality_checks_fall_back_to_items_and_pick_the_latest_session() -> None:
    backend = MemoryBackend()
    for day, items in (
        (date(2026, 10, 1), {"bars_fresh": "FAIL"}),
        (date(2026, 10, 2), {"bars_fresh": "PASS"}),
    ):
        run = start_run("data_quality", day, NOW)
        run.items = items
        backend.runs.save(run.finish(NOW))
    store = store_over(backend, MemoryConfigStore({}), UserContext("local"))
    report = quality_checks(store)
    assert report.session == date(2026, 10, 2)
    assert [(c.name, c.status, c.detail) for c in report.checks] == [("bars_fresh", "PASS", "")]
    assert quality_checks(store, date(2026, 10, 1)).checks[0].status == "FAIL"
    with pytest.raises(NotFoundError):
        quality_checks(store, date(2026, 9, 30))
    with pytest.raises(NotFoundError):
        run_items(store, "nope")
