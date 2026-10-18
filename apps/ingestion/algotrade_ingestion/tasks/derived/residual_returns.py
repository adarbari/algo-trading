"""The ``residual-returns`` task (ADR 0053 amendment, EB H11): for every forward-outcome window a
session closes, write each name's factor-neutral return to
``outcomes/instrument/residual_returns@v1``, the sibling grain of ``forward_returns@v2`` that only
the edge harness reads (``algotrade.data.outcomes``).

The windows, names and horizons are the ``outcomes`` task's own (the same universe at S,
delistings and flagged bars; ``outcome_paths.window_rows`` gives each name's return and status;
the horizons are the open edges' that measure ``residual_return``, with the harness default): a
window of S..T over h sessions is written to partition S.
Per name the row carries the return minus the loadings times the factor returns of the window
(``residual_paths``), from the ``factor_betas@v1`` rows of the session before S (252 sessions
ending there: nothing of the window is in them). A name the betas or the factor ETFs cannot
cover is UNMEASURED with a reason
(MTUM and VLUE start in 2013, so earlier windows all say ``NO_FACTOR_HISTORY``); the forward
grain's rows are untouched, so no stored leg is invalidated.

``--from/--to`` backfills run each window-end session as its own run, as ``outcomes`` does, and
need ``factor_betas@v1`` stored for the sessions before each S (``algotrade-ingest rollups
--only factor_betas@v1 --from ... --to ...``): without it every name is ``NO_BETAS``. The nightly
(no ``--from``) recomputes the last ``RECHECK + 1`` window ends; the nightly step of the same
name runs it after ``outcomes`` and ``rollups`` and accepts it with ``check_residual_returns``.
"""

from collections.abc import Sequence
from datetime import date

import pandas as pd

from algotrade.config.edges.document import CLOSED, EXCESS_MEASURES
from algotrade.config.edges.loading import Documents, load_edges
from algotrade.config.site.settings import SourcesSettings
from algotrade.core.time.calendar import (
    close_time,
    previous_session,
    sessions_between,
    sessions_ending,
)
from algotrade.data import StoreReader
from algotrade.data.prices import SessionBars
from algotrade.data.rollups import rollup_rows
from algotrade.features.rollups.relative.factor_betas import BETAS
from algotrade.storage.runs import RunRecord, RunStatus
from algotrade.storage.tables.schemas import FORWARD_RETURNS, RESIDUAL_RETURNS
from algotrade_ingestion.tasks.derived.outcome_paths import wide_closes, window_rows
from algotrade_ingestion.tasks.derived.outcomes import (
    CHUNK,
    DEFAULT_HORIZON,
    RECHECK,
    SITE,
    left_by,
    read_panel,
    scope_of,
    universe_ids,
    windows,
)
from algotrade_ingestion.tasks.derived.residual_paths import FACTOR_ETFS, residual_rows
from algotrade_ingestion.tasks.framework.run import IngestRun, TaskContext
from algotrade_ingestion.tasks.maintenance.quality import Check

TASK = "residual-returns"
SOURCE = "residual_returns"
TABLE = RESIDUAL_RETURNS
TABLES = (TABLE,)
FACTOR_BETAS = "rollups/instrument/factor_betas@v1"  # the group's table (features.rollups.relative)


def residual_horizons(configs: Documents | None = None) -> list[int]:
    """The horizons (sessions) of the open edges that measure ``residual_return``, with the
    harness default (``DEFAULT_HORIZON``, always computed)."""
    edges = [e for e in load_edges(configs or SITE) if e.status not in CLOSED]
    outcomes = [o for e in edges for o in (e.outcome, *(v.outcome for v in e.variants))]
    horizons = {DEFAULT_HORIZON} | {
        h for o in outcomes if o.measure in EXCESS_MEASURES for h in o.horizon_sessions
    }
    return sorted(horizons)


def compute_residual_returns(
    ctx: TaskContext, session: date, start: date | None = None, end: date | None = None
) -> RunRecord:
    """The residual returns of the windows ``session`` and the ``RECHECK`` sessions before it
    close, or of every window-end session in ``start..end`` (one run each) -> the last run."""
    ends = (
        sessions_between(start, end or session) if start else sessions_ending(session, RECHECK + 1)
    )
    if not ends:
        raise ValueError(f"no exchange session in {start}..{end or session}")
    if close_time(ends[-1]) > ctx.clock():
        raise ValueError(f"the window ending {ends[-1]} has not closed yet")
    horizons = residual_horizons(ctx.configs)
    nightly = start is None
    gone, listed, first = scope_of(ctx.reader, ends[-1])
    record: RunRecord | None = None
    for i in range(0, len(ends), CHUNK):
        chunk = ends[i : i + CHUNK]
        panel = read_panel(ctx, chunk, horizons, nightly, first)
        betas: dict[date, pd.DataFrame | None] = {}  # the betas of a session before S, once
        for t in chunk:
            record = _one(ctx, t, horizons, first, panel, gone, listed, nightly, betas)
    assert record is not None
    return record


def _one(
    ctx: TaskContext,
    end: date,
    horizons: Sequence[int],
    first: date,
    panel: SessionBars,
    gone: dict[str, date],
    listed: dict[str, date],
    nightly: bool,
    betas: dict[date, pd.DataFrame | None],
) -> RunRecord:
    left = left_by(end, gone, listed)
    with IngestRun(ctx, TASK, end) as run:
        for h, window in windows(run, end, horizons, first, nightly):
            names, _ = universe_ids(run.reader, window.start, not nightly)
            resolver = run.resolver(window.start)
            etf = {t: resolver.id_for(t) for t in FACTOR_ETFS if resolver.knows(t)}
            prices = panel.window(window.start, end)
            forward, _ = window_rows(prices, window, names, None, left, panel.flagged)
            before = previous_session(window.start)  # the betas known before the entry close
            if before not in betas:
                betas[before] = _betas_at(run.reader, before)
            out = residual_rows(
                forward, wide_closes(prices, window, "close"), window, etf, betas[before], before
            )
            out = out.assign(
                ts=close_time(window.start), horizon_sessions=h, window_end=end
            ).sort_values("instrument_id", kind="stable")
            if len(out):
                run.write(TABLE, out.reset_index(drop=True), SOURCE, session=window.start)
            why = out.loc[out["outcome_status"] == "UNMEASURED", "outcome_reason"].value_counts()
            run.record_item(f"h{h}", f"OK: {len(out)} rows")
            run.stats[f"h{h}"] = {
                "start": window.start.isoformat(),
                "rows": len(out),
                "measured": int((out["outcome_status"] != "UNMEASURED").sum()),
                "unmeasured": {str(k): int(v) for k, v in why.items()},
                "beta_session": before.isoformat(),
                "betas_stored": betas[before] is not None,
            }
    return run.record


def _betas_at(reader: StoreReader, day: date) -> pd.DataFrame | None:
    """``factor_betas@v1``'s rows of exactly ``day`` (never an older partition), indexed by
    instrument id; None: not stored."""
    rows = rollup_rows(reader, FACTOR_BETAS, day, day)
    if rows is None:
        return None
    rows = rows[["instrument_id", *BETAS[:4], "factor_status"]].assign(
        instrument_id=lambda f: f["instrument_id"].astype(str)
    )
    return rows.drop_duplicates("instrument_id", keep="last").set_index("instrument_id")


def check_residual_returns(reader: StoreReader, session: date, s: SourcesSettings) -> list[Check]:
    """The acceptance of the ``residual-returns`` step for window end ``session``: for each
    horizon the run computed, every name the forward outcomes of that window hold has a residual
    row (counted again here from the stored partitions, not taken from the run), and the run's
    rows are stored. Names the factors or betas cannot cover are UNMEASURED rows, a WARN naming
    the reasons, never a failure: they are the grain's honest gaps."""
    runs = [r for r in reader.runs(TASK, session) if r.status == RunStatus.COMPLETE]
    if not runs:
        return [
            Check("residual-returns", "FAIL", f"no complete residual-returns run for {session}")
        ]
    problems: list[str] = []
    gaps: list[str] = []
    for key, value in sorted(runs[-1].stats.items()):
        if not (key.startswith("h") and isinstance(value, dict)):
            continue
        start, horizon = date.fromisoformat(value["start"]), int(key[1:])
        mine = _names(reader.table(TABLE, start), session, horizon)
        forward = _names(reader.table(FORWARD_RETURNS, start), session, horizon)
        if forward - mine or len(mine) != value["rows"]:
            problems.append(
                f"{key}: {len(forward - mine)} forward rows without a residual row, "
                f"{len(mine)} of {value['rows']} rows stored"
            )
        if value["unmeasured"]:
            gaps.append(f"{key}: {value['unmeasured']}")
    if problems:
        return [Check("residual-returns", "FAIL", "; ".join(problems))]
    detail = f"every forward outcome of {session}'s windows has a residual row"
    if gaps:
        return [Check("residual-returns", "WARN", f"{detail}; unmeasured: {'; '.join(gaps)}")]
    return [Check("residual-returns", "PASS", detail)]


def _names(frame: pd.DataFrame | None, session: date, horizon: int) -> set[str]:
    """The instrument ids of ``frame``'s rows of one window end and horizon."""
    if frame is None:
        return set()
    keep = (pd.to_datetime(frame["window_end"]).dt.date == session) & (
        frame["horizon_sessions"] == horizon
    )
    return set(frame.loc[keep, "instrument_id"].astype(str))
