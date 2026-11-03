"""``trades_of``: only counted picks become trades, at their own S when they have one, with the
window's planned exit, the pick's exit, capital and licence (ADR 0088, G15)."""

from datetime import date

from algotrade.core.time.calendar import next_session
from algotrade.services.evaluation.cross_section.measures import Pick
from algotrade.services.evaluation.portfolio_level.trades import trades_of

S = date(2026, 9, 1)
OWN = date(2026, 9, 2)


def test_only_counted_picks_are_trades_with_their_own_entry_exit_capital_and_licence() -> None:
    picks = [
        Pick("A", 1, "", 0.1, True, exit_session=OWN, capital=500.0, outcome_licence="open"),
        Pick("B", 2, "no_entry_bar"),
        Pick("C", 3, "", 0.0, entry_session=OWN),
    ]
    a, c = trades_of(picks, S, 2)
    planned = next_session(next_session(S))
    assert (a.instrument_id, a.entry_session, a.exit_session, a.planned_exit) == (
        "A", S, OWN, planned,
    )  # fmt: skip
    assert (a.capital, a.licence) == (500.0, "open")
    assert c.entry_session == OWN and c.exit_session is None
    assert c.planned_exit == next_session(next_session(OWN)) and c.licence == "personal"
