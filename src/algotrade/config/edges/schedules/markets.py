"""Market-level triggers of an edge document (ADR 0075): the triggers an
``on_market:<trigger>`` schedule may name and its parsing and fail-closed validity check. A
market trigger is one fact about the whole market (not an event class: its base would be the
universe), so an edge on it is measured by the time-series harness (ADR 0073): a named universe,
``base = "out_of_window"``, benchmark ``none``, one horizon. ``document`` re-exports every name."""

from collections.abc import Mapping

from algotrade.config.site.fields import Table
from algotrade.core.model.errors import ConfigurationError

ON_MARKET = "on_market:"
# The triggers a schedule may name and, for each, the stored field that dates it (read at the
# decision session D from the ``MKT:US`` row, ``time_series/triggers.py``; kept equal by a
# fitness test). D is the session the trigger was first known (``<= D``, never earlier).
MARKET_TRIGGERS: Mapping[str, str] = {
    "vix_spike": "market.market_triggers@v1.vix_spike_date",
}
# The stored field that is null when the reading behind the trigger is stale (UNKNOWN): the
# placement counts such a session as not known, never as "no trigger".
MARKET_TRIGGER_AGE: Mapping[str, str] = {
    "vix_spike": "market.market_triggers@v1.sessions_since_vix_spike",
}


def market_trigger(schedule: str) -> str | None:
    """The trigger of an ``on_market:<trigger>`` schedule (any text after the prefix), else None."""
    return schedule.removeprefix(ON_MARKET) if schedule.startswith(ON_MARKET) else None


def market_schedule_ok(t: Table, schedule: str) -> bool:
    """Whether ``schedule`` is an ``on_market:`` schedule; fail closed on a trigger not in
    ``MARKET_TRIGGERS``. False for any other schedule."""
    trigger = market_trigger(schedule)
    if trigger is None:
        return False
    if trigger not in MARKET_TRIGGERS:
        raise ConfigurationError(
            f"{t.where} schedule: {trigger!r} is not a market trigger "
            f"(known: {sorted(MARKET_TRIGGERS)})"
        )
    return True
