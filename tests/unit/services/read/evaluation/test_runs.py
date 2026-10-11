"""The edge runs read by run: the canonical run is the latest committed site run at the
frozen split, an exploratory or null-split run is never canonical, no such run is NOT_RUN with
the reason, and a run's rows are its own even when another run shares the partition."""

from datetime import date, timedelta

import pytest

from algotrade.services.read.evaluation.edges import load_edge, load_edges
from algotrade.services.read.evaluation.runs import (
    load_canonical_run,
    load_edge_runs,
    load_run_draws,
    load_run_rows,
    load_run_series,
)
from algotrade.services.read.values import UnknownCode
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.runs import RunStatus
from tests.unit.services.read.evaluation.conftest import (
    FROZEN,
    row,
    series_row,
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


def test_a_legacy_local_run_is_the_sites_and_says_so(backend: MemoryBackend) -> None:
    write_run(backend, "old-local", FROZEN, 0.5, owner="local")
    ctx = stores(backend)
    edge = load_edge(ctx, "drift")
    assert edge is not None
    run = load_canonical_run(ctx, edge).run
    assert run is not None and run.run_id == "old-local"
    assert (run.owner, run.legacy_owner) == ("site", "local")
    write_run(backend, "new-site", FROZEN, 0.6, minutes=5)
    assert load_canonical_run(ctx, edge).run.run_id == "new-site"  # type: ignore[union-attr]
    assert load_canonical_run(ctx, edge).run.legacy_owner is None  # type: ignore[union-attr]


def test_a_run_serves_its_trigger_and_none_for_one_from_before(backend: MemoryBackend) -> None:
    write_run(backend, "old", FROZEN, 0.5)
    write_run(backend, "new", FROZEN, 0.6, minutes=5, trigger="ui")
    ctx = stores(backend)
    edge = load_edge(ctx, "drift")
    assert edge is not None
    by_id = {r.run_id: r for r in load_edge_runs(ctx, edge)}
    assert (by_id["old"].trigger, by_id["new"].trigger) == (None, "ui")


def test_a_local_run_after_the_cutoff_is_the_users_not_the_sites(backend: MemoryBackend) -> None:
    write_run(backend, "later-local", FROZEN, 0.5, owner="local", finished_minutes=60 * 24 * 30)
    ctx = stores(backend)
    edge = load_edge(ctx, "drift")
    assert edge is not None
    assert load_canonical_run(ctx, edge).run is None  # not the site's
    assert load_edge_runs(ctx, edge) == ()  # the viewer is "me"


def test_viewer_local_sees_each_legacy_run_once_as_the_sites(backend: MemoryBackend) -> None:
    write_run(backend, "old-local", FROZEN, 0.5, owner="local")
    write_run(
        backend, "new-local", FROZEN, 0.6, owner="local", minutes=5, finished_minutes=60 * 24 * 30
    )
    ctx = stores(backend, "local")
    edge = load_edge(ctx, "drift")
    assert edge is not None
    assert [(r.run_id, r.owner) for r in load_edge_runs(ctx, edge)] == [
        ("new-local", "local"), ("old-local", "site"),
    ]  # fmt: skip


def test_a_legacy_run_at_another_split_is_not_canonical(backend: MemoryBackend) -> None:
    write_run(backend, "explore", date(2026, 3, 1), 0.5, owner="local")
    ctx = stores(backend)
    edge = load_edge(ctx, "drift")
    assert edge is not None
    assert load_canonical_run(ctx, edge).run is None


def test_a_runs_series_is_its_own_rows_in_decision_order(backend: MemoryBackend) -> None:
    days = [date(2026, 3, 2) + timedelta(days=7 * i) for i in range(4)]
    write_run(backend, "r1", FROZEN, 0.6, series=[series_row(d, FROZEN) for d in reversed(days)])
    write_run(backend, "r2", FROZEN, 0.7, minutes=10, series=[series_row(days[0], FROZEN)])
    ctx = stores(backend)
    edge = load_edge(ctx, "drift")
    assert edge is not None
    first = next(r for r in load_edge_runs(ctx, edge) if r.run_id == "r1")
    found = load_run_series(ctx, first)
    assert [r.decision_session for r in found] == days
    top = found[0]
    assert (top.variant, top.unit, top.status, top.picks, top.before_split) == (
        "momo", "excess_return", "measured", 5, True,
    )  # fmt: skip
    assert top.exit_session == days[0] + timedelta(days=29) and top.pick_mean == 0.02
    assert top.lost_table is None and top.decile_means == ()


def test_a_run_from_before_the_series_has_none(backend: MemoryBackend) -> None:
    write_run(backend, "old", FROZEN, 0.6)
    ctx = stores(backend)
    edge = load_edge(ctx, "drift")
    assert edge is not None
    (run,) = load_edge_runs(ctx, edge)
    assert load_run_series(ctx, run) == ()
