"""The periods of an ``on_market:<trigger>`` time-series edge (ADR 0075, ADR 0073): the trigger
sessions D read from the market entity's stored ``market_triggers@v2`` row, one session at a
time (the row of D holds D as the trigger's date: first known at D, never before), each placed as a
window of ``horizon`` sessions that starts after S = D + 1's close, and the stretches of the same
length outside every window.

A trigger within ``horizon`` sessions of the last counted window is skipped (its window would
overlap it: windows of one kind never overlap, so a period is one unit for every count). A window
that runs past the range end is not counted but still occupies its sessions, as does a skipped
trigger's, so the base never contains a stretch the trigger moved. The base is tiled by
``core.time.windows.out_of_window_stretches`` and depends on the triggers inside the range, so a
stretch near the range end can change when the range is extended (the run record says so). A
session whose row is not stored, or holds no trigger date, is no trigger, never a window. Reads
only the market entity's feature row; the outcomes are read by ``harness.py`` alone."""

from dataclasses import dataclass
from datetime import date, datetime

import pandas as pd

from algotrade.config.edges.schedules.markets import MARKET_TRIGGER_AGE, MARKET_TRIGGERS
from algotrade.core.model.errors import ConfigurationError
from algotrade.core.model.instruments import market_id
from algotrade.core.time.calendar import (
    next_session,
    sessions_between,
    sessions_ending,
)
from algotrade.core.time.windows import out_of_window_stretches
from algotrade.data import StoreReader
from algotrade.services.evaluation.time_series.periods import Period, period
from algotrade.services.features import entity_field_view

US = market_id("US")


STALE = "STALE_TRIGGER"  # the lost reason of a stretch left out: its trigger reading was not known


@dataclass(frozen=True)
class Placed:
    """The periods of a trigger edge and the base stretches left out for a stale reading."""

    periods: list[Period]
    dropped: int = 0


def reading(
    reader: StoreReader, trigger: str, day: date, as_of: datetime
) -> tuple[bool, bool] | None:
    """``(triggered, known)`` of ``trigger`` at session ``day`` from the stored market row:
    triggered when its date is ``day``, known unless the age field is null (a stale reading).
    ``None``: the partition is not stored."""
    fields = [MARKET_TRIGGERS[trigger], MARKET_TRIGGER_AGE[trigger]]
    frame, missing = entity_field_view(reader, day, fields, [US], as_of)
    if missing or frame.empty:
        return None
    row = frame.iloc[0]
    known = bool(pd.notna(row[fields[1]]))
    value = row[fields[0]]
    return bool(pd.notna(value)) and pd.Timestamp(value).date() == day, known


def _window(decision: date, horizon: int) -> list[date]:
    """The ``horizon`` sessions held after the close of S = D + 1 (the calendar's, also past the
    range end)."""
    out: list[date] = []
    day = next_session(decision)  # S
    while len(out) < horizon:
        day = next_session(day)
        out.append(day)
    return out


def sessions_after(p: Period, horizon: int) -> list[date]:
    """The ``horizon`` sessions a period holds (from its first session)."""
    out, day = [p.first], p.first
    while len(out) < horizon:
        day = next_session(day)
        out.append(day)
    return out


def trigger_periods(
    reader: StoreReader, trigger: str, first: date, last: date, horizon: int, as_of: datetime
) -> Placed:
    """The windows of ``trigger`` with D in ``[first, last]`` that end by ``last`` and the
    out-of-window stretches of ``horizon`` sessions that end by ``last`` (tiled from ``first``,
    none holding a session whose reading was stale), in order of their first session."""
    if trigger not in MARKET_TRIGGERS:
        raise ConfigurationError(
            f"unknown market trigger {trigger!r}: one of {sorted(MARKET_TRIGGERS)}"
        )
    if horizon < 1:
        raise ConfigurationError(f"horizon must be >= 1 session, got {horizon}")
    counted: list[list[date]] = []
    occupied: list[list[date]] = []
    stale: set[date] = set()
    early = [
        d for d in sessions_ending(first, horizon + 2) if d < first
    ]  # earlier triggers' windows run into the range
    for day in [*early, *sessions_between(first, last)]:
        got = reading(reader, trigger, day, as_of)
        if got is None:
            if day >= first:
                raise ConfigurationError(
                    f"market trigger {trigger}: no stored market row for {day}: run the "
                    f"market rollups before the evaluation"
                )
            continue  # before the range: nothing to place
        fired, known = got
        if not known:
            stale.add(day)
        if not fired:
            continue
        window = _window(day, horizon)
        occupied.append(window)
        if day >= first and (not counted or window[0] > counted[-1][-1]) and window[-1] <= last:
            counted.append(window)
    stretches = out_of_window_stretches(occupied, horizon, last, first)
    base = [period(s, False) for s in stretches]
    kept = [p for p in base if not stale & {p.decision, p.entry, *sessions_after(p, horizon)}]
    found = [*(period(w, True) for w in counted), *kept]
    return Placed(sorted(found, key=lambda p: p.first), len(base) - len(kept))
