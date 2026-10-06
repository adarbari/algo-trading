"""Use cases: evaluate every strategy on every golden dataset against the baseline, and score the
regime model against the reference crash episodes (``regime_scorecard``, ``regime_report``)."""

from algotrade.services.evaluation.baseline import compare_to_baseline, load_baseline, save_baseline
from algotrade.services.evaluation.suite import EvaluationRow, run_suite

__all__ = ["EvaluationRow", "compare_to_baseline", "load_baseline", "run_suite", "save_baseline"]
