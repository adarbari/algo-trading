"""``evaluate_edge``: a known result by hand, exclusions that are never misses, picks that never
see an outcome (the lookahead tests), a deterministic result, and the trial count."""

import dataclasses
import random
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest

from algotrade.config.user import UserContext
from algotrade.core.model.errors import ConfigurationError, MissingDataError
from algotrade.core.time.calendar import sessions_between
from algotrade.services.configs import resolve_config
from algotrade.services.evaluation.cross_section.harness import EdgeEvaluation, _pbo, evaluate_edge
from algotrade.services.evaluation.cross_section.picks import screen_variant
from algotrade.services.evaluation.cross_section.results import write_edge_eval
from algotrade.storage.configs.files import MemoryConfigStore
from tests.helpers.stored_frames import stamped
from tests.unit.services.evaluation.cross_section.conftest import (
    ACTIVE,
    AS_OF,
    DAYS,
    IDS,
    PRICE,
    N,
    World,
    build_world,
    edge,
    outcome_row,
    screen,
)  # fmt: skip

USER = UserContext("site")
STARTS = [DAYS[0], DAYS[2], DAYS[4], DAYS[6]]  # every 2nd session of Sept 1-10


def run(w: World, e=None, as_of: datetime = AS_OF) -> EdgeEvaluation:  # type: ignore[no-untyped-def]
    return evaluate_edge(
        w.reader, w.results, w.configs, USER, e or edge(), DAYS[0], DAYS[-1], as_of
    )


def test_a_known_result_by_hand(world: World) -> None:
    ev = run(world)
    (r,) = ev.results
    m = r.measures[0]
    # Name i earns (i - 9.5)%: the top 5 (i = 15..19) all hit, half of the 20 names do.
    assert (m.sessions, m.picks, m.hits, m.eligible, m.base_hits) == (4, 20, 20, 80, 40)
    assert (m.hit_rate, m.base_rate, m.lift) == (1.0, 0.5, 2.0)
    assert m.mean_excess_picks == pytest.approx(0.075)
    assert m.bh_mean == pytest.approx(0.0, abs=1e-12)  # the floor: the eligible mean
    assert m.top_decile_mean == pytest.approx(0.09)  # names 18, 19
    assert m.decile_spread == pytest.approx(0.18)  # 0.09 - (-0.09)
    assert m.decile_sessions == 4
    assert [s.session for s in r.stats] == STARTS
    assert ev.start_sessions == {2: 4} and ev.unclosed_sessions == {2: 0}
    assert ev.trials == 1 and m.trials == 1
    assert [x.slice_kind for x in r.measures] == ["all", "year", "regime"]  # no frozen slice
    assert [x.slice_value for x in r.measures] == ["all", "2026", "UNKNOWN"]


def test_a_frozen_period_is_reported_only_when_the_document_sets_it(world: World) -> None:
    frozen = run(world, edge(frozen_from="2026-09-04")).results[0].measures[-1]
    assert (frozen.slice_kind, frozen.sessions) == ("frozen", 2)  # Sept 4 and 8 starts


def test_an_unclosed_or_null_window_is_excluded_never_a_miss() -> None:
    def rows(day: date) -> list[dict[str, Any]]:
        out = [outcome_row(iid, i, day) for i, iid in enumerate(IDS) if i != 19]  # 19: not closed
        out[18] = outcome_row(IDS[18], 18, day, fwd_excess_return=float("nan"))  # 18: no benchmark
        return out

    first = run(build_world(rows_of=rows)).results[0].stats[0]
    assert (first.excluded_unclosed, first.excluded_missing) == (1, 1)
    assert first.pick_hits == len(first.pick_values) == 3  # the other three picks, all hits
    assert first.eligible == 18  # neither name is in the base rate


def test_a_start_session_with_no_closed_window_is_counted_not_measured() -> None:
    ev = run(build_world(closed=DAYS[:6]))  # nothing stored for the Sept 9 start session
    assert ev.unclosed_sessions == {2: 1} and ev.start_sessions == {2: 4}
    assert [s.session for s in ev.results[0].stats] == STARTS[:3]


def test_outcomes_known_after_as_of_are_invisible() -> None:
    w = build_world()
    with pytest.raises(MissingDataError):
        run(w, as_of=datetime(2026, 9, 1, tzinfo=UTC))


def test_picks_never_see_an_outcome_and_depend_only_on_their_own_session() -> None:
    base = build_world()
    config = resolve_config(base.configs, "momo", USER)
    day = DAYS[2]
    # Every outcome row changes: the picks and the ranking are identical.
    other = build_world()
    for d in DAYS:
        other.write_outcomes(
            d,
            [
                outcome_row(iid, N - i, d, fwd_excess_return=0.5 - i / 100)
                for i, iid in enumerate(IDS)
            ],
            known=datetime(2026, 9, 30, 23, tzinfo=UTC),
        )
    a, b = screen_variant(base.reader, config, day), screen_variant(other.reader, config, day)
    assert (a.ranking, a.qualified) == (b.ranking, b.qualified)
    # The next session's features are reversed: the picks at `day` are unchanged.
    flipped = build_world(price_of=lambda d, i: 100.0 + 10 * (i if d <= day else N - i))
    c = screen_variant(flipped.reader, config, day)
    assert (a.ranking, a.qualified) == (c.ranking, c.qualified)
    assert screen_variant(flipped.reader, config, DAYS[3]).qualified == tuple(
        IDS
    )  # the flip is real


def test_the_result_is_deterministic_whatever_the_stored_row_order() -> None:
    shuffled = build_world()
    for d in DAYS:
        rows = [outcome_row(iid, i, d) for i, iid in enumerate(IDS)]
        random.Random(d.toordinal()).shuffle(rows)
        shuffled.write_outcomes(d, rows, known=datetime(2026, 9, 30, 23, tzinfo=UTC))
    a, b = run(build_world()), run(shuffled)
    assert a.results == b.results
    assert dataclasses.replace(a, results=()) == dataclasses.replace(
        b, results=()
    )  # the run hash too


def test_the_trial_count_is_every_distinct_variant_hash_and_horizon_tried_before() -> None:
    w = build_world()
    first = run(w)
    write_edge_eval(w.results, first, AS_OF)
    again = run(w)
    assert again.trials == 1  # the same variant, the same hash, the same horizon: not a new trial
    w.configs = type(w.configs)(
        {
            ("site", "selections", "active"): w.configs.load("site", "selections", "active"),
            ("site", "strategies", "momo"): screen("asc"),  # another config hash: a new trial
        }
    )
    assert run(w).trials == 2


def test_the_run_hash_follows_the_document_the_range_and_the_as_of(world: World) -> None:
    base = run(world).run_hash
    assert base == run(world).run_hash
    assert run(world, edge(top_k=6)).run_hash != base
    assert run(world, as_of=AS_OF + timedelta(days=1)).run_hash != base


def test_an_event_schedule_and_an_edge_without_screeners_are_not_evaluated(world: World) -> None:
    with pytest.raises(ConfigurationError, match="ED4"):
        run(world, edge(schedule="on_event:earnings"))
    with pytest.raises(ConfigurationError, match="no screeners"):
        run(world, edge(screeners=[]))


def test_baselines_are_variants_and_probability_of_overfitting_needs_enough_sessions() -> None:
    days = sessions_between(date(2026, 8, 3), date(2026, 9, 25))  # 40 sessions: 20 starts
    w = build_world(
        days,
        rows_of=lambda d: [
            outcome_row(x, i, d, fwd_excess_return=(i - 9.5) / 100 + d.day / 1000)
            for i, x in enumerate(IDS)
        ],
    )
    w.configs = type(w.configs)(
        {
            ("site", "selections", "active"): w.configs.load("site", "selections", "active"),
            ("site", "strategies", "momo"): screen(),
            ("site", "strategies", "dearest_last"): {**screen("asc"), "id": "dearest_last"},
        }
    )
    e = edge(baselines=["dearest_last"])
    ev = evaluate_edge(w.reader, w.results, w.configs, USER, e, days[0], days[-1], AS_OF)
    assert [(r.variant, r.role) for r in ev.results] == [
        ("momo", "screener"),
        ("dearest_last", "baseline"),
    ]
    assert ev.trials == 2
    best, worst = (r.measures[0] for r in ev.results)
    assert best.hit_rate == 1.0 and worst.hit_rate == 0.0
    assert best.pbo == worst.pbo is not None  # one number per edge and horizon
    assert best.deflated_sharpe is not None


def test_a_ratio_measure_divides_the_realised_vol_by_the_implied_vol_known_at_the_start() -> None:
    vrp = {
        "kind": "hit_target", "horizon_sessions": [2], "benchmark": "none", "target": 1.0,
        "measure": "realised_to_implied_vol", "direction": "below",
    }  # fmt: skip

    def rows(day: date) -> list[dict[str, Any]]:
        return [
            outcome_row(iid, i, day, fwd_realised_vol=0.2 if i >= 10 else 0.6)
            for i, iid in enumerate(IDS)
        ]

    w = build_world(rows_of=rows)
    for day in DAYS:  # IV30 of 0.4 everywhere, but N19's is not stored
        iv = [{"instrument_id": iid, "iv30": 0.4} for iid in IDS[:-1]]
        w.writer.write_table(
            "rollups/instrument/iv30@v1", day, f"iv-{day}", stamped(iv, day, f"iv-{day}")
        )
    first = run(w, edge(outcome=vrp)).results[0].stats[0]
    assert first.pick_values == pytest.approx((-0.5,) * 4)  # 0.2 / 0.4 oriented: lower is better
    assert first.pick_hits == 4 and first.excluded_missing == 1  # N19: no IV30, excluded
    assert first.base_hits == 9 and first.eligible == 19


def test_a_session_whose_screen_read_incomplete_data_is_not_measured_but_counted() -> None:
    ev = run(build_world(no_features=[DAYS[2]]))  # the Sept 3 screen finds no feature table
    (r,) = ev.results
    m = r.measures[0]
    assert (m.sessions, m.excluded_coverage) == (3, 1)  # four start sessions, one not measured
    assert m.picks == 15  # nothing from the incomplete session reaches the pooled numbers


def test_trials_are_counted_per_user_and_the_regime_label_is_the_sites() -> None:
    w = build_world()
    write_edge_eval(w.results, run(w), AS_OF)
    other = evaluate_edge(
        w.reader, w.results, w.configs, UserContext("bob"), edge(), DAYS[0], DAYS[-1], AS_OF
    )
    assert other.trials == 1 and other.user_id == "bob"  # site's earlier trial is not bob's
    assert write_edge_eval(w.results, other, AS_OF).job == "edge-eval:drift:bob"


def test_the_probability_of_overfitting_leaves_out_sessions_a_variant_held_nothing() -> None:
    days = sessions_between(date(2026, 8, 3), date(2026, 9, 25))
    w = build_world(days)
    w.configs = type(w.configs)(
        {
            ("site", "selections", "active"): w.configs.load("site", "selections", "active"),
            ("site", "strategies", "momo"): screen(),
            ("site", "strategies", "other"): {**screen("asc"), "id": "other"},
        }
    )
    ev = evaluate_edge(
        w.reader, w.results, w.configs, USER, edge(baselines=["other"]), days[0], days[-1], AS_OF
    )
    peers = list(ev.results)
    assert _pbo(peers) is not None
    held = tuple(dataclasses.replace(s, pick_values=()) for s in peers[1].stats)
    nothing = [peers[0], dataclasses.replace(peers[1], stats=held)]
    assert _pbo(nothing) is None  # no session where both held something: no guess at zero


def test_session_without_scores_is_excluded_not_ranked() -> None:
    # No name has a stored score on the first session (a rule screen still grades it COMPLETE).
    w = build_world(price_of=lambda d, i: None if d == DAYS[0] else 100.0 + 10 * i)  # type: ignore[arg-type,return-value]
    m = run(w).results[0].measures[0]
    assert m.excluded_coverage == 1  # one start session is never ranked
    assert m.sessions == 3 and m.decile_sessions == 3
    assert m.top_decile_mean is not None and m.top_decile_mean == pytest.approx(0.09)


def test_deciles_rank_by_edge_score_not_rule_rank() -> None:
    # Ascending score: the cheapest names score best, and they are REJECTed (price <= 150).
    rule = {**screen("asc"), "criteria": {"price": {"field": PRICE, "op": "gt", "value": 150}}}
    w = build_world(price_of=lambda d, i: None if i == N - 1 else 100.0 + 10 * i)  # type: ignore[arg-type,return-value]
    w.configs = MemoryConfigStore(
        {("site", "selections", "active"): ACTIVE, ("site", "strategies", "momo"): rule}
    )
    m = run(w).results[0].measures[0]
    # Top decile = the 2 best scores of the 19 scored names (N00, N01: rejects), not the
    # qualified names the rule rank puts first.
    assert m.top_decile_mean == pytest.approx(-0.09)
    assert m.unscored == 4  # N19 has no price on any of the 4 sessions: outside the deciles


def test_score_coverage_boundary() -> None:
    def measured(unscored: int) -> int:
        w = build_world(price_of=lambda d, i: None if i < unscored else 100.0 + 10 * i)  # type: ignore[arg-type,return-value]
        return run(w).results[0].measures[0].sessions

    assert measured(4) == 4  # 16 of 20 scored: exactly 80%, measured
    assert measured(5) == 0  # 75%: not measured
