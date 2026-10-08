"""An evaluation as stored rows and a run record (ADR 0053, ADR 0015): ``results/edge_eval``
gets one row per (variant, horizon, slice) of the run's range, published atomically (pending,
then committed); the run record ``edge-eval:<edge>`` keeps the trial log (the "all" row of each
variant and horizon, the count the next run's deflated Sharpe ratio is taken over), the run
hash and how much was excluded."""

from dataclasses import asdict
from datetime import datetime
from typing import Any

import pandas as pd

from algotrade.services.evaluation.cross_section.harness import (
    EdgeEvaluation,
    VariantResult,
    job_name,
)
from algotrade.storage.runs import RunRecord, start_run
from algotrade.storage.tables.result_writer import ResultWriter

RESULT = "edge_eval"
SOURCE = "edge-eval"
MEASURE_COLUMNS = (
    "sessions", "picks", "hits", "hit_rate", "eligible", "base_hits", "base_rate", "lift",
    "mean_excess_picks", "bh_mean", "top_decile_mean", "decile_spread", "decile_t",
    "decile_sessions", "effect_size", "sharpe", "deflated_sharpe", "trials", "pbo",
    "excluded_unclosed", "excluded_missing", "excluded_coverage", "delisted",
    "pre_snapshot_sessions",
)  # fmt: skip


def edge_eval_frame(evaluation: EdgeEvaluation, run_id: str, now: datetime) -> pd.DataFrame:
    """The ``results/edge_eval`` rows of ``evaluation``, stamped."""
    rows = []
    for r in evaluation.results:
        for m in r.measures:
            measured = asdict(m)
            rows.append(
                {
                    "edge_id": evaluation.edge_id,
                    "user_id": evaluation.user_id,
                    "variant": r.variant,
                    "role": r.role,
                    "config_hash": r.config_hash,
                    "run_config_hash": evaluation.run_hash,
                    "benchmark": evaluation.benchmark,
                    "horizon_sessions": r.horizon,
                    "slice_kind": m.slice_kind,
                    "slice_value": m.slice_value,
                    "range_from": evaluation.start,
                    "range_to": evaluation.end,
                    **{c: measured[c] for c in MEASURE_COLUMNS},
                }
            )
    frame = pd.DataFrame(rows)
    frame["session_date"] = evaluation.end
    frame["knowledge_ts"] = pd.Timestamp(now)
    frame["source"] = SOURCE
    frame["run_id"] = run_id
    return frame


def records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    """``frame``'s rows as JSON-able dicts (a missing number is None, never NaN)."""
    return [
        {str(k): (None if pd.isna(v) else v) for k, v in row.items()}
        for row in frame.drop(columns=["knowledge_ts", "session_date"]).to_dict("records")
    ]


def _trial(evaluation: EdgeEvaluation, r: VariantResult) -> dict[str, Any]:
    m = r.measures[0]  # the "all" slice
    eligible = sum(s.eligible for s in r.stats)
    return {
        "variant": r.variant,
        "role": r.role,
        "config_hash": r.config_hash,
        "horizon": r.horizon,
        "sessions": m.sessions,
        "picks": m.picks,
        "hit_rate": m.hit_rate,
        "base_rate": m.base_rate,
        "lift": m.lift,
        "decile_spread": m.decile_spread,
        "sharpe": m.sharpe,
        "deflated_sharpe": m.deflated_sharpe,
        "ranked_share": sum(s.ranked for s in r.stats) / eligible if eligible else None,
        "outside_universe": sum(s.outside_universe for s in r.stats),
        "excluded_coverage": m.excluded_coverage,
    }


def survivorship(evaluation: EdgeEvaluation) -> dict[int, tuple[int, int]]:
    """Per horizon, how many of the evaluated sessions read a universe snapshot taken after
    them (``(n, m)``: the survivorship caveat beside every number over them)."""
    out: dict[int, tuple[int, int]] = {}
    for r in evaluation.results:
        if r.horizon not in out:
            out[r.horizon] = (r.measures[0].pre_snapshot_sessions, r.measures[0].sessions)
    return out


def write_edge_eval(writer: ResultWriter, evaluation: EdgeEvaluation, now: datetime) -> RunRecord:
    """Save ``evaluation``: its rows (both visible or neither) and its run record, whose stats
    hold the trial log. Returns the finished record."""
    record = start_run(job_name(evaluation.edge_id, evaluation.user_id), evaluation.end, now)
    frame = edge_eval_frame(evaluation, record.run_id, now)
    stats = {
        "edge": evaluation.edge_id,
        "run_hash": evaluation.run_hash,
        "range": [evaluation.start.isoformat(), evaluation.end.isoformat()],
        "as_of": evaluation.as_of.isoformat(),
        "trials_counted": evaluation.trials,
        "trials": [_trial(evaluation, r) for r in evaluation.results],
        "start_sessions": dict(evaluation.start_sessions),
        "unclosed_sessions": dict(evaluation.unclosed_sessions),
        "universe_snapshot": evaluation.snapshot.isoformat() if evaluation.snapshot else None,
    }
    # The record goes in before the commit: a crash between the two leaves a trial counted
    # without its rows (the deflated Sharpe ratio errs conservative), never rows without a trial.
    with writer.publishing(record.run_id, now):
        writer.write_result(RESULT, evaluation.end, record.run_id, frame, pending=True)
        writer.save_run(record.finish(now, complete=True, stats=stats))
    return record
