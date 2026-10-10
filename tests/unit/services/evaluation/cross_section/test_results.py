"""``write_edge_eval``: the rows of an evaluation land in ``results/edge_eval`` (committed
together, one per variant, horizon and slice, keyed so a re-run of the range replaces them), its
run record keeps the trial log, and the survivorship caveat is countable."""

from datetime import date, datetime, timedelta

import pandas as pd
import pyarrow as pa
import pytest

from algotrade.config.user import UserContext
from algotrade.core.model.errors import DataValidationError
from algotrade.services.evaluation.cross_section.harness import evaluate_edge
from algotrade.services.evaluation.cross_section.results import (
    edge_eval_frame,
    iv_coverage,
    records,
    survivorship,
    write_edge_eval,
)
from algotrade.storage.backends.run_selection import merge_rows
from algotrade.storage.tables.schemas import EDGE_EVAL
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


def test_the_iv_source_licence_and_rate_columns_are_null_until_something_fills_them(
    world: World,
) -> None:
    row = edge_eval_frame(evaluate(world), "r1", NOW).iloc[0]
    assert pd.isna(row["edge_variant"]) and pd.isna(row["iv_source"]) and pd.isna(row["licence"])
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
