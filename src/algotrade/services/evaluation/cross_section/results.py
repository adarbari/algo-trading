"""An evaluation as stored rows and a run record (ADR 0053, ADR 0015): ``results/edge_eval``
gets one row per (edge variant, variant, horizon, slice) of the run's range, published
atomically (pending, then committed); the run record ``edge-eval:<edge>`` keeps the trial log
(the "all" row of each variant and horizon, the count the next run's deflated Sharpe ratio is
taken over), the run hash, the split and whether the run was
exploratory, and how much was excluded."""

from dataclasses import asdict
from datetime import datetime
from typing import Any

import pandas as pd

from algotrade.config.edges.document import MAIN, job_name
from algotrade.services.evaluation.cross_section.harness import (
    EdgeEvaluation,
    VariantResult,
)
from algotrade.services.evaluation.cross_section.measures import BUCKETS, SliceMeasure
from algotrade.services.evaluation.cross_section.random_picks import RANDOM
from algotrade.storage.runs import RunRecord, start_run
from algotrade.storage.tables.result_writer import ResultWriter

RESULT = "edge_eval"
SOURCE = "edge-eval"
MEASURE_COLUMNS = (
    "sessions", "picks", "hits", "hit_rate", "eligible", "base_hits", "base_rate", "lift",
    "mean_excess_picks", "bh_mean", "top_decile_mean", "decile_spread", "decile_t",
    "decile_sessions", "effect_size", "sharpe", "deflated_sharpe", "trials", "pbo",
    "unscored", "excluded_score_coverage", "excluded_unclosed", "excluded_missing",
    "excluded_coverage", "delisted",
    "pre_snapshot_sessions",
)  # fmt: skip


def _nan(value: float | None) -> float:
    return float("nan") if value is None else value


def _row(
    evaluation: EdgeEvaluation,
    m: SliceMeasure,
    edge_variant: str,
    variant: str,
    role: str,
    horizon: int,
    result: VariantResult | None = None,
    config_hash: str = "",
) -> dict[str, Any]:
    """One stored row of ``m``; ``result``: the screener or baseline it measured (none for a
    random draw, which has no config)."""
    measured = asdict(m)
    deciles = m.decile_means or (float("nan"),) * BUCKETS  # none: not measured, never zero
    return {
        "edge_id": evaluation.edge_id,
        "user_id": evaluation.user_id,
        "edge_variant": None if edge_variant == MAIN else edge_variant,
        "variant": variant,
        "role": role,
        "config_hash": result.config_hash if result else config_hash,
        "run_config_hash": evaluation.run_hash,
        "benchmark": evaluation.benchmark,
        "horizon_sessions": horizon,
        "slice_kind": m.slice_kind,
        "slice_value": m.slice_value,
        "range_from": evaluation.start,
        "split_from": evaluation.split_from,
        "exploratory": evaluation.exploratory,
        "in_sample": m.in_sample,
        "range_to": evaluation.end,
        "iv_source": result.iv_source if result else None,
        "licence": result.licence if result else None,
        # Filled by an expires_otm outcome only (ADR 0053 amendment 2026-10-08).
        "reference_rate": _nan(m.reference_rate),
        "touch_rate": _nan(m.touch_rate),
        **{f"decile_mean_{i:02d}": d for i, d in enumerate(deciles, start=1)},
        **{c: measured[c] for c in MEASURE_COLUMNS},
    }


def edge_eval_frame(evaluation: EdgeEvaluation, run_id: str, now: datetime) -> pd.DataFrame:
    """The ``results/edge_eval`` rows of ``evaluation``, stamped."""
    rows = []
    for r in evaluation.results:
        for m in r.measures:
            rows.append(_row(evaluation, m, r.edge_variant, r.variant, r.role, r.horizon, r))
    for random in evaluation.random_picks:
        for m in random.draws:
            rows.append(
                _row(
                    evaluation,
                    m,
                    random.edge_variant,
                    f"{RANDOM}:{random.variant}",
                    RANDOM,
                    random.horizon,
                    config_hash=random.config_hash,
                )
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
        "edge_variant": r.edge_variant,
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
        "no_entry_bar": sum(s.no_entry_bar for s in r.stats),
        "excluded_coverage": m.excluded_coverage,
        "lost_sessions": dict(r.lost_sessions),  # table with no data -> decision sessions
        "report_containment": None
        if r.report_containment is None
        else asdict(r.report_containment),
    }


def lost_sessions(evaluation: EdgeEvaluation) -> list[dict[str, Any]]:
    """The decision sessions each variant lost to a table with no data for them (a screener
    that could not run there), by reason: counted in ``excluded_coverage``, never a miss."""
    return [
        {
            "variant": f"{r.edge_variant}/{r.variant}",
            "horizon": r.horizon,
            "table": table,
            "sessions": n,
        }
        for r in evaluation.results
        for table, n in sorted(r.lost_sessions.items())
    ]


def report_containment(evaluation: EdgeEvaluation) -> list[dict[str, Any]]:
    """Per variant and horizon of an ``earnings_expected`` edge, the share of event windows that
    contained the real report (a diagnostic, ``report_containment.py``; none for other edges)."""
    return [
        {
            "variant": f"{r.edge_variant}/{r.variant}",
            "horizon": r.horizon,
            "windows": r.report_containment.windows,
            "contained": r.report_containment.contained,
            "no_report": r.report_containment.no_report,
        }
        for r in evaluation.results
        if r.report_containment is not None
    ]


def survivorship(evaluation: EdgeEvaluation) -> dict[int, tuple[int, int]]:
    """Per horizon, how many of the evaluated sessions read a universe snapshot taken after
    them (``(n, m)``: the survivorship caveat beside every number over them)."""
    out: dict[int, tuple[int, int]] = {}
    for r in evaluation.results:
        if r.horizon not in out:
            out[r.horizon] = (r.measures[0].pre_snapshot_sessions, r.measures[0].sessions)
    return out


def historical_identity(evaluation: EdgeEvaluation) -> dict[str, Any] | None:
    """The caveat of sessions read before the first reference snapshot (the rule and the names
    by path: today's flag, liquidity proxy); None when the run read none."""
    return None if evaluation.historical is None else evaluation.historical.as_dict()


def write_edge_eval(writer: ResultWriter, evaluation: EdgeEvaluation, now: datetime) -> RunRecord:
    """Save ``evaluation``: its rows (both visible or neither) and its run record, whose stats
    hold the trial log. Returns the finished record."""
    record = start_run(job_name(evaluation.edge_id, evaluation.user_id), evaluation.end, now)
    frame = edge_eval_frame(evaluation, record.run_id, now)
    stats = {
        "edge": evaluation.edge_id,
        "run_hash": evaluation.run_hash,
        "split_from": evaluation.split_from.isoformat() if evaluation.split_from else None,
        "exploratory": evaluation.exploratory,
        "range": [evaluation.start.isoformat(), evaluation.end.isoformat()],
        "as_of": evaluation.as_of.isoformat(),
        "trials_counted": evaluation.trials,
        "trials": [_trial(evaluation, r) for r in evaluation.results],
        "start_sessions": dict(evaluation.start_sessions),
        "unclosed_sessions": dict(evaluation.unclosed_sessions),
        "event_unknown": dict(evaluation.event_unknown),
        "universe_snapshot": evaluation.snapshot.isoformat() if evaluation.snapshot else None,
        "historical_identity": historical_identity(evaluation),
    }
    # The record goes in before the commit: a crash between the two leaves a trial counted
    # without its rows (the deflated Sharpe ratio errs conservative), never rows without a trial.
    with writer.publishing(record.run_id, now):
        writer.write_result(RESULT, evaluation.end, record.run_id, frame, pending=True)
        writer.save_run(record.finish(now, complete=True, stats=stats))
    return record
