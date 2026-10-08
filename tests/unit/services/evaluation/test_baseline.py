from pathlib import Path

import pytest

from algotrade.services.evaluation.baseline import (
    compare_to_baseline,
    diff_metrics,
    edge_metrics,
    load_baseline,
    load_edge_baseline,
    save_baseline,
    save_edge_baseline,
)
from algotrade.services.evaluation.suite import EvaluationRow, with_benchmark_excess

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


EDGE = {"edge": "e", "rows": [
    {"variant": "v", "edge_variant": "main", "horizon_sessions": 20, "slice_kind": "all",
     "slice_value": "all", "sessions": 16, "decile_spread": 0.0569, "decile_t": None,
     "deflated_sharpe": 0.99},
]}  # fmt: skip


def test_edge_baseline_fails_on_drift_beyond_tolerance() -> None:
    current = edge_metrics(EDGE)
    assert current == {"e:main/v@h20/all=all": {"sessions": 16.0, "decile_spread": 0.0569}}
    assert diff_metrics(current, current) == []
    moved = {k: {**v, "decile_spread": 0.0570} for k, v in current.items()}
    assert [d.describe() for d in diff_metrics(moved, current)] == [
        "e:main/v@h20/all=all.decile_spread: 0.0569 -> 0.057"
    ]
    near = {k: {**v, "decile_spread": 0.0569 * (1 + 1e-9)} for k, v in current.items()}
    assert diff_metrics(near, current) == []


def test_save_baseline_preserves_the_other_section(tmp_path: Path) -> None:
    path = tmp_path / "b.json"
    save_baseline(ROWS, path)
    save_edge_baseline(edge_metrics(EDGE), path)
    assert compare_to_baseline(ROWS, load_baseline(path)) == []  # results kept by the edge write
    save_baseline([ROWS[0]], path)
    assert load_edge_baseline(path) == edge_metrics(EDGE)  # edges kept by the results write
    assert list(load_baseline(path)) == ["buy_and_hold@d"]
