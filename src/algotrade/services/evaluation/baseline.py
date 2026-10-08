"""Golden-master regression baseline for strategy results.

``benchmarks/baseline.json`` stores the metrics every strategy produced on every golden
dataset. CI fails if *anything* changes. That is intentional: a change in results is
either a bug or a deliberate improvement, and the latter must be reviewed and committed
explicitly via ``algotrade-backtest evaluate --update-baseline``.

The file has two sections: ``results`` (strategy x dataset) and ``edges`` (the edge harness on
the golden cross-section, ADR 0053: one entry per ``<edge>@h<horizon>/<slice>``). Each is written
by its own command and keeps the other intact (``make baseline`` runs both).
"""

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from algotrade.services.evaluation.suite import EvaluationRow

SCHEMA_VERSION = 1
# The row fields of an ``edge-eval`` result that are held to the baseline: the measures of a
# slice, not the deflated Sharpe ratio or PBO (they depend on the trial log, i.e. on earlier runs).
EDGE_METRICS = (
    "sessions", "picks", "hit_rate", "base_rate", "lift", "mean_excess_picks", "bh_mean",
    "top_decile_mean", "decile_spread", "decile_t", "decile_sessions",
)  # fmt: skip
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


def edge_metrics(result: Mapping[str, Any]) -> dict[str, dict[str, float]]:
    """The baseline entries of one ``edge-eval`` job result: ``<edge>/<variant>@h<h>/<slice>``
    -> the slice's measures (a measure the slice does not have, e.g. no deciles, is left out)."""
    out: dict[str, dict[str, float]] = {}
    for row in result["rows"]:
        variant = (
            f"{row['edge_variant']}/{row['variant']}" if row.get("edge_variant") else row["variant"]
        )
        key = (
            f"{result['edge']}:{variant}@h{row['horizon_sessions']}"
            f"/{row['slice_kind']}={row['slice_value']}"
        )
        out[key] = {m: float(row[m]) for m in EDGE_METRICS if row.get(m) is not None}
    return out


def _read(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(path.read_text())
    if data.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"{path}: unsupported baseline schema {data.get('schema_version')}")
    return data


def _write(path: Path, section: str, metrics: dict[str, dict[str, float]]) -> None:
    """Replace one section of the file, keeping every other section as it is."""
    data: dict[str, Any] = _read(path) if path.exists() else {}
    data[section] = {k: dict(sorted(metrics[k].items())) for k in sorted(metrics)}
    data = {
        "schema_version": SCHEMA_VERSION,
        **{k: data[k] for k in sorted(data) if k != "schema_version"},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")


def save_baseline(rows: list[EvaluationRow], path: Path) -> None:
    _write(path, "results", {r.key: r.metrics for r in rows})


def load_baseline(path: Path) -> dict[str, dict[str, float]]:
    results: dict[str, dict[str, float]] = _read(path)["results"]
    return results


def save_edge_baseline(metrics: dict[str, dict[str, float]], path: Path) -> None:
    _write(path, "edges", metrics)


def load_edge_baseline(path: Path) -> dict[str, dict[str, float]]:
    edges: dict[str, dict[str, float]] = _read(path).get("edges", {})
    return edges


def compare_to_baseline(
    rows: list[EvaluationRow], baseline: dict[str, dict[str, float]]
) -> list[BaselineDiff]:
    return diff_metrics({r.key: r.metrics for r in rows}, baseline)


def diff_metrics(
    current: dict[str, dict[str, float]], baseline: dict[str, dict[str, float]]
) -> list[BaselineDiff]:
    """Every key or metric that is new, missing or moved beyond ``REL_TOL`` / ``ABS_TOL``."""
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
