"""Case values in the harness (ADR 0088, design 2.4, E13b): each name's cases are read at D only
and resolved by ``resolve_case`` (UNKNOWN first: CASE_UNKNOWN, never the default); a name takes
the row of its own point's key, relabelled to the default point's, picks and base alike; a later
session's fields change nothing; refusals at run start (a share outcome, G9-M4)."""

from dataclasses import asdict, replace
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pandas as pd
import pytest

from algotrade.config.edges.identity import identity_dict
from algotrade.config.strategy.schema import parse_selection
from algotrade.config.user import UserContext
from algotrade.core.model.errors import ConfigurationError
from algotrade.core.time.calendar import next_session
from algotrade.core.views.market_features import MARKET_FEATURES
from algotrade.engines.selection.cases import CASE_UNKNOWN
from algotrade.services.evaluation.cross_section.harness import evaluate_edge
from algotrade.services.evaluation.cross_section.reads import cases as case_reads
from algotrade.services.evaluation.cross_section.reads.cases import (
    Resolved,
    case_keys,
    cased_rows,
    check_cases,
    read_cases,
)
from algotrade.services.evaluation.cross_section.reads.session import SessionReads
from algotrade.services.evaluation.cross_section.run.evaluation import EdgeEvaluation
from algotrade.services.evaluation.cross_section.sessions import Leg
from algotrade.services.features import site_features
from algotrade.storage.configs.files import FileConfigStore
from algotrade.storage.tables.schemas import STRUCTURE_PNL
from tests.conftest import REPO_ROOT
from tests.helpers.stored_frames import stamped, structure_pnl_row
from tests.unit.services.evaluation.cross_section.conftest import (
    ACTIVE,
    AS_OF,
    DAYS,
    IDS,
    World,
    build_world,
    edge,
)

SIGNAL_TABLE = "rollups/instrument/price_stats@v2"
SIGNAL = "rollup.price_stats@v2.adv_usd_20d"
TENOR = {"cases": [{"when": {"all": [{"field": SIGNAL, "op": "gt", "value": 0}]}, "value": 45}],
         "default": 30}  # fmt: skip
OUTCOME = {
    "kind": "option_pnl", "horizon_sessions": [2], "benchmark": "none", "tenor_days": TENOR,
    "position": "short_put", "strike_delta": 0.25, "start_offset_sessions": 1,
}  # fmt: skip
CASED = edge(outcome=OUTCOME)
KEYS = case_keys(CASED.outcome)
assert KEYS is not None
LONG_KEY, SHORT_KEY = KEYS.keys[(45,)][2], KEYS.keys[(30,)][2]  # 45 and 30 day tenors
USER = UserContext("site")
CHAIN_PLAIN = {**OUTCOME, "tenor_days": 30}  # a position baseline's outcome: no cases


def test_case_keys_name_every_point_and_the_default_is_the_literal() -> None:
    assert set(KEYS.keys) == {(30,), (45,)} and KEYS.default == {2: SHORT_KEY}
    assert LONG_KEY != SHORT_KEY


def signal_at(w: World, day: date, value: Any) -> None:
    rows = [{"instrument_id": iid, "adv_usd_20d": v} for i, iid in enumerate(IDS)
            if (v := value(i)) is not None]  # fmt: skip
    w.write_rollup(SIGNAL_TABLE, day, rows)


def even_long(i: int) -> float | None:
    """Even names hold the case (tenor 45), odd ones do not (30); name 19 has no value."""
    return None if i == 19 else (1.0 if i % 2 == 0 else -1.0)


def test_cases_are_read_at_d_only_and_unknown_is_never_the_default() -> None:
    w = build_world()
    signal_at(w, DAYS[0], even_long)
    signal_at(w, DAYS[1], lambda i: -1.0)  # the next session says otherwise: never read
    found = read_cases(w.reader, KEYS.cases, IDS, DAYS[0])
    assert found.chosen[IDS[0]] == (45,) and found.chosen[IDS[1]] == (30,)
    assert found.reasons == {IDS[19]: CASE_UNKNOWN} and IDS[19] not in found.chosen


def test_each_name_keeps_its_own_points_row_relabelled_and_other_keys_stay() -> None:
    rows = pd.DataFrame({
        "instrument_id": ["a", "a", "b", "b", "c", "a"],
        "position_key": [SHORT_KEY, LONG_KEY, SHORT_KEY, LONG_KEY, SHORT_KEY, "baseline"],
        "horizon_sessions": [2] * 6, "v": [1, 2, 3, 4, 5, 6],
    })  # fmt: skip
    resolved = Resolved({"a": (45,), "b": (30,)}, {"c": CASE_UNKNOWN})
    out = cased_rows(rows, resolved, KEYS)
    assert sorted(zip(out["instrument_id"], out["v"], out["position_key"], strict=True)) == [
        ("a", 2, SHORT_KEY), ("a", 6, "baseline"), ("b", 3, SHORT_KEY),
    ]  # fmt: skip


def test_case_values_on_a_share_outcome_and_a_field_with_no_rows_are_refused() -> None:
    w = build_world()
    shares = edge(outcome={"kind": "excess_return", "horizon_sessions": [2], "benchmark": "SPY",
                           "start_offset_sessions": 1})  # fmt: skip
    check_cases(w.reader, shares, site_features(), DAYS[0], DAYS[-1], AS_OF)  # no cases: nothing
    with pytest.raises(ConfigurationError, match=r"G9-M4"):
        check_cases(w.reader, CASED, site_features(), DAYS[0], DAYS[-1], AS_OF)


def chain_world(signal: Any = even_long, later: Any = None) -> World:
    """The harness store (with the site's position templates) and option rows at both points for
    every name: the 45-day point earns 5 more than the 30-day one; the signal at every session
    (``later``: from the second on)."""
    w = build_world()
    site = FileConfigStore(REPO_ROOT / "config", local=False)
    docs = {k: w.configs.load(*k) for k in [("site", "selections", "active"),
                                             ("site", "strategies", "momo")]}  # fmt: skip
    templates = ("site", "positions", "templates")
    w.configs = type(w.configs)({**docs, templates: site.load(*templates)})
    for k, day in enumerate([*DAYS, next_session(DAYS[-1])]):
        rows = [
            structure_pnl_row(
                iid, key, day, hold=2, ts=datetime.combine(day, datetime.min.time(), UTC),
                window_end=day + timedelta(days=2), price_source="option_history",
                licence="personal", entry_spot=100.0, entry_half_spread=0.0, exit_half_spread=0.0,
                pnl_mid=i - 9.5 + extra, option_pnl=i - 9.5 + extra,
            )
            for i, iid in enumerate(IDS)
            for key, extra in ((SHORT_KEY, 0.0), (LONG_KEY, 5.0))
        ]  # fmt: skip
        w.writer.write_table(STRUCTURE_PNL, day, f"cp-{day}", stamped(rows, day, f"cp-{day}"))
        signal_at(w, day, later if later is not None and k > 0 else signal)
    return w


def run(w: World) -> EdgeEvaluation:
    return evaluate_edge(w.reader, w.results, w.configs, USER, CASED, DAYS[0], DAYS[-1], AS_OF)


def test_each_pick_and_base_name_is_measured_at_its_own_point() -> None:
    (r,) = run(chain_world()).results
    for s in r.stats:
        got = {p.instrument_id: p for p in s.picks}
        assert got[IDS[19]].reason == CASE_UNKNOWN and s.case_unknown == 1
        gross = {i: got[IDS[i]].value for i in (15, 16, 17, 18)}
        for i, value in gross.items():  # 45 days (+5) for the even names, 30 for the odd
            assert value == pytest.approx((i - 9.5 + (5 if i % 2 == 0 else 0)) / 100, abs=2e-4)
        assert s.eligible == len(IDS) - 1  # the unselectable name is in no base either


def test_what_a_later_session_says_changes_nothing_and_the_result_is_deterministic() -> None:
    plain = run(chain_world()).results[0].stats
    assert run(chain_world(later=lambda i: -1.0)).results[0].stats != plain  # D's read matters
    first = chain_world(later=even_long)
    assert run(first).results[0].stats == plain == run(chain_world()).results[0].stats


def test_case_values_never_loaded_against_the_templates_are_refused_never_the_default() -> None:
    position = CASED.outcome.position
    assert position is not None
    bare = replace(CASED.outcome, position=replace(position, points=()))
    with pytest.raises(ConfigurationError, match=r"points"):
        case_keys(bare)


def test_a_case_point_s_key_is_in_the_trial_identity() -> None:
    """A template edit that moves a case point's key moves the trial (stored legs not reused)."""
    position = CASED.outcome.position
    assert position is not None
    moved = tuple((v, h, f"{k}-edited") for v, h, k in position.points)
    edited = replace(CASED.outcome, position=replace(position, points=moved))
    assert identity_dict(asdict(edited)) != identity_dict(asdict(CASED.outcome))


def test_a_share_outcome_with_case_values_is_refused() -> None:
    w = build_world()
    signal_at(w, DAYS[0], even_long)
    shares = edge(outcome={"kind": "excess_return", "horizon_sessions": [2], "benchmark": "SPY",
                           "start_offset_sessions": 1})  # fmt: skip
    position = CASED.outcome.position
    cased = replace(shares, outcome=replace(shares.outcome, position=position))
    with pytest.raises(ConfigurationError, match=r"only an option_pnl"):
        check_cases(w.reader, cased, site_features(), DAYS[0], DAYS[-1], AS_OF)


def test_a_market_gap_at_d_loses_the_leg(monkeypatch: Any) -> None:
    w = build_world()
    rule = {"all": [{"field": "market.market_conditions@v1.vix", "op": "gt", "value": 30}]}
    vix = edge(outcome={**OUTCOME, "tenor_days": {"cases": [{"when": rule, "value": 45}],
                                                  "default": 30}})  # fmt: skip
    keys = case_keys(vix.outcome)
    assert keys is not None
    monkeypatch.setattr(case_reads, "session_market", lambda r, names, day: dict.fromkeys(names))
    found = read_cases(w.reader, keys.cases, IDS, DAYS[0])
    assert (found.gap, found.chosen, found.reasons) == (MARKET_FEATURES, {}, {})


def test_a_baseline_holds_out_the_setup_s_unselectable_names() -> None:
    w = chain_world()
    session = SessionReads(w.reader, "x")
    plain = edge(outcome=CHAIN_PLAIN)
    rows = pd.DataFrame({"instrument_id": IDS, "position_key": ["baseline"] * len(IDS),
                         "horizon_sessions": [2] * len(IDS)})  # fmt: skip
    universe = parse_selection(ACTIVE, "active")
    leg = Leg(DAYS[0], next_session(DAYS[0]))
    found, kept, _ = session.entered(plain, universe, "b", leg, {}, rows, CASED)
    assert found is not None and found.reasons == {IDS[19]: CASE_UNKNOWN}
    assert found.at == dict.fromkeys(IDS[:19], leg.entry)  # the others enter at the leg's own S
    assert kept is not None and IDS[19] not in set(kept["instrument_id"])
    assert len(kept) == len(IDS) - 1
