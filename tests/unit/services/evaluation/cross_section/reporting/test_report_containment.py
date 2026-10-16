"""The report-containment diagnostic of an ``on_event:earnings_expected`` edge: a window whose
real report fell outside it counts in the denominator, not the numerator, and the picks and hits
are identical with and without the diagnostic (it is read after the outcomes, never an input)."""

from datetime import UTC, date, datetime, timedelta

import pandas as pd

from algotrade.config.user import UserContext
from algotrade.services.evaluation.cross_section.harness import evaluate_edge
from algotrade.services.evaluation.cross_section.legs.reuse import FULL, INCREMENTAL
from algotrade.services.evaluation.cross_section.reporting.report import render_edge_report
from algotrade.services.evaluation.cross_section.results import (
    lost_sessions,
    report_containment,
    write_edge_eval,
)
from tests.helpers.stored_frames import stamped
from tests.unit.services.evaluation.cross_section.conftest import (
    DAYS,
    IDS,
    World,
    build_world,
    edge,
)
from tests.unit.services.evaluation.cross_section.test_harness import run

EXPECTED = "rollups/instrument/earnings_expected@v1"
D = DAYS[1]  # Sept 2: the expected report is today (sessions_to_expected_report 0 = offset 1)
INSIDE, OUTSIDE = date(2026, 9, 4), date(2026, 9, 20)  # the window is S = Sept 3 .. Sept 8


def world_with(reports: dict[int, date], *, store: bool = True) -> World:
    w = build_world()
    rows = [
        {"instrument_id": IDS[i], "sessions_to_expected_report": 0, "expected_report_date": D}
        for i in (10, 11, 12)
    ]
    w.writer.write_table(EXPECTED, D, "e1", stamped(rows, D, "e1"))
    if store:
        stored = date(2026, 10, 1)  # a backfill: stored late, known from the report day
        found = [
            {
                "instrument_id": IDS[i], "ts": pd.Timestamp(day, tz="UTC"), "time": "pre_market",
                "known_from": day, "reported": True,
            }
            for i, day in reports.items()
        ]  # fmt: skip
        w.writer.write_table("events/earnings", stored, "e2", stamped(found, stored, "e2"))
    return w


def expected_edge():  # type: ignore[no-untyped-def]
    outcome = {
        "kind": "excess_return", "horizon_sessions": [2], "benchmark": "SPY",
        "start_offset_sessions": 1,
    }  # fmt: skip
    return edge(schedule="on_event:earnings_expected", top_k="all", outcome=outcome)


def test_a_window_whose_real_report_fell_outside_counts_in_the_denominator_only() -> None:
    ev = run(world_with({10: INSIDE, 11: OUTSIDE}), expected_edge())
    (c,) = [r.report_containment for r in ev.results]
    assert c is not None
    # Name 10 reported inside the window; 11 after it; 12 has no stored report.
    assert (c.windows, c.contained, c.no_report) == (3, 1, 1)
    assert c.share == 1 / 3
    (row,) = report_containment(ev)
    assert (row["windows"], row["contained"], row["horizon"]) == (3, 1, 2)
    text = render_edge_report(
        {
            "edge": "drift", "run_id": "r", "trials": 1, "survivorship": {},
            "unclosed_sessions": {}, "lost_sessions": lost_sessions(ev),
            "report_containment": report_containment(ev), "rows": [],
        }
    )  # fmt: skip
    assert "contained the report: 33% of 3 windows" in text


def test_the_picks_and_hits_are_identical_with_and_without_the_diagnostic() -> None:
    with_reports = run(world_with({10: INSIDE, 11: OUTSIDE}), expected_edge())
    without = run(world_with({}, store=False), expected_edge())
    assert [r.stats for r in with_reports.results] == [r.stats for r in without.results]
    assert [r.measures for r in with_reports.results] == [r.measures for r in without.results]
    assert without.results[0].report_containment is not None
    assert without.results[0].report_containment.contained == 0  # none stored: all missing


def test_an_edge_without_the_expected_report_schedule_has_no_diagnostic() -> None:
    ev = run(build_world(), edge())
    assert [r.report_containment for r in ev.results] == [None]
    assert report_containment(ev) == []


def test_an_earnings_expected_edge_run_incrementally_reuses_its_legs_and_keeps_the_diagnostic() -> (
    None
):
    w = world_with({10: INSIDE, 11: OUTSIDE})

    def go(at: datetime, *, full: bool = False):  # type: ignore[no-untyped-def]
        ev = evaluate_edge(
            w.reader, w.results, w.configs, UserContext("site"), expected_edge(),
            DAYS[0], DAYS[-1], at, full=full,
        )  # fmt: skip
        if not full:
            write_edge_eval(w.results, ev, at)
        return ev

    t1 = datetime(2026, 10, 6, 12, tzinfo=UTC)
    first = go(t1)
    again = go(t1)
    assert (first.legs_computed, first.legs_reused) != (0, 0)
    assert (again.mode, again.legs_computed) == (INCREMENTAL, 0) and again.legs_reused > 0
    full = go(t1 + timedelta(hours=1), full=True)
    assert full.mode == FULL
    assert [r.report_containment for r in again.results] == [
        r.report_containment for r in full.results
    ]
    assert next(r.report_containment for r in again.results) is not None
    assert [r.stats for r in again.results] == [r.stats for r in full.results]
    assert [r.measures for r in again.results] == [r.measures for r in full.results]
