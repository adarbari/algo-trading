"""Reads of the outcomes grain (ADR 0053 decisions 3 and 4): what happened after a start
session, the one table read across sessions. Importable only from ``algotrade.services.evaluation``
(import-linter contract and ``tests/architecture/data/test_outcomes_quarantine.py``): no screener,
strategy, feature or page read can see the future because nothing it may import serves it."""

from algotrade.data.outcomes.reading import (
    OUTCOME_FIELDS,
    missing_outcomes,
    outcome_known,
    outcome_seqs,
    outcome_stamps,
    read_outcomes,
    read_stored,
    select_outcomes,
    stored_sessions,
)
from algotrade.data.outcomes.residuals import (
    NO_RESIDUAL_ROW,
    RESIDUAL_FIELDS,
    attach_residuals,
    read_residuals,
)

__all__ = [
    "NO_RESIDUAL_ROW",
    "OUTCOME_FIELDS",
    "RESIDUAL_FIELDS",
    "attach_residuals",
    "missing_outcomes",
    "outcome_known",
    "outcome_seqs",
    "outcome_stamps",
    "read_outcomes",
    "read_residuals",
    "read_stored",
    "select_outcomes",
    "stored_sessions",
]
