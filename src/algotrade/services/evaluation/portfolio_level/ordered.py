"""Whether an edge must be evaluated in order (ADR 0088, G15): true when any rule of its gate, a
variant's gate, an entry condition or a case value names a field of a level whose rows depend on
the trades of earlier decision sessions (``Level.in_order``, today the portfolio level). Driven by
``LEVELS``, never by a level's name."""

from collections.abc import Iterator

from algotrade.config.edges.document import Edge, Outcome
from algotrade.config.strategy.levels import level_of_field
from algotrade.core.model.predicates import Group


def _groups(edge: Edge) -> Iterator[Group]:
    """Every rule group of ``edge`` a level-bound field may sit in."""
    if edge.gate is not None:
        yield edge.gate
    outcomes: list[Outcome] = [edge.outcome]
    for variant in edge.variants:
        if variant.gate is not None:
            yield variant.gate
        outcomes.append(variant.outcome)
    for outcome in outcomes:
        if outcome.entry is not None:
            yield outcome.entry.when
        if outcome.position is not None:
            for value in outcome.position.cases:
                for case in value.cases:
                    yield case.when


def in_order(edge: Edge) -> bool:
    """Whether any field ``edge`` names is of an ``in_order`` level."""
    for group in _groups(edge):
        for rule in group.rules():
            level = level_of_field(rule.field)
            if level is not None and level.in_order:
                return True
    return False
