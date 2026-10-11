"""The trade ledger (ADR 0064 decision 2): one row per pick of the main edge variant's
implementation screeners, excluded picks with their public kind, the window's close from the
calendar, the side of the split the leg's block is on; written in the run's one publish with its
row count on the run record (all or nothing), and the licences of the trial and its columns."""

from dataclasses import replace
from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd
import pytest

from algotrade.config.user import UserContext
from algotrade.core.time.calendar import next_session
from algotrade.services.evaluation.cross_section.detail import trades
from algotrade.services.evaluation.cross_section.detail.trades import trades_frame
from algotrade.services.evaluation.cross_section.harness import EdgeEvaluation, evaluate_edge
from algotrade.services.evaluation.cross_section.measures import Pick
from algotrade.services.evaluation.cross_section.results import write_edge_eval
from algotrade.storage.configs.files import MemoryConfigStore
from algotrade.storage.tables.edge_schemas import EDGE_TRADES
from tests.unit.services.evaluation.cross_section.conftest import (
    AS_OF,
    DAYS,
    IDS,
    World,
    build_world,
    edge,
    outcome_row,
    screen,
)

NOW = datetime(2026, 10, 6, 12, tzinfo=AS_OF.tzinfo)
SPLIT = {"frozen_from": DAYS[2].isoformat()}  # decisions D1 before it; D2, D3, D4 after
STARTS = [DAYS[0], DAYS[2], DAYS[4], DAYS[6]]


def evaluate(w: World, **changes: Any) -> EdgeEvaluation:
    return evaluate_edge(
        w.reader, w.results, w.configs, UserContext("site"), edge(**{**SPLIT, **changes}),
        DAYS[0], DAYS[-1], AS_OF,
    )  # fmt: skip


def with_baseline(w: World) -> World:
    w.configs = MemoryConfigStore(
        {**w.configs._docs, ("site", "strategies", "cheap"): {**screen("asc"), "id": "cheap"}}  # type: ignore[attr-defined]
    )
    return w


def test_every_pick_of_an_implementation_screener_is_a_row(world: World) -> None:
    ev = evaluate(with_baseline(world), baselines=["cheap"])
    frame = trades_frame(ev, "r1", NOW)
    assert set(frame["variant"]) == {"momo"}  # a baseline is never listed
    assert len(frame) == 4 * 5  # four decisions, top 5 each
    first = frame.iloc[0]
    assert (first["decision_session"], first["rank"], first["instrument_id"]) == (
        DAYS[0], 1, IDS[19]
    )  # fmt: skip
    assert first["entry_session"] == next_session(DAYS[0])
    assert first["exit_session"] == next_session(next_session(first["entry_session"]))
    assert (first["status"], first["hit"], first["value"]) == ("won", True, pytest.approx(0.095))
    assert pd.isna(first["excluded_reason"]) and pd.isna(first["edge_variant"])
    assert list(frame.groupby("decision_session")["before_split"].first()) == [
        True, False, False, False,
    ]  # fmt: skip
    assert set(frame["licence"]) == {"open"} and set(frame["score_licence"]) == {"open"}
    assert list(frame.columns) <= [c.name for c in EDGE_TRADES.columns]


def test_an_excluded_pick_is_listed_with_its_public_kind_and_no_outcome() -> None:
    def rows_of(day: date) -> list[dict[str, Any]]:
        return [outcome_row(iid, i, day) for i, iid in enumerate(IDS) if i != 19]

    ev = evaluate(build_world(rows_of=rows_of))
    frame = trades_frame(ev, "r1", NOW)
    gone = frame[frame["instrument_id"] == IDS[19]]
    assert set(gone["status"]) == {"excluded"} and set(gone["excluded_reason"]) == {"NO_ENTRY_BAR"}
    assert gone["value"].isna().all() and gone["hit"].isna().all()
    assert set(frame[frame["instrument_id"] != IDS[19]]["status"]) == {"won"}


def test_a_leg_is_on_the_side_of_its_blocks_first_session(world: World) -> None:
    """An event block that starts before the split is in sample whole, as for the slices."""
    ev = evaluate(world)
    (r,) = ev.results
    late = replace(r.legs[1], block=DAYS[0])  # D2 (after the split) in a block from D1
    moved = replace(ev, results=(replace(r, legs=(r.legs[0], late)),))
    frame = trades_frame(moved, "r1", NOW)
    assert frame["before_split"].all()


def test_a_reason_without_a_public_kind_fails(world: World) -> None:
    ev = evaluate(world)
    (r,) = ev.results
    odd = replace(r.legs[0].stat, picks=(Pick("EQ:X", 1, "something_new"),))
    leg = replace(r.legs[0], stat=odd)
    with pytest.raises(ValueError, match="no public kind"):
        trades_frame(replace(ev, results=(replace(r, legs=(leg,)),)), "r1", NOW)


def test_every_harness_reason_has_a_public_kind() -> None:
    assert set(trades.EXCLUDED_KINDS.values()) == {
        "UNMEASURED", "MISSING_VALUE", "NO_ENTRY_BAR", "NO_IMPLIED_VOL", "MISSING_DRAWDOWN",
    }  # fmt: skip


def test_the_ledger_is_published_with_the_run_and_counted_on_its_record(world: World) -> None:
    ev = evaluate(world)
    record = write_edge_eval(world.results, ev, NOW)
    stored = world.reader.read_run(EDGE_TRADES.name, ev.end, record.run_id)
    assert stored is not None and len(stored) == 20
    saved = world.results.runs_for(record.job)[-1]
    assert saved.stats["ledger_rows"] == 20


def test_a_crash_before_the_commit_leaves_no_ledger(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    ev = evaluate(world)

    def crash(*_: Any) -> None:
        raise RuntimeError("crash before the commit")

    monkeypatch.setattr(world.results.__class__, "save_run", crash)
    results = world.results
    with pytest.raises(RuntimeError):
        write_edge_eval(results, ev, NOW)
    assert world.reader.dates(EDGE_TRADES.name) == []


def test_an_edge_with_no_screener_picks_writes_no_ledger_and_counts_zero(world: World) -> None:
    ev = evaluate(world)
    (r,) = ev.results
    empty = replace(ev, results=(replace(r, legs=()),))
    record = write_edge_eval(world.results, empty, NOW + timedelta(minutes=1))
    assert world.results.runs_for(record.job)[-1].stats["ledger_rows"] == 0
    assert world.reader.dates(EDGE_TRADES.name) == []


def test_an_incremental_runs_ledger_is_a_full_runs(world: World) -> None:
    """The ledger is a pure function of the legs: reused legs give the rows computed ones do."""
    full = evaluate_edge(
        world.reader, world.results, world.configs, UserContext("site"), edge(**SPLIT),
        DAYS[0], DAYS[-1], NOW, full=True,
    )  # fmt: skip
    write_edge_eval(world.results, full, NOW)
    again = evaluate_edge(
        world.reader, world.results, world.configs, UserContext("site"), edge(**SPLIT),
        DAYS[0], DAYS[-1], NOW,
    )  # fmt: skip
    assert again.legs_reused == 4 and again.legs_computed == 0
    pd.testing.assert_frame_equal(trades_frame(again, "r", NOW), trades_frame(full, "r", NOW))
