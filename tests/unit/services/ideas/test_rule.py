"""The Ideas ranking rule (owner decision 2026-10-22): properties (order invariance, the same
bytes twice, a viewer's third pick equals a site first, max not sum), the licence exclusion,
the override, NOT_RUN and the PAUSED section."""

from fractions import Fraction

from hypothesis import given, settings
from hypothesis import strategies as st

from algotrade.config.ranking.ideas import IdeasRule
from algotrade.services.ideas.rule import (
    NOT_RUN,
    RAN,
    WITHHELD,
    PoolRow,
    PoolRun,
    pool_standing,
    rank_ideas,
    rank_paused,
)

RULE = IdeasRule()
TICKERS = [f"EQ:{c}" for c in "ABCDEFGHIJ"]


def run(config_id: str, tickers: list[str], *, own: bool = False, **kw: object) -> PoolRun:
    return PoolRun(
        "me" if own else "site", config_id, own, RAN, f"run-{config_id}",
        picked=tuple(PoolRow(t, "QUALIFIED") for t in tickers), **kw,
    )  # type: ignore[arg-type]  # fmt: skip


def ids(pool: list[PoolRun]) -> list[str]:
    return [i.instrument_id for i in rank_ideas(pool, RULE)]


pools = st.lists(
    st.tuples(
        st.sampled_from(["a", "b", "c", "d", "e"]),
        st.booleans(),
        st.lists(st.sampled_from(TICKERS), unique=True, max_size=10),
    ),
    unique_by=lambda t: (t[0], t[1]),
    max_size=8,
).map(lambda rows: [run(c, tk, own=o) for c, o, tk in rows])


@settings(max_examples=150, deadline=None)
@given(pools, st.randoms())
def test_the_order_the_pool_is_given_in_never_changes_the_list(pool, rnd) -> None:  # type: ignore[no-untyped-def]
    shuffled = list(pool)
    rnd.shuffle(shuffled)
    assert rank_ideas(shuffled, RULE) == rank_ideas(pool, RULE)
    assert rank_paused(shuffled, RULE) == rank_paused(pool, RULE)


@settings(max_examples=100, deadline=None)
@given(pools)
def test_the_same_inputs_give_the_same_bytes(pool) -> None:  # type: ignore[no-untyped-def]
    assert repr(rank_ideas(pool, RULE)) == repr(rank_ideas(list(pool), RULE))


@settings(max_examples=100, deadline=None)
@given(pools)
def test_every_idea_is_its_best_pick_and_the_list_is_in_the_documented_order(pool) -> None:  # type: ignore[no-untyped-def]
    ideas = rank_ideas(pool, RULE)
    for idea in ideas:
        assert idea.score == max(p.score for p in idea.picked_by) == idea.best.score
        assert idea.best in idea.picked_by
        assert [p.score for p in idea.picked_by] == sorted(
            (p.score for p in idea.picked_by), reverse=True
        )
    keys = [
        (-i.score, -len(i.picked_by), -sum(p.score for p in i.picked_by), i.instrument_id)
        for i in ideas
    ]
    assert keys == sorted(keys)
    assert [i.rank for i in ideas] == list(range(1, len(ideas) + 1))


def test_a_viewers_third_pick_equals_a_site_first_pick() -> None:
    mine = run("mine", ["EQ:B", "EQ:C", "EQ:A"], own=True)  # A at position 3: 3 / 3
    site = run("site1", ["EQ:D"])  # D at position 1: 1
    ideas = {i.instrument_id: i for i in rank_ideas([mine, site], RULE)}
    assert ideas["EQ:A"].score == ideas["EQ:D"].score == Fraction(1)
    # B (3), C (3 / 2), then A and D tie at 1 and the viewer's own wins the tie on best
    assert [i.instrument_id for i in rank_ideas([mine, site], RULE)] == [
        "EQ:B", "EQ:C", "EQ:A", "EQ:D",
    ]  # fmt: skip


def test_an_idea_is_its_best_pick_not_the_sum_of_its_picks() -> None:
    crowd = [run(f"s{n}", ["EQ:A"]) for n in range(12)]  # A first in twelve site screeners
    mine = run("mine", ["EQ:B"], own=True)  # B first in one of the viewer's: 3
    ideas = rank_ideas([*crowd, mine], RULE)
    assert [i.instrument_id for i in ideas] == ["EQ:B", "EQ:A"]
    a = ideas[1]
    assert a.score == 1 and len(a.picked_by) == 12  # consensus is only a tie-break


def test_consensus_then_sum_then_instrument_break_ties() -> None:
    one = run("a", ["EQ:Z", "EQ:Y"])
    two = run("b", ["EQ:Y"])
    # Y: best 1 from b, also 1 / 2 from a; Z: 1 only from a. Same best score, Y has more picks.
    assert ids([one, two]) == ["EQ:Y", "EQ:Z"]
    # Same score and count, so the instrument id decides
    assert ids([run("a", ["EQ:B"]), run("b", ["EQ:A"])]) == ["EQ:A", "EQ:B"]


def test_best_tie_goes_to_the_viewers_screener_then_the_screener_id() -> None:
    mine = run("zzz", ["EQ:A", "EQ:B", "EQ:C"], own=True)  # C at 3 / 3
    site_a = run("aaa", ["EQ:C"])
    site_b = run("bbb", ["EQ:C"])
    c = next(i for i in rank_ideas([site_b, site_a, mine], RULE) if i.instrument_id == "EQ:C")
    assert c.best.config_id == "zzz" and c.best.own
    assert [p.config_id for p in c.picked_by] == ["zzz", "aaa", "bbb"]
    d = next(i for i in rank_ideas([site_b, site_a], RULE) if i.instrument_id == "EQ:C")
    assert d.best.config_id == "aaa"


def test_only_the_first_picks_count() -> None:
    many = [f"EQ:{n}" for n in range(30)]
    site = rank_ideas([run("s", many)], RULE)
    assert len(site) == RULE.site_top == 5
    own = rank_ideas([run("m", many, own=True)], RULE)
    assert len(own) == RULE.user_top == 20
    assert own[19].score == Fraction(3, 20)


def test_a_withheld_run_contributes_nothing_and_is_listed() -> None:
    hidden = PoolRun(
        "site", "iv", False, WITHHELD, "run-iv",
        picked=(PoolRow("EQ:A", "QUALIFIED"),), paused=(PoolRow("EQ:B", "PAUSED"),),
    )  # fmt: skip
    visible = run("ok", ["EQ:C"])
    assert ids([hidden, visible]) == ["EQ:C"]
    assert rank_paused([hidden, visible], RULE) == []
    standing = {s.config_id: s for s in pool_standing([hidden, visible], RULE)}
    assert standing["iv"].status == WITHHELD and standing["iv"].top == ()
    assert standing["ok"].status == RAN


def test_a_run_that_did_not_run_contributes_nothing_and_says_why() -> None:
    gone = PoolRun("site", "late", False, NOT_RUN, None, "no run stored for the session")
    standing = pool_standing([gone, run("ok", ["EQ:A"])], RULE)
    late = next(s for s in standing if s.config_id == "late")
    assert (late.status, late.reason, late.top) == (NOT_RUN, "no run stored for the session", ())
    assert ids([gone]) == []


def test_a_viewers_screener_replaces_the_preset_with_its_id() -> None:
    preset = run("vrp", ["EQ:A", "EQ:B"])
    mine = run("vrp", ["EQ:C"], own=True)
    assert ids([preset, mine]) == ["EQ:C"]
    assert [s.own for s in pool_standing([preset, mine], RULE)] == [True]


def test_the_paused_section_follows_the_rule_one_entry_per_screener_and_ticker() -> None:
    gated = PoolRun(
        "site", "g", False, RAN, "run-g", picked=(PoolRow("EQ:A", "QUALIFIED"),),
        paused=(PoolRow("EQ:P", "PAUSED"), PoolRow("EQ:Q", "PAUSED"), PoolRow("EQ:P", "PAUSED")),
    )  # fmt: skip
    mine = PoolRun("me", "m", True, RAN, "run-m", paused=(PoolRow("EQ:Q", "PAUSED"),))
    held = rank_paused([gated, mine], RULE)
    assert [(h.instrument_id, h.pick.config_id, h.pick.score) for h in held] == [
        ("EQ:Q", "m", Fraction(3)),
        ("EQ:P", "g", Fraction(1)),
        ("EQ:Q", "g", Fraction(1, 2)),
    ]
    assert ids([gated, mine]) == ["EQ:A"]  # a paused row is no idea


def test_the_summary_lists_the_first_three_pool_picks() -> None:
    standing = pool_standing([run("s", [f"EQ:{n}" for n in range(8)])], RULE)
    assert [p.instrument_id for p in standing[0].top] == ["EQ:0", "EQ:1", "EQ:2"]
    assert len(standing[0].top) == 3
    assert [p.position for p in standing[0].top] == [1, 2, 3]
