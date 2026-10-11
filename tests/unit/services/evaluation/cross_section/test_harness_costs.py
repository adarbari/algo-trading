"""The harness writes cost rows and capacity columns on ``results/edge_eval`` (ADR 0064 decision
5): a return edge gets one row per period and cost (its own plus the site's grid), an outcome that
is not a return none, and the capacity floor is applied at the statistics stage."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pandas as pd
import pytest

from algotrade.config.user import UserContext
from algotrade.services.evaluation.cross_section.harness import EdgeEvaluation, evaluate_edge
from algotrade.services.evaluation.cross_section.results import edge_eval_frame, write_edge_eval
from tests.helpers.stored_frames import stamped
from tests.unit.services.evaluation.cross_section.conftest import (
    DAYS,
    IDS,
    World,
    build_world,
    edge,
)
from tests.unit.services.evaluation.cross_section.test_harness import OTM_OUTCOME, otm_world

T1 = datetime(2026, 10, 6, 12, tzinfo=UTC)
ADV = "rollups/instrument/price_stats@v2"
SPLIT = {"frozen_from": DAYS[2].isoformat()}
OWN_BP = 20  # the document's cost: between the grid's 15 and 30 bp


def run(w: World, at: datetime = T1, **changes: Any) -> EdgeEvaluation:
    return evaluate_edge(
        w.reader, w.results, w.configs, UserContext("site"), edge(**{**SPLIT, **changes}),
        DAYS[0], DAYS[-1], at,
    )  # fmt: skip


def with_adv(w: World, scale: float = 1e6) -> World:
    for day in DAYS:
        rows = [{"instrument_id": i, "adv_usd_20d": scale * (k + 1)} for k, i in enumerate(IDS[1:])]
        w.writer.write_table(ADV, day, f"adv-{day}", stamped(rows, day, f"adv-{day}"))
    return w


def costed(ev: EdgeEvaluation) -> pd.DataFrame:
    frame = edge_eval_frame(ev, "r", T1)
    return frame[frame["slice_kind"] == "cost"].set_index("slice_value")


def test_a_return_edge_has_a_cost_row_per_period_and_cost_with_its_own_cost_included() -> None:
    outcome = {
        "kind": "excess_return", "horizon_sessions": [2], "benchmark": "SPY",
        "start_offset_sessions": 1, "cost_bps": OWN_BP,
    }  # fmt: skip
    rows = costed(run(build_world(), outcome=outcome))
    periods = ("all", "in_sample", "frozen")
    assert sorted(rows.index) == sorted(f"{p}:{bp}" for p in periods for bp in (0, 15, 20, 30, 50))
    assert not rows[["hit_rate", "lift", "mean_excess_picks"]].isna().any().any()
    # a cost is linear in the mean: every level's mean is the gross less its own cost
    gross = rows.loc["all:0", "mean_excess_picks"]
    for bp in (15, 20, 30, 50):
        assert rows.loc[f"all:{bp}", "mean_excess_picks"] == pytest.approx(gross - bp / 1e4)
    assert rows["decile_spread"].isna().all()  # cost-invariant: the all row's, not restated


def test_the_stored_row_at_the_documents_cost_is_the_all_row_itself() -> None:
    ev = run(build_world(), outcome={
        "kind": "excess_return", "horizon_sessions": [2], "benchmark": "SPY",
        "start_offset_sessions": 1, "cost_bps": OWN_BP,
    })  # fmt: skip
    frame = edge_eval_frame(ev, "r", T1)
    own = frame[(frame["slice_kind"] == "cost") & (frame["slice_value"] == "all:20")].iloc[0]
    whole = frame[frame["slice_kind"] == "all"].iloc[0]
    for col in ("hits", "base_hits", "hit_rate", "base_rate", "lift", "mean_excess_picks"):
        assert own[col] == whole[col]


def test_an_outcome_that_is_not_a_return_writes_no_cost_row() -> None:
    ev = run(otm_world(), outcome=OTM_OUTCOME)
    assert costed(ev).empty and ev.results[0].costs == ()


def test_no_split_no_period_rows_beyond_all() -> None:
    frame = edge_eval_frame(run(build_world(), frozen_from=None), "r", T1)
    assert sorted(frame[frame["slice_kind"] == "cost"]["slice_value"]) == [
        "all:0",
        "all:15",
        "all:30",
        "all:50",
    ]  # the document's cost is none: its own level is the grid's 0


def test_capacity_columns_count_the_picks_adv_against_the_site_floor() -> None:
    w = with_adv(build_world())  # name k has ADV (k) million; the five picks are names 15 to 19
    row = edge_eval_frame(run(w), "r", T1).query("slice_kind == 'all'").iloc[0]
    assert row["pick_adv_known"] == 20  # 4 sessions x 5 picks
    assert row["pick_adv_median"] == pytest.approx(17e6)
    assert row["pick_adv_low"] == 0  # all above the default 5M floor
    w.configs._docs["site", "settings", "verdict"] = {"capacity_adv_floor_usd": 18e6}
    low = edge_eval_frame(run(w), "r", T1).query("slice_kind == 'all'").iloc[0]
    assert low["pick_adv_low"] == 12  # names 15, 16 and 17 in each of the four sessions


def test_capacity_is_unknown_not_zero_when_no_adv_is_stored() -> None:
    row = edge_eval_frame(run(build_world()), "r", T1).query("slice_kind == 'all'").iloc[0]
    assert row["pick_adv_known"] == 0 and pd.isna(row["pick_adv_median"])


def test_a_changed_capacity_floor_recomputes_no_leg() -> None:
    w = with_adv(build_world())
    first = run(w)
    write_edge_eval(w.results, first, T1)
    w.configs._docs["site", "settings", "verdict"] = {"capacity_adv_floor_usd": 18e6}
    again = run(w, T1 + timedelta(days=1))
    assert (again.legs_computed, again.legs_reused) == (0, first.legs_computed)


def test_a_cost_row_is_written_by_a_full_and_an_incremental_run_alike() -> None:
    w = build_world()
    first = run(w)
    write_edge_eval(w.results, first, T1)
    again = run(w)
    assert again.legs_reused == first.legs_computed
    key = ["variant", "horizon_sessions", "slice_kind", "slice_value"]

    def frame(ev: EdgeEvaluation) -> pd.DataFrame:
        f = edge_eval_frame(ev, "r", T1).drop(columns=["knowledge_ts", "run_id"])
        return f.sort_values(key).reset_index(drop=True)

    assert (frame(first)["slice_kind"] == "cost").any()
    pd.testing.assert_frame_equal(frame(first), frame(again), check_exact=True)
