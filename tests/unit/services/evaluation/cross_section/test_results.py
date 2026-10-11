"""``write_edge_eval``: the rows of an evaluation land in ``results/edge_eval`` (committed
together, one per variant, horizon and slice, keyed so a re-run of the range replaces them), its
run record keeps the trial log, and the survivorship caveat is countable."""

from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd
import pyarrow as pa
import pytest

from algotrade.config.user import UserContext
from algotrade.core.model.errors import DataValidationError
from algotrade.data import dates_digest
from algotrade.services.evaluation.cross_section.harness import EdgeEvaluation, evaluate_edge
from algotrade.services.evaluation.cross_section.legs.rows import (
    decode_leg,
    decode_reads,
    encode_leg,
)
from algotrade.services.evaluation.cross_section.legs.store import read_legs
from algotrade.services.evaluation.cross_section.results import (
    edge_eval_frame,
    iv_coverage,
    records,
    survivorship,
    write_edge_eval,
)
from algotrade.storage.backends.run_selection import merge_rows
from algotrade.storage.tables.edge_schemas import EDGE_EVAL
from tests.helpers.stored_frames import stamped
from tests.unit.services.evaluation.cross_section.conftest import (
    AS_OF,
    DAYS,
    IDS,
    PRICE,
    World,
    build_world,
    edge,
    with_listing_history,
)  # fmt: skip
from tests.unit.services.evaluation.cross_section.test_harness import OTM_OUTCOME, otm_world

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
    assert stored is not None and len(stored) == len(ev.results[0].measures + ev.results[0].costs)
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


def test_edge_variants_are_rows_of_their_own_and_the_edge_itself_has_a_null_key(
    world: World,
) -> None:
    cheap = {"where": {"all": [{"field": PRICE, "op": "lt", "value": 200}]}}
    changes = {"variants": [{"id": "cheap", "universe": cheap}]}
    write_edge_eval(world.results, evaluate(world, **changes), NOW)
    write_edge_eval(world.results, evaluate(world, **changes), NOW + timedelta(hours=1))
    stored = world.reader.table("results/edge_eval", DAYS[-1])
    assert stored is not None
    all_rows = stored[stored["slice_kind"] == "all"]
    # Two runs merged on the key (edge variant included): one row per edge variant, not four.
    assert sorted(all_rows["edge_variant"].fillna("main")) == ["cheap", "main"]
    assert (
        all_rows.set_index(all_rows["edge_variant"].fillna("main")).loc["cheap", "eligible"] == 40
    )
    trials = world.results.runs_for("edge-eval:drift:site")[-1].stats["trials"]
    assert [(t["edge_variant"], t["variant"]) for t in trials] == [
        ("main", "momo"),
        ("cheap", "momo"),
    ]


def test_the_iv_source_and_rate_columns_are_null_until_something_fills_them(
    world: World,
) -> None:
    row = edge_eval_frame(evaluate(world), "r1", NOW).iloc[0]
    assert pd.isna(row["edge_variant"]) and pd.isna(row["iv_source"])
    assert row["licence"] == "open"  # the trial's: its screen's and universe's features (ADR 0064)
    assert pd.isna(row["reference_rate"]) and pd.isna(row["touch_rate"])


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


def test_sessions_before_the_first_snapshot_are_a_historical_caveat_not_survivorship() -> None:
    w = with_listing_history(build_world(snapshot=DAYS[3]), DAYS[3])  # starts Sept 1, 3 precede it
    ev = evaluate(w)
    assert survivorship(ev) == {2: (0, 4)}  # read from the listing history, not a later snapshot
    assert ev.historical is not None and ev.historical.sessions == 2


def test_an_exploratory_split_writes_rows_under_its_own_key_and_leaves_the_sites(
    world: World,
) -> None:
    def run(split: str | None, user: str, at: datetime) -> None:
        ev = evaluate_edge(
            world.reader, world.results, world.configs, UserContext(user),
            edge(frozen_from="2026-09-04"), DAYS[0], DAYS[-1], AS_OF,
            split_from=datetime.fromisoformat(split).date() if split else None,
        )  # fmt: skip
        write_edge_eval(world.results, ev, at)

    run(None, "site", NOW)
    site_rows = world.reader.table("results/edge_eval", DAYS[-1])
    assert site_rows is not None
    run("2026-09-09", "site", NOW + timedelta(hours=1))
    stored = world.reader.table("results/edge_eval", DAYS[-1])
    assert stored is not None
    mine = stored[stored["split_from"] == pd.Timestamp("2026-09-09").date()]
    assert mine["exploratory"].all() and len(mine) == len(site_rows)  # its own rows
    kept = stored[stored["split_from"] == pd.Timestamp("2026-09-04").date()]
    assert not kept["exploratory"].any()
    cols = ["slice_kind", "slice_value", "sessions", "lift"]
    assert kept[cols].reset_index(drop=True).equals(site_rows[cols].reset_index(drop=True))
    record = world.results.runs_for("edge-eval:drift:site")[-1]
    assert record.stats["exploratory"] and record.stats["split_from"] == "2026-09-09"


def test_rows_written_before_the_split_columns_keep_the_null_key_beside_a_dated_run(
    world: World,
) -> None:
    """Runs written before ``split_from`` was a key column carry none: merge_rows reads it as
    null, a distinct key from a new run's date, so both stay in one partition."""
    new = edge_eval_frame(evaluate(world), "r1", NOW).assign(split_from=date(2026, 4, 1))
    old = new.drop(columns=["split_from", "exploratory"]).assign(picks=-1, run_id="r0")
    both = pa.concat_tables(
        [pa.Table.from_pandas(f, preserve_index=False) for f in (old, new)],
        promote_options="default",
    )
    merged = merge_rows("results/edge_eval", both).to_pandas()
    assert len(merged) == len(old) + len(new)
    assert set(merged["run_id"]) == {"r0", "r1"}
    assert merged[merged["run_id"] == "r0"]["split_from"].isna().all()
    assert (merged[merged["run_id"] == "r1"]["split_from"] == date(2026, 4, 1)).all()


IBKR, OURS = "rollup.ibkr_iv@v1.iv30_ibkr", "rollup.iv30@v1.iv30"
OTM = {
    "kind": "expires_otm", "horizon_sessions": [2], "benchmark": "none", "structure": "put",
    "strike_delta": 0.30, "iv_field": IBKR, "start_offset_sessions": 1,
}  # fmt: skip


def iv_world(ours_from: date | None) -> World:
    """IBKR's IV on every session; ours (``iv30@v1``) only from ``ours_from`` (None: never)."""
    w = build_world()
    for day in [*DAYS, DAYS[-1] + timedelta(days=1)]:
        rows = [{"instrument_id": iid, "iv30_ibkr": 0.4} for iid in IDS]
        w.writer.write_table(
            "rollups/instrument/ibkr_iv@v1", day, f"ib-{day}", stamped(rows, day, f"ib-{day}")
        )
        if ours_from is not None and day >= ours_from:
            ours = [{"instrument_id": iid, "iv30": 0.4} for iid in IDS]
            w.writer.write_table(
                "rollups/instrument/iv30@v1", day, f"iv-{day}", stamped(ours, day, f"iv-{day}")
            )
    return w


def test_a_variant_whose_iv_field_has_no_rows_in_range_is_stated_not_a_silent_zero() -> None:
    variants = [{"id": "ours", "outcome": {"iv_field": OURS}}]
    ev = evaluate(iv_world(None), outcome=OTM, variants=variants)
    main, ours = ev.results
    assert ours.measures[0].picks == 0 and main.measures[0].picks > 0  # the silent zero
    (gap,) = iv_coverage(ev)  # the edge's own field is stored throughout: no line for it
    assert (gap["variant"], gap["horizon"], gap["field"]) == ("ours/momo", 2, OURS)
    assert gap["stored"] == 0 and gap["sessions"] == ours.measures[0].sessions > 0
    assert gap["picks"] == main.measures[0].picks  # every pick the field would have measured


def test_an_iv_field_stored_part_of_the_range_counts_the_sessions_that_have_it() -> None:
    variants = [{"id": "ours", "outcome": {"iv_field": OURS}}]
    (gap,) = iv_coverage(evaluate(iv_world(DAYS[4]), outcome=OTM, variants=variants))
    assert 0 < gap["stored"] < gap["sessions"] and gap["picks"] > 0
    assert iv_coverage(evaluate(iv_world(DAYS[0]), outcome=OTM, variants=variants)) == []
    assert iv_coverage(evaluate(iv_world(None))) == []  # an outcome that reads no implied vol


def test_the_legs_are_stored_with_the_run_and_hold_what_its_rows_were_measured_from(
    world: World,
) -> None:
    """ADR 0063: one leg row per decision session, the reads log of each session and its
    outcome read; the run's statistics come from the decoded legs, so the stored ones are
    exactly what produced its ``edge_eval`` rows."""
    ev = evaluate(world, frozen_from="2026-09-04")
    record = write_edge_eval(world.results, ev, NOW)
    found = read_legs(world.reader, "site", "drift", DAYS[0], DAYS[-1])
    (result,) = ev.results
    decisions = [s.session for s in result.stats]
    assert len(decisions) == 4
    assert sorted(d for *_, d in found.legs) == decisions and sorted(found.reads) == decisions
    assert [leg.stat for leg in sorted(found.legs.values(), key=lambda x: x.day)] == list(
        result.stats
    )
    drawn = [leg for leg in found.legs.values() if leg.random is not None]
    assert sorted(leg.day for leg in drawn) == [d for d in decisions if d >= date(2026, 9, 4)]
    assert all(leg.random is not None and leg.random.value_sums.size == 1000 for leg in drawn)
    assert all(leg.known == NOW and leg.outcomes_as_of == AS_OF for leg in found.legs.values())
    day = decisions[1]
    reads = found.reads[day]
    tables = {(r.table, r.start, r.kind) for r in reads.reads}
    assert ("rollups/instrument/option_liquidity@v1", day, "rows") in tables
    assert {"universe", "instruments/reference"} <= {
        r.table for r in reads.reads if r.kind == "dates"
    }
    assert all(r.end <= day for r in reads.reads)  # nothing after D is ever read
    assert not any("forward_returns" in r.table for r in reads.reads)  # outcomes: their own rows
    assert reads.inputs_seq is not None
    seen = found.outcomes["main", 2, day]
    assert seen.entry == DAYS[DAYS.index(day) + 1] and seen.as_of == AS_OF
    assert seen.seq is not None
    stored = world.reader.table_range("results/edge_legs", DAYS[0], DAYS[-1])
    assert stored is not None and (stored["run_id"] == record.run_id).all()


def test_a_crash_while_publishing_leaves_no_legs_and_no_rows(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    ev = evaluate(world)
    writer = world.results

    def crash(_: object) -> None:
        raise RuntimeError("disk full")

    monkeypatch.setattr(writer, "save_run", crash)
    with pytest.raises(RuntimeError):
        write_edge_eval(writer, ev, NOW)
    assert world.reader.table_range("results/edge_legs", DAYS[0], DAYS[-1]) is None
    assert world.reader.table("results/edge_eval", ev.end) is None
    assert writer.runs_for("edge-eval:drift:site") == []


def test_a_rerun_replaces_a_leg_under_its_key_instead_of_adding_one(world: World) -> None:
    write_edge_eval(world.results, evaluate(world), NOW)
    write_edge_eval(world.results, evaluate(world), NOW + timedelta(hours=1))
    found = read_legs(world.reader, "site", "drift", DAYS[0], DAYS[-1])
    assert len(found.legs) == 4 and {leg.known for leg in found.legs.values()} == {
        NOW + timedelta(hours=1)
    }


def test_the_evaluations_own_leg_rows_decode_to_the_statistics_it_measured(world: World) -> None:
    ev = evaluate(world)
    legs = [decode_leg(r) for r in ev.leg_rows if r["row_kind"] == "leg"]
    assert [leg.stat for leg in legs] == list(ev.results[0].stats)
    assert all(encode_leg(leg, "site", "drift")["leg_key"] == leg.key for leg in legs)


def test_a_snapshot_after_a_session_never_ends_its_reads_log_past_it() -> None:
    """The snapshot read lists only the partitions up to D: a later snapshot cannot change what
    D read (ADR 0063); before the first snapshot the earliest one is logged as that one
    partition, so a later snapshot never invalidates D and an earlier one does."""
    w = with_listing_history(build_world(snapshot=DAYS[3]), DAYS[3])  # first snapshot Sept 4
    reads = {
        r.day: r
        for r in (decode_reads(x) for x in evaluate(w).leg_rows if x["row_kind"] == "reads")
    }
    assert len(reads) == 4
    for day, found in reads.items():
        for rec in found.reads:
            if rec.table not in ("universe", "instruments/reference"):
                continue
            if day >= DAYS[3]:  # a snapshot on or before D: nothing is listed past D
                assert rec.end <= day, (day, rec)
            elif rec.start > day and rec.kind == "dates":  # before the first: only the earliest
                assert (rec.start, rec.end) == (DAYS[3], DAYS[3])
                assert rec.digest == dates_digest([DAYS[3]])


def test_the_run_record_names_its_owner_trigger_and_job(world: World) -> None:
    ev = evaluate(world)
    record = write_edge_eval(world.results, ev, NOW, owner="site", trigger="ui", job_id="j-1")
    stats = world.results.load_run(record.run_id).stats  # type: ignore[union-attr]
    assert (stats["owner"], stats["trigger"], stats["job_id"]) == ("site", "ui", "j-1")
    other = write_edge_eval(world.results, ev, NOW + timedelta(hours=1))
    stats = world.results.load_run(other.run_id).stats  # type: ignore[union-attr]
    assert (stats["owner"], stats["trigger"], stats["job_id"]) == ("site", "cli", None)


def test_the_all_row_carries_the_projected_exits_and_the_decision_session_counts(
    world: World,
) -> None:
    ev = evaluate(world, frozen_from=DAYS[4].isoformat())
    frame = edge_eval_frame(ev, "r", NOW)
    all_row = frame[frame["slice_kind"] == "all"].iloc[0]
    exits = list(all_row["projected_exits"])
    assert len(exits) == 400 and exits == sorted(exits)  # ceil(100 / 0.25), the default thresholds
    assert exits[0] > DAYS[-1]  # the next decisions after the last measured window
    assert (all_row["decisions_scheduled"], all_row["decisions_measured"]) == (4, 4)
    assert (all_row["decisions_scheduled_oos"], all_row["decisions_measured_oos"]) == (2, 2)
    others = frame[frame["slice_kind"] != "all"]
    assert others["projected_exits"].isna().all() and others["decisions_scheduled"].isna().all()


def test_a_run_without_a_split_counts_the_whole_run_and_no_out_of_sample_side(
    world: World,
) -> None:
    frame = edge_eval_frame(evaluate(world), "r", NOW)
    all_row = frame[frame["slice_kind"] == "all"].iloc[0]
    assert all_row["decisions_scheduled"] == 4 and pd.isna(all_row["decisions_scheduled_oos"])


def test_the_job_report_leaves_out_the_stored_projection(world: World) -> None:
    rows = records(edge_eval_frame(evaluate(world), "r", NOW))
    assert rows and all("projected_exits" not in r for r in rows)


# --- cost rows and capacity columns (ADR 0064 decision 5) ---

ADV = "rollups/instrument/price_stats@v2"
SPLIT = {"frozen_from": DAYS[2].isoformat()}
OWN_BP = 20  # the document's cost: between the grid's 15 and 30 bp


def run_costs(w: World, at: datetime = NOW, **changes: Any) -> EdgeEvaluation:
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
    frame = edge_eval_frame(ev, "r", NOW)
    return frame[frame["slice_kind"] == "cost"].set_index("slice_value")


def test_a_return_edge_has_a_cost_row_per_period_and_cost_with_its_own_cost_included() -> None:
    outcome = {
        "kind": "excess_return", "horizon_sessions": [2], "benchmark": "SPY",
        "start_offset_sessions": 1, "cost_bps": OWN_BP,
    }  # fmt: skip
    rows = costed(run_costs(build_world(), outcome=outcome))
    periods = ("all", "in_sample", "frozen")
    assert sorted(rows.index) == sorted(f"{p}:{bp}" for p in periods for bp in (0, 15, 20, 30, 50))
    assert not rows[["hit_rate", "lift", "mean_excess_picks"]].isna().any().any()
    # a cost is linear in the mean: every level's mean is the gross less its own cost
    gross = rows.loc["all:0", "mean_excess_picks"]
    for bp in (15, 20, 30, 50):
        assert rows.loc[f"all:{bp}", "mean_excess_picks"] == pytest.approx(gross - bp / 1e4)
    assert rows["decile_spread"].isna().all()  # cost-invariant: the all row's, not restated


def test_the_stored_row_at_the_documents_cost_is_the_all_row_itself() -> None:
    ev = run_costs(build_world(), outcome={
        "kind": "excess_return", "horizon_sessions": [2], "benchmark": "SPY",
        "start_offset_sessions": 1, "cost_bps": OWN_BP,
    })  # fmt: skip
    frame = edge_eval_frame(ev, "r", NOW)
    own = frame[(frame["slice_kind"] == "cost") & (frame["slice_value"] == "all:20")].iloc[0]
    whole = frame[frame["slice_kind"] == "all"].iloc[0]
    for col in ("hits", "base_hits", "hit_rate", "base_rate", "lift", "mean_excess_picks"):
        assert own[col] == whole[col]


def test_an_outcome_that_is_not_a_return_writes_no_cost_row() -> None:
    ev = run_costs(otm_world(), outcome=OTM_OUTCOME)
    assert costed(ev).empty and ev.results[0].costs == ()


def test_no_split_no_period_rows_beyond_all() -> None:
    frame = edge_eval_frame(run_costs(build_world(), frozen_from=None), "r", NOW)
    assert sorted(frame[frame["slice_kind"] == "cost"]["slice_value"]) == [
        "all:0",
        "all:15",
        "all:30",
        "all:50",
    ]  # the document's cost is none: its own level is the grid's 0


def test_capacity_columns_count_the_picks_adv_against_the_site_floor() -> None:
    w = with_adv(build_world())  # name k has ADV (k) million; the five picks are names 15 to 19
    row = edge_eval_frame(run_costs(w), "r", NOW).query("slice_kind == 'all'").iloc[0]
    assert row["pick_adv_known"] == 20  # 4 sessions x 5 picks
    assert row["pick_adv_median"] == pytest.approx(17e6)
    assert row["pick_adv_low"] == 0  # all above the default 5M floor
    w.configs._docs["site", "settings", "verdict"] = {"capacity_adv_floor_usd": 18e6}
    low = edge_eval_frame(run_costs(w), "r", NOW).query("slice_kind == 'all'").iloc[0]
    assert low["pick_adv_low"] == 12  # names 15, 16 and 17 in each of the four sessions


def test_capacity_is_unknown_not_zero_when_no_adv_is_stored() -> None:
    row = edge_eval_frame(run_costs(build_world()), "r", NOW).query("slice_kind == 'all'").iloc[0]
    assert row["pick_adv_known"] == 0 and pd.isna(row["pick_adv_median"])


def test_a_changed_capacity_floor_recomputes_no_leg() -> None:
    w = with_adv(build_world())
    first = run_costs(w)
    write_edge_eval(w.results, first, NOW)
    w.configs._docs["site", "settings", "verdict"] = {"capacity_adv_floor_usd": 18e6}
    again = run_costs(w, NOW + timedelta(days=1))
    assert (again.legs_computed, again.legs_reused) == (0, first.legs_computed)


def test_a_cost_row_is_written_by_a_full_and_an_incremental_run_alike() -> None:
    w = build_world()
    first = run_costs(w)
    write_edge_eval(w.results, first, NOW)
    again = run_costs(w)
    assert again.legs_reused == first.legs_computed
    key = ["variant", "horizon_sessions", "slice_kind", "slice_value"]

    def frame(ev: EdgeEvaluation) -> pd.DataFrame:
        f = edge_eval_frame(ev, "r", NOW).drop(columns=["knowledge_ts", "run_id"])
        return f.sort_values(key).reset_index(drop=True)

    assert (frame(first)["slice_kind"] == "cost").any()
    pd.testing.assert_frame_equal(frame(first), frame(again), check_exact=True)
