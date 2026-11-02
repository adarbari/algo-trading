"""``evaluate_edge`` with an entry condition (ADR 0088, design 2.4a, E13): each name enters at
its own S (the first close of the wait its rule held, plus the offset), picks and base alike, so a
rule that alone explains the returns gives no lift (risk 22); names never entered are counted
(NOT_TRIGGERED, ENTRY_UNKNOWN), never misses; what a name's fields do after its entering close
changes nothing; the result is deterministic; an S a name entered at with no partition loses the
leg."""

from collections.abc import Callable
from datetime import date
from typing import Any

import pytest

from algotrade.config.user import UserContext
from algotrade.core.time.calendar import next_session
from algotrade.engines.selection.entry import ENTRY_UNKNOWN, NOT_TRIGGERED
from algotrade.services.evaluation.cross_section.harness import EdgeEvaluation, evaluate_edge
from tests.unit.services.evaluation.cross_section.conftest import (
    AS_OF,
    DAYS,
    IDS,
    World,
    build_world,
    edge,
    outcome_row,
)

USER = UserContext("site")
SIGNAL_TABLE = "rollups/instrument/price_stats@v2"
SIGNAL = "rollup.price_stats@v2.adv_usd_20d"
STARTS = [DAYS[0], DAYS[2], DAYS[4], DAYS[6]]  # every 2nd session (horizon 2)
AFTER = [next_session(DAYS[-1]), next_session(next_session(DAYS[-1]))]  # Sept 11, Sept 14
PICKS = IDS[15:]  # the screen's top 5 (dearest names)


def entry_edge(wait: int) -> Any:
    return edge(
        outcome={
            "kind": "excess_return", "horizon_sessions": [2], "benchmark": "SPY",
            "start_offset_sessions": 1,
            "entry": {"when": {"all": [{"field": SIGNAL, "op": "gt", "value": 0}]},
                      "within_sessions": wait},
        }
    )  # fmt: skip


def world(
    signal: Callable[[date, int], float | None],
    rows_of: Callable[[date], list[dict[str, Any]]] | None = None,
    closed: list[date] | None = None,
) -> World:
    """The harness store, outcomes stored through Sept 14 (the last wait's S), and the signal of
    name i at each session (None: no row)."""
    days = [*DAYS, *AFTER]
    w = build_world(rows_of=rows_of, closed=closed)
    for day in days:
        rows = [{"instrument_id": iid, "adv_usd_20d": v} for i, iid in enumerate(IDS)
                if (v := signal(day, i)) is not None]  # fmt: skip
        w.write_rollup(SIGNAL_TABLE, day, rows)
    if closed is None or AFTER[1] in closed:
        w.write_outcomes(AFTER[1], (rows_of or _rows)(AFTER[1]))
    return w


def _rows(day: date) -> list[dict[str, Any]]:
    return [outcome_row(iid, i, day) for i, iid in enumerate(IDS)]


def run(w: World, wait: int) -> EdgeEvaluation:
    return evaluate_edge(
        w.reader, w.results, w.configs, USER, entry_edge(wait), DAYS[0], DAYS[-1], AS_OF
    )


def odd_waits(day: date, i: int) -> float:
    """Even names hold at every close; odd ones only off the decision sessions (one close later)."""
    return 1.0 if i % 2 == 0 or day not in STARTS else -1.0


def test_each_name_enters_at_its_own_s_after_the_close_its_rule_held() -> None:
    (r,) = run(world(odd_waits), wait=2).results
    assert [s.session for s in r.stats] == STARTS  # the cohort is D
    for s in r.stats:
        d1 = next_session(s.session)
        got = {p.instrument_id: p.entry_session for p in s.picks}
        for i, iid in enumerate(IDS[15:], start=15):
            assert got[iid] == (d1 if i % 2 == 0 else next_session(d1))  # S = t + 1, t >= D
        assert (s.not_triggered, s.entry_unknown, s.no_entry_bar) == (0, 0, 0)


def test_what_a_name_reads_after_its_entering_close_changes_nothing() -> None:
    later = world(lambda d, i: odd_waits(d, i) if d in STARTS or i % 2 else -5.0)
    assert run(later, 2).results[0].stats == run(world(odd_waits), 2).results[0].stats


def test_a_rule_that_alone_explains_the_returns_gives_no_lift() -> None:
    def rows(day: date) -> list[dict[str, Any]]:  # even names earn +1%, odd names lose 1%
        earn = [0.01 if i % 2 == 0 else -0.01 for i in range(len(IDS))]
        return [
            outcome_row(iid, i, day, fwd_return=earn[i], fwd_excess_return=earn[i])
            for i, iid in enumerate(IDS)
        ]

    (r,) = run(world(lambda d, i: 1.0 if i % 2 == 0 else -1.0, rows), wait=1).results
    m = r.measures[0]
    assert (m.hit_rate, m.base_rate, m.lift) == (1.0, 1.0, 1.0)  # the base entered as the picks
    for s in r.stats:
        assert s.not_triggered == len(IDS) // 2
        assert [p.reason for p in s.picks if p.instrument_id in PICKS[::2]] == [NOT_TRIGGERED] * 3


def test_names_whose_rule_is_unknown_first_are_counted_never_misses() -> None:
    (r,) = run(world(lambda d, i: None if i < 4 or i == 19 else 1.0), wait=2).results
    for s in r.stats:
        assert (s.entry_unknown, s.not_triggered, s.no_entry_bar) == (5, 0, 0)
        assert next(p.reason for p in s.picks if p.instrument_id == IDS[19]) == ENTRY_UNKNOWN
        assert s.eligible == len(IDS) - 5  # not in the base rate either


def test_the_result_is_deterministic() -> None:
    a, b = run(world(odd_waits), 2), run(world(odd_waits), 2)
    assert a.results[0].stats == b.results[0].stats
    assert a.results[0].measures == b.results[0].measures


def test_an_s_a_name_entered_at_with_no_partition_loses_the_leg() -> None:
    gone = DAYS[2]  # the first leg's middle S (wait 3: S in DAYS[1..3])
    closed = [d for d in [*DAYS, *AFTER] if d != gone]
    (r,) = run(world(odd_waits, closed=closed), wait=3).results
    first = next(s for s in r.stats if s.session == DAYS[0])
    assert first.excluded_coverage == 1 and not first.picks


@pytest.mark.parametrize("wait", [1, 2])
def test_the_leg_is_measured_only_once_its_whole_wait_can_be_read(wait: int) -> None:
    closed = [d for d in [*DAYS, *AFTER] if d != AFTER[1]]  # no Sept 14 partition
    ev = run(world(odd_waits, closed=closed), wait)
    assert ev.unclosed_sessions == {2: 0 if wait == 1 else 1}
