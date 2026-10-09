"""A discovery run as stored rows and a run record (ADR 0053 amendment 2026-10-09, ED6):
``results/winners_study`` gets one run's block effects, pooled tells, proposals and exclusions,
published atomically (pending, then committed, with the run record) so a run is wholly there or
not at all, and the run record keeps what the drafts writer reads: whether the gate passed, the
clusters and their qualifying tells, the seed and the horizon. The count of units is
``blocks``, never "independent sessions": neighbouring blocks' outcome windows overlap."""

from datetime import datetime
from typing import Any

import pandas as pd

from algotrade.services.evaluation.discovery.results import DiscoveryResult
from algotrade.storage.runs import RunRecord, start_run
from algotrade.storage.tables.result_writer import ResultWriter
from algotrade.storage.tables.schemas import WINNERS_STUDY

RESULT = "winners_study"
SOURCE = "winners-study"
JOB = "winners-study"  # the run record's job; the drafts writer finds a run by it
NOTE = (
    "blocks are not independent: the outcome windows of neighbouring blocks overlap, so the "
    "count is a proposal's evidence, never a count of independent sessions"
)


def _row(kind: str, feature: str, **values: Any) -> dict[str, Any]:
    """One row with every column of the table (absent: -1 for a count or index, False, NaN, '')."""
    row: dict[str, Any] = {}
    for c in WINNERS_STUDY.columns:
        if c.type in {"string"}:
            row[c.name] = ""
        elif c.type == "int64":
            row[c.name] = -1
        elif c.type == "bool":
            row[c.name] = False
        elif c.type == "float64":
            row[c.name] = float("nan")
    return {**row, "row_kind": kind, "feature": feature, **values}


def winners_frame(result: DiscoveryResult, run_id: str, now: datetime) -> pd.DataFrame:
    """The ``results/winners_study`` rows of ``result``, stamped."""
    common = {"passed": result.passed, "blocks": result.blocks}
    rows = [
        _row("block", b.feature, block=b.block, mean_g=b.mean_g, sessions=b.sessions, **common)
        for b in result.block_effects
    ]
    rows += [
        _row(
            "tell",
            t.feature,
            block=-1,
            mean_g=t.mean_g,
            sign=t.sign,
            agreeing_blocks=t.agreeing_blocks,
            halves_agree=t.halves_agree,
            stable=t.stable,
            qualifies=t.qualifies,
            cluster=-1 if t.cluster is None else t.cluster,
            sessions=t.blocks,
            **common,
        )
        for t in result.tells
    ]
    rows += [
        _row(
            "proposal",
            p.feature,
            block=-1,
            rank=p.rank,
            coefficient=p.coefficient,
            gain=p.gain,
            rows=p.rows,
            converged=p.converged,
            proposed_by=p.proposed_by,
            **common,
        )
        for p in result.proposals
    ]
    rows += [
        _row("exclusion", x.feature, block=-1, reason=x.reason, sessions=x.sessions, **common)
        for x in result.excluded
    ]
    frame = pd.DataFrame(rows, columns=[c.name for c in WINNERS_STUDY.columns])
    frame["session_date"] = result.sessions[-1].session
    frame["knowledge_ts"] = pd.Timestamp(now)
    frame["source"] = SOURCE
    frame["run_id"] = run_id
    return frame


def run_stats(result: DiscoveryResult) -> dict[str, Any]:
    """What the run record keeps: the gate, the clusters and the qualifying tells with their sign
    (a draft's evidence), the settings that shaped the run, and the blocks caveat."""
    s = result.settings
    return {
        "passed": result.passed,
        "blocks": result.blocks,
        "note": NOTE,
        "grid_sessions": len(result.sessions),
        "observed_clusters": result.observed_clusters,
        "null_counts": list(result.null_counts),
        "null_threshold": result.null_threshold,
        "seed": result.seed,
        "horizon_sessions": s.horizon_sessions,
        "benchmark": s.benchmark,
        "frozen_from": s.frozen_from.isoformat(),
        "clusters": [list(c) for c in result.clusters],
        "tells": [
            {"feature": t.feature, "mean_g": t.mean_g, "sign": t.sign, "cluster": t.cluster}
            for t in result.tells
            if t.qualifies
        ],
    }


def write_winners_study(writer: ResultWriter, result: DiscoveryResult, now: datetime) -> RunRecord:
    """Save ``result``: its rows (all visible or none) and its run record, one run. Returns the
    finished record. The rows go in pending and commit with the record; a crash or an invalid
    frame leaves nothing visible."""
    last = result.sessions[-1].session
    record = start_run(JOB, last, now)
    frame = winners_frame(result, record.run_id, now)
    with writer.publishing(record.run_id, now):
        writer.write_result(RESULT, last, record.run_id, frame, pending=True)
        writer.save_run(record.finish(now, complete=True, stats=run_stats(result)))
    return record
