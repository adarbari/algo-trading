"""The edge runs read by run: the canonical run is the latest committed site run at the
frozen split, an exploratory or null-split run is never canonical, no such run is NOT_RUN with
the reason, and a run's rows are its own even when another run shares the partition."""

from datetime import date

import pytest

from algotrade.services.read.evaluation.edges import load_edge, load_edges
from algotrade.services.read.evaluation.runs import (
    load_canonical_run,
    load_edge_runs,
    load_run_draws,
    load_run_rows,
)
from algotrade.services.read.values import UnknownCode
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.runs import RunStatus
from tests.unit.services.read.evaluation.conftest import (
    FROZEN,
    row,
    session_ctx,
    stores,
    write_run,
)


def test_the_edge_document_and_its_status(backend: MemoryBackend) -> None:
    (edge,) = load_edges(stores(backend))
    assert (edge.id, edge.status, edge.frozen_from, edge.screeners) == (
        "drift", "candidate", FROZEN, ("momo",),
    )  # fmt: skip
    assert edge.variants == ("main",) and edge.horizons == (20,)
    assert load_edge(stores(backend), "nope") is None


def test_the_canonical_run_is_the_latest_at_the_frozen_split(backend: MemoryBackend) -> None:
    write_run(backend, "old", FROZEN, 0.5, minutes=0)
    write_run(backend, "new", FROZEN, 0.6, minutes=10)
    write_run(backend, "later-exploratory", date(2026, 3, 1), 0.9, minutes=20)
    ctx = stores(backend)
    edge = load_edge(ctx, "drift")
    assert edge is not None
    found = load_canonical_run(ctx, edge)
    assert found.run is not None and found.run.run_id == "new" and not found.run.exploratory
    assert found.not_run is None
    runs = load_edge_runs(ctx, edge)
    assert [(r.run_id, r.exploratory) for r in runs] == [
        ("later-exploratory", True), ("new", False), ("old", False),
    ]  # fmt: skip


def test_no_run_at_the_frozen_split_is_not_run_never_an_older_one(backend: MemoryBackend) -> None:
    write_run(backend, "explore", date(2026, 3, 1), 0.9)
    write_run(backend, "legacy", None, 0.9, minutes=5)  # before the split was recorded
    write_run(backend, "running", FROZEN, 0.9, minutes=6, status=RunStatus.RUNNING)
    ctx = stores(backend)
    edge = load_edge(ctx, "drift")
    assert edge is not None
    found = load_canonical_run(ctx, edge)
    assert found.run is None and found.not_run is not None
    assert found.not_run.code is UnknownCode.NOT_RUN


def test_a_users_run_is_never_canonical(backend: MemoryBackend) -> None:
    write_run(backend, "mine", FROZEN, 0.9, owner="me")
    ctx = stores(backend)
    edge = load_edge(ctx, "drift")
    assert edge is not None
    assert load_canonical_run(ctx, edge).run is None  # the site's run is the canonical one
    assert [r.run_id for r in load_edge_runs(ctx, edge)] == ["mine"]  # but it is theirs to see


def test_rows_are_read_by_run_id(backend: MemoryBackend) -> None:
    write_run(backend, "legacy", None, 0.11)  # a null-split run in the same range-end partition
    write_run(backend, "canon", FROZEN, 0.66, minutes=5)
    ctx = stores(backend)
    edge = load_edge(ctx, "drift")
    assert edge is not None
    run = load_canonical_run(ctx, edge).run
    assert run is not None
    rows = load_run_rows(ctx, run)
    assert {r.slice_kind for r in rows} == {"all", "frozen"}
    frozen = next(r for r in rows if r.slice_kind == "frozen")
    assert frozen.hit_rate == 0.66 and frozen.edge_variant == "main"
    assert (run.run_id, run.range_to, run.split_from) == ("canon", date(2026, 9, 30), FROZEN)
    assert run.as_of is not None and run.knowledge_ts is not None


def test_random_draws_never_reach_the_screener_rows_and_deciles_are_empty_when_not_stored(
    backend: MemoryBackend,
) -> None:
    deciles = {f"decile_mean_{i:02d}": 0.1 - i / 100 for i in range(1, 11)}
    draws = [
        row("random", "draw", 0.4, FROZEN, role="random", slice_value=str(i), lift=1.0 + i / 10)
        for i in range(3)
    ]
    year_row = row("momo", "year", 0.5, FROZEN, **deciles)
    write_run(backend, "canon", FROZEN, 0.66, extra=[*draws, year_row])
    ctx = stores(backend)
    edge = load_edge(ctx, "drift")
    assert edge is not None
    run = load_canonical_run(ctx, edge).run
    assert run is not None
    rows = load_run_rows(ctx, run)
    assert {r.role for r in rows} == {"screener"} and "draw" not in {r.slice_kind for r in rows}
    assert [d.lift for d in load_run_draws(ctx, run)] == [1.0, 1.1, 1.2]
    year = next(r for r in rows if r.slice_kind == "year")
    assert year.decile_means == pytest.approx([0.1 - i / 100 for i in range(1, 11)])
    assert next(r for r in rows if r.slice_kind == "all").decile_means == ()  # not stored: not 0


def test_after_session_is_set_for_a_run_committed_after_the_session(
    backend: MemoryBackend,
) -> None:
    write_run(backend, "canon", FROZEN, 0.6)  # committed 2026-10-02, after the session
    store = stores(backend)
    edge = load_edge(store, "drift")
    assert edge is not None
    run = load_canonical_run(store, edge).run
    assert run is not None and run.after_session is False  # a StoreContext has no session
    read = session_ctx(store, date(2026, 9, 30))
    run = load_canonical_run(read, edge).run
    assert run is not None and run.after_session is True
    read = session_ctx(store, date(2026, 10, 2))
    run = load_canonical_run(read, edge).run
    assert run is not None and run.after_session is False


def test_latest_is_by_commit_time_not_start_time(backend: MemoryBackend) -> None:
    write_run(backend, "long", FROZEN, 0.5, minutes=0, finished_minutes=50)  # started first
    write_run(backend, "short", FROZEN, 0.6, minutes=10, finished_minutes=20)
    ctx = stores(backend)
    edge = load_edge(ctx, "drift")
    assert edge is not None
    run = load_canonical_run(ctx, edge).run
    assert run is not None and run.run_id == "long"
