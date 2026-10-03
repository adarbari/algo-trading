from pathlib import Path

import pytest

from algotrade.evaluation.baseline import compare_to_baseline, load_baseline, save_baseline
from algotrade.evaluation.suite import EvaluationRow, with_benchmark_excess

ROWS = [
    EvaluationRow("buy_and_hold", "d", {"sharpe": 1.0, "total_return": 0.1}),
    EvaluationRow("s", "d", {"sharpe": 1.5, "total_return": 0.3}),
]


def test_roundtrip_has_no_diffs(tmp_path: Path) -> None:
    path = tmp_path / "b.json"
    save_baseline(ROWS, path)
    assert compare_to_baseline(ROWS, load_baseline(path)) == []


def test_detects_changed_new_and_missing() -> None:
    baseline = {"s@d": {"sharpe": 1.4, "total_return": 0.3}, "gone@d": {"sharpe": 0.0}}
    descriptions = [d.describe() for d in compare_to_baseline(ROWS, baseline)]
    assert "buy_and_hold@d: new result not in baseline" in descriptions
    assert "gone@d: missing from current run" in descriptions
    assert "s@d.sharpe: 1.4 -> 1.5" in descriptions


def test_rejects_unknown_schema(tmp_path: Path) -> None:
    path = tmp_path / "b.json"
    path.write_text('{"schema_version": 99, "results": {}}')
    with pytest.raises(ValueError, match="schema"):
        load_baseline(path)


def test_benchmark_excess() -> None:
    flat = with_benchmark_excess(ROWS)
    assert flat[1]["excess_sharpe"] == pytest.approx(0.5)
    assert flat[1]["excess_return"] == pytest.approx(0.2)
