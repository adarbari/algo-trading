"""Golden-master regression baseline for strategy results.

``benchmarks/baseline.json`` stores the metrics every strategy produced on every golden
dataset. CI fails if *anything* changes. That is intentional: a change in results is
either a bug or a deliberate improvement, and the latter must be reviewed and committed
explicitly via ``algotrade-backtest evaluate --update-baseline``.
"""

import json
import math
from dataclasses import dataclass
from pathlib import Path

from algotrade.services.evaluation.suite import EvaluationRow

SCHEMA_VERSION = 1
REL_TOL = 1e-6
ABS_TOL = 1e-9


@dataclass(frozen=True)
class BaselineDiff:
    key: str
    metric: str
    baseline: float | None
    current: float | None

    def describe(self) -> str:
        if self.baseline is None:
            return f"{self.key}: new result not in baseline"
        if self.current is None:
            return f"{self.key}: missing from current run"
        return f"{self.key}.{self.metric}: {self.baseline:.6g} -> {self.current:.6g}"


def save_baseline(rows: list[EvaluationRow], path: Path) -> None:
    data = {
        "schema_version": SCHEMA_VERSION,
        "results": {
            r.key: dict(sorted(r.metrics.items())) for r in sorted(rows, key=lambda r: r.key)
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")


def load_baseline(path: Path) -> dict[str, dict[str, float]]:
    data = json.loads(path.read_text())
    if data.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"{path}: unsupported baseline schema {data.get('schema_version')}")
    results: dict[str, dict[str, float]] = data["results"]
    return results


def compare_to_baseline(
    rows: list[EvaluationRow], baseline: dict[str, dict[str, float]]
) -> list[BaselineDiff]:
    current = {r.key: r.metrics for r in rows}
    diffs: list[BaselineDiff] = []
    for key in sorted(set(current) | set(baseline)):
        if key not in baseline:
            diffs.append(BaselineDiff(key, "*", None, 0.0))
        elif key not in current:
            diffs.append(BaselineDiff(key, "*", 0.0, None))
        else:
            for metric in sorted(set(current[key]) | set(baseline[key])):
                old, new = baseline[key].get(metric), current[key].get(metric)
                if (
                    old is None
                    or new is None
                    or not math.isclose(old, new, rel_tol=REL_TOL, abs_tol=ABS_TOL)
                ):
                    diffs.append(BaselineDiff(key, metric, old, new))
    return diffs
