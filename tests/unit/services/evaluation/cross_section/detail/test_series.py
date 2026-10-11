"""The per-session series (ADR 0064): one row per measured block of the main edge variant, its
exit session from the calendar, ``before_split`` decided by the run's split, a status for every
block that holds no number, and the rows published with the run or not at all."""

from datetime import date, datetime

import pytest

from algotrade.config.user import UserContext
from algotrade.core.time.calendar import next_session
from algotrade.services.evaluation.cross_section.detail.series import _status, edge_series_frame
from algotrade.services.evaluation.cross_section.detail.windows import BlockWindow
from algotrade.services.evaluation.cross_section.harness import evaluate_edge
from algotrade.services.evaluation.cross_section.measures import SessionStat
from algotrade.services.evaluation.cross_section.results import write_edge_eval
from algotrade.storage.tables.edge_schemas import EDGE_SERIES
from tests.unit.services.evaluation.cross_section.conftest import (
    AS_OF,
    DAYS,
    World,
    edge,
)

NOW = datetime(2026, 10, 6, 12, tzinfo=AS_OF.tzinfo)
SPLIT = DAYS[4]  # the decisions of DAYS[0], [2] are in sample, [4], [6] out of sample
DECISIONS = [DAYS[0], DAYS[2], DAYS[4], DAYS[6]]


def evaluated(w: World, **changes: object):  # type: ignore[no-untyped-def]
    return evaluate_edge(
        w.reader, w.results, w.configs, UserContext("site"), edge(**changes),
        DAYS[0], DAYS[-1], AS_OF,
    )  # fmt: skip


def test_one_row_per_measured_block_with_the_calendar_close_of_its_window(world: World) -> None:
    frame = edge_series_frame(evaluated(world, frozen_from=SPLIT.isoformat()), "r", NOW)
    assert list(frame["decision_session"]) == DECISIONS
    assert list(frame["entry_session"]) == [next_session(d) for d in DECISIONS]  # D + offset 1
    assert list(frame["exit_session"]) == [
        next_session(next_session(e)) for e in frame["entry_session"]
    ]
    assert set(frame["status"]) == {"measured"} and set(frame["unit"]) == {"excess_return"}
    assert list(frame["before_split"]) == [True, True, False, False]
    assert (frame["picks"] == 5).all() and (frame["eligible"] == 20).all()
    assert frame["pick_mean"].gt(frame["base_mean"]).all()  # the screen ranks by the outcome


def test_a_run_without_a_split_has_no_before_split_session(world: World) -> None:
    frame = edge_series_frame(evaluated(world), "r", NOW)
    assert not frame["before_split"].any() and frame["split_from"].isna().all()


def test_a_variant_of_the_edge_has_no_series_row(world: World) -> None:
    ev = evaluated(world)
    assert set(edge_series_frame(ev, "r", NOW)["variant"]) == {"momo"}
    assert set(edge_series_frame(ev, "r", NOW)["edge_variant"].fillna("main")) == {"main"}


def test_the_rows_are_published_with_the_run_and_match_the_schema(world: World) -> None:
    ev = evaluated(world, frozen_from=SPLIT.isoformat())
    record = write_edge_eval(world.results, ev, NOW)
    stored = world.reader.table("results/edge_series", ev.end)
    assert stored is not None and len(stored) == 4
    assert (stored["run_id"] == record.run_id).all()
    assert {c.name for c in EDGE_SERIES.columns} >= set(stored.columns)
    assert list(stored["before_split"]) == [True, True, False, False]


def test_a_crash_while_publishing_leaves_no_series(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    ev = evaluated(world)
    writer = world.results

    def crash(_: object) -> None:
        raise RuntimeError("disk full")

    monkeypatch.setattr(writer, "save_run", crash)
    with pytest.raises(RuntimeError):
        write_edge_eval(writer, ev, NOW)
    assert world.reader.table("results/edge_series", ev.end) is None


def test_a_block_with_no_picks_and_a_block_the_screen_could_not_measure_say_so() -> None:
    day = date(2026, 9, 1)
    window = BlockWindow(day, day)
    assert _status(SessionStat(day, "UNKNOWN"), window) == "no_picks"
    assert _status(SessionStat(day, "UNKNOWN", excluded_coverage=1), window) == "excluded_coverage"
    lost = BlockWindow(day, day, lost_table="rollups/x")
    assert _status(SessionStat(day, "UNKNOWN", excluded_coverage=1), lost) == "lost_input"
    stat = SessionStat(day, "UNKNOWN", pick_values=(0.1,))
    assert _status(stat, window) == "measured"
