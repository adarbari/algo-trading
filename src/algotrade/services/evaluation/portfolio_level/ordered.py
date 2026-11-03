"""Whether an edge must be evaluated in order (ADR 0088, G15): true when any rule of its gate, a
variant's gate, an entry condition or a case value names a field of a level whose rows depend on
the trades of earlier decision sessions (``Level.in_order``, today the portfolio level). Driven by
``LEVELS``, never by a level's name."""

from algotrade.config.edges.document import Edge
from algotrade.config.edges.positions.spec import rule_groups
from algotrade.config.strategy.levels import level_of_field


def in_order(edge: Edge) -> bool:
    """Whether any field ``edge`` names is of an ``in_order`` level."""
    for group in rule_groups(edge):
        for rule in group.rules():
            level = level_of_field(rule.field)
            if level is not None and level.in_order:
                return True
    return False
