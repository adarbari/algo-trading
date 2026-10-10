"""Reusing stored legs (ADR 0063): an incremental run gives the rows of a full one at the same
``as_of``, whatever it reused; a change in what a leg read (a re-committed feature partition, a
snapshot up to its session, a rewritten or late outcome row, draws it lacks) recomputes exactly
the legs it touches; a run at an earlier ``as_of`` is full; legs of a trial the edge dropped are
tombstoned and never read back."""

from datetime import UTC, date, datetime, timedelta
from typing import Any
from unittest.mock import patch

import pandas as pd
import pytest

from algotrade.config.user import UserContext
from algotrade.core.model.errors import MissingDataError
from algotrade.core.time.calendar import next_session
from algotrade.data import ReadRecord, dates_digest
from algotrade.services.evaluation.cross_section.harness import EdgeEvaluation, evaluate_edge
from algotrade.services.evaluation.cross_section.legs.reuse import (
    FULL,
    INCREMENTAL,
    Need,
    Reuse,
    _listing_unchanged,
    lost_error,
    tombstones,
)
from algotrade.services.evaluation.cross_section.legs.rows import DayReads, LegRecord, StoredLegs
from algotrade.services.evaluation.cross_section.legs.store import TABLE, read_legs
from algotrade.services.evaluation.cross_section.measures import SessionStat
from algotrade.services.evaluation.cross_section.reads import session as session_reads
from algotrade.services.evaluation.cross_section.results import edge_eval_frame, write_edge_eval
from algotrade.storage.configs.files import MemoryConfigStore
from algotrade.storage.tables.schemas import FORWARD_RETURNS
from tests.helpers.stored_frames import stamped, universe_rows
from tests.unit.services.evaluation.cross_section.conftest import (
    DAYS,
    FEATURE,
    IDS,
    World,
    build_world,
    edge,
    outcome_row,
    screen,
    with_listing_history,
)
from tests.unit.services.evaluation.cross_section.test_harness import (
    EVENTS,
    event_edge,
    event_world,
)

T1 = datetime(2026, 10, 6, 12, tzinfo=UTC)  # one night's run
T2 = T1 + timedelta(days=1)  # the next night's
D1, D2, D3, D4 = DAYS[0], DAYS[2], DAYS[4], DAYS[6]  # the decision sessions of horizon 2
SPLIT = {"frozen_from": DAYS[2].isoformat()}  # the last three decisions are out of sample


def run(
    w: World, at: datetime, *, full: bool = False, write: bool = True, **changes: Any
) -> EdgeEvaluation:
    ev = evaluate_edge(
        w.reader, w.results, w.configs, UserContext("site"), edge(**{**SPLIT, **changes}),
        DAYS[0], DAYS[-1], at, full=full,
    )  # fmt: skip
    if write:
        write_edge_eval(w.results, ev, at)
    return ev


def rows(ev: EdgeEvaluation) -> pd.DataFrame:
    """The ``edge_eval`` rows of a run without what only says which run wrote them."""
    frame = edge_eval_frame(ev, "r", T1).drop(columns=["knowledge_ts", "run_id"])
    order = ["edge_variant", "variant", "horizon_sessions", "slice_kind", "slice_value"]
    return frame.sort_values(order, na_position="first").reset_index(drop=True)


def same(a: EdgeEvaluation, b: EdgeEvaluation) -> None:
    pd.testing.assert_frame_equal(rows(a), rows(b), check_exact=True)
    assert [r.stats for r in a.results] == [r.stats for r in b.results]


def recommit(w: World, table: str, day: date, run_id: str, rows_: list[dict[str, Any]]) -> None:
    """A restatement the way ingestion publishes it: written pending, then committed."""
    w.writer.write_table(table, day, run_id, stamped(rows_, day, run_id), pending=True)
    w.backend.tables.commit_run(run_id, T1 + timedelta(minutes=30))


def expensive(day: date) -> list[dict[str, Any]]:
    return [{"instrument_id": i, "underlying_price": 500.0 - 10 * k} for k, i in enumerate(IDS)]


def test_an_incremental_run_after_a_full_one_reuses_every_leg_and_gives_its_rows(
    world: World,
) -> None:
    first = run(world, T1, full=True)
    again = run(world, T1)
    assert (first.mode, first.legs_computed, first.legs_reused) == (FULL, 4, 0)
    assert (again.mode, again.legs_computed, again.legs_reused) == (INCREMENTAL, 0, 4)
    assert dict(again.legs_invalidated) == {}
    same(first, again)
    assert again.leg_rows == ()  # nothing is rewritten: its sessions stay as they were
    record = world.results.runs_for("edge-eval:drift:site")[-1]
    assert record.stats["mode"] == INCREMENTAL and record.stats["legs_reused"] == 4
    assert record.stats["legs_computed"] == 0 and record.stats["legs_invalidated"] == {}


def test_the_first_run_of_an_edge_is_incremental_with_nothing_to_reuse(world: World) -> None:
    first = run(world, T1, write=False)
    assert (first.mode, first.legs_computed, first.legs_reused) == (INCREMENTAL, 4, 0)
    same(first, run(world, T1, full=True, write=False))


def test_a_full_run_then_an_incremental_one_a_night_later_equals_a_full_run_that_night() -> None:
    w = build_world(closed=DAYS[:-1] + [DAYS[-1]][:0])  # the last entry session is not closed
    first = run(w, T1)
    assert first.legs_computed == 3  # the last decision's window has not closed
    outcomes = [outcome_row(iid, i, next_session(DAYS[-1])) for i, iid in enumerate(IDS)]
    w.write_outcomes(next_session(DAYS[-1]), outcomes, T1 + timedelta(hours=1))
    night = run(w, T2, write=False)
    assert (night.legs_reused, night.legs_computed) == (3, 1)  # only the leg that closed
    assert dict(night.legs_invalidated) == {}
    same(night, run(w, T2, full=True, write=False))


def test_an_unmeasured_rewrite_of_an_outcome_recomputes_exactly_that_leg(world: World) -> None:
    run(world, T1)
    entry = next_session(D2)
    bad = [
        outcome_row(iid, i, entry, outcome_status="UNMEASURED", fwd_return=None,
                    fwd_excess_return=None, fwd_max_return=None, fwd_max_drawdown=None,
                    fwd_realised_vol=None, outcome_reason="BAD_BAR")
        if i < 4 else outcome_row(iid, i, entry)
        for i, iid in enumerate(IDS)
    ]  # fmt: skip
    world.write_outcomes(entry, bad, T1 + timedelta(hours=1))
    night = run(world, T2, write=False)
    assert (night.legs_computed, night.legs_reused) == (1, 3)
    assert dict(night.legs_invalidated) == {"outcomes": 1}
    full = run(world, T2, full=True, write=False)
    same(night, full)
    assert rows(night)["excluded_unmeasured"].sum() == rows(full)["excluded_unmeasured"].sum()


def test_an_outcome_commit_after_the_legs_read_it_recomputes_even_with_an_old_timestamp(
    world: World,
) -> None:
    """The outcome partition's commit sequence, not only its rows' ``knowledge_ts``: a revision
    stamped before the leg's read but committed after it still changes the leg."""
    run(world, T1)
    entry = next_session(D3)
    recommit(
        world, FORWARD_RETURNS, entry, "late", [outcome_row(i, k, entry) for k, i in enumerate(IDS)]
    )
    night = run(world, T2, write=False)
    assert dict(night.legs_invalidated) == {"outcomes": 1} and night.legs_computed == 1
    same(night, run(world, T2, full=True, write=False))


def test_a_recommitted_feature_partition_recomputes_exactly_the_legs_of_its_session(
    world: World,
) -> None:
    run(world, T1)
    recommit(world, FEATURE, D2, "restated", expensive(D2))
    night = run(world, T2, write=False)
    assert (night.legs_computed, night.legs_reused) == (1, 3)
    assert dict(night.legs_invalidated) == {"inputs": 1}
    same(night, run(world, T2, full=True, write=False))
    # a feature partition of a session no decision read leaves every leg as it is
    other = DAYS[1]
    recommit(world, FEATURE, other, "restated-2", expensive(other))
    assert run(world, T2, write=False).legs_computed == 1  # still only D2: the first is not stored


def test_a_restatement_of_a_session_no_leg_read_changes_nothing(world: World) -> None:
    run(world, T1)
    recommit(world, FEATURE, DAYS[1], "restated", expensive(DAYS[1]))  # not a decision session
    night = run(world, T2, write=False)
    assert (night.legs_computed, night.legs_reused) == (0, 4)


def snapshot(w: World, day: date) -> None:
    universe = universe_rows([f"N{i:02d}" for i in range(len(IDS))])
    w.writer.write_table("universe", day, f"u-{day}", stamped(universe, day, f"u-{day}"))


def test_a_new_snapshot_up_to_a_session_invalidates_it_and_one_after_it_does_not(
    world: World,
) -> None:
    run(world, T1)
    snapshot(world, DAYS[-1] + timedelta(days=10))  # after every decision session
    assert run(world, T2, write=False).legs_computed == 0
    snapshot(world, DAYS[1])  # after the first decision session, before the others
    night = run(world, T2, write=False)
    assert (night.legs_computed, night.legs_reused) == (3, 1)
    assert dict(night.legs_invalidated) == {"inputs": 3}
    same(night, run(world, T2, full=True, write=False))


def test_a_run_at_an_earlier_as_of_than_a_stored_leg_is_full(world: World) -> None:
    run(world, T1)
    early = T1 - timedelta(hours=1)
    historical = run(world, early, write=False)
    assert (historical.mode, historical.legs_reused, historical.legs_computed) == (FULL, 0, 4)
    same(historical, run(world, early, full=True, write=False))


def test_a_move_of_the_split_recomputes_only_the_sessions_whose_draws_are_missing(
    world: World,
) -> None:
    run(world, T1, frozen_from=DAYS[-1].isoformat())  # only the last decision is out of sample
    night = run(world, T2, write=False)  # the split is the document's: D3 and D4 now draw too
    assert (night.legs_computed, night.legs_reused) == (2, 2)
    assert dict(night.legs_invalidated) == {"draws": 2}
    same(night, run(world, T2, full=True, write=False))
    run(world, T2, frozen_from=DAYS[0].isoformat())
    later = run(world, T2, write=False)  # draws stored but the run needs none before its split
    same(later, run(world, T2, full=True, write=False))


def two_screeners(w: World) -> World:
    second = {**screen("asc"), "id": "momo2"}
    w.configs = MemoryConfigStore(
        {
            **w.configs._docs,  # type: ignore[attr-defined]
            ("site", "strategies", "momo2"): second,
        }
    )
    return w


def test_the_legs_of_a_dropped_screener_are_tombstoned_and_never_read_back(world: World) -> None:
    w = two_screeners(world)
    both = run(w, T1, screeners=["momo", "momo2"])
    assert both.legs_computed == 8
    kept = run(w, T2, screeners=["momo"])
    assert (kept.legs_reused, kept.legs_computed) == (4, 0)
    same(kept, run(w, T2, full=True, write=False, screeners=["momo"]))
    stored = read_legs(w.reader, "site", "drift", DAYS[0], DAYS[-1])
    assert len(stored.legs) == 4 and {i[2] for i in stored.legs} == {"momo"}
    raw = w.reader.table_range(TABLE, DAYS[0], DAYS[-1])
    assert raw is not None and int(raw["tombstone"].fillna(False).astype(bool).sum()) == 4
    back = run(w, T2, screeners=["momo", "momo2"], write=False)  # it returns: no leg of it stored
    assert (back.legs_reused, back.legs_computed) == (0, 8)  # a session is computed whole
    assert dict(back.legs_invalidated) == {"session": 4}


def key(day: date, who: str = "k") -> tuple[str, str, str, int, date]:
    return (who, "main", "momo", 2, day)


def leg(day: date, who: str = "k") -> LegRecord:
    return LegRecord(
        who,
        "t",
        "main",
        "momo",
        2,
        next_session(day),
        SessionStat(session=day, regime="UP"),
        T1,
        known=T1,
    )


def test_tombstones_retire_old_keys_everywhere_and_uncomputed_legs_at_rewritten_sessions() -> None:
    stored = StoredLegs(
        legs={
            key(D1): leg(D1),
            key(D2): leg(D2),
            key(D3): leg(D3),
            key(D4, "old"): leg(D4, "old"),
        }
    )
    reuse = Reuse(INCREMENTAL, reused={key(D1): leg(D1)})
    needs = [Need(key(D1), D1, False)]
    gone = tombstones(stored, reuse, [], needs, rewritten={D2, D1}, user_id="u", edge_id="e")
    assert sorted((r["leg_key"], r["session_date"]) for r in gone) == [("k", D2), ("old", D4)]
    assert all(r["tombstone"] is True and r["row_kind"] == "leg" for r in gone)


def test_a_lost_screener_error_is_rebuilt_from_the_stored_table() -> None:
    error = lost_error({D3: "rollups/instrument/x@v1", D2: "rollups/instrument/y@v1"})
    assert error.dataset == "rollups/instrument/y@v1" and D2.isoformat() in str(error)


def test_a_listing_up_to_the_session_is_checked_and_a_read_of_the_future_never_reusable() -> None:
    now = [D1, D2, D3]
    up_to = ReadRecord("t", D1, D2, "dates", dates_digest([D1, D2]))
    assert _listing_unchanged(up_to, D2, now)  # D3 is after the session: not part of the read
    assert not _listing_unchanged(up_to, D2, [D1 - timedelta(days=1), *now])
    future = ReadRecord("t", D1, D3, "dates", dates_digest([D1, D3]))
    assert not _listing_unchanged(future, D2, [D1, D3])
    earliest = ReadRecord("t", D3, D3, "dates", dates_digest([D3]))
    assert _listing_unchanged(earliest, D1, [D3, D3 + timedelta(days=1)])
    assert not _listing_unchanged(earliest, D1, [D2, D3])  # an earlier snapshot is the earliest
    nothing = ReadRecord("t", D2, D2, "dates", dates_digest([]))
    assert _listing_unchanged(nothing, D2, [D3]) and not _listing_unchanged(nothing, D2, [D1])


def test_a_session_whose_reads_log_is_not_stored_is_computed_again(world: World) -> None:
    """Its legs hold nothing to check them against: a stored leg alone is never reused."""
    run(world, T1)
    found = read_legs(world.reader, "site", "drift", DAYS[0], DAYS[-1])
    assert set(found.reads) == {D1, D2, D3, D4} and isinstance(found.reads[D1], DayReads)
    feature = [r for r in found.reads[D2].reads if r.table == FEATURE]
    assert [(r.kind, r.digest) for r in feature] == [("rows", dates_digest([D2]))]
    without = StoredLegs(legs=found.legs, reads={d: r for d, r in found.reads.items() if d != D2})
    ev = evaluate_with(world, without)
    assert (ev.legs_computed, ev.legs_reused) == (1, 3)
    assert dict(ev.legs_invalidated) == {"inputs": 1}


def evaluate_with(w: World, stored: StoredLegs) -> EdgeEvaluation:
    """A run whose store holds ``stored`` (the legs and reads logs it was handed)."""
    target = "algotrade.services.evaluation.cross_section.harness.read_legs"
    with patch(target, return_value=stored):
        return run(w, T1, write=False)


def test_an_event_edge_reuses_its_legs_until_the_names_of_an_event_session_change() -> None:
    w = event_world(EVENTS)

    def go(at: datetime, *, full: bool = False) -> EdgeEvaluation:
        ev = evaluate_edge(
            w.reader, w.results, w.configs, UserContext("site"), event_edge(2), DAYS[0], DAYS[-1],
            at, full=full,
        )  # fmt: skip
        if not full:
            write_edge_eval(w.results, ev, at)
        return ev

    first = go(T1)
    again = go(T1)
    assert (first.legs_computed, again.legs_computed, again.legs_reused) == (3, 0, 3)
    same(first, again)
    # the schedule is read over the whole range on every run: a changed event set of a
    # session changes the names of its leg, whatever the reads log of that session says
    w.write_reactions(DAYS[5], {IDS[i]: 0 for i in (3, 4)})
    night = go(T2)
    assert (night.legs_computed, night.legs_reused) == (1, 2)
    assert dict(night.legs_invalidated) == {"events": 1}
    same(night, go(T2, full=True))


def test_sessions_a_screener_lost_to_a_missing_table_are_reused_as_lost(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real = session_reads.screen_variant

    def missing_on_second(reader: Any, config: Any, day: date) -> Any:
        if day == D2:
            raise MissingDataError(FEATURE, "no rows", "ingest")
        return real(reader, config, day)

    w = build_world()
    with monkeypatch.context() as patch:
        patch.setattr(session_reads, "screen_variant", missing_on_second)
        first = run(w, T1)
    again = run(w, T1)  # the screen would run now: the stored leg says it was lost
    assert (again.legs_reused, again.legs_computed) == (4, 0)
    same(first, again)
    assert dict(again.results[0].lost_sessions) == {FEATURE: 1}


def test_reused_sessions_still_count_in_the_historical_caveat_and_the_snapshot() -> None:
    w = with_listing_history(build_world(snapshot=DAYS[3]), DAYS[3])  # two decisions precede it
    first = run(w, T1)
    again = run(w, T1)
    assert (again.legs_reused, again.legs_computed) == (4, 0)
    assert first.historical is not None and first.historical.sessions == 2
    assert again.historical == first.historical and again.snapshot == first.snapshot
    same(first, again)
