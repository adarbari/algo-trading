"""The stored verdict headline of an edge evaluation (ADR 0053 amendment 2026-10-22):
``results/edge_verdict``, one row for the site edge's run, framed by the one judge and published
in the run's own atomic publish beside its ``edge_eval`` rows.

The frame judges the run's in-memory ``edge_eval`` frame (its rows are still pending, so the
reader's path cannot see them) as the reader judges the stored ones: the same parse
(``runs.rows_of_frame``), the same judge call (``rule.judge_call``) and the same settings, so
the row equals what ``load_edge_verdict`` would answer from the committed rows. Only a run the
list would call canonical gets a row: the site's, at the edge's own frozen period, not
exploratory. Anything else gets none, and the reader judges live. The headline only: the haircut
moves with the site's trials, so it is never stored. Written by the edge-eval publish (and the
edge-verdicts task, through ``verdict_frame``); ML never frames it (ADR 0053 decision 8)."""

from datetime import datetime
from typing import Any

import pandas as pd

from algotrade.config.edges.document import MAIN, job_name
from algotrade.config.edges.verdict import VerdictSettings
from algotrade.config.site.settings import load_verdict
from algotrade.config.user import SITE_USER
from algotrade.services.read.context import Stores
from algotrade.services.read.evaluation import edges, runs
from algotrade.services.read.evaluation.edges import Edge
from algotrade.services.read.evaluation.runs import EdgeRow, EdgeRun
from algotrade.services.read.evaluation.verdict import fingerprint as stamp
from algotrade.services.read.evaluation.verdict.model import EdgeSummary, summary_of
from algotrade.services.read.evaluation.verdict.rule import judge, judge_call
from algotrade.storage.runs import RunRecord
from algotrade.storage.tables.edge_schemas import EDGE_VERDICT

RESULT = EDGE_VERDICT.name.removeprefix("results/")
SOURCE = "edge-eval"  # the writer when the run's own publish frames it


def canonical_kind(edge: Edge, run: EdgeRun) -> bool:
    """Whether ``run`` is a run the reader would resolve as ``edge``'s canonical one: the site's
    own edge (never a user's copy), its out-of-sample result shown, a frozen period, at which the
    run was split and which is not exploratory. Anything else is never stored."""
    return (
        not edge.mine
        and edge.frozen_from is not None
        and not run.oos_hidden
        and not run.exploratory
        and run.owner == SITE_USER
        and run.split_from == edge.frozen_from
    )


def _licence(rows: tuple[EdgeRow, ...]) -> str | None:
    """The strictest licence of the main edge variant's rows: ``personal`` if any row has it,
    else the first by name; None when none is recorded (a run from before licences)."""
    found = {r.licence for r in rows if r.edge_variant == MAIN and r.licence}
    if runs.PERSONAL in found:
        return runs.PERSONAL
    return min(found) if found else None


def verdict_frame(
    summary: EdgeSummary,
    run: EdgeRun,
    *,
    fingerprint: str,
    settings: VerdictSettings,
    licence: str | None,
    run_id: str,
    source: str,
    now: datetime,
) -> pd.DataFrame:
    """The one ``results/edge_verdict`` row of ``summary``, the headline of ``run`` under
    ``fingerprint``, stamped: ``run_id`` and ``source`` name the writer, ``now`` is the
    ``knowledge_ts`` (the write instant, never back-dated). A number that was not measured
    stays null, never 0."""
    row: dict[str, Any] = {
        "edge_id": summary.edge_id,
        "user_id": SITE_USER,
        "judged_run_id": run.run_id,
        "fingerprint": fingerprint,
        "judge_version": stamp.JUDGE_VERSION,
        "judge_digest": stamp.judge_digest(),
        "settings_hash": stamp.settings_hash(settings),
        "split_from": run.split_from,
        "verdict": summary.verdict,
        "result": summary.result,
        "basis": summary.basis,
        "trades": summary.trades,
        "oos_trades": summary.oos_trades,
        "lift": summary.lift,
        "lift_pts": summary.lift_pts,
        "licence": licence,
    }
    frame = pd.DataFrame([row])
    for column in ("trades", "oos_trades"):  # a null count stays null, never a float or a 0
        frame[column] = frame[column].astype("Int64")
    frame["session_date"] = run.range_to
    frame["knowledge_ts"] = pd.Timestamp(now)
    frame["source"] = source
    frame["run_id"] = run_id
    return frame


def edge_verdict_frame(
    stores: Stores, edge_id: str, record: RunRecord, frame: pd.DataFrame, now: datetime
) -> pd.DataFrame | None:
    """The ``results/edge_verdict`` row of the run ``record`` that is publishing ``frame`` (its
    ``edge_eval`` rows), or None when the run is not one a reader would resolve as canonical (a
    user's, exploratory, at another split, or an edge the site has no document for): the reader
    then judges live."""
    edge = edges.load_edge(stores, edge_id)
    if edge is None:
        return None
    if record.job != job_name(edge_id, SITE_USER):  # a run of another user's: never the site's
        return None
    run = runs.run_of_record(record, edge, str(record.stats.get("owner") or SITE_USER))
    if not canonical_kind(edge, run):
        return None
    settings = load_verdict(stores.configs)
    rows, draws = runs.rows_of_frame(frame)
    call = judge_call(edge, run, True)
    verdict = judge(rows=rows, draws=draws, t=settings, headline=True, **call.kwargs())
    return verdict_frame(
        summary_of(verdict),
        run,
        fingerprint=stamp.fingerprint(call, run, settings),
        settings=settings,
        licence=_licence(rows),
        run_id=record.run_id,
        source=SOURCE,
        now=now,
    )
