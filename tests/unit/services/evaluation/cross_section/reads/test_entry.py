"""``read_entries`` (ADR 0088, design 2.4a, E13): each close t of the wait is read from t's own
partition, the first TRUE close gives S = t + the offset (so S >= t + 1, never t), a name never TRUE
is NOT_TRIGGERED, an UNKNOWN close first is ENTRY_UNKNOWN, a market gap at a reached close loses
the leg; ``entered_rows`` takes each name's row at its own S; ``check_entry`` refuses at run start
what cannot be measured (G9-M3, G9-M4). Through ``evaluate_edge``: each name enters at its own
S, picks and base alike, so a rule that alone explains the returns gives no lift (risk 22); names
never entered are counted, never misses; what a name reads after its entering close changes
nothing; the result is deterministic; an S a name entered at with no partition loses the leg."""

from collections.abc import Callable
from datetime import date
from typing import Any

import pandas as pd
import pytest

from algotrade.config.edges.positions.cases import EntrySpec
from algotrade.config.strategy.schema import parse_group
from algotrade.config.user import UserContext
from algotrade.core.model.errors import ConfigurationError
from algotrade.core.time.calendar import next_session
from algotrade.core.views.market_features import MARKET_FEATURES
from algotrade.engines.selection.entry import ENTRY_UNKNOWN, NOT_TRIGGERED
from algotrade.services.evaluation.cross_section.harness import EdgeEvaluation, evaluate_edge
from algotrade.services.evaluation.cross_section.reads import entry as entry_reads
from algotrade.services.evaluation.cross_section.reads.entry import (
    Entered,
    check_entry,
    entered_rows,
    read_entries,
)
from algotrade.services.features import site_features
from tests.unit.services.evaluation.cross_section.conftest import (
    AS_OF,
    DAYS,
    IDS,
    World,
    build_world,
    edge,
    outcome_row,
)

SIGNAL_TABLE = "rollups/instrument/price_stats@v2"
SIGNAL = "rollup.price_stats@v2.adv_usd_20d"
POSITIVE = parse_group({"all": [{"field": SIGNAL, "op": "gt", "value": 0}]}, "entry")
D = DAYS[0]


def signal_world(value: Callable[[date, int], float | None], days: list[date]) -> World:
    """The store with the signal of name i at each of ``days`` (None: no row for the name)."""
    w = build_world()
    for day in days:
        rows = [
            {"instrument_id": iid, "adv_usd_20d": v}
            for i, iid in enumerate(IDS)
            if (v := value(day, i)) is not None
        ]
        w.write_rollup(SIGNAL_TABLE, day, rows)
    return w


def closes(n: int) -> list[date]:
    out = [D]
    while len(out) < n:
        out.append(next_session(out[-1]))
    return out


def test_the_first_true_close_gives_s_after_it_read_from_that_close_only() -> None:
    wait = closes(3)
    # name i turns positive at close i % 3 of the wait; partition t holds only t's value
    w = signal_world(lambda day, i: 1.0 if wait.index(day) >= i % 3 else -1.0, wait)
    found = read_entries(w.reader, EntrySpec(POSITIVE, 3), 1, IDS[:6], D)
    for i, iid in enumerate(IDS[:6]):
        t = wait[i % 3]
        assert found.at[iid] == next_session(t) > t  # S = t + 1: never t's own close
    assert found.closes == tuple(wait) and not found.reasons


def test_a_later_partition_never_moves_an_earlier_decision() -> None:
    wait = closes(2)
    # TRUE only in the second close's partition: nobody enters after the first close
    w = signal_world(lambda day, i: 1.0 if day == wait[1] else -1.0, wait)
    found = read_entries(w.reader, EntrySpec(POSITIVE, 2), 2, IDS[:3], D)
    s = next_session(next_session(wait[1]))  # t = the second close, offset 2
    assert set(found.at.values()) == {s}


def test_never_true_is_not_triggered_and_unknown_first_is_entry_unknown() -> None:
    wait = closes(2)
    w = signal_world(lambda day, i: None if i == 1 else -1.0, wait)  # name 1 has no row
    found = read_entries(w.reader, EntrySpec(POSITIVE, 2), 1, IDS[:3], D)
    assert found.reasons == {IDS[0]: NOT_TRIGGERED, IDS[1]: ENTRY_UNKNOWN, IDS[2]: NOT_TRIGGERED}
    assert not found.at


def test_a_market_gap_at_a_reached_close_loses_the_leg(monkeypatch: Any) -> None:
    w = signal_world(lambda day, i: -1.0, closes(2))
    rule = parse_group(
        {"all": [{"field": "market.market_conditions@v1.vix", "op": "lt", "value": 30}]}, "entry"
    )
    monkeypatch.setattr(entry_reads, "session_market", lambda r, names, day: dict.fromkeys(names))
    found = read_entries(w.reader, EntrySpec(rule, 2), 1, IDS[:3], D)
    assert (found.gap, found.at, found.reasons) == (MARKET_FEATURES, {}, {})


def test_entered_rows_take_each_name_from_its_own_s() -> None:
    s1, s2 = date(2026, 9, 2), date(2026, 9, 3)
    by_entry = {
        s1: pd.DataFrame({"instrument_id": ["a", "b"], "v": [1.0, 2.0]}),
        s2: pd.DataFrame({"instrument_id": ["a", "b"], "v": [3.0, 4.0]}),
    }
    rows, missing = entered_rows(by_entry, Entered({"a": s2, "b": s1}, {"c": NOT_TRIGGERED}), s2)
    assert missing is None and rows is not None
    assert dict(zip(rows["instrument_id"], rows["v"], strict=True)) == {"a": 3.0, "b": 2.0}
    rows, missing = entered_rows(by_entry, Entered({"a": date(2026, 9, 4)}), s2)
    assert (rows, missing) == (None, date(2026, 9, 4))  # no partition: the leg is lost
    rows, _ = entered_rows(by_entry, Entered({}, {"a": NOT_TRIGGERED}), s2)
    assert rows is not None and rows.empty


def _entry_edge(**outcome: Any) -> Any:
    doc = {
        "kind": "excess_return", "horizon_sessions": [2], "benchmark": "SPY",
        "start_offset_sessions": 1, "entry": {"when": {"all": [
            {"field": SIGNAL, "op": "gt", "value": 0}]}, "within_sessions": 2},
    }  # fmt: skip
    return edge(outcome={**doc, **outcome})


def test_a_rule_field_with_no_rows_over_the_run_is_refused_at_run_start() -> None:
    w = build_world()  # no signal stored
    with pytest.raises(ConfigurationError, match=r"G9-M4"):
        check_entry(w.reader, _entry_edge(), site_features(), DAYS[0], DAYS[-1], AS_OF)
    w.write_rollup(SIGNAL_TABLE, DAYS[3], [{"instrument_id": IDS[0], "adv_usd_20d": 1.0}])
    check_entry(w.reader, _entry_edge(), site_features(), DAYS[0], DAYS[-1], AS_OF)


def test_an_entry_on_an_option_pnl_outcome_is_refused_until_the_writers_cover_the_wait() -> None:
    w = build_world()
    option = edge(
        outcome={
            "kind": "option_pnl", "horizon_sessions": [2], "benchmark": "none",
            "start_offset_sessions": 1, "position": "short_put", "strike_delta": 0.3,
            "tenor_days": 30,
            "entry": {"when": {"all": [{"field": SIGNAL, "op": "gt", "value": 0}]}},
        }
    )  # fmt: skip
    with pytest.raises(ConfigurationError, match=r"G9-M3"):
        check_entry(w.reader, option, site_features(), DAYS[0], DAYS[-1], AS_OF)


def test_a_pair_spread_with_an_entry_condition_is_refused() -> None:
    w = signal_world(lambda day, i: 1.0, closes(1))
    pair = _entry_edge(
        kind="pair_spread", benchmark="none", pair_field="rollup.share_classes@v1.sibling_id"
    )
    with pytest.raises(ConfigurationError, match=r"pair_spread"):
        check_entry(w.reader, pair, site_features(), DAYS[0], DAYS[0], AS_OF)


# The harness end to end (evaluate_edge)

USER = UserContext("site")
STARTS = [DAYS[0], DAYS[2], DAYS[4], DAYS[6]]  # every 2nd session (horizon 2, a wait of 1)
SPACED = [DAYS[0], DAYS[3], DAYS[6]]  # a wait of 2: h + wait - 1 = 3 sessions apart
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


def run(w: World, wait: int, full: bool = False) -> EdgeEvaluation:
    return evaluate_edge(
        w.reader, w.results, w.configs, USER, entry_edge(wait), DAYS[0], DAYS[-1], AS_OF,
        full=full,
    )  # fmt: skip


def odd_waits(day: date, i: int) -> float:
    """Even names hold at every close; odd ones only off the decision sessions (one close later)."""
    return 1.0 if i % 2 == 0 or day not in SPACED else -1.0


def test_each_name_enters_at_its_own_s_after_the_close_its_rule_held() -> None:
    (r,) = run(world(odd_waits), wait=2).results
    assert [s.session for s in r.stats] == SPACED  # the cohort is D; windows never overlap
    for s in r.stats:
        d1 = next_session(s.session)
        got = {p.instrument_id: p.entry_session for p in s.picks}
        for i, iid in enumerate(IDS[15:], start=15):
            assert got[iid] == (d1 if i % 2 == 0 else next_session(d1))  # S = t + 1, t >= D
        assert (s.not_triggered, s.entry_unknown, s.no_entry_bar) == (0, 0, 0)


def test_what_a_name_reads_after_its_entering_close_changes_nothing() -> None:
    later = world(lambda d, i: odd_waits(d, i) if d in SPACED or i % 2 else -5.0)
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


def test_a_full_run_still_refuses_what_an_entry_condition_cannot_measure() -> None:
    w = build_world()  # no signal stored: the rule would be UNKNOWN everywhere (G9-M4)
    with pytest.raises(ConfigurationError, match=r"G9-M4"):
        run(w, 2, full=True)
