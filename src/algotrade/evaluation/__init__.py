"""Continuous strategy evaluation: every strategy x every golden dataset, vs a baseline."""

from algotrade.evaluation.baseline import compare_to_baseline, load_baseline, save_baseline
from algotrade.evaluation.suite import EvaluationRow, run_suite

__all__ = ["EvaluationRow", "compare_to_baseline", "load_baseline", "run_suite", "save_baseline"]
