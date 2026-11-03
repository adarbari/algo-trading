"""How much of a name's biggest recent moves is attributed (EV8, plan 5.5): of the ``TOP_MOVES``
largest absolute close-to-close moves of its last ``YEAR`` sessions (split-adjusted closes through
``data.prices.window_closes``, the session's own included), the share with a row in
``events/attribution`` known by the session (any source: filing, model or analyst review).

A name with fewer than ``MIN_SESSIONS`` sessions of bars has no share (None, never zero): its
biggest moves are not a year's. The attribution rows are read by the one read rule
(``known_from <= S``), so a row written after the session never counts for it."""

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from algotrade.core.time.calendar import sessions_ending
from algotrade.data import StoreReader
from algotrade.data.events import read_events
from algotrade.data.prices import window_closes
from algotrade.features.rollups.event_study.moves import MIN_SESSIONS, TOP_MOVES, YEAR, log_returns

ATTRIBUTION = "events/attribution"


@dataclass(frozen=True)
class MoveShare:
    """``attributed`` of the ``big`` largest moves of the last year have an attribution:
    ``share`` is their ratio (the server's, never the browser's)."""

    big: int
    attributed: int
    share: float


def attributed_moves(
    reader: StoreReader, session: date, instrument_ids: list[str]
) -> dict[str, MoveShare]:
    """The ``MoveShare`` of each of ``instrument_ids`` with a year of bars (the others absent)."""
    if not instrument_ids:
        return {}
    first = sessions_ending(session, YEAR + 1)[0]
    closes = window_closes(reader, [(first, session)], session, instrument_ids)
    if closes.empty:
        return {}
    wide = closes.assign(instrument_id=closes["instrument_id"].astype(str)).pivot_table(
        index="day", columns="instrument_id", values="close", aggfunc="last"
    )
    returns = pd.DataFrame(
        log_returns(wide.to_numpy(dtype=np.float64)), index=wide.index, columns=wide.columns
    )
    attributions = read_events(
        reader, ATTRIBUTION, first, session, instrument_ids, through=session
    ).frame
    explained: set[tuple[str, date]] = set()
    if not attributions.empty:
        days = pd.to_datetime(attributions["ts"], utc=True).dt.date
        explained = set(zip(attributions["instrument_id"].astype(str), days, strict=True))
    out: dict[str, MoveShare] = {}
    for instrument_id in returns.columns:
        series = returns[instrument_id].dropna()
        if wide[instrument_id].notna().sum() < MIN_SESSIONS or series.empty:
            continue
        top = series.abs().sort_values(ascending=False, kind="stable").head(TOP_MOVES)
        hit = sum((instrument_id, pd.Timestamp(day).date()) in explained for day in top.index)
        out[instrument_id] = MoveShare(len(top), hit, hit / len(top))
    return out
