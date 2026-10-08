"""Reads of the outcomes grain (ADR 0053 decisions 3 and 4): what happened after a start
session, the one table read across sessions. Importable only from ``algotrade.services.evaluation``
(import-linter contract and ``tests/architecture/data/test_outcomes_quarantine.py``): no screener,
strategy, feature or page read can see the future because nothing it may import serves it."""

from algotrade.data.outcomes.reading import OUTCOME_FIELDS, read_outcomes

__all__ = ["OUTCOME_FIELDS", "read_outcomes"]
