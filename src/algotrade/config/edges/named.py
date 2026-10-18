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


def named_symbols(universe: Selection, where: str = "universe") -> tuple[str, ...]:
    """The symbols ``universe`` names, in order, each once; ``ConfigurationError`` when it is
    anything but one ``instrument.symbol`` ``in`` / ``eq`` rule over 1 to ``MAX_NAMED`` symbols."""
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
