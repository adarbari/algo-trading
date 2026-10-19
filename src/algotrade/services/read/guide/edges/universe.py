"""Who an edge trades, in words, and its asset-class tag (ADR 0051): the Guide's one rule for
``asset`` and the sentence for the ``universe`` fact, both read from the edge document's
universe (an inline ``[universe.where]`` or a named selection preset of the site) and its outcome
kinds. Session-free: the rules are read as written, never run against a snapshot.

The asset-class rule (``asset_of``), first match wins:

0. the document's own ``asset_class`` (required where a hand-listed symbol universe names no
   security type, a fitness test);
1. ``options``: the edge's outcome, or any variant's, is an option outcome
   (``option_model_pnl``, ``expires_otm``, ``option_pnl``);
2. ``etfs`` (shown as "ETFs and funds"): the universe's ``instrument.security_type`` rules name
   fund types only (``FUND_TYPES``), or it names no type and lists symbols by hand (a fallback
   for drafts: a site edge with a hand list declares ``asset_class``);
3. ``stocks``: everything else (common stocks and ADRs, a preset's listed companies)."""

from collections.abc import Iterable
from dataclasses import dataclass

from algotrade.config.edges.document import Edge, Outcome
from algotrade.config.strategy.schema import Selection, parse_selection
from algotrade.core.model.errors import ConfigurationError
from algotrade.core.model.predicates import Group, Rule
from algotrade.services.read.context import Stores

ASSETS = ("stocks", "etfs", "options")  # the asset-class tags, in the Guide's filter order
OPTION_KINDS = ("option_model_pnl", "expires_otm", "option_pnl")
FUND_TYPES = ("ETF", "ETN", "CEF", "FUND")
TYPE_WORDS = {
    "COMMON_STOCK": "common stocks",
    "ADR": "ADRs",
    "ETF": "ETFs",
    "ETN": "ETNs",
    "CEF": "closed-end funds",
    "FUND": "funds",
}
TYPE_FIELD, SYMBOL_FIELD = "instrument.security_type", "instrument.symbol"
VOLUME_FIELD = "rollup.price_stats@v2.adv_usd_20d"
PRICE_FIELD = "rollup.price_stats@v2.close"
LISTED = 8  # symbols named in a sentence; more are counted
SELECTIONS = "selections"


@dataclass(frozen=True)
class Universe:
    """An edge's universe as the Guide reads it: its ``rules`` (none when a named preset cannot
    be read) and ``preset`` (the name, when it is one)."""

    rules: tuple[Rule, ...]
    preset: str | None


def universe_of(ctx: Stores, edge: Edge) -> Universe:
    """``edge``'s universe rules: inline as written, or the named site preset's."""
    if isinstance(edge.universe, Selection):
        return Universe(tuple(edge.universe.where.rules()), None)
    doc = ctx.configs.load("site", SELECTIONS, edge.universe)
    try:
        where: Group = parse_selection(doc or {}, f"selections/{edge.universe}").where
    except ConfigurationError:
        return Universe((), edge.universe)
    return Universe(tuple(where.rules()), edge.universe)


def outcomes_of(edge: Edge) -> Iterable[Outcome]:
    """The edge's outcome and every variant's."""
    yield edge.outcome
    yield from (v.outcome for v in edge.variants)


def asset_of(edge: Edge, universe: Universe) -> str:
    """The asset-class tag of ``edge`` (module docstring): one of ``ASSETS``."""
    if edge.asset_class is not None:
        return edge.asset_class
    if any(o.kind in OPTION_KINDS for o in outcomes_of(edge)):
        return "options"
    types = _types(universe.rules)
    if types:
        return "etfs" if all(t in FUND_TYPES for t in types) else "stocks"
    return "etfs" if _symbols(universe.rules) else "stocks"


def universe_text(universe: Universe) -> str:
    """The universe in one sentence: ``Common stocks and ADRs, trading at least $50M a day``."""
    types = [TYPE_WORDS.get(t, t.lower()) for t in _types(universe.rules)]
    symbols = _symbols(universe.rules)
    parts = [_join(types)[0].upper() + _join(types)[1:]] if types else []
    if symbols:
        listed = ", ".join(symbols[:LISTED])
        more = f" and {len(symbols) - LISTED} more" if len(symbols) > LISTED else ""
        parts.append(f"{len(symbols)} listed symbols: {listed}{more}")
    elif not types and universe.preset is not None:
        parts.append(universe.preset.replace("_", " ").capitalize())
    volume = _number(universe.rules, VOLUME_FIELD, "gte")
    price = _number(universe.rules, PRICE_FIELD, "gt")
    floors = [
        *([f"trading at least {_money(volume)} a day"] if volume is not None else []),
        *([f"priced above ${price:g}"] if price is not None else []),
    ]
    head = "; ".join(parts) if parts else "Every instrument in the snapshot"
    return head + (", " + " and ".join(floors) if floors else "")


def _types(rules: tuple[Rule, ...]) -> list[str]:
    found = [str(v) for r in rules if r.field == TYPE_FIELD for v in _values(r)]
    return list(dict.fromkeys(found))


def _symbols(rules: tuple[Rule, ...]) -> list[str]:
    found = [str(v) for r in rules if r.field == SYMBOL_FIELD for v in _values(r)]
    return list(dict.fromkeys(found))


def _values(rule: Rule) -> list[object]:
    if rule.op == "in" and isinstance(rule.value, tuple | list):
        return list(rule.value)
    return [rule.value] if rule.op == "eq" else []


def _number(rules: tuple[Rule, ...], field: str, op: str) -> float | None:
    for r in rules:
        if r.field == field and r.op == op and isinstance(r.value, int | float):
            return float(r.value)
    return None


def _money(value: float) -> str:
    if value >= 1_000_000_000:
        return f"${value / 1_000_000_000:g}B"
    return f"${value / 1_000_000:g}M" if value >= 1_000_000 else f"${value:,.0f}"


def _join(words: list[str]) -> str:
    return words[0] if len(words) == 1 else ", ".join(words[:-1]) + " and " + words[-1]
