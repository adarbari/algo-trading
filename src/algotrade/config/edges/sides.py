"""The checks of an outcome's side and buy/hold band (ADR 0053 amendments): what a short or
long-short outcome and a ``hold_rank`` may combine with. Split from ``document.py`` (at its line
cap), which calls them while it parses an ``[outcome]``."""

from collections.abc import Sequence

from algotrade.config.site.fields import Table
from algotrade.core.model.errors import ConfigurationError

LONG, SHORT, LONG_SHORT = "long", "short", "long_short"
SIDES = (LONG, SHORT, LONG_SHORT)  # which names an outcome holds and in which direction


def check_side(
    o: Table, side: str, borrow: float | None, kind: str, drawdown: float | None
) -> None:
    """A short or long-short outcome is an excess return with no drawdown limit (the dip of a
    short is the rally, which the store keeps apart); the borrow cost belongs to a short leg."""
    if side == LONG:
        if borrow is not None:
            raise ConfigurationError(f"{o.where} borrow_bps_annual: only a short leg pays borrow")
        return
    if kind != "excess_return" or drawdown is not None:
        raise ConfigurationError(
            f"{o.where} side: {side!r} needs an excess_return outcome with no max_drawdown"
        )


def hold_rank_of(
    o: Table,
    side: str,
    kind: str,
    schedule: str,
    schedules: Sequence[str],
    horizons: tuple[int, ...],
) -> int | None:
    """The outcome's buy/hold band rank (None: no band). Refused for a spread (``long_short`` has
    no cost rows), a return that is not an excess return and an event or calendar schedule. The
    schedule limit (``month_end``, or ``every_session`` at one session) is stricter than needed:
    windows never overlap on a plain schedule (``sessions.py``), so loosening it is a later PR."""
    if "hold_rank" not in o.names():
        return None
    rank = o.integer("hold_rank", 1, 1)
    if side == LONG_SHORT or kind != "excess_return":
        raise ConfigurationError(
            f"{o.where} hold_rank: a band is for a long or short excess_return (a long_short "
            f"spread has no cost rows to turn over)"
        )
    if schedule not in schedules or (schedule == "every_session" and horizons != (1,)):
        raise ConfigurationError(
            f"{o.where} hold_rank: for now the schedule is month_end, or every_session at "
            f"horizon_sessions = [1] (kept stricter than needed), got {schedule!r} with "
            f"{list(horizons)}"
        )
    return rank
