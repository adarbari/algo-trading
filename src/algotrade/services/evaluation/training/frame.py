"""The training frame of a learned scorer: the only way labels reach a fit (ADR 0053 amendment,
``docs/edges-plan.md`` ED7). **With ``cross_section/harness.py`` the only module that imports
``algotrade.data.outcomes``** (a fitness test checks both).

A row is (instrument, decision session D) of the edge's schedule (``sessions``), the features the
edge document declares (``[scorer] features``) read at D only (``fields_view``: what was stored
for D, never a later session), and the label: whether the edge's hit held for the window that
starts at the entry session S (``hit.apply_outcome``). A name with a missing feature or a
window with no counted outcome is dropped, never filled.

The fit never sees the frozen period. A window is kept only when it closes (``window_end``) before
the session ``h`` sessions before ``frozen_from``: the window is purged from the frozen period
(no label overlaps it) and one more horizon is embargoed (the last training windows do not abut
the first frozen one), after de Prado's purged cross-validation. The purge reads ``window_end``,
not ``knowledge_ts``: that column is when the row was written (a backfill writes old windows
today), never before the close. ``fitted_through`` is the latest kept ``window_end``.
"""

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from algotrade.config.edges.document import Edge
from algotrade.config.strategy.schema import Selection
from algotrade.core.model.errors import ConfigurationError
from algotrade.core.time.calendar import previous_session, sessions_between
from algotrade.data import StoreReader
from algotrade.data.outcomes import read_outcomes
from algotrade.services.evaluation.cross_section.harness import BENCHMARK
from algotrade.services.evaluation.cross_section.hit import apply_outcome, needs_implied_vol
from algotrade.services.evaluation.cross_section.picks import eligible
from algotrade.services.evaluation.cross_section.sessions import decision_sessions, entry_session
from algotrade.services.selection import fields_view

LABEL = "hit"


@dataclass(frozen=True)
class TrainingFrame:
    """``frame``: one row per (session, instrument_id) with the ``features`` columns and the 0 / 1
    ``hit`` label; ``cutoff``: the date a kept window closed before; ``fitted_through``: the
    date of the latest kept window close (None: no row)."""

    edge_id: str
    horizon: int
    features: tuple[str, ...]
    frame: pd.DataFrame
    cutoff: date
    fitted_through: date | None
    sessions: int  # decision sessions with at least one training row


def purge_cutoff(frozen_from: date, horizon: int) -> date:
    """The session ``horizon`` sessions before ``frozen_from``: a training window must close before
    it (purged and embargoed by one horizon)."""
    day = frozen_from
    for _ in range(horizon):
        day = previous_session(day)
    return day


def training_frame(
    reader: StoreReader,
    edge: Edge,
    universe: Selection,
    start: date,
    until: date,
    horizon: int | None = None,
) -> TrainingFrame:
    """Training rows of ``edge`` over the decision sessions in ``start``..``until`` for the first
    horizon (or ``horizon``). Raises ``ConfigurationError`` for an edge with no ``[scorer]``
    features, no ``frozen_from``, an event schedule or an outcome that needs an implied vol (not
    fitted by ED7a), and ``MissingDataError`` when no outcome is stored."""
    h = horizon or edge.outcome.horizon_sessions[0]
    _check(edge, h)
    assert edge.frozen_from is not None
    cutoff = purge_cutoff(edge.frozen_from, h)
    days = sessions_between(start, until)
    decisions = decision_sessions(edge.schedule, days, h)
    legs = {d: entry_session(d, edge.outcome.start_offset_sessions) for d in decisions}
    outcomes = read_outcomes(reader, h, sorted(set(legs.values())), BENCHMARK)
    outcomes = outcomes[outcomes["window_end"].map(_day) < cutoff]
    closes = {  # the close of each kept window, by (entry session, instrument)
        (_day(r.session_date), r.instrument_id): _day(r.window_end) for r in outcomes.itertuples()
    }
    by_entry = dict(tuple(outcomes.groupby(outcomes["session_date"].map(_day))))
    rows: list[pd.DataFrame] = []
    latest: date | None = None
    for d, s in legs.items():
        if s not in by_entry:
            continue
        ids = sorted(eligible(reader, universe, d).ids)
        counted = apply_outcome(edge, by_entry[s][by_entry[s]["instrument_id"].isin(ids)])
        counted = counted[counted["excluded"] == ""]
        view, _ = fields_view(
            reader, edge.scorer_features, d, [str(i) for i in counted["instrument_id"]]
        )
        values = {
            f: [_number(view.get(i, f)) for i in counted["instrument_id"]]
            for f in edge.scorer_features
        }
        part = pd.DataFrame(
            {"session": d, "instrument_id": counted["instrument_id"].to_numpy(), **values}
        )
        part[LABEL] = counted["hit"].astype(float).to_numpy()
        whole = part[list(edge.scorer_features)].notna().all(axis=1).to_numpy()
        part = part[whole]
        if len(part):
            rows.append(part)
            for i in part["instrument_id"]:
                close = closes[s, i]
                latest = close if latest is None or close > latest else latest
    frame = (
        pd.concat(rows, ignore_index=True)
        if rows
        else pd.DataFrame(columns=["session", "instrument_id", *edge.scorer_features, LABEL])
    )
    return TrainingFrame(
        edge_id=edge.id,
        horizon=h,
        features=edge.scorer_features,
        frame=frame,
        cutoff=cutoff,
        fitted_through=None if latest is None else latest,
        sessions=frame["session"].nunique() if len(frame) else 0,
    )


def _check(edge: Edge, horizon: int) -> None:
    if not edge.scorer_features:
        raise ConfigurationError(f"edge {edge.id}: no [scorer] features to fit on")
    if edge.frozen_from is None:
        raise ConfigurationError(
            f"edge {edge.id}: a scorer needs frozen_from (the fit stops there)"
        )
    if edge.event_class is not None:
        raise ConfigurationError(f"edge {edge.id}: an event schedule is not fitted yet (ED7a)")
    if needs_implied_vol(edge):
        raise ConfigurationError(
            f"edge {edge.id}: an outcome that reads an implied vol is not fitted yet"
        )
    if horizon not in edge.outcome.horizon_sessions:
        raise ConfigurationError(f"edge {edge.id}: horizon {horizon} is not one of its horizons")


def _number(value: object) -> float:
    ok = isinstance(value, (int, float)) and not isinstance(value, bool)
    return float(value) if ok and np.isfinite(float(value)) else float("nan")  # type: ignore[arg-type]


def _day(value: object) -> date:
    return pd.Timestamp(value).date()  # type: ignore[arg-type]
