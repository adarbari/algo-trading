"""The ordered exit list over closes (ADR 0088, design 2.4a): the first rule in declared order wins
at one close, a catalogue-field rule acts one close after it is observed and a position-only one
on the same close, an UNKNOWN rule never fires and is counted, a rule acting past the last close
does not act, and the walk is independent of how a mark was priced (share rows work the same)."""

from algotrade.config.edges.positions.spec import ExitSettings, exit_rules
from algotrade.config.strategy.schema import Group, Rule
from algotrade.engines.structures.exits import scan_exits

PROFIT = "position.profit_share_of_credit"


def rows(*profits: float | None, **extra: list[float | None]) -> list[dict[str, float | None]]:
    return [
        {PROFIT: p, "position.dte": 30 - i, **{k: v[i] for k, v in extra.items()}}
        for i, p in enumerate(profits)
    ]


def test_take_profit_fires_at_the_close_it_is_observed() -> None:
    rules = exit_rules(ExitSettings(take_profit=0.5, stop_loss=2.0))
    hit = scan_exits(rules, rows(0.1, 0.5, 0.9)).hit
    assert (hit.kind, hit.at, hit.observed) == ("TAKE_PROFIT", 1, 1)  # type: ignore[union-attr]


def test_first_in_declared_order_wins_at_one_close() -> None:
    both = exit_rules(ExitSettings(take_profit=0.5, exit_dte=29))
    assert scan_exits(both, rows(0.1, 0.1)).hit.kind == "EXIT_DTE"  # type: ignore[union-attr]
    # dte 29 is reached at close 1 together with take profit: take profit is declared first
    assert scan_exits(both, rows(0.6, 0.6)).hit.kind == "TAKE_PROFIT"  # type: ignore[union-attr]


def test_catalogue_rule_acts_one_close_later_and_position_rule_same_close() -> None:
    when = Group("all", (Rule("market.vix_close", "gt", 30),))
    rules = exit_rules(ExitSettings(exit_dte=29, when=when))
    r = rows(0.0, 0.0, 0.0, **{"market.vix_close": [35.0, 10.0, 10.0]})
    hit = scan_exits(rules, r).hit
    assert (hit.kind, hit.at, hit.observed) == ("EXIT_DTE", 1, 1)  # type: ignore[union-attr]
    only_when = exit_rules(ExitSettings(when=when))
    hit = scan_exits(only_when, r).hit
    assert (hit.kind, hit.at, hit.observed) == ("CONDITION", 1, 0)  # type: ignore[union-attr]


def test_catalogue_rule_observed_on_the_last_close_does_not_act() -> None:
    when = Group("all", (Rule("market.vix_close", "gt", 30),))
    r = rows(0.0, 0.0, **{"market.vix_close": [10.0, 35.0]})
    assert scan_exits(exit_rules(ExitSettings(when=when)), r).hit is None


def test_unknown_rule_never_fires_and_is_counted() -> None:
    rules = exit_rules(ExitSettings(take_profit=0.5))
    scan = scan_exits(rules, rows(None, None, 0.2))
    assert scan.hit is None and scan.unknown_closes == 2
    later = scan_exits(rules, rows(None, 0.6))
    assert later.hit is not None and later.hit.unknown_closes == 1


def test_no_rules_no_exit() -> None:
    assert scan_exits((), rows(0.9, 0.9)).hit is None


def test_unknown_on_a_rule_that_cannot_act_is_not_counted() -> None:
    when = Group("all", (Rule("market.vix_close", "gt", 30),))
    r = rows(0.0, 0.0, **{"market.vix_close": [10.0, None]})
    assert scan_exits(exit_rules(ExitSettings(when=when)), r).unknown_closes == 0
