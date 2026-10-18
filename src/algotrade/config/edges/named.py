"""The named instruments of a time-series edge (ADR 0073): an edge with ``base = "out_of_window"``
times a few instruments by a calendar window, so its universe is a short list of symbols, not a
screen: one rule ``instrument.symbol in [...]`` (or ``eq``) over at most ``MAX_NAMED`` symbols.
Pure: it reads the parsed selection only; turning a symbol into an id is the harness's, through
``SymbolResolver`` (ADR 0018), never a string built here."""

from algotrade.config.strategy.schema import Selection
from algotrade.core.model.errors import ConfigurationError
from algotrade.core.model.predicates import Rule

OUT_OF_WINDOW = "out_of_window"  # the ``base`` of a time-series edge
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


def check_variants(where: str, *bases: str | None) -> None:
    """A time-series edge (any of the ``bases`` of an edge and its variant) has no variants."""
    if OUT_OF_WINDOW in bases:
        raise ConfigurationError(f"{where}: a time-series edge has no variants")


def check_time_series(base: str, calendar: bool, universe: str | Selection, where: str) -> None:
    """``base = "out_of_window"`` needs a ``calendar`` schedule and a named universe."""
    if base != OUT_OF_WINDOW:
        return
    if not calendar:
        raise ConfigurationError(f"{where} base: 'out_of_window' needs a calendar schedule")
    named_symbols(universe, f"{where} universe")


def named_symbols(universe: str | Selection, where: str = "universe") -> tuple[str, ...]:
    """The symbols ``universe`` names, in order, each once; ``ConfigurationError`` when it is
    a preset name (the instruments are named inline) or anything but one ``instrument.symbol``
    ``in`` / ``eq`` rule over 1 to ``MAX_NAMED`` symbols."""
    if isinstance(universe, str):
        raise ConfigurationError(
            f"{where}: base 'out_of_window' names its instruments inline "
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
