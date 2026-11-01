"""The edge runs read by run: the canonical run is the latest committed site run at the
frozen split, an exploratory or null-split run is never canonical, no such run is NOT_RUN with
the reason, and a run's rows are its own even when another run shares the partition."""

from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from typing import Any

import pytest

from algotrade.config.user import UserContext
from algotrade.core.time.calendar import is_session
from algotrade.quant.edges.statistics import window_weights
from algotrade.services.read.context import ResultCache, open_stores, run_partition
from algotrade.services.read.evaluation import edges as edges_module
from algotrade.services.read.evaluation import runs as runs_module
from algotrade.services.read.evaluation.edges import load_edge, load_edges
from algotrade.services.read.evaluation.runs import (
    Draw,
    _committed,
    _row,
    draws_of_record,
    load_canonical_run,
    load_edge_runs,
    load_run_draws,
    load_run_rows,
    load_run_series,
    load_site_trials,
    measured_sessions,
    rows_of_frame,
    rows_of_record,
    run_of_record,
)
from algotrade.services.read.evaluation.verdict import load_edge_verdict
from algotrade.services.read.values import UnknownCode
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import MemoryConfigStore
from algotrade.storage.runs import RunStatus
from algotrade.storage.tables.readers import StoreReader
from algotrade.storage.tables.schemas import result_table
from tests.unit.services.read.evaluation.conftest import (
    DOCS,
    EDGE,
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


def _all_row_with_projection(**changes: object) -> dict[str, object]:
    exits = [date(2026, 11, 2) + timedelta(days=i) for i in range(3)]
    return row(
        "momo", "all", 0.3, FROZEN, horizon_sessions=15, projected_exits=exits,
        decisions_scheduled=10, decisions_measured=8, decisions_scheduled_oos=4,
        decisions_measured_oos=3, **changes,
    )  # fmt: skip


def test_the_all_row_serves_the_projected_exits_and_the_decision_session_counts(
    backend: MemoryBackend,
) -> None:
    write_run(backend, "r1", FROZEN, 0.6, extra=[_all_row_with_projection()])
    ctx = stores(backend)
    edge = load_edge(ctx, "drift")
    assert edge is not None
    run = load_canonical_run(ctx, edge).run
    assert run is not None
    (found,) = [r for r in load_run_rows(ctx, run) if r.projected_exits]
    assert found.projected_exits == tuple(date(2026, 11, 2) + timedelta(days=i) for i in range(3))
    assert (found.decisions_scheduled, found.decisions_measured) == (10, 8)
    assert (found.decisions_scheduled_oos, found.decisions_measured_oos) == (4, 3)
    plain = [r for r in load_run_rows(ctx, run) if r.slice_kind == "frozen"]
    assert plain[0].projected_exits == () and plain[0].decisions_scheduled is None  # never zero


def test_a_hidden_run_withholds_the_out_of_sample_counts_and_the_exits(
    backend: MemoryBackend,
) -> None:
    mine = _all_row_with_projection(slice_kind="in_sample", user_id="me")
    write_run(backend, "c1", FROZEN, 0.6, owner="me", extra=[mine])
    ctx = stores(backend)
    edge = load_edge(ctx, "drift")
    assert edge is not None
    run = next(r for r in load_edge_runs(ctx, edge) if r.owner == "me")
    hidden = type(run)(**{**run.__dict__, "oos_hidden": True})
    for served in load_run_rows(ctx, hidden):
        assert served.slice_kind == "in_sample"
        assert served.projected_exits == () and served.decisions_scheduled_oos is None
        assert served.decisions_measured_oos is None


def test_measured_sessions_count_the_basis_windows_with_picks(backend: MemoryBackend) -> None:
    days = [date(2026, 1, 2) + timedelta(days=30 * i) for i in range(4)]  # 20+ sessions apart
    stored = [
        series_row(days[0], FROZEN),
        series_row(days[1], FROZEN, status="excluded_coverage", picks=None, pick_mean=None),
        series_row(days[2], FROZEN, status="no_picks", picks=None, pick_mean=None),
        series_row(days[3], FROZEN, picks=0),
        series_row(days[3], FROZEN, role="baseline", variant="spy"),
    ]
    write_run(backend, "r1", FROZEN, 0.6, series=stored)
    ctx = stores(backend)
    edge = load_edge(ctx, "drift")
    assert edge is not None
    run = load_canonical_run(ctx, edge).run
    assert run is not None
    assert measured_sessions(load_run_series(ctx, run)) == {("momo", 20): 1}


def test_window_weights_are_a_tranche_portfolio_share() -> None:
    days = [date(2026, 3, 2), date(2026, 3, 3), date(2026, 3, 4), date(2026, 4, 20)]
    w = window_weights(days, 20)
    assert [w[d] for d in days[:3]] == [1 / 20, 1 / 20, 1 / 20]  # the first takes the next's gap
    assert w[days[3]] == 1.0  # 33 sessions after the previous: no overlap
    assert window_weights(days[:1], 20) == {days[0]: 1.0}


def test_overlapping_sessions_are_not_independent_for_the_haircut(backend: MemoryBackend) -> None:
    days = [d for d in (date(2026, 1, 5) + timedelta(days=i) for i in range(60)) if is_session(d)]
    write_run(backend, "r1", FROZEN, 0.6, series=[series_row(d, FROZEN) for d in days])
    ctx = stores(backend)
    edge = load_edge(ctx, "drift")
    assert edge is not None
    run = load_canonical_run(ctx, edge).run
    assert run is not None
    found = measured_sessions(load_run_series(ctx, run))
    assert found == {("momo", 20): round(len(days) / 20)}  # about two, not forty


def test_the_touch_and_reference_rates_are_read_and_none_when_not_stored_never_zero(
    backend: MemoryBackend,
) -> None:
    extra = [row("momo", "in_sample", 0.5, FROZEN, reference_rate=0.63, touch_rate=0.54)]
    write_run(backend, "r1", FROZEN, 0.6, extra=extra)
    ctx = stores(backend)
    edge = load_edge(ctx, "drift")
    assert edge is not None
    run = load_canonical_run(ctx, edge).run
    assert run is not None
    by = {r.slice_kind: r for r in load_run_rows(ctx, run) if r.variant == "momo"}
    assert (by["in_sample"].reference_rate, by["in_sample"].touch_rate) == (0.63, 0.54)
    assert by["frozen"].reference_rate is None and by["frozen"].touch_rate is None


def _site_docs(**second: object) -> dict[tuple[str, str, str], dict]:
    """The store's documents with a second site edge ``other`` beside ``drift``."""
    return {**DOCS, ("site", "edges", "other"): {**EDGE, "id": "other", "name": "Other", **second}}


def test_the_site_trial_count_sums_the_canonical_runs_of_every_site_edge(
    backend: MemoryBackend,
) -> None:
    docs = _site_docs()
    assert load_site_trials(stores(backend, docs=docs)) == 0  # no run yet: nothing was tried
    write_run(backend, "explore", date(2026, 3, 1), 0.9, minutes=5, trials_counted=50)
    assert load_site_trials(stores(backend, docs=docs)) == 0  # exploratory: not canonical
    write_run(backend, "d1", FROZEN, 0.6, minutes=10, trials_counted=7)
    assert load_site_trials(stores(backend, docs=docs)) == 7
    write_run(backend, "o1", FROZEN, 0.6, minutes=11, edge="other", trials_counted=5)
    assert load_site_trials(stores(backend, docs=docs)) == 12  # more than one edge
    write_run(backend, "d2", FROZEN, 0.6, minutes=20, trials_counted=9)  # the latest is canonical
    assert load_site_trials(stores(backend, docs=docs)) == 14


def test_a_rejected_or_blocked_edges_trials_still_count(backend: MemoryBackend) -> None:
    """A trial stays a trial once the idea is dropped (architect review of H1)."""
    docs = _site_docs(status="rejected", rejection_reason="Costs eat it.")
    write_run(backend, "d1", FROZEN, 0.6, minutes=10, trials_counted=7)
    write_run(backend, "o1", FROZEN, 0.6, minutes=11, edge="other", trials_counted=5)
    assert load_site_trials(stores(backend, docs=docs)) == 12


def test_the_site_trial_count_recounts_when_a_site_edge_document_changes(
    backend: MemoryBackend,
) -> None:
    """One cache serves every request: its key moves with the site edges' status and period."""
    write_run(backend, "d1", FROZEN, 0.6, minutes=10, trials_counted=7)
    write_run(backend, "o1", FROZEN, 0.6, minutes=11, edge="other", trials_counted=5)
    cache = ResultCache()
    assert load_site_trials(stores(backend, cache=cache)) == 7  # no ``other`` document yet
    added = stores(backend, docs=_site_docs(), cache=cache)  # the same store and published state
    assert load_site_trials(added) == 12
    closed = _site_docs(status="blocked", rejection_reason="No data.")
    assert load_site_trials(stores(backend, docs=closed, cache=cache)) == 12  # still counted


def test_a_row_serves_its_side_and_one_from_before_sides_is_long() -> None:
    base = row("momo", "all", 0.6, None)
    assert _row(base).side == "long"  # no column: a run from before sides
    assert _row({**base, "side": float("nan")}).side == "long"  # a null in a frame is NaN
    assert _row({**base, "side": "short"}).side == "short"


def _mixed_run(backend: MemoryBackend) -> Any:
    """A run with random draws, screener frozen rows, an exploratory row and an in-sample row."""
    draws = [
        row("random", "draw", 0.4, FROZEN, role="random", slice_value=str(i)) for i in range(5)
    ]
    extra = [
        *draws,
        row("momo", "frozen", 0.3, FROZEN, exploratory=True, slice_value="x"),
        row("momo", "in_sample", 0.2, FROZEN, in_sample=True),
        row("momo", "year", 0.5, FROZEN),
    ]
    write_run(backend, "canon", FROZEN, 0.66, extra=extra)
    ctx = stores(backend)
    edge = load_edge(ctx, "drift")
    assert edge is not None
    run = load_canonical_run(ctx, edge).run
    assert run is not None
    record = ctx.reader.run(run.run_id)
    assert record is not None
    return ctx, record


def _decoded_after_filtering(ctx: Any, record: Any) -> list[Any]:
    """The decode of the whole partition, filtered afterwards (what the reader did before)."""
    frame = runs_module.run_partition(ctx, runs_module.result_table(runs_module.EDGE_EVAL), record)
    assert frame is not None
    return [runs_module._row({str(k): v for k, v in r.items()}) for r in frame.to_dict("records")]


def _as_draws(rows: Any) -> tuple[Draw, ...]:
    return tuple(Draw(r.edge_variant, r.variant, r.horizon_sessions, r.lift) for r in rows)


def test_draws_built_from_columns_equal_the_decoded_rows_with_nulls_and_a_restated_run(
    backend: MemoryBackend,
) -> None:
    nan, none = float("nan"), None
    lifts = [1.0, nan, 1.3, none, 0.7, 2.0]
    draws = [
        row(
            f"random:{'momo' if i % 2 else 'other'}",
            "draw",
            0.4,
            FROZEN,
            role="random",
            slice_value=str(i),
            lift=x,
            horizon_sessions=1 + i % 3,
        )
        for i, x in enumerate(lifts)
    ]
    write_run(backend, "first", FROZEN, 0.66, minutes=10, extra=draws)
    write_run(
        backend, "canon", FROZEN, 0.66, minutes=20, extra=[{**d, "lift": 9.0} for d in draws[:4]]
    )  # restated
    ctx = stores(backend)
    for run_id in ("first", "canon"):
        record = ctx.reader.run(run_id)
        assert record is not None
        old = _decoded_after_filtering(ctx, record)
        got = draws_of_record(ctx, record)
        assert got == _as_draws(r for r in old if r.role == "random")
        assert all(d.lift is None or isinstance(d.lift, float) for d in got)
        assert [d.lift for d in got if d.lift is not None] == [
            r.lift for r in old if r.role == "random" and r.lift is not None
        ]
    wanted = [d.lift for d in draws_of_record(ctx, ctx.reader.run("first"))]
    assert wanted.count(None) == 2  # NaN and None both read as no lift


def test_filtering_the_frame_before_decoding_serves_the_same_rows_as_after(
    backend: MemoryBackend,
) -> None:
    ctx, record = _mixed_run(backend)
    everything = _decoded_after_filtering(ctx, record)
    assert rows_of_record(ctx, record) == tuple(r for r in everything if r.role != "random")
    assert draws_of_record(ctx, record) == _as_draws(r for r in everything if r.role == "random")
    assert len(draws_of_record(ctx, record)) == 5
    frozen = rows_of_record(ctx, record, ("frozen",))
    assert frozen == tuple(r for r in everything if r.role != "random" and r.slice_kind == "frozen")
    assert {r.exploratory for r in frozen} == {False, True}  # the caller still drops these


def test_random_rows_are_never_converted_to_edge_rows_for_the_screener_rows(
    backend: MemoryBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx, record = _mixed_run(backend)
    total = len(_decoded_after_filtering(ctx, record))
    seen: list[str] = []
    real = runs_module._row

    def counting(r: Any) -> Any:
        seen.append(str(r["role"]))
        return real(r)

    monkeypatch.setattr(runs_module, "_row", counting)
    rows_of_record(ctx, record)
    assert seen and "random" not in seen
    seen.clear()
    rows_of_record(ctx, record, ("frozen",))
    assert seen and len(seen) < total - 5
    seen.clear()
    draws_of_record(ctx, record)
    assert seen == []  # draws are cut from the columns: no EdgeRow is built for one


# the run records behind an edge page are decoded once per run-record generation
MEMO_EDGES = 6
IDS = [f"e{i}" for i in range(MEMO_EDGES)]


def _docs() -> dict[tuple[str, str, str], dict]:
    return {
        **DOCS,
        **{("site", "edges", i): {**EDGE, "id": i, "name": i.upper()} for i in IDS},
    }


def _filled(backend: MemoryBackend) -> None:
    for k, edge in enumerate(["drift", *IDS]):
        write_run(backend, f"a{k}", FROZEN, 0.6, minutes=k, edge=edge, trials_counted=3 + k)
        write_run(backend, f"b{k}", FROZEN, 0.5, minutes=40 + k, edge=edge, trials_counted=4 + k)


def _calls(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    seen: list[str] = []
    real = runs_module._read_committed

    def spy(ctx: Any, edge: Any, owner: str) -> Any:
        seen.append(f"{edge.id}:{owner}")
        return real(ctx, edge, owner)

    monkeypatch.setattr(runs_module, "_read_committed", spy)
    return seen


def test_a_page_of_edges_decodes_each_edges_records_once_however_many_fields_ask(
    backend: MemoryBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    _filled(backend)
    ctx = session_ctx(stores(backend, docs=_docs()), date(2026, 10, 1))
    seen = _calls(monkeypatch)
    edges = load_edges(ctx)
    assert len(edges) == MEMO_EDGES + 1
    for _ in range(5):  # five resolvers per edge, each judging and counting the site's trials
        for edge in edges:
            load_edge_verdict(ctx, edge)
            load_edge_runs(ctx, edge)
    assert len(seen) == len(set(seen)) <= 2 * len(edges)  # O(edges), not O(edges x resolvers)
    assert len(ctx.cache._items) <= 2  # the shared cache is not flooded by a page of edges


def test_the_cached_runs_and_verdicts_equal_the_uncached_ones(
    backend: MemoryBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    _filled(backend)
    ctx = session_ctx(stores(backend, docs=_docs()), date(2026, 10, 1))
    edges = load_edges(ctx)

    def answers(c: Any) -> list[Any]:
        return [
            (load_edge_runs(c, e), load_canonical_run(c, e), load_edge_verdict(c, e)) for e in edges
        ] + [load_site_trials(c)]

    first, again = answers(ctx), answers(ctx)  # the second round is all hits
    monkeypatch.setattr(runs_module, "_committed", runs_module._read_committed)
    plain = answers(session_ctx(stores(backend, docs=_docs()), date(2026, 10, 1)))
    assert first == again == plain
    assert plain[-1] == sum(
        4 + k for k in range(MEMO_EDGES + 1)
    )  # the newest canonical run's count


def test_a_run_saved_since_is_seen_by_the_next_read_not_an_older_entry(
    backend: MemoryBackend,
) -> None:
    write_run(backend, "r1", FROZEN, 0.6, minutes=1, trials_counted=2)
    cache = ResultCache()
    ctx = session_ctx(stores(backend, cache=cache), date(2026, 10, 1))
    (edge,) = load_edges(ctx)
    assert [r.run_id for r in _committed(ctx, edge, "site")] == ["r1"]
    write_run(backend, "r2", FROZEN, 0.6, minutes=9, trials_counted=8)
    fresh = session_ctx(stores(backend, cache=cache), date(2026, 10, 1))  # a later request
    assert [r.run_id for r in _committed(fresh, edge, "site")] == ["r2", "r1"]
    assert load_site_trials(fresh) == 8


def test_a_snapshot_reader_is_never_cached(
    backend: MemoryBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_run(backend, "r1", FROZEN, 0.6, minutes=1)
    cache = ResultCache()
    base = stores(backend, cache=cache)
    frozen = StoreReader(backend).with_runs_frozen(["edge-eval:drift:site"])
    ctx = session_ctx(base, date(2026, 10, 1))
    ctx = type(ctx)(frozen, ctx.configs, ctx.user, ctx.session, ctx.features, cache)
    (edge,) = load_edges(ctx)
    seen = _calls(monkeypatch)
    _committed(ctx, edge, "site")
    _committed(ctx, edge, "site")
    assert len(seen) == 2


def test_the_site_trial_count_is_taken_once_per_request(
    backend: MemoryBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    _filled(backend)
    ctx = session_ctx(stores(backend, docs=_docs()), date(2026, 10, 1))
    taken: list[int] = []
    real = runs_module._site_trials
    monkeypatch.setattr(runs_module, "_site_trials", lambda c: taken.append(1) or real(c))
    for _ in range(50):
        load_site_trials(ctx)
    assert len(taken) == 1


# The page's resolvers share one ``StoreContext`` (``RequestContext.stores()``: no session, so no
# ``ReadContext``): the once-per-request reads must hold there, and from threads side by side.


def _spy_parses(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    seen: list[str] = []
    real = edges_module.loading.load_edges

    def spy(configs: Any, user: str = "site", catalog: Any = None) -> Any:
        seen.append(user)
        return real(configs, user, catalog)

    monkeypatch.setattr(edges_module.loading, "load_edges", spy)
    return seen


def test_a_page_of_80_verdicts_on_the_stores_context_counts_site_trials_once(
    backend: MemoryBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    _filled(backend)
    ctx = stores(backend, docs=_docs())
    taken: list[int] = []
    real = runs_module._site_trials
    monkeypatch.setattr(runs_module, "_site_trials", lambda c: taken.append(1) or real(c))
    edges = load_edges(ctx)

    def verdict(edge: Any) -> Any:  # a judged edge with a Sharpe asks for the count
        return load_edge_verdict(ctx, edge), load_site_trials(ctx)

    with ThreadPoolExecutor(6) as pool:  # the read pool's side-by-side resolvers
        list(pool.map(verdict, [e for _ in range(12) for e in edges]))
    assert len(taken) == 1
    assert len(ctx.cache._items) <= 2  # one entry for the count, not one per resolver


def test_the_edge_documents_are_parsed_once_per_request_and_generation(
    backend: MemoryBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    _filled(backend)
    ctx = stores(backend, docs=_docs())
    seen = _spy_parses(monkeypatch)
    for _ in range(20):
        for edge in load_edges(ctx):
            load_edge_verdict(ctx, edge)
            load_site_trials(ctx)
    assert sorted(seen) == ["me", "site"]  # the viewer's own list, the site's for the count
    assert load_edges(stores(backend, docs=_docs())) == load_edges(ctx)  # a request: its own memo
    assert len(seen) == 3


def test_a_config_write_or_a_new_run_is_seen_by_the_same_context_keys(
    backend: MemoryBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    _filled(backend)
    store = MemoryConfigStore(_docs())
    ctx = open_stores(StoreReader(backend), store, UserContext("me"))
    seen = _spy_parses(monkeypatch)
    load_edges(ctx)
    store.generation = lambda user: 2  # type: ignore[method-assign]  # a finished write
    load_edges(ctx)
    assert seen.count("me") == 2  # a new generation re-parses: no stale edge after an edit
    store.generation = lambda user: 3  # type: ignore[method-assign]  # a write in flight
    load_edges(ctx)
    load_edges(ctx)
    assert seen.count("me") == 4  # an odd generation is never memoised
    before = load_site_trials(ctx)
    write_run(backend, "late", FROZEN, 0.6, minutes=99, edge="e0", trials_counted=50)
    assert load_site_trials(ctx) == before + 50 - 4 - 1  # e0's canonical run is the new one


def test_the_memoised_page_equals_one_read_without_sharing(backend: MemoryBackend) -> None:
    _filled(backend)
    shared = stores(backend, docs=_docs())

    def page(ctx_of: Any) -> list[Any]:
        return [
            (e, load_edge_verdict(ctx_of(), e), load_site_trials(ctx_of()))
            for e in load_edges(ctx_of())
        ]

    assert page(lambda: shared) == page(lambda: stores(backend, docs=_docs()))


def test_rows_of_frame_parses_a_frame_as_the_reader_reads_it_back(backend: MemoryBackend) -> None:
    """The writer judges the frame it is publishing: the same rows and draws the reader decodes
    from the committed partition (licence included)."""
    ctx, record = _mixed_run(backend)
    frame = run_partition(ctx, result_table("edge_eval"), record)
    assert frame is not None
    rows, drawn = rows_of_frame(frame)
    assert rows == rows_of_record(ctx, record)
    assert drawn == draws_of_record(ctx, record) and len(drawn) == 5


def test_a_rows_licence_is_read_and_a_null_is_none(backend: MemoryBackend) -> None:
    write_run(
        backend, "canon", FROZEN, 0.66, extra=[row("momo", "year", 0.5, FROZEN, licence="personal")]
    )
    ctx = stores(backend)
    record = ctx.reader.run("canon")
    assert record is not None
    licences = {(r.slice_kind, r.licence) for r in rows_of_record(ctx, record)}
    assert ("year", "personal") in licences and ("all", None) in licences


def test_run_of_record_is_the_run_the_reader_builds_without_a_store_read(
    backend: MemoryBackend,
) -> None:
    write_run(backend, "canon", FROZEN, 0.66, trigger="nightly")
    ctx = stores(backend)
    edge = load_edge(ctx, "drift")
    record = ctx.reader.run("canon")
    assert edge is not None and record is not None
    built = run_of_record(record, edge, "site")
    assert built == load_canonical_run(ctx, edge).run
    assert built.trigger == "nightly" and built.after_session is False


class _Committed:
    """A committed run as ``load_canonical_run`` filters it."""

    def __init__(self, run_id: str, after_session: bool) -> None:
        self.run_id, self.exploratory, self.after_session = run_id, False, after_session


def test_bounded_canonical_run_skips_a_run_committed_after_the_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ADR 0083 decision 2 (point in time): bounded, the newest run is skipped for the older one;
    with only newer runs there is none."""
    edge: Any = type("E", (), {"id": "e1", "frozen_from": date(2026, 1, 1)})()
    found = [_Committed("new", True), _Committed("old", False)]
    monkeypatch.setattr(runs_module, "_committed", lambda ctx, e, owner: found)
    assert runs_module.load_canonical_run(None, edge).run.run_id == "new"  # type: ignore[arg-type, union-attr]
    assert runs_module.load_canonical_run(None, edge, bounded=True).run.run_id == "old"  # type: ignore[arg-type, union-attr]
    found[:] = [_Committed("new", True)]
    only_newer = runs_module.load_canonical_run(None, edge, bounded=True)  # type: ignore[arg-type]
    assert only_newer.run is None and only_newer.not_run is not None
