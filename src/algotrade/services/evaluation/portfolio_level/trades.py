"""The setup's own trades from a leg's picks (ADR 0088, G15): the counted picks of a decision
session become ``OpenTrade`` rows of its book. A pick the leg excluded (a reason) never entered,
so it is no trade. The entry is the pick's own S (an entry condition) or the leg's; the exit the
pick's recorded exit session, None while the contract has not given one; the planned exit the
window's end, so a trade whose exit is not known is still held until then."""

from collections.abc import Iterable
from datetime import date

from algotrade.services.evaluation.cross_section.measures import Pick
from algotrade.services.evaluation.cross_section.reporting.report_containment import window_end
from algotrade.services.evaluation.portfolio_level.book import OpenTrade
from algotrade.services.licences import PERSONAL


def trades_of(picks: Iterable[Pick], leg_entry: date, horizon: int) -> list[OpenTrade]:
    """The trades of ``picks`` (a leg's, entry ``leg_entry``, window ``horizon`` sessions): one per
    counted pick. A pick with no outcome licence is priced from the strictest source, never open."""
    out: list[OpenTrade] = []
    for pick in picks:
        if pick.reason != "":
            continue
        entry = pick.entry_session or leg_entry
        out.append(
            OpenTrade(
                pick.instrument_id,
                entry,
                pick.exit_session,
                window_end(entry, horizon),
                pick.capital,
                pick.outcome_licence or PERSONAL,
            )
        )
    return out
