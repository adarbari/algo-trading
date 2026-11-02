"""The ``edge-verdicts`` task (ADR 0053 amendment 2026-10-22): the backfill and the re-judge in one,
resumable and idempotent by the store, one publish per run, one edge's failure counted and never
stopping the rest, and the row it stores equal to what the live judge answers."""

import itertools
from dataclasses import replace
from datetime import timedelta
from typing import Any

import pandas as pd
import pytest

from algotrade.config.edges.document import parse_edge
from algotrade.config.site.settings import load_verdict
from algotrade.config.user import UserContext
from algotrade.core.model.errors import ConfigurationError
from algotrade.services.evaluation.cross_section.detail import verdict as framer
from algotrade.services.evaluation.cross_section.harness import evaluate_edge
from algotrade.services.evaluation.cross_section.results import write_edge_eval
from algotrade.services.read.context import StoreContext, open_stores
from algotrade.services.read.evaluation import edges, runs
from algotrade.services.read.evaluation.verdict import fingerprint as stamp
from algotrade.services.read.evaluation.verdict import load_edge_summary
from algotrade.services.read.evaluation.verdict.model import EdgeSummary
from algotrade.storage.configs.files import MemoryConfigStore
from algotrade.storage.runs import RunStatus
from algotrade_ingestion.tasks.edges import verdicts as task
from algotrade_ingestion.tasks.framework import entries_ops
from algotrade_ingestion.workflows.nightly.nightly import skip_reason
from tests.helpers.ingest_fakes import task_ctx
from tests.unit.services.evaluation.cross_section.conftest import (
    ACTIVE,
    AS_OF,
    DAYS,
    World,
    edge_document,
    screen,
    world,  # noqa: F401  (the fixture)
)

SPLIT = DAYS[4]
NOW = AS_OF.replace(hour=12)
TABLE = "results/edge_verdict"
CLOCK = (NOW.replace(hour=20) + timedelta(minutes=i) for i in itertools.count())


def configs(
    extra: dict[tuple[str, str, str], Any] | None = None, **changes: Any
) -> MemoryConfigStore:
    """The site's documents: two edges (``changes`` edit ``drift``), ``extra`` more documents."""
    docs: dict[tuple[str, str, str], Any] = {
        ("site", "selections", "active"): ACTIVE,
        ("site", "strategies", "momo"): screen(),
        ("site", "edges", "drift"): edge_document(frozen_from=SPLIT.isoformat(), **changes),
        ("site", "edges", "second"): edge_document(
            id="second", name="Second", frozen_from=SPLIT.isoformat()
        ),
    }
    return MemoryConfigStore({**docs, **(extra or {})})


def stores(w: World, cfg: MemoryConfigStore) -> StoreContext:
    return open_stores(w.reader, cfg, UserContext("site"))


def document(cfg: MemoryConfigStore, edge_id: str) -> Any:
    return parse_edge(cfg.load("site", "edges", edge_id) or {}, edge_id, f"{edge_id}.toml")


def evaluate(w: World, cfg: MemoryConfigStore, edge_id: str, publish_verdict: bool = False) -> None:
    """Evaluate and publish one edge as the nightly does (``publish_verdict``: with its row)."""
    ctx = stores(w, cfg)
    found = document(cfg, edge_id)
    ev = evaluate_edge(
        w.reader, w.results, cfg, UserContext("site"), found, DAYS[0], DAYS[-1], AS_OF,
    )  # fmt: skip
    write_edge_eval(w.results, ev, NOW, stores=ctx if publish_verdict else None)


def run(w: World, cfg: MemoryConfigStore, **params: Any):  # type: ignore[no-untyped-def]
    """One task run, a minute after the last (a run id names its start: runs never collide)."""
    tick = next(CLOCK)
    ctx = replace(task_ctx(w.writer, w.reader, clock=lambda: tick), configs=cfg)
    edge_id = params.pop("edge_id", None)
    return task.rejudge_edges(ctx, task.Options(**params), edge_id)


def rows(w: World) -> pd.DataFrame:
    found = w.reader.table(TABLE, DAYS[-1])
    return pd.DataFrame() if found is None else found


@pytest.fixture
def evaluated(world: World) -> World:  # noqa: F811
    """Both edges evaluated before the table existed: no verdict rows yet."""
    for edge_id in ("drift", "second"):
        evaluate(world, configs(), edge_id)
    return world


def test_the_first_run_backfills_every_site_edge_with_a_canonical_run(evaluated: World) -> None:
    record = run(evaluated, configs())
    assert record.status is RunStatus.COMPLETE
    assert record.stats["written"] == 2 and record.stats["edges"] == 2
    found = rows(evaluated)
    assert sorted(found["edge_id"]) == ["drift", "second"]
    assert set(found["source"]) == {"edge-verdicts"} and set(found["run_id"]) == {record.run_id}
    assert set(found["user_id"]) == {"site"}
    assert (found["knowledge_ts"] > pd.Timestamp(NOW)).all()  # the write instant, never the run's


def test_a_second_run_is_idempotent_and_writes_nothing(evaluated: World) -> None:
    run(evaluated, configs())
    before = rows(evaluated)
    record = run(evaluated, configs())
    assert record.stats["written"] == 0 and record.stats["skipped"] == 2
    assert record.status is RunStatus.COMPLETE
    pd.testing.assert_frame_equal(rows(evaluated), before)


def test_an_edge_whose_edge_eval_publish_wrote_its_row_is_skipped(world: World) -> None:  # noqa: F811
    cfg = configs()
    evaluate(world, cfg, "drift", publish_verdict=True)
    assert len(rows(world)) == 1
    record = run(world, cfg, edge_id="drift")
    assert record.stats["skipped"] == 1 and record.stats["written"] == 0
    assert len(rows(world)) == 1  # the publish's row is the current one


def test_a_changed_verdict_setting_rejudges_every_edge(evaluated: World) -> None:
    run(evaluated, configs())
    changed = configs({("site", "settings", "verdict"): {"min_oos_trades": 7}})
    record = run(evaluated, changed)
    assert record.stats["written"] == 2 and record.stats["skipped"] == 0
    found = rows(evaluated)
    assert len(found) == 4 and found.groupby("edge_id")["fingerprint"].nunique().eq(2).all()
    assert set(found["settings_hash"]) and found["settings_hash"].nunique() == 2


def test_a_changed_edge_document_rejudges_only_that_edge(evaluated: World) -> None:
    run(evaluated, configs())
    record = run(evaluated, configs(implementation={"promoted": "momo"}))
    assert record.stats["written"] == 1 and record.stats["skipped"] == 1
    assert (rows(evaluated)["edge_id"] == "drift").sum() == 2


def test_a_changed_judge_version_rejudges(
    evaluated: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    run(evaluated, configs())
    monkeypatch.setattr(stamp, "JUDGE_VERSION", stamp.JUDGE_VERSION + 1)
    record = run(evaluated, configs())
    assert record.stats["written"] == 2


def test_limit_caps_the_rows_and_the_next_run_finishes_the_rest(evaluated: World) -> None:
    first = run(evaluated, configs(), limit=1)
    assert first.stats["written"] == 1 and first.stats["not_reached"] == 1
    assert first.status is RunStatus.PARTIAL and len(rows(evaluated)) == 1
    second = run(evaluated, configs(), limit=1)
    assert second.stats["written"] == 1 and second.stats["skipped"] == 1
    assert second.status is RunStatus.COMPLETE and len(rows(evaluated)) == 2


def test_one_edges_failure_is_counted_and_the_rest_are_written(
    evaluated: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = framer.rejudged_frame

    def flaky(ctx: Any, edge: Any, found: Any, **kw: Any) -> Any:
        if edge.id == "drift":
            raise ValueError("the judge broke on this one")
        return real(ctx, edge, found, **kw)

    monkeypatch.setattr(framer, "rejudged_frame", flaky)
    record = run(evaluated, configs())
    assert record.status is RunStatus.PARTIAL
    assert record.stats["failed"] == 1 and record.stats["written"] == 1
    assert "drift: ValueError" in record.stats["failures"][0]
    assert list(rows(evaluated)["edge_id"]) == ["second"]
    monkeypatch.setattr(framer, "rejudged_frame", real)  # fixed: the next run finishes it
    again = run(evaluated, configs())
    assert again.stats["written"] == 1 and again.stats["skipped"] == 1


def test_a_failure_while_publishing_writes_no_row_at_all(
    evaluated: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    def crash(*_: object, **__: object) -> None:
        raise RuntimeError("disk full")

    monkeypatch.setattr(evaluated.writer, "commit_run", crash)
    with pytest.raises(RuntimeError):
        run(evaluated, configs())
    assert rows(evaluated).empty  # pending rows were never visible


def test_the_stored_row_equals_the_live_judge(evaluated: World) -> None:
    cfg = configs({("site", "settings", "verdict"): {"min_oos_trades": 7}})
    run(evaluated, cfg)
    ctx = stores(evaluated, cfg)
    stored = framer.stored_summaries(ctx, DAYS[-1])
    assert len(stored) == 2
    for (edge_id, _, _), summary in stored.items():
        found = edges.load_edge(ctx, edge_id)
        assert found is not None and summary == load_edge_summary(ctx, found)


def test_verify_lists_a_row_that_differs_from_the_live_judge_and_never_rewrites_it(
    evaluated: World,
) -> None:
    cfg = configs()
    ctx = stores(evaluated, cfg)
    found = edges.load_edge(ctx, "drift")
    assert found is not None
    canonical = runs.load_canonical_run(ctx, found).run
    assert canonical is not None
    lie = EdgeSummary("drift", "works", "A lie", None, 1, 1, 9.0, 9.0)
    frame = framer.verdict_frame(
        lie, canonical, fingerprint=framer.run_fingerprint(ctx, found, canonical),
        settings=load_verdict(cfg), licence=None, run_id="x", source="test", now=NOW,
    )  # fmt: skip
    evaluated.results.write_result("edge_verdict", DAYS[-1], "x", frame)
    plain = run(evaluated, cfg, edge_id="drift")
    assert plain.stats["skipped"] == 1 and plain.stats["mismatch_count"] == 0  # not checked
    checked = run(evaluated, cfg, edge_id="drift", verify=True)
    assert checked.stats["mismatch_count"] == 1 and "drift" in checked.stats["mismatches"][0]
    assert checked.stats["written"] == 0 and checked.status is RunStatus.PARTIAL
    assert list(rows(evaluated)["result"]) == ["A lie"]  # reported, never overwritten


def test_dry_run_counts_and_writes_nothing(evaluated: World) -> None:
    record = run(evaluated, configs(), dry_run=True)
    assert record.stats["would_write"] == 2 and record.stats["written"] == 0
    assert rows(evaluated).empty


def test_an_exploratory_run_and_an_edge_without_a_run_get_no_row(world: World) -> None:  # noqa: F811
    cfg = configs()
    ev = evaluate_edge(
        world.reader, world.results, cfg, UserContext("site"), document(cfg, "drift"),
        DAYS[0], DAYS[-1], AS_OF, split_from=DAYS[2],
    )  # fmt: skip
    write_edge_eval(world.results, ev, NOW)  # exploratory: not the frozen period
    record = run(world, cfg)
    assert record.stats["none"] == 2 and record.stats["written"] == 0 and rows(world).empty


def test_the_window_filters_on_the_runs_range_end(evaluated: World) -> None:
    out = run(evaluated, configs(), start=DAYS[-1] + pd.Timedelta(days=1).to_pytimedelta())
    assert out.stats["outside_window"] == 2 and out.stats["written"] == 0
    inside = run(evaluated, configs(), start=DAYS[0], end=DAYS[-1])
    assert inside.stats["written"] == 2


def test_an_unknown_edge_is_a_configuration_error(evaluated: World) -> None:
    with pytest.raises(ConfigurationError):
        run(evaluated, configs(), edge_id="nope")


def test_the_task_needs_the_config_store(evaluated: World) -> None:
    with pytest.raises(ConfigurationError):
        task.rejudge_edges(task_ctx(evaluated.writer, evaluated.reader))


def test_date_is_a_window_but_the_post_session_steps_session_is_not(evaluated: World) -> None:
    ctx = replace(task_ctx(evaluated.writer, evaluated.reader, clock=lambda: next(CLOCK)),
                  configs=configs())  # fmt: skip
    other = DAYS[0]  # the runs end on DAYS[-1]
    assert entries_ops.run_edge_verdicts(ctx, {"session": other}).stats["outside_window"] == 2
    stepped = entries_ops.run_edge_verdicts(ctx, {"session": other, "all_edges": True})
    assert stepped.stats["written"] == 2  # every edge, whatever session the step runs for


def test_without_a_config_store_a_workflow_skips_the_task_saying_so(evaluated: World) -> None:
    bare = task_ctx(evaluated.writer, evaluated.reader)
    assert "no config store" in (skip_reason("edge-verdicts", bare) or "")
    assert skip_reason("edge-verdicts", replace(bare, configs=configs())) is None


def test_each_row_is_stamped_when_its_edge_is_judged_not_when_the_task_started(
    evaluated: World,
) -> None:
    ticks = itertools.count()
    start = NOW.replace(hour=20)
    clock = lambda: start + timedelta(minutes=next(ticks))  # noqa: E731
    ctx = replace(task_ctx(evaluated.writer, evaluated.reader, clock=clock), configs=configs())
    task.rejudge_edges(ctx)
    stamps = sorted(rows(evaluated)["knowledge_ts"])
    assert stamps[0] > pd.Timestamp(start) and stamps[0] < stamps[1]


def test_every_edge_failing_fails_the_run(
    evaluated: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(*_: object, **__: object) -> None:
        raise ValueError("broken judge")

    monkeypatch.setattr(framer, "rejudged_frame", broken)
    record = run(evaluated, configs())
    assert record.status is RunStatus.FAILED and record.stats["failed"] == 2
    assert rows(evaluated).empty


def test_verify_is_read_only_even_for_a_missing_row(evaluated: World) -> None:
    record = run(evaluated, configs(), verify=True)
    assert record.stats["written"] == 0 and record.stats["would_write"] == 2
    assert rows(evaluated).empty


# ---- --expect-same-headlines (ADR 0088 design 2.6, risk 16: the deploy of a judge change) ----


def tuned(**tails: Any) -> MemoryConfigStore:
    """A settings change that moves the fingerprint and no label: a ``[tails_verdict]`` tune."""
    return configs({("site", "settings", "verdict"): {"tails_verdict": tails}})


def lying() -> MemoryConfigStore:
    """A settings change that moves the result line: no run has 10,000 out-of-sample trades."""
    return configs({("site", "settings", "verdict"): {"min_oos_trades": 10_000}})


def test_an_equal_prior_passes_and_the_new_rows_are_written(evaluated: World) -> None:
    run(evaluated, configs())
    record = run(evaluated, tuned(bootstrap_draws=3000), expect_same=True)
    assert record.status is RunStatus.COMPLETE
    assert (record.stats["compared"], record.stats["written"]) == (2, 2)
    assert record.stats["changed_count"] == 0 and record.stats["no_prior"] == 0
    assert len(rows(evaluated)) == 4 and rows(evaluated).groupby("edge_id").size().eq(2).all()


def test_a_differing_prior_fails_the_run_and_writes_nothing(evaluated: World) -> None:
    run(evaluated, configs())
    before = rows(evaluated)
    record = run(evaluated, lying(), expect_same=True)
    assert record.status is RunStatus.FAILED
    assert record.stats["written"] == 0 and record.stats["withheld"] == 2
    assert record.stats["changed_count"] == 2 and "result:" in record.stats["changed"][0]
    pd.testing.assert_frame_equal(rows(evaluated), before)  # not one row, the equal edge's neither


def test_an_edge_that_could_not_be_compared_fails_the_run_and_writes_nothing(
    evaluated: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A re-judge that raises is no comparison: the other edge's row must not publish either."""
    run(evaluated, configs())
    before = rows(evaluated)
    real = framer.rejudged_frame

    def flaky(ctx: Any, edge: Any, found: Any, **kw: Any) -> Any:
        if edge.id == "drift":
            raise ValueError("the judge broke on this one")
        return real(ctx, edge, found, **kw)

    monkeypatch.setattr(framer, "rejudged_frame", flaky)
    record = run(evaluated, tuned(bootstrap_draws=3000), expect_same=True)
    assert record.status is RunStatus.FAILED
    assert record.stats["failed"] == 1 and record.stats["written"] == 0
    assert record.stats["withheld"] == 1
    pd.testing.assert_frame_equal(rows(evaluated), before)
    # without the flag the same failure stays PARTIAL and the other edge is written
    plain = run(evaluated, tuned(bootstrap_draws=3500))
    assert plain.status is RunStatus.PARTIAL and plain.stats["written"] == 1


def test_one_changed_edge_withholds_the_unchanged_ones_too(evaluated: World) -> None:
    run(evaluated, configs())
    moved = configs(
        {("site", "settings", "verdict"): {"min_oos_trades": 10_000}},
        implementation={"promoted": "momo"},
    )
    only = run(evaluated, moved, expect_same=True, edge_id="drift")
    assert only.status is RunStatus.FAILED and len(rows(evaluated)) == 2


def test_a_run_with_no_earlier_row_is_counted_and_is_no_failure(evaluated: World) -> None:
    record = run(evaluated, configs(), expect_same=True)
    assert record.status is RunStatus.COMPLETE
    assert (record.stats["no_prior"], record.stats["compared"], record.stats["written"]) == (
        2,
        0,
        2,
    )


def test_the_newest_earlier_row_is_the_one_compared(evaluated: World) -> None:
    run(evaluated, configs())  # A: the real headline
    run(evaluated, lying())  # C: a different one, written without the check
    run(evaluated, tuned(bootstrap_draws=3000))  # B: the real headline again, the newest
    ok = run(evaluated, tuned(bootstrap_draws=4000), expect_same=True)  # newest prior is B
    assert ok.status is RunStatus.COMPLETE and ok.stats["compared"] == 2
    assert len(rows(evaluated)) == 8
    bad = run(
        evaluated,
        configs({("site", "settings", "verdict"): {"min_oos_trades": 20_000}}),
        expect_same=True,
    )  # newest prior is D (the real headline): the new one differs
    assert bad.status is RunStatus.FAILED and len(rows(evaluated)) == 8


def test_an_already_current_row_is_still_compared(evaluated: World) -> None:
    run(evaluated, configs())
    run(evaluated, tuned(bootstrap_draws=3000))  # the current row exists now
    again = run(evaluated, tuned(bootstrap_draws=3000), expect_same=True)
    assert again.status is RunStatus.COMPLETE
    assert (
        again.stats["compared"] == 2 and again.stats["skipped"] == 2 and again.stats["written"] == 0
    )
    assert len(rows(evaluated)) == 4
    # a current row that differs from the earlier one fails the check (nothing to write either way)
    run(evaluated, lying())  # the current row of ``lying`` differs from its earlier ones
    again = run(evaluated, lying(), expect_same=True)
    assert again.status is RunStatus.FAILED and again.stats["changed_count"] == 2


def test_dry_run_compares_without_writing(evaluated: World) -> None:
    run(evaluated, configs())
    same = run(evaluated, tuned(bootstrap_draws=3000), expect_same=True, dry_run=True)
    assert same.status is RunStatus.COMPLETE and same.stats["compared"] == 2
    assert same.stats["would_write"] == 2 and len(rows(evaluated)) == 2
    bad = run(evaluated, lying(), expect_same=True, dry_run=True)
    assert bad.status is RunStatus.FAILED and len(rows(evaluated)) == 2


def test_every_summary_field_is_compared_not_only_the_label(evaluated: World) -> None:
    """A moved lift with the same label and result line is still a difference."""
    run(evaluated, configs())
    ctx = stores(evaluated, configs())
    found = edges.load_edge(ctx, "drift")
    assert found is not None
    canonical = runs.load_canonical_run(ctx, found).run
    assert canonical is not None
    prior = framer.stored_headlines(ctx, DAYS[-1])[("drift", canonical.run_id)][0]
    nudged = replace(prior.summary, lift=(prior.summary.lift or 1.0) + 0.5)
    frame = framer.verdict_frame(
        nudged, canonical, fingerprint="older-fingerprint", settings=load_verdict(configs()),
        licence=None, run_id="x", source="test", now=NOW + timedelta(days=30),
    )  # fmt: skip
    evaluated.results.write_result("edge_verdict", DAYS[-1], "x", frame)  # the newest earlier row
    record = run(evaluated, configs(), expect_same=True, edge_id="drift")
    assert record.status is RunStatus.FAILED and "lift" in record.stats["changed"][0]
    assert "verdict:" not in record.stats["changed"][0]  # the label itself did not move


def test_the_cli_flag_reaches_the_options(evaluated: World) -> None:
    from algotrade_ingestion.tasks.framework.registry import TASKS  # noqa: PLC0415

    flags = {f for p in TASKS["edge-verdicts"].params for f in p.flags}
    assert "--expect-same-headlines" in flags
    ctx = replace(task_ctx(evaluated.writer, evaluated.reader, clock=lambda: next(CLOCK)),
                  configs=lying())  # fmt: skip
    entries_ops.run_edge_verdicts(replace(ctx, configs=configs()), {"all_edges": True})
    record = entries_ops.run_edge_verdicts(ctx, {"all_edges": True, "expect_same": True})
    assert record.status is RunStatus.FAILED and record.stats["expect_same"] is True
