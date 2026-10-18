"""The periods of an ``on_market:<trigger>`` time-series edge (ADR 0075, ADR 0073): the trigger
sessions D read from the market entity's stored ``market_triggers@v1`` row, one session at a
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

from datetime import date, datetime

import pandas as pd

from algotrade.config.edges.schedules.markets import MARKET_TRIGGERS
from algotrade.core.model.errors import ConfigurationError
from algotrade.core.model.instruments import market_id
from algotrade.core.time.calendar import next_session, sessions_between
from algotrade.core.time.windows import out_of_window_stretches
from algotrade.data import StoreReader
from algotrade.services.evaluation.time_series.periods import Period, period
from algotrade.services.features import entity_field_view

US = market_id("US")


def triggered(reader: StoreReader, trigger: str, day: date, as_of: datetime) -> bool:
    """Whether ``trigger`` first fired at session ``day``: the stored row of ``day`` says its
    date is ``day`` (UNKNOWN, or an older trigger, is not)."""
    field = MARKET_TRIGGERS[trigger]
    frame, _ = entity_field_view(reader, day, [field], [US], as_of)
    if frame.empty or field not in frame.columns:
        return False
    value = frame.iloc[0][field]
    return bool(pd.notna(value)) and pd.Timestamp(value).date() == day


def _window(decision: date, horizon: int) -> list[date]:
    """The ``horizon`` sessions held after the close of S = D + 1 (the calendar's, also past the
    range end)."""
    out: list[date] = []
    day = next_session(decision)  # S
    while len(out) < horizon:
        day = next_session(day)
        out.append(day)
    return out


def trigger_periods(
    reader: StoreReader, trigger: str, first: date, last: date, horizon: int, as_of: datetime
) -> list[Period]:
    """The windows of ``trigger`` with D in ``[first, last]`` that end by ``last`` and the
    out-of-window stretches of ``horizon`` sessions that end by ``last``, in order of their first
    session."""
    if trigger not in MARKET_TRIGGERS:
        raise ConfigurationError(
            f"unknown market trigger {trigger!r}: one of {sorted(MARKET_TRIGGERS)}"
        )
    if horizon < 1:
        raise ConfigurationError(f"horizon must be >= 1 session, got {horizon}")
    counted: list[list[date]] = []
    occupied: list[list[date]] = []
    for day in sessions_between(first, last):
        if not triggered(reader, trigger, day, as_of):
            continue
        window = _window(day, horizon)
        occupied.append(window)
        if (not counted or window[0] > counted[-1][-1]) and window[-1] <= last:
            counted.append(window)
    stretches = out_of_window_stretches(occupied, horizon, last)
    found = [*(period(w, True) for w in counted), *(period(s, False) for s in stretches)]
    return sorted(found, key=lambda p: p.first)
