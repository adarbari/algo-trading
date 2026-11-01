"""``rank_picks``: the one Ideas ranking rule (ADR 0083 decision 2): evidence strength, then the
pick's place, then the instrument; one idea per ticker at its best position, the others listed."""

from algotrade.services.ideas.setup_rule import (
    CandidatePick,
    SetupStanding,
    rank_picks,
    setup_key,
)

WORKS_BIG = SetupStanding("a_big", "works", 4.0, 300)
WORKS_SMALL = SetupStanding("b_small", "works", 2.0, 900)
PROMISING = SetupStanding("c_prom", "promising", 9.0, 900)


def _ids(picks: list[CandidatePick]) -> list[str]:
    return [i.instrument_id for i in rank_picks(picks)]


def test_works_before_promising_then_lift_then_trades_then_id() -> None:
    nulls = SetupStanding("z_null", "works", None, 10)
    more = SetupStanding("y_more", "works", 2.0, 1000)
    order = sorted([PROMISING, nulls, WORKS_SMALL, more, WORKS_BIG], key=setup_key)
    assert [s.edge_id for s in order] == ["a_big", "y_more", "b_small", "z_null", "c_prom"]


def test_ranks_by_setup_then_place_then_instrument() -> None:
    picks = [
        CandidatePick("EQ:P1", PROMISING, 1),
        CandidatePick("EQ:B2", WORKS_BIG, 2),
        CandidatePick("EQ:B1", WORKS_BIG, 1),
        CandidatePick("EQ:S1", WORKS_SMALL, 1),
    ]
    found = rank_picks(picks)
    assert [(i.rank, i.instrument_id) for i in found] == [
        (1, "EQ:B1"), (2, "EQ:B2"), (3, "EQ:S1"), (4, "EQ:P1")
    ]  # fmt: skip


def test_a_ticker_two_setups_picked_is_one_idea_at_its_best_with_the_other_listed() -> None:
    picks = [
        CandidatePick("EQ:X", PROMISING, 1),
        CandidatePick("EQ:X", WORKS_SMALL, 5),
        CandidatePick("EQ:Y", WORKS_BIG, 3),
    ]
    found = rank_picks(picks)
    assert [i.instrument_id for i in found] == ["EQ:Y", "EQ:X"]
    x = found[1]
    assert (x.best.setup.edge_id, x.best.place) == ("b_small", 5)
    assert [(p.setup.edge_id, p.place) for p in x.also_in] == [("c_prom", 1)]


def test_the_same_inputs_rank_the_same_whatever_their_order() -> None:
    picks = [CandidatePick(f"EQ:{c}", WORKS_BIG, n) for n, c in enumerate("ABCD", 1)]
    assert _ids(picks) == _ids(list(reversed(picks))) == ["EQ:A", "EQ:B", "EQ:C", "EQ:D"]
