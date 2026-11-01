"""``LEVELS``: the feature levels a rule may name, declared once (ADR 0088, design 2.15). A level
is what one row of feature values is about (an instrument on a session, a market on a session, a
trade at a close, a setup's book on a decision session); each names its field heads, where its
values come from (``stored`` feature groups of an entity, or a ``computed`` producer named by a
string, so ``config`` never imports the engine that computes it), how a row reaches the scope a
rule evaluates in, and the use sites that may read it. The catalogue (``catalog.py``) is written
against this table, never against a level by name: a new level is one entry here, its field head
and its provider."""

from dataclasses import dataclass

SCREENER, UNIVERSE, GATE, ENTRY, CASE, EXIT = (
    "screener",
    "universe",
    "gate",
    "entry",
    "case",
    "exit",
)
SITES = (SCREENER, UNIVERSE, GATE, ENTRY, CASE, EXIT)
# The sites whose rules are never null-tested and whose string ``ne`` / ``not_in`` need a
# declared domain (design 2.13 "fail closed at the four new sites").
STRICT_SITES = (GATE, ENTRY, CASE, EXIT)
OPEN_ONLY_SITES = (GATE,)  # the gate's fields must be openly licensed (owner decision 9, H1)


@dataclass(frozen=True)
class Level:
    key: str  # what a row is about: instrument | market | position | portfolio
    heads: tuple[str, ...]  # the field heads that name this level's fields
    provider: str  # stored | computed
    producer: str | None  # computed: the producer, by string (never imported here)
    row: str  # what one row is about
    pit: str  # the one read rule the provider applies
    join: str  # self | broadcast | through <key field>
    scopes: tuple[str, ...]  # the use sites that may read it
    licence: str  # where a field's licence comes from


LEVELS: tuple[Level, ...] = (
    Level(
        "instrument", ("instrument", "rollup"), "stored", None, "(instrument, session)",
        "the session's partition (ADR 0007)", "self",
        (SCREENER, UNIVERSE, ENTRY, CASE, EXIT), "Feature.licence",
    ),
    Level(
        "market", ("market",), "stored", None, "(market, session)",
        "that session's row only", "broadcast", (GATE, ENTRY, CASE, EXIT), "Feature.licence",
    ),
    Level(
        "position", ("position",), "computed", "engines.structures", "(trade, close)",
        "close t's quotes and the entry facts", "self", (EXIT,), "the trade's price source",
    ),
    Level(
        "portfolio", ("portfolio",), "computed", "services.evaluation.portfolio",
        "(setup, decision session)", "trades with S <= D still open after D's close",
        "broadcast", (GATE, ENTRY, CASE), "the strictest price source of the trades it reads",
    ),
)  # fmt: skip
BY_KEY = {level.key: level for level in LEVELS}


def levels_at(site: str, declared: tuple[Level, ...] = LEVELS) -> tuple[Level, ...]:
    """The levels a rule at ``site`` may name, from ``declared[*].scopes`` (none hand-written)."""
    return tuple(level for level in declared if site in level.scopes)
