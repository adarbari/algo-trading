"""The trade ledger of an evaluation (ADR 0064 decision 2): ``results/edge_trades``, one row per
pick of the main edge variant's implementation screeners at every horizon, framed from the run's
v2 legs (``harness.LegDetail``), never recomputed.

A pick is ``won`` or ``lost`` by the edge's own hit (``hit.apply_outcome``), or ``excluded`` with
the public kind of its reason (``EXCLUDED_KINDS``); eligible names that were not picked are never
listed. ``exit_session`` is S + h sessions (the window's close, from the calendar);
``before_split`` is the side of the run's split the leg's block is on, as for the slices (a run
with no split has no out-of-sample side: every row is before it). A block the screen could not
measure has no rows, as it has no statistic. Rows are ordered by their key, so a run's ledger is
a pure function of its legs."""

from datetime import datetime
from typing import Any

import pandas as pd

from algotrade.config.edges.document import MAIN
from algotrade.services.evaluation.cross_section.harness import (
    EdgeEvaluation,
    LegDetail,
    VariantResult,
)
from algotrade.services.evaluation.cross_section.hit import (
    INVALID_IMPLIED_VOL,
    MISSING_DRAWDOWN,
    MISSING_VALUE,
    NO_IMPLIED_VOL,
    UNMEASURED,
)
from algotrade.services.evaluation.cross_section.measures import SCREENER, Pick
from algotrade.services.evaluation.cross_section.measuring import NO_ENTRY_BAR
from algotrade.services.evaluation.cross_section.reporting.report_containment import window_end
from algotrade.storage.tables.edge_schemas import EDGE_TRADES

RESULT = EDGE_TRADES.name.removeprefix("results/")
SOURCE = "edge-eval"
WON, LOST, EXCLUDED = "won", "lost", "excluded"
STATUSES = (WON, LOST, EXCLUDED)
# The harness's reason for a pick it did not count -> its public kind (ADR 0064, ADR 0056).
EXCLUDED_KINDS = {
    UNMEASURED: "UNMEASURED",
    MISSING_VALUE: "MISSING_VALUE",
    NO_ENTRY_BAR: "NO_ENTRY_BAR",
    NO_IMPLIED_VOL: "NO_IMPLIED_VOL",
    INVALID_IMPLIED_VOL: "NO_IMPLIED_VOL",
    MISSING_DRAWDOWN: "MISSING_DRAWDOWN",
}
ORDER = ["variant", "horizon_sessions", "decision_session", "side", "rank"]


def _status(pick: Pick) -> tuple[str, str | None]:
    if pick.reason == "":
        return (WON if pick.hit else LOST), None
    kind = EXCLUDED_KINDS.get(pick.reason)
    if kind is None:  # a new harness reason must get its public kind here first
        raise ValueError(f"no public kind for the exclusion reason {pick.reason!r}")
    return EXCLUDED, kind


def _row(ev: EdgeEvaluation, r: VariantResult, leg: LegDetail, pick: Pick) -> dict[str, Any]:
    status, kind = _status(pick)
    licences = r.licences
    return {
        "edge_id": ev.edge_id,
        "user_id": ev.user_id,
        "edge_variant": None,  # the main edge variant, stored as on edge_eval
        "variant": r.variant,
        "side": pick.side,
        "role": r.role,
        "config_hash": r.config_hash,
        "run_config_hash": ev.run_hash,
        "benchmark": ev.benchmark,
        "horizon_sessions": r.horizon,
        "range_from": ev.start,
        "range_to": ev.end,
        "split_from": ev.split_from,
        "exploratory": ev.exploratory,
        "decision_session": leg.decision,
        "entry_session": leg.entry,
        "exit_session": window_end(leg.entry, r.horizon),
        "before_split": ev.split_from is None or leg.block < ev.split_from,
        "instrument_id": pick.instrument_id,
        "rank": pick.rank,
        "score": pick.score,
        "value": pick.value,
        "gross_value": pick.gross,
        "hit": pick.hit if status != EXCLUDED else None,
        "status": status,
        "excluded_reason": kind,
        "delisted": pick.delisted,
        "max_drawdown": pick.drawdown,
        "adv_usd_20d": pick.adv,
        "reference": pick.reference,
        "touch": pick.touch,
        "licence": r.licence,
        "value_licence": licences.value if licences else None,
        "score_licence": licences.score if licences else None,
        "adv_licence": licences.adv if licences else None,
    }


def trades_frame(evaluation: EdgeEvaluation, run_id: str, now: datetime) -> pd.DataFrame:
    """The ``results/edge_trades`` rows of ``evaluation``, stamped and ordered by key (empty:
    no pick of an implementation screener)."""
    rows = [
        _row(evaluation, r, leg, pick)
        for r in evaluation.results
        if r.edge_variant == MAIN and r.role == SCREENER  # implementations, never a baseline
        for leg in r.legs
        for pick in leg.stat.picks
    ]
    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame(rows).sort_values(ORDER, kind="stable").reset_index(drop=True)
    frame["session_date"] = evaluation.end
    frame["knowledge_ts"] = pd.Timestamp(now)
    frame["source"] = SOURCE
    frame["run_id"] = run_id
    return frame
