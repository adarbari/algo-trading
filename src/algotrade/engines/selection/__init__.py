"""Selection engine: apply a ``Selection`` to point-in-time instrument rows, with an audit."""

from algotrade.engines.selection.evaluate import RuleAudit, SelectionResult, evaluate_selection

__all__ = ["RuleAudit", "SelectionResult", "evaluate_selection"]
