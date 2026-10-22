"""The stored verdict headline (ADR 0053 amendment 2026-10-22): the row an edge-eval publish
frames from its own pending rows equals what the reader judges from the committed ones, is
published with them or not at all, and a run the reader would not call canonical gets none."""

from datetime import date, datetime
from typing import Any

import pandas as pd
import pytest

from algotrade.config.site.settings import load_verdict
from algotrade.config.user import UserContext
from algotrade.services.evaluation.cross_section.detail import verdict as framer
from algotrade.services.evaluation.cross_section.harness import evaluate_edge
from algotrade.services.evaluation.cross_section.results import edge_eval_frame, write_edge_eval
from algotrade.services.read.context import StoreContext, open_stores
from algotrade.services.read.evaluation import edges, runs
from algotrade.services.read.evaluation.verdict import fingerprint as stamp
from algotrade.services.read.evaluation.verdict import judge_call, load_edge_summary
from algotrade.services.read.evaluation.verdict.model import EdgeSummary
from algotrade.storage.configs.files import MemoryConfigStore
from algotrade.storage.tables.edge_schemas import EDGE_VERDICT
from tests.unit.services.evaluation.cross_section.conftest import (
    ACTIVE,
    AS_OF,
    DAYS,
    World,
    edge,
    edge_document,
    screen,
)

NOW = datetime(2026, 10, 6, 12, tzinfo=AS_OF.tzinfo)
SPLIT = DAYS[4]
TABLE = "results/edge_verdict"


def site_stores(w: World, **changes: Any) -> StoreContext:
    """The site's stores over ``w`` with the edge's document (frozen at ``SPLIT``)."""
    docs = {
        ("site", "selections", "active"): ACTIVE,
        ("site", "strategies", "momo"): screen(),
        ("site", "edges", "drift"): edge_document(frozen_from=SPLIT.isoformat(), **changes),
    }
    return open_stores(w.reader, MemoryConfigStore(docs), UserContext("site"))


def evaluated(w: World, ctx: StoreContext, split: str | None = None):  # type: ignore[no-untyped-def]
    return evaluate_edge(
        w.reader, w.results, ctx.configs, UserContext("site"),
        edge(frozen_from=SPLIT.isoformat()), DAYS[0], DAYS[-1], AS_OF,
        split_from=date.fromisoformat(split) if split else None,
    )  # fmt: skip


def stored(w: World) -> Any:
    return w.reader.table(TABLE, DAYS[-1])


@pytest.mark.parametrize(
    "changes",
    [{}, {"implementation": {"promoted": "momo"}}, {"top_k": 3}],
    ids=["plain", "declared basis", "fewer picks"],
)
def test_the_published_row_equals_the_readers_judgement_of_the_committed_rows(
    world: World, changes: dict[str, Any]
) -> None:
    ctx = site_stores(world, **changes)
    record = write_edge_eval(world.results, evaluated(world, ctx), NOW, stores=ctx)
    row = stored(world).iloc[0]
    found = edges.load_edge(ctx, "drift")
    assert found is not None
    live = load_edge_summary(ctx, found)
    run = runs.load_canonical_run(ctx, found).run
    assert run is not None and run.run_id == record.run_id
    got = EdgeSummary(
        row["edge_id"], row["verdict"], row["result"], row["basis"],
        None if row["trades"] is None or row["trades"] != row["trades"] else int(row["trades"]),
        None if row["oos_trades"] != row["oos_trades"] else int(row["oos_trades"]),
        None if row["lift"] != row["lift"] else float(row["lift"]),
        None if row["lift_pts"] != row["lift_pts"] else float(row["lift_pts"]),
    )  # fmt: skip
    assert got == live  # the same bytes the reader would judge
    assert row["fingerprint"] == stamp.fingerprint(
        judge_call(found, run, True), run, load_verdict(ctx.configs)
    )
    assert (row["user_id"], row["judged_run_id"], row["run_id"]) == (
        "site", record.run_id, record.run_id,
    )  # fmt: skip
    assert row["source"] == "edge-eval" and row["judge_version"] == stamp.JUDGE_VERSION
    assert row["judge_digest"] == stamp.judge_digest()
    assert row["knowledge_ts"] == pd.Timestamp(NOW)  # the write instant, as its edge_eval rows
    assert {c.name for c in EDGE_VERDICT.columns} >= set(stored(world).columns)


def test_a_crash_after_the_verdict_frame_leaves_no_verdict_row(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = site_stores(world)
    ev = evaluated(world, ctx)

    def crash(_: object) -> None:
        raise RuntimeError("disk full")

    writer = world.results
    monkeypatch.setattr(writer, "save_run", crash)
    with pytest.raises(RuntimeError):
        write_edge_eval(writer, ev, NOW, stores=ctx)
    assert stored(world) is None and world.reader.table("results/edge_eval", DAYS[-1]) is None


def test_a_framing_error_keeps_the_evaluation_and_writes_no_row(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = site_stores(world)

    def broken(*_: object) -> None:
        raise ValueError("the judge changed under us")

    monkeypatch.setattr(framer, "edge_verdict_frame", broken)
    record = write_edge_eval(world.results, evaluated(world, ctx), NOW, stores=ctx)
    assert stored(world) is None
    assert world.reader.table("results/edge_eval", DAYS[-1]) is not None
    saved = world.results.load_run(record.run_id)
    assert saved is not None and saved.stats["verdict_row"] is False


def test_a_run_the_reader_would_not_call_canonical_gets_no_row(world: World) -> None:
    ctx = site_stores(world)
    ev = evaluated(world, ctx, split=DAYS[2].isoformat())  # exploratory: not the frozen period
    write_edge_eval(world.results, ev, NOW, stores=ctx)
    assert stored(world) is None


def test_a_direct_call_without_stores_writes_no_row(world: World) -> None:
    ctx = site_stores(world)
    record = write_edge_eval(world.results, evaluated(world, ctx), NOW)
    assert stored(world) is None
    saved = world.results.load_run(record.run_id)
    assert saved is not None and "verdict_row" not in saved.stats


def test_a_users_own_run_of_a_site_edge_gets_no_row(world: World) -> None:
    ctx = site_stores(world)
    record = write_edge_eval(world.results, evaluated(world, ctx), NOW, owner="bob")
    assert record.run_id and stored(world) is None
    ctx_bob = open_stores(world.reader, ctx.configs, UserContext("bob"))
    found = edges.load_edge(ctx_bob, "drift")
    assert found is not None
    assert framer.edge_verdict_frame(
        ctx_bob, "drift", world.results.load_run(record.run_id), edge_eval_frame(  # type: ignore[arg-type]
            evaluated(world, ctx), record.run_id, NOW
        ), NOW,
    ) is None  # fmt: skip


def test_a_number_not_measured_stays_null_never_zero(world: World) -> None:
    ctx = site_stores(world)
    found = edges.load_edge(ctx, "drift")
    assert found is not None
    write_edge_eval(world.results, evaluated(world, ctx), NOW, stores=ctx)
    run = runs.load_canonical_run(ctx, found).run
    assert run is not None
    summary = EdgeSummary("drift", "waiting_on_data", "r", None, None, None, None, None)
    frame = framer.verdict_frame(
        summary, run, fingerprint="f", settings=load_verdict(ctx.configs), licence=None, run_id="w",
        source="edge-verdicts", now=NOW,
    )  # fmt: skip
    for column in ("trades", "oos_trades", "lift", "lift_pts", "basis", "licence"):
        assert frame[column].isna().all(), column
    assert (frame["session_date"] == run.range_to).all() and (
        frame["source"] == "edge-verdicts"
    ).all()


def test_the_edge_edit_that_moves_the_judge_changes_the_stored_fingerprint(world: World) -> None:
    ctx = site_stores(world)
    write_edge_eval(world.results, evaluated(world, ctx), NOW, stores=ctx)
    first = stored(world).iloc[0]["fingerprint"]
    other = site_stores(
        world, implementation={"promoted": "momo"}
    )  # a declared basis is a judge input
    found = edges.load_edge(other, "drift")
    run = runs.load_canonical_run(other, found).run  # type: ignore[arg-type]
    assert run is not None
    assert (
        stamp.fingerprint(judge_call(found, run, True), run, load_verdict(other.configs))  # type: ignore[arg-type]
        != first
    )
