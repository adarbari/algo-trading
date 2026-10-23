"""The stored verdict headline, read (ADR 0053 amendment 2026-10-22): the row of
``results/edge_verdict`` for a site edge's canonical run, used only when its fingerprint equals
the one this process computes from the parsed documents now; anything else is ``None``, which
means "judge live" (slower, never wrong), never Waiting on data and never a blank.

The canonical run is still resolved on every read (a row alone cannot prove its run is still
the canonical one: a newer committed run, legacy owners and the exploratory rule live in
``runs.load_canonical_run``), then the row is looked up for exactly that run and fingerprint,
so a row of another run, another judge, other settings or another edge document is never
returned. Own edges and hidden copies never touch the table. The haircut is not stored, so the
full verdict stays live (``rule.load_edge_verdict``)."""

import logging
from typing import Any

import pandas as pd

from algotrade.config.site.settings import load_verdict
from algotrade.config.user import SITE_USER
from algotrade.services.read.context import Stores, run_day_rows
from algotrade.services.read.evaluation import runs
from algotrade.services.read.evaluation.edges import Edge
from algotrade.services.read.evaluation.verdict.fingerprint import fingerprint
from algotrade.services.read.evaluation.verdict.model import EdgeSummary
from algotrade.services.read.evaluation.verdict.rule import judge_call

log = logging.getLogger(__name__)

TABLE = "results/edge_verdict"
KEY = ("edge_id", "user_id", "judged_run_id", "fingerprint")


def _none(value: Any) -> Any:
    """A stored null (None, NaN or pandas' NA) as None: a figure not measured is never 0."""
    return None if value is None or pd.isna(value) else value


def _summary(edge_id: str, row: dict[str, Any]) -> EdgeSummary:
    """The headline of a stored ``row``; ``KeyError`` / ``ValueError`` / ``TypeError`` for a
    row that does not decode (the caller then judges live)."""
    trades, oos_trades = _none(row["trades"]), _none(row["oos_trades"])
    lift, lift_pts = _none(row["lift"]), _none(row["lift_pts"])
    verdict, result = row["verdict"], row["result"]
    if not isinstance(verdict, str) or not isinstance(result, str) or not verdict:
        raise TypeError("a stored verdict row without its level or result")
    return EdgeSummary(
        edge_id,
        verdict,
        result,
        _none(row["basis"]),
        None if trades is None else int(trades),
        None if oos_trades is None else int(oos_trades),
        None if lift is None else float(lift),
        None if lift_pts is None else float(lift_pts),
    )


def load_stored_summary(ctx: Stores, edge: Edge) -> EdgeSummary | None:
    """The stored headline of ``edge``'s canonical run, or None: judge live. None for an own
    edge or hidden copy, a run that is missing or has its out-of-sample result hidden, a row that
    is absent, whose fingerprint differs, or that cannot be read or decoded."""
    if edge.mine:
        return None  # a user's own edge and a hidden copy are always judged live
    run = runs.load_canonical_run(ctx, edge).run  # memoised per request
    if run is None or run.oos_hidden:
        return None  # the live path answers "no run" cheaply
    settings = load_verdict(ctx.configs)
    wanted = (
        edge.id,
        SITE_USER,
        run.run_id,
        fingerprint(judge_call(edge, run, True), run, settings),
    )
    try:
        row = run_day_rows(ctx, TABLE, run.range_to, KEY).get(wanted)
        return None if row is None else _summary(edge.id, row)
    except Exception:  # a cache that cannot be read is a miss, never an error
        log.warning("stored verdict of %s unreadable; judging live", edge.id, exc_info=True)
        return None
