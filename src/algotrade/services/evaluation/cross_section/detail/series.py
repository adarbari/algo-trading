"""The per-session series of an edge evaluation (ADR 0064 decisions 1 and 3): one
``results/edge_series`` row per (main edge variant, screener or baseline, horizon, measured block
of decision sessions), framed from the run's pooled legs (the stats the measures are over), so no
leg changes and a run needs no re-computation of one. ``exit_session`` is the calendar close of
the window (the curve's x: no point shows a return before it closed); ``before_split`` is
decided here, from the run's split, never re-derived from a date by a reader; ``status`` says why
a block holds no number (``excluded_coverage``, ``lost_input`` with the table in ``lost_table``,
``no_picks``). The rows are written by ``results.write_edge_eval`` inside the run's one publish
block, so a run's series is visible with it or not at all."""

from datetime import datetime

import pandas as pd

from algotrade.config.edges.document import MAIN
from algotrade.services.evaluation.cross_section.detail.windows import BlockWindow
from algotrade.services.evaluation.cross_section.harness import EdgeEvaluation, VariantResult
from algotrade.services.evaluation.cross_section.measures import BUCKETS, SessionStat

RESULT = "edge_series"
SOURCE = "edge-eval"
MEASURED, EXCLUDED_COVERAGE, LOST_INPUT, NO_PICKS = (
    "measured", "excluded_coverage", "lost_input", "no_picks",
)  # fmt: skip
DECILES = tuple(f"decile_mean_{i:02d}" for i in range(1, BUCKETS + 1))


def _status(stat: SessionStat, window: BlockWindow) -> str:
    if window.lost_table is not None:
        return LOST_INPUT
    if stat.excluded_coverage:
        return EXCLUDED_COVERAGE
    return MEASURED if stat.pick_values else NO_PICKS


def _base_mean(stat: SessionStat) -> float | None:
    """The equal-weight mean over every counted eligible name of the block (the picks too)."""
    n = stat.eligible
    if not n:
        return None
    return (sum(stat.pick_values) + stat.rest[0] * stat.rest[1]) / n


def _nan(value: float | None) -> float:
    return float("nan") if value is None else value


def _row(
    evaluation: EdgeEvaluation, r: VariantResult, stat: SessionStat, window: BlockWindow
) -> dict[str, object]:
    split = evaluation.split_from
    status = _status(stat, window)
    measured = status in (MEASURED, NO_PICKS)
    deciles = stat.deciles if measured and stat.deciles else (float("nan"),) * BUCKETS
    assert r.series is not None
    return {
        "edge_id": evaluation.edge_id,
        "user_id": evaluation.user_id,
        "edge_variant": None,  # the main edge variant only (the key's null is read as "main")
        "variant": r.variant,
        "role": r.role,
        "config_hash": r.config_hash,
        "run_config_hash": evaluation.run_hash,
        "benchmark": evaluation.benchmark,
        "horizon_sessions": r.horizon,
        "range_from": evaluation.start,
        "range_to": evaluation.end,
        "split_from": split,
        "exploratory": evaluation.exploratory,
        "decision_session": stat.session,
        "entry_session": window.entry,
        "exit_session": window.exit,
        "block_days": window.days,
        "before_split": split is not None and stat.session < split,
        "regime": stat.regime,
        "status": status,
        "lost_table": window.lost_table,
        "unit": r.series.unit,
        "licence": r.licence,
        # Counts and means are null where nothing was measured, never zero.
        "picks": len(stat.pick_values) if measured else None,
        "pick_hits": stat.pick_hits if measured else None,
        "pick_mean": _nan(stat.pick_mean if measured else None),
        "eligible": stat.eligible if measured else None,
        "base_hits": stat.base_hits if measured else None,
        "base_mean": _nan(_base_mean(stat) if measured else None),
        "excluded_missing": stat.excluded_missing if measured else None,
        "excluded_unmeasured": stat.excluded_unmeasured if measured else None,
        "excluded_score_coverage": stat.excluded_score_coverage if measured else None,
        "no_entry_bar": stat.no_entry_bar if measured else None,
        "no_implied_vol": stat.no_implied_vol if measured else None,
        "outside_universe": stat.outside_universe if measured else None,
        "delisted": stat.delisted if measured else None,
        "unscored": stat.unscored if measured else None,
        **dict(zip(DECILES, deciles, strict=True)),
    }


def edge_series_frame(evaluation: EdgeEvaluation, run_id: str, now: datetime) -> pd.DataFrame:
    """The ``results/edge_series`` rows of ``evaluation``'s main edge variant, stamped; empty
    when it has none (an evaluation built without windows)."""
    rows = [
        _row(evaluation, r, stat, window)
        for r in evaluation.results
        if r.edge_variant == MAIN and r.series is not None
        for stat, window in zip(r.stats, r.series.windows, strict=True)
    ]
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    frame["session_date"] = evaluation.end
    frame["knowledge_ts"] = pd.Timestamp(now)
    frame["source"] = SOURCE
    frame["run_id"] = run_id
    return frame
