"""``evaluate_edge``: a known result by hand, exclusions that are never misses, picks that never
see an outcome (the lookahead tests), a deterministic result, and the trial count."""

import dataclasses
import random
from datetime import UTC, date, datetime, timedelta
from typing import Any, ClassVar

import pytest

from algotrade.config.user import UserContext
from algotrade.core.model.errors import ConfigurationError, MissingDataError
from algotrade.core.time.calendar import sessions_between
from algotrade.services.configs import resolve_config
from algotrade.services.evaluation.cross_section.harness import (
    EdgeEvaluation,
    _pbo,
    _prior_trials,
    evaluate_edge,
)
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
    assert (first.no_entry_bar, first.excluded_missing) == (1, 1)
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


def test_an_edge_without_screeners_is_not_evaluated(world: World) -> None:
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
        "measure": "realised_to_implied_vol", "direction": "below", "start_offset_sessions": 1,
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
    assert (m.excluded_score_coverage, m.excluded_coverage) == (1, 0)  # never ranked
    assert m.sessions == 4 and m.decile_sessions == 3  # its picks still count
    assert m.picks == 15 and m.hits == 15 and m.unscored == 0  # the 3 ranked sessions' picks
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
        return run(w).results[0].measures[0].decile_sessions

    assert measured(4) == 4  # 16 of 20 scored: exactly 80%, ranked
    assert measured(5) == 0  # 75%: no deciles (the picks still count)


# ---- decision session D, entry session S (ADR 0053 amendment of 2026-10-08) ----------------


def _poisoned(rows_at: set[date]) -> World:
    """The world whose outcome partitions on ``rows_at`` hold nonsense (a huge loss)."""

    def rows(day: date) -> list[dict[str, Any]]:
        bad = day in rows_at
        return [
            outcome_row(iid, i, day, **({"fwd_excess_return": -9.0} if bad else {}))
            for i, iid in enumerate(IDS)
        ]

    return build_world(rows_of=rows)


def test_the_outcome_is_the_partition_at_the_entry_session_never_the_decision_session() -> None:
    clean = run(build_world())
    # Every decision session's own partition is poisoned: the window starts at S's close.
    poisoned = run(_poisoned(set(STARTS)))
    assert poisoned.results == clean.results
    # Poisoning an entry session (the day after each decision) changes it: S is what is read.
    assert run(_poisoned({d for d in DAYS if d not in STARTS})).results != clean.results


def test_the_screen_is_read_at_the_decision_session_not_the_entry_session() -> None:
    clean = run(build_world())
    # The features at every entry session are reversed: the picks and ranking at D do not move.
    flipped = build_world(price_of=lambda d, i: 100.0 + 10 * (i if d in STARTS else N - i))
    a, b = clean.results[0].stats, run(flipped).results[0].stats
    assert [(s.pick_hits, s.top_decile, s.spread) for s in a] == [
        (s.pick_hits, s.top_decile, s.spread) for s in b
    ]


def test_a_name_eligible_at_the_decision_with_no_row_at_the_entry_has_no_entry_bar() -> None:
    def rows(day: date) -> list[dict[str, Any]]:
        return [outcome_row(iid, i, day) for i, iid in enumerate(IDS) if i != 19]

    stat = run(build_world(rows_of=rows)).results[0].stats[0]
    assert stat.no_entry_bar == 1 and stat.excluded_unclosed == 0  # N19: counted here only
    assert stat.eligible == 19  # neither a hit nor a miss, and not in the base rate
    assert run(build_world()).results[0].stats[0].no_entry_bar == 0


def test_the_implied_vol_is_read_at_the_decision_session() -> None:
    vrp = {
        "kind": "hit_target", "horizon_sessions": [2], "benchmark": "none", "target": 1.0,
        "measure": "realised_to_implied_vol", "direction": "below", "start_offset_sessions": 1,
    }  # fmt: skip
    w = build_world()
    for day in [*DAYS, DAYS[-1] + timedelta(days=1)]:  # 0.4 at the decisions, 0.1 at the entries
        level = 0.4 if day in STARTS else 0.1
        iv = [{"instrument_id": iid, "iv30": level} for iid in IDS]
        w.writer.write_table(
            "rollups/instrument/iv30@v1", day, f"iv-{day}", stamped(iv, day, f"iv-{day}")
        )
    stat = run(w, edge(outcome=vrp)).results[0].stats[0]
    assert stat.pick_values == pytest.approx((-0.5,) * 5)  # 0.2 / 0.4 at D, not 0.2 / 0.1


def test_the_run_records_the_iv_field_its_source_and_licence() -> None:
    vrp = {
        "kind": "hit_target", "horizon_sessions": [2], "benchmark": "none", "target": 1.0,
        "measure": "realised_to_implied_vol", "direction": "below", "start_offset_sessions": 1,
    }  # fmt: skip
    w = build_world()
    for day in [*DAYS, DAYS[-1] + timedelta(days=1)]:
        iv = [{"instrument_id": iid, "iv30_ibkr": 0.4} for iid in IDS]
        w.writer.write_table(
            "rollups/instrument/ibkr_iv@v1", day, f"ib-{day}", stamped(iv, day, f"ib-{day}")
        )
    ibkr = "rollup.ibkr_iv@v1.iv30_ibkr"
    (r,) = evaluate_edge(
        w.reader, w.results, w.configs, USER, edge(outcome=vrp), DAYS[0], DAYS[-1], AS_OF, ibkr
    ).results
    assert (r.iv_source, r.licence) == (ibkr, "personal")  # the catalogue's, never assumed
    assert r.stats[0].pick_hits == 5  # read from IBKR's field
    (plain,) = run(w).results  # an outcome that reads no implied vol records none
    assert (plain.iv_source, plain.licence) == (None, None)
    with pytest.raises(ConfigurationError, match="mixes sources"):
        evaluate_edge(
            w.reader, w.results, w.configs, USER, edge(), DAYS[0], DAYS[-1], AS_OF,
            "feature.vrp_iv30",
        )  # fmt: skip
    with pytest.raises(ConfigurationError, match="not a catalogue feature"):
        evaluate_edge(
            w.reader, w.results, w.configs, USER, edge(outcome=vrp), DAYS[0], DAYS[-1], AS_OF,
            "rollup.nothing@v1.iv",
        )  # fmt: skip


# ---- event schedules: names at D, blocks of one horizon, one statistic per block ----------


def event_world(days_with: dict[date, list[int]]) -> World:
    """Names ``i`` have the reaction on a decision session: sessions-since 0 (= offset 1)."""
    w = build_world()
    for day, names in days_with.items():
        w.write_reactions(day, {IDS[i]: 0 for i in names})
    return w


def event_edge(horizon: int = 2, **changes: Any):  # type: ignore[no-untyped-def]
    outcome = {
        "kind": "excess_return", "horizon_sessions": [horizon], "benchmark": "SPY",
        "start_offset_sessions": 1,
    }  # fmt: skip
    return edge(schedule="on_event:earnings_reaction", top_k="all", outcome=outcome, **changes)


EVENTS = {DAYS[1]: [10, 11, 12], DAYS[2]: [15, 16], DAYS[5]: [0, 1, 2]}


def test_event_names_are_the_picks_and_the_base_and_blocks_pool_overlapping_windows() -> None:
    ev = run(event_world(EVENTS), event_edge(2))
    (r,) = ev.results
    # Sessions DAYS[1] and DAYS[2] are one block (fewer than 2 sessions apart): one statistic,
    # at the block's first day, pooling both days' names; DAYS[5] is the second block.
    assert [s.session for s in r.stats] == [DAYS[1], DAYS[5]]
    assert [len(s.pick_values) for s in r.stats] == [5, 3]
    assert ev.start_sessions == {2: 2} and ev.unclosed_sessions == {2: 0}
    first, second = r.stats
    # Names 10, 11, 12, 15, 16 earn (i - 9.5)%: all hit; names 0, 1, 2 lose.
    assert (first.pick_hits, second.pick_hits) == (5, 0)
    assert (first.eligible, second.eligible) == (5, 3)  # the base is the event names
    m = r.measures[0]
    assert (m.sessions, m.picks, m.hits, m.eligible, m.base_hits) == (2, 8, 5, 8, 5)
    assert m.lift == pytest.approx(1.0)  # picks = base: nothing to beat
    assert ev.event_unknown == {"no_event_row": 17 + 18 + 17}  # names with no row, by session


def test_overlapping_event_days_never_add_independent_sessions() -> None:
    # Events on two consecutive sessions have overlapping 2-session windows: one block, one
    # session; the same names matching again the next day are one event, not a second.
    w = event_world({DAYS[0]: [10, 11], DAYS[1]: [12, 10], DAYS[4]: [13]})
    r = run(w, event_edge(2)).results[0]
    assert [s.session for s in r.stats] == [DAYS[0], DAYS[4]]
    assert [len(s.pick_values) for s in r.stats] == [3, 1]  # N10 counted once (name, quarter)
    assert r.measures[0].sessions == 2


def test_a_universe_base_compares_the_event_names_with_every_eligible_name() -> None:
    ev = run(event_world(EVENTS), event_edge(2, base="universe"))
    (r,) = ev.results
    assert [len(s.pick_values) for s in r.stats] == [5, 3]
    assert [s.eligible for s in r.stats] == [
        N * 2,
        N,
    ]  # every eligible name, each session of a block


def test_an_event_session_whose_entry_is_not_closed_is_counted_not_measured() -> None:
    w = build_world(closed=[d for d in DAYS if d != DAYS[6]])  # DAYS[5]'s entry: nothing stored
    for day, names in EVENTS.items():
        w.write_reactions(day, {IDS[i]: 0 for i in names})
    ev = run(w, event_edge(2))
    assert ev.start_sessions == {2: 2} and ev.unclosed_sessions == {2: 1}
    assert [s.session for s in ev.results[0].stats] == [DAYS[1]]


def test_an_event_class_without_a_declared_field_is_refused() -> None:
    with pytest.raises(ConfigurationError, match="no declared field"):
        run(build_world(), edge(schedule="on_event:index_change", top_k="all"))


def test_an_event_edge_with_no_event_in_range_has_empty_blocks_not_a_guess() -> None:
    ev = run(event_world({}), event_edge(2))
    assert ev.results[0].stats == () and ev.results[0].measures[0].sessions == 0
    assert ev.start_sessions == {2: 0}


# ---- edge variants: [[variants]] evaluated like the edge, each a trial --------------------


CHEAP = {"where": {"all": [{"field": PRICE, "op": "lt", "value": 200}]}}  # names N00..N09


def test_each_variant_is_evaluated_under_its_own_key_and_is_a_trial() -> None:
    e = edge(
        variants=[
            {"id": "cheap", "universe": CHEAP},
            {"id": "costly", "outcome": {"cost_bps": 1500}},
        ]
    )
    w = build_world()
    ev = run(w, e)
    keys = [(r.edge_variant, r.variant) for r in ev.results]
    assert keys == [("main", "momo"), ("cheap", "momo"), ("costly", "momo")]
    assert ev.trials == 3 and ev.results[0].measures[0].trials == 3
    main, cheap, costly = (r.measures[0] for r in ev.results)
    assert main.eligible == 80 and cheap.eligible == 40  # the cheap names only
    assert main.hit_rate == 1.0 and costly.hit_rate < main.hit_rate  # 15% cost: top names miss
    assert [r.measures[0].trials for r in ev.results] == [3, 3, 3]
    # Re-running the same trials adds none: the trial key includes the edge variant.
    write_edge_eval(w.results, ev, AS_OF)
    assert run(w, e).trials == 3
    assert run(w, edge(variants=[{"id": "cheap", "universe": CHEAP}])).trials == 3


def test_a_trial_logged_before_edge_variants_is_the_edges_own() -> None:
    class Record:
        stats: ClassVar = {"trials": [{"variant": "momo", "config_hash": "h", "horizon": 2}]}

    class Writer:
        def runs_for(self, job: str) -> list[Record]:
            return [Record()]

    assert _prior_trials(Writer(), "drift", "site") == {("main", "momo", "h", 2)}  # type: ignore[arg-type]


def test_changing_a_variants_override_changes_its_trial_key_and_adds_a_trial() -> None:
    w = build_world()
    first = run(w, edge(variants=[{"id": "costly", "outcome": {"cost_bps": 100}}]))
    write_edge_eval(w.results, first, AS_OF)
    again = run(w, edge(variants=[{"id": "costly", "outcome": {"cost_bps": 100}}]))
    edited = run(w, edge(variants=[{"id": "costly", "outcome": {"cost_bps": 200}}]))
    assert again.trials == 2 and edited.trials == 3  # main + the old override + the new one
    hashes = {r.edge_variant: r.config_hash for r in edited.results}
    assert hashes["costly"] != hashes["main"] != ""
    assert hashes["costly"] != {r.edge_variant: r.config_hash for r in first.results}["costly"]


def test_changing_the_edges_offset_or_horizon_adds_a_trial() -> None:
    w = build_world()
    write_edge_eval(w.results, run(w), AS_OF)
    assert run(w).trials == 1
    longer = {"kind": "excess_return", "horizon_sessions": [2], "benchmark": "SPY",
              "start_offset_sessions": 2}  # fmt: skip
    assert run(w, edge(outcome=longer)).trials == 2  # the same screener, another entry session


def test_an_event_edge_never_reads_the_decision_sessions_own_outcome_partition() -> None:
    events = {DAYS[1]: [10, 11], DAYS[5]: [0, 1]}  # entries DAYS[2] and DAYS[6]
    clean = run(event_world(events), event_edge(2))
    poisoned = _poisoned({DAYS[1], DAYS[5]})
    for day, names in events.items():
        poisoned.write_reactions(day, {IDS[i]: 0 for i in names})
    assert run(poisoned, event_edge(2)).results == clean.results
    assert len(clean.results[0].stats) == 2


def test_a_reaction_row_stored_only_from_the_next_session_is_not_an_event_before_it() -> None:
    w = build_world()
    w.write_reactions(DAYS[2], {IDS[10]: 0})  # truncated at D = DAYS[1]: no row there yet
    (r,) = run(w, event_edge(2)).results
    assert [s.session for s in r.stats] == [DAYS[2]]  # D is the first session that has the row


def test_a_variant_may_override_the_offset_and_reads_its_own_entry_partition() -> None:
    late = {"id": "late", "outcome": {"start_offset_sessions": 2}}
    e = edge(variants=[late])
    clean = run(build_world(), e)
    # Poison the partitions two sessions after each decision (the variant's S, not the edge's).
    poisoned = run(_poisoned({DAYS[2], DAYS[4], DAYS[6]}), e)
    main_clean, late_clean = clean.results
    main_bad, late_bad = poisoned.results
    assert main_bad.stats == main_clean.stats  # the edge's own entries are untouched
    assert late_bad.stats != late_clean.stats and late_bad.stats[0].pick_values[0] == -9.0
    assert [s.session for s in late_clean.stats] == [DAYS[0], DAYS[2], DAYS[4]]  # DAYS[6]: no S


# ---- ED5a: the train / test split


def _user_world(split: str | None) -> World:
    w = build_world()
    if split:
        w.configs._docs[("alice", "evaluation", "evaluation")] = {"split_from": split}
    return w


def _split_run(w: World, user: str = "alice", **kw: Any) -> EdgeEvaluation:
    return evaluate_edge(
        w.reader, w.results, w.configs, UserContext(user), edge(frozen_from="2026-09-04"),
        DAYS[0], DAYS[-1], AS_OF, **kw,
    )  # fmt: skip


def test_the_site_split_is_the_edges_frozen_from_and_not_exploratory(world: World) -> None:
    ev = _split_run(world, "site")
    assert (ev.split_from, ev.exploratory) == (date(2026, 9, 4), False)
    assert ev.results[0].measures[-1].slice_kind == "frozen"


def test_a_users_split_makes_the_run_exploratory_with_its_own_test_slice() -> None:
    ev = _split_run(_user_world("2026-09-09"))
    assert (ev.split_from, ev.exploratory) == (date(2026, 9, 9), True)
    test = ev.results[0].measures[-1]
    assert (test.slice_kind, test.sessions) == ("split", 1)  # only the Sept 9 or later start
    assert not any(m.slice_kind == "frozen" for m in ev.results[0].measures)


def test_the_run_split_beats_the_users_which_beats_the_edges() -> None:
    w = _user_world("2026-09-09")
    assert _split_run(w).split_from == date(2026, 9, 9)  # user over the edge
    assert _split_run(w, split_from=date(2026, 9, 2)).split_from == date(2026, 9, 2)  # run wins
    assert _split_run(w, "bob").split_from == date(2026, 9, 4)  # another user: the edge's
    same = _split_run(w, split_from=date(2026, 9, 4))
    assert not same.exploratory  # the run restating the frozen_from is the site's split


def test_the_split_joins_the_run_hash() -> None:
    w = _user_world(None)
    hashes = {
        _split_run(w, split_from=d).run_hash for d in (None, date(2026, 9, 2), date(2026, 9, 9))
    }
    assert len(hashes) == 3
