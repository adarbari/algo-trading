"""Leg v2 (ADR 0064 decision 4): a leg holds every pick (rank, score at D, reason, gross value,
the window's dip, ADV at D; a value not stored is None, never 0) and its hits at each level of the
site's cost grid; ADV is read through the recording reader, so a restated liquidity partition
recomputes exactly the legs that read it; a changed grid is a new key."""

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pandas as pd
import pytest

from algotrade.config.user import UserContext
from algotrade.services.evaluation.cross_section import measuring
from algotrade.services.evaluation.cross_section.harness import EdgeEvaluation, evaluate_edge
from algotrade.services.evaluation.cross_section.results import write_edge_eval
from tests.helpers.stored_frames import stamped
from tests.unit.services.evaluation.cross_section.conftest import (
    DAYS,
    IDS,
    World,
    build_world,
    edge,
    outcome_row,
)

T1 = datetime(2026, 10, 6, 12, tzinfo=UTC)
T2 = T1 + timedelta(days=1)
ADV = "rollups/instrument/price_stats@v2"
D2 = DAYS[2]


def write_adv(w: World, day: date, run_id: str, scale: float = 1e6, pending: bool = False) -> None:
    rows = [{"instrument_id": i, "adv_usd_20d": scale * (k + 1)} for k, i in enumerate(IDS[1:])]
    w.writer.write_table(ADV, day, run_id, stamped(rows, day, run_id), pending=pending)
    if pending:
        w.backend.tables.commit_run(run_id, T1 + timedelta(minutes=30))


def run(w: World, at: datetime = T1, write: bool = False, **changes: Any) -> EdgeEvaluation:
    ev = evaluate_edge(
        w.reader, w.results, w.configs, UserContext("site"), edge(**changes), DAYS[0], DAYS[-1], at
    )
    if write:
        write_edge_eval(w.results, ev, at)
    return ev


def grid(w: World, levels: list[float]) -> None:
    """The site's ``verdict.toml`` with ``[edge_costs] levels_bps = levels``."""
    w.configs._docs["site", "settings", "verdict"] = {"edge_costs": {"levels_bps": levels}}


@pytest.fixture
def stored() -> World:
    """The harness world with ADV stored at every session but for name 0 (never stored)."""
    w = build_world()
    for day in DAYS:
        write_adv(w, day, f"adv-{day}")
    return w


def test_every_pick_is_in_its_leg_with_its_rank_score_gross_dip_and_adv(stored: World) -> None:
    (r,) = run(stored).results
    first = r.stats[0]
    assert [p.instrument_id for p in first.picks] == IDS[15:][::-1]  # dearest first
    assert [p.rank for p in first.picks] == [1, 2, 3, 4, 5]
    top = first.picks[0]  # name 19: price 290, excess (19 - 9.5)%, ADV 19M
    assert top.reason == "" and top.hit and not top.delisted
    assert top.score == pytest.approx(290.0)
    assert top.value == pytest.approx(0.095) and top.gross == pytest.approx(0.095)
    assert top.drawdown == 0.0 and top.adv == pytest.approx(19e6)
    assert top.reference is None and top.touch is None  # not an expires_otm outcome
    assert [p.value for p in first.picks] == list(first.pick_values)  # counted, in order


def test_a_net_value_keeps_the_gross_beside_it(stored: World) -> None:
    doc_outcome = {
        "kind": "excess_return", "horizon_sessions": [2], "benchmark": "SPY",
        "start_offset_sessions": 1, "cost_bps": 20,
    }  # fmt: skip
    (r,) = run(stored, outcome=doc_outcome).results
    top = r.stats[0].picks[0]
    assert top.value == pytest.approx(0.093) and top.gross == pytest.approx(0.095)


def test_excluded_picks_are_kept_with_their_reason_and_no_value() -> None:
    """A pick with no outcome row at S is ``no_entry_bar``; an UNMEASURED window ``unmeasured``;
    a name with no ADV stored has ``adv`` None (never 0)."""

    def rows_of(day: date) -> list[dict[str, Any]]:
        out = []
        for i, iid in enumerate(IDS):
            if i == 19:
                continue  # no entry bar
            if i == 18:
                out.append(
                    outcome_row(iid, i, day, outcome_status="UNMEASURED", fwd_return=None,
                                fwd_excess_return=None, fwd_max_return=None,
                                fwd_max_drawdown=None, fwd_realised_vol=None,
                                outcome_reason="BAD_BAR")
                )  # fmt: skip
            else:
                out.append(outcome_row(iid, i, day))
        return out

    w = build_world(rows_of=rows_of)
    (r,) = run(w).results
    picks = {p.instrument_id: p for p in r.stats[0].picks}
    assert picks[IDS[19]].reason == measuring.NO_ENTRY_BAR and picks[IDS[19]].value is None
    assert picks[IDS[18]].reason == "unmeasured" and picks[IDS[18]].drawdown is None
    assert not picks[IDS[18]].hit and picks[IDS[18]].gross is None
    assert all(p.adv is None for p in picks.values())  # no ADV stored at all: unknown
    assert len(r.stats[0].pick_values) == 3


def test_hits_are_counted_at_every_level_of_the_cost_grid(stored: World) -> None:
    """Name i earns (i - 9.5)%: at 50 bp name 10's 0.5% is no longer a hit; the picks (15..19)
    hit at every level. The grid is the site's (``[edge_costs] levels_bps``)."""
    (r,) = run(stored).results
    first = r.stats[0]
    assert first.base_hits_at == (10, 10, 10, 9)  # 0, 15, 30, 50 bp
    assert first.pick_hits_at == (5, 5, 5, 5)
    grid(stored, [100])
    (again,) = run(stored).results
    assert again.stats[0].base_hits_at == (9,)  # 1% cost: names 11..19


def test_a_restated_adv_partition_recomputes_exactly_the_legs_that_read_it(stored: World) -> None:
    run(stored, write=True)
    write_adv(stored, D2, "restated", scale=2e6, pending=True)
    night = run(stored, T2)
    assert (night.legs_computed, night.legs_reused) == (1, 3)
    assert dict(night.legs_invalidated) == {"inputs": 1}
    (r,) = night.results
    assert r.stats[1].picks[0].adv == pytest.approx(38e6)


def test_a_changed_cost_grid_is_a_new_leg_key(stored: World) -> None:
    run(stored, write=True)
    grid(stored, [0, 10])
    night = run(stored, T2)
    assert (night.legs_computed, night.legs_reused) == (4, 0)


def test_an_outcome_that_is_not_a_return_counts_no_cost_levels() -> None:
    otm = SimpleNamespace(
        outcome=SimpleNamespace(
            kind="hit_target", measure="realised_to_implied_vol", is_return=False
        )
    )
    scope = SimpleNamespace(edge=otm, key="main")
    found = measuring._hits_at(
        scope,
        None,
        None,
        2,
        pd.DataFrame(),
        frozenset(),
        (0.0, 15.0),  # type: ignore[arg-type]
    )
    assert found == []
