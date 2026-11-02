"""The named instruments of a time-series edge (ADR 0073; ADR 0088 decision 14): an edge with
``base = "out_of_window"`` times a few instruments by a calendar window, and a named option sleeve
(``base = "delta_equivalent"``) holds its option position on a few instruments at every decision
session of its schedule, so its universe is a short list of symbols, not a screen: one rule
``instrument.symbol in [...]`` (or ``eq``) over at most ``MAX_NAMED`` symbols. A sleeve lifts ADR
0073 decision 1's calendar-schedule, ``excess_return`` and no-variants limits for that base only:
it measures an ``option_pnl`` outcome of one hold on a plain or calendar schedule, and may have
variants and a grid. Pure: it reads the parsed selection only; turning a symbol into an id is the
harness's, through ``SymbolResolver`` (ADR 0018), never a string built here."""

from algotrade.config.edges.positions.chain import CHAIN_KIND
from algotrade.config.edges.schedules.events import ON_EVENT
from algotrade.config.strategy.schema import Selection
from algotrade.core.model.errors import ConfigurationError
from algotrade.core.model.predicates import Rule

OUT_OF_WINDOW = "out_of_window"  # the ``base`` of a time-series edge
DELTA_EQUIVALENT = "delta_equivalent"  # the ``base`` of a named option sleeve (ADR 0088)
TIME_SERIES = (OUT_OF_WINDOW, DELTA_EQUIVALENT)  # the bases the time-series harness measures
SYMBOL_FIELD = "instrument.symbol"
MAX_NAMED = 10


def check_raw_returns(where: str, kind: str, benchmark: str, timed: bool) -> None:
    """An excess return needs SPY; a time-series edge's (``timed``) is the raw return, only."""
    if kind == "excess_return" and benchmark == "none" and not timed:
        raise ConfigurationError(f"{where} benchmark: an excess return needs SPY, not 'none'")
    if timed and (kind != "excess_return" or benchmark != "none"):
        raise ConfigurationError(
            f"{where} kind: base 'out_of_window' compares raw returns: kind "
            f"'excess_return' with benchmark 'none', got {kind!r} over {benchmark!r}"
        )


def check_variants(where: str, base: str | None, edge_base: str, universe: bool = False) -> None:
    """A variant's ``base`` (None: the edge's) against the edge's ``edge_base``: an out-of-window
    edge has no variants, and a named option sleeve's variants stay sleeves (a variant neither
    leaves nor joins ``delta_equivalent``) over the edge's own names (``universe``: the variant
    sets one)."""
    if OUT_OF_WINDOW in (base, edge_base):
        raise ConfigurationError(f"{where}: a time-series edge has no variants")
    if universe and edge_base == DELTA_EQUIVALENT:
        raise ConfigurationError(
            f"{where} universe: a named option sleeve's variants hold the edge's own names"
        )
    if base is not None and DELTA_EQUIVALENT in (base, edge_base) and base != edge_base:
        raise ConfigurationError(
            f"{where} base: a named option sleeve's variants keep base "
            f"{DELTA_EQUIVALENT!r}, and only a sleeve has it; got {base!r} on an edge "
            f"of base {edge_base!r}"
        )


def check_sleeve(
    where: str, kind: str, horizons: int, base: str, tracks: str | None = None
) -> None:
    """A named option sleeve (an outcome measured at ``base = "delta_equivalent"``) holds one
    ``option_pnl`` position of one hold (``horizons``: the number of its ``horizon_sessions``);
    only a sleeve ``tracks`` a Cboe strategy index (E8b)."""
    if tracks is not None and base != DELTA_EQUIVALENT:
        raise ConfigurationError(
            f"{where} tracks: only a named option sleeve (base {DELTA_EQUIVALENT!r}) is tracked "
            f"against a Cboe strategy index, got base {base!r}"
        )
    if base == DELTA_EQUIVALENT and (kind != CHAIN_KIND or horizons != 1):
        raise ConfigurationError(
            f"{where} kind: base {DELTA_EQUIVALENT!r} pairs an option position with its "
            f"delta-equivalent stock, so an {CHAIN_KIND!r} outcome with one horizon_sessions "
            f"value, got {kind!r} over {horizons}"
        )


def check_time_series(
    base: str,
    calendar: bool,
    universe: str | Selection,
    where: str,
    market: bool = False,
    schedule: str = "",
) -> None:
    """``base = "out_of_window"`` needs a ``calendar`` or ``on_market`` (``market``) schedule and
    a named universe; an ``on_market`` schedule needs that base (ADR 0075: a market trigger's
    base is not the cross-section). ``base = "delta_equivalent"`` needs a named universe and a
    plain or calendar ``schedule`` (its entries come from the schedule, not from events)."""
    if market and base != OUT_OF_WINDOW:
        raise ConfigurationError(
            f"{where} base: an on_market schedule is measured against the out-of-window "
            f"stretches, so base = 'out_of_window', got {base!r}"
        )
    if base not in TIME_SERIES:
        return
    if base == OUT_OF_WINDOW and not calendar and not market:
        raise ConfigurationError(
            f"{where} base: 'out_of_window' needs a calendar or on_market schedule"
        )
    if base == DELTA_EQUIVALENT and schedule.startswith(ON_EVENT):
        raise ConfigurationError(
            f"{where} base: {DELTA_EQUIVALENT!r} enters at the sessions its schedule places, "
            f"so a calendar, every_session or month_end schedule, got {schedule!r}"
        )
    named_symbols(universe, f"{where} universe", base)


def named_symbols(
    universe: str | Selection, where: str = "universe", base: str = OUT_OF_WINDOW
) -> tuple[str, ...]:
    """The symbols ``universe`` names, in order, each once; ``ConfigurationError`` when it is
    a preset name (the instruments are named inline) or anything but one ``instrument.symbol``
    ``in`` / ``eq`` rule over 1 to ``MAX_NAMED`` symbols."""
    if isinstance(universe, str):
        raise ConfigurationError(
            f"{where}: base {base!r} names its instruments inline "
            f"([universe] where = ...), not a preset"
        )
    rules = universe.where.rules()
    only = universe.where.kind == "all" and len(rules) == 1 == len(universe.where.children)
    rule: Rule = rules[0] if rules else Rule("", "eq")
    if not only or rule.field != SYMBOL_FIELD or rule.op not in ("in", "eq"):
        raise ConfigurationError(
            f"{where}: a time-series edge names its instruments with one rule "
            f"{SYMBOL_FIELD} in [...] (at most {MAX_NAMED}); got a selection of "
            f"{len(rules)} rule(s)"
        )
    raw = rule.value if isinstance(rule.value, tuple) else (rule.value,)
    symbols = tuple(dict.fromkeys(str(s).strip().upper() for s in raw if str(s).strip()))
    if not symbols or len(symbols) > MAX_NAMED:
        raise ConfigurationError(
            f"{where}: a time-series edge times 1 to {MAX_NAMED} named instruments, "
            f"got {len(symbols)}"
        )
    return symbols
