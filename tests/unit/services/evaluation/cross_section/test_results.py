"""``write_edge_eval``: the rows of an evaluation land in ``results/edge_eval`` (committed
together, one per variant, horizon and slice, keyed so a re-run of the range replaces them), its
run record keeps the trial log, and the survivorship caveat is countable."""

from datetime import datetime, timedelta

import pandas as pd
import pytest

from algotrade.config.user import UserContext
from algotrade.core.model.errors import DataValidationError
from algotrade.services.evaluation.cross_section.harness import evaluate_edge
from algotrade.services.evaluation.cross_section.results import (
    edge_eval_frame,
    records,
    survivorship,
    write_edge_eval,
)
from algotrade.storage.tables.schemas import EDGE_EVAL
from tests.unit.services.evaluation.cross_section.conftest import (
    AS_OF,
    DAYS,
    World,
    build_world,
    edge,
)  # fmt: skip

NOW = datetime(2026, 10, 6, 12, tzinfo=AS_OF.tzinfo)


def evaluate(w: World, **changes: object):  # type: ignore[no-untyped-def]
    return evaluate_edge(
        w.reader,
        w.results,
        w.configs,
        UserContext("site"),
        edge(**changes),
        DAYS[0],
        DAYS[-1],
        AS_OF,
    )


def test_rows_and_a_run_record_with_the_trial_log(world: World) -> None:
    ev = evaluate(world)
    record = write_edge_eval(world.results, ev, NOW)
    stored = world.reader.table("results/edge_eval", DAYS[-1])
    assert stored is not None and len(stored) == len(ev.results[0].measures)
    all_row = stored[stored["slice_kind"] == "all"].iloc[0]
    assert (all_row["edge_id"], all_row["variant"], all_row["horizon_sessions"]) == (
        "drift",
        "momo",
        2,
    )
    assert (all_row["sessions"], all_row["picks"], all_row["lift"]) == (4, 20, 2.0)
    assert all_row["run_config_hash"] == ev.run_hash and all_row["benchmark"] == "SPY"
    assert pd.Timestamp(all_row["range_from"]).date() == DAYS[0]
    assert pd.isna(all_row["deflated_sharpe"]) and all_row["trials"] == 1
    saved = world.results.load_run(record.run_id)
    assert saved is not None and saved.job == "edge-eval:drift:site"
    assert all_row["user_id"] == "site" and saved.stats["trials"][0]["excluded_coverage"] == 0
    (trial,) = saved.stats["trials"]
    assert (trial["variant"], trial["horizon"], trial["lift"], trial["ranked_share"]) == (
        "momo",
        2,
        2.0,
        1.0,
    )


def test_rerunning_a_range_replaces_its_rows(world: World) -> None:
    write_edge_eval(world.results, evaluate(world), NOW)
    write_edge_eval(world.results, evaluate(world, top_k=3), NOW + timedelta(hours=1))
    stored = world.reader.table("results/edge_eval", DAYS[-1])
    assert stored is not None
    all_rows = stored[stored["slice_kind"] == "all"]
    assert len(all_rows) == 1 and all_rows.iloc[0]["picks"] == 12  # the later run won the key


def test_an_invalid_frame_publishes_nothing(world: World) -> None:
    ev = evaluate(world)
    bad = edge_eval_frame(ev, "r1", NOW).assign(surprise=1.0)  # an undeclared column
    with pytest.raises(DataValidationError), world.results.publishing("r1", NOW):
        world.results.write_result("edge_eval", ev.end, "r1", bad, pending=True)
    assert world.reader.table("results/edge_eval", ev.end) is None


def test_the_frame_has_exactly_the_tables_columns(world: World) -> None:
    frame = edge_eval_frame(evaluate(world), "r1", NOW)
    assert {c.name for c in EDGE_EVAL.columns} == set(frame.columns)


def test_records_are_json_able_with_none_for_missing(world: World) -> None:
    rows = records(edge_eval_frame(evaluate(world), "r1", NOW))
    first = rows[0]
    assert first["deflated_sharpe"] is None and "knowledge_ts" not in first
    assert first["range_from"] == DAYS[0]


def test_survivorship_counts_sessions_read_from_a_later_snapshot() -> None:
    w = build_world(snapshot=DAYS[3])  # the snapshot is Sept 4: starts Sept 1 and Sept 3 precede it
    assert survivorship(evaluate(w)) == {2: (2, 4)}
