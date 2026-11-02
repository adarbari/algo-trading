"""What a setup gate does to a variant's blocks: the slices read every block, the edge's own
series only the open ones; an ungated edge passes through unchanged."""

from dataclasses import replace
from datetime import date

from algotrade.services.evaluation.cross_section.detail.gating import (
    open_blocks,
    open_only,
    pooled_blocks,
    turned,
)
from algotrade.services.evaluation.cross_section.sessions import Leg
from tests.unit.services.evaluation.cross_section.conftest import edge
from tests.unit.services.evaluation.cross_section.test_measures import stat

D = [date(2026, 4, 1), date(2026, 4, 2), date(2026, 4, 6)]
GATE = {"all": [{"field": "market.regime@v3.label", "op": "not_in", "value": ["STRESS"]}]}
BLOCKS = [[Leg(d, date(2026, 5, 1))] for d in D]


def found(*states: str):  # type: ignore[no-untyped-def]
    return {d: replace(stat(d, (0.01,), (0.0,), 1), gate=g) for d, g in zip(D, states, strict=True)}


def test_a_gated_edge_keeps_every_block_for_the_slices_and_the_open_ones_for_its_series() -> None:
    seen = found("open", "closed", "unknown")
    every, blocks, stats = pooled_blocks(edge(gate=GATE), seen, BLOCKS, {date(2026, 5, 1)})
    assert [s.gate for s in every] == ["open", "closed", "unknown"]
    assert blocks == [BLOCKS[0]] and [s.session for s in stats] == [D[0]]
    assert open_blocks(edge(gate=GATE), BLOCKS, seen) == [BLOCKS[0]]


def test_an_ungated_edge_is_passed_through_whole() -> None:
    seen = found("", "", "")
    every, blocks, stats = pooled_blocks(edge(), seen, BLOCKS, {date(2026, 5, 1)})
    assert blocks == BLOCKS and stats == every and len(every) == 3
    assert open_blocks(edge(), BLOCKS, seen) == BLOCKS
    assert open_only(edge(), BLOCKS, every) == (BLOCKS, every)


def test_the_slices_read_the_turned_over_series_of_an_ungated_edge_too() -> None:
    seen = found("", "", "")
    every = tuple(seen.values())
    calls: list[int] = []

    def turn(series):  # type: ignore[no-untyped-def]
        calls.append(len(series))
        return tuple(replace(s, pick_hits=9) for s in series)

    out_every, out_own = turned(every, every, turn)
    assert out_every == out_own and all(s.pick_hits == 9 for s in out_every) and calls == [3]
    own = every[:1]  # a gated edge turns both series, apart
    out_every, out_own = turned(every, own, turn)
    assert len(out_every) == 3 and len(out_own) == 1 and all(s.pick_hits == 9 for s in out_every)
