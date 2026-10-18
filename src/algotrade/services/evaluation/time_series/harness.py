"""The reads of a time-series evaluation (ADR 0073): the only module of this package that
imports ``algotrade.data.outcomes`` (a fitness test checks it), as ``cross_section/harness.py``
is the one of its package. It reads the raw (benchmark ``none``) returns of the named instruments
over a window's length from the outcome partition at each period's entry session S, never
anything the partition did not hold at ``as_of``; a period with no usable row has a reason, not a
value (an unclosed window, a missing row and an UNMEASURED one are excluded, never a zero). It also
turns the edge's symbols into ids through ``SymbolResolver`` (ADR 0018) and reads the Treasury bill
rate known at a decision session D, for the "long in the window, bills otherwise" Sharpe ratio."""

from collections.abc import Collection, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime

import pandas as pd

from algotrade.core.model.errors import MissingDataError
from algotrade.data import StoreReader
from algotrade.data.outcomes import read_stored, select_outcomes
from algotrade.data.rates import curve
from algotrade.data.reference import resolver

BENCHMARK = "none"  # raw returns: the window's base is the instrument's own other stretches
BILL_DAYS = 91  # the curve's tenor nearest this one is the bill (about 3 months)
TRADING_DAYS = 252
NO_OUTCOME = "NO_OUTCOME"  # no row at S: the window is not closed, or not computed, or no entry bar
UNKNOWN_SYMBOL = "UNKNOWN_SYMBOL"  # the reference snapshot does not know the symbol


@dataclass(frozen=True)
class Returns:
    """The raw returns read: ``values`` by (instrument id, entry session) and, for each period
    with none, the reason."""

    values: dict[tuple[str, date], float] = field(default_factory=dict)
    reasons: dict[tuple[str, date], str] = field(default_factory=dict)


def resolve_symbols(
    reader: StoreReader, symbols: Sequence[str], on: date, as_of: datetime | None
) -> tuple[dict[str, str], dict[str, str]]:
    """``(ids, reasons)``: the instrument id of each symbol the reference snapshot as of ``on``
    knows, and ``UNKNOWN_SYMBOL`` for the rest."""
    known = resolver(reader, on, as_of)
    ids = {s: known.id_for(s) for s in symbols if known.knows(s)}
    return ids, {s: UNKNOWN_SYMBOL for s in symbols if s not in ids}


def read_returns(
    reader: StoreReader,
    ids: Collection[str],
    entries: Sequence[date],
    horizon: int,
    as_of: datetime,
) -> Returns:
    """The ``horizon``-session raw return of each of ``ids`` over the window starting at each of
    the ``entries`` (S), as the partitions held it at ``as_of``."""
    wanted = sorted(set(entries))
    out = Returns()
    stored = read_stored(reader, wanted, as_of, list(ids)) if wanted and ids else None
    rows: dict[tuple[str, date], pd.Series] = {}
    if stored is not None:
        found = select_outcomes(stored, horizon, wanted, BENCHMARK, as_of)
        for _, row in found.iterrows():
            rows[str(row["instrument_id"]), pd.Timestamp(row["session_date"]).date()] = row
    for i in sorted(ids):
        for entry in wanted:
            found_row = rows.get((i, entry))
            if found_row is None:
                out.reasons[i, entry] = NO_OUTCOME
            elif found_row["outcome_status"] == "UNMEASURED" or pd.isna(found_row["fwd_return"]):
                why = found_row.get("outcome_reason") or "UNKNOWN"
                out.reasons[i, entry] = f"UNMEASURED:{why}"
            else:
                out.values[i, entry] = float(found_row["fwd_return"])
    return out


def bill_returns(
    reader: StoreReader, decisions: Collection[date], horizon: int, as_of: datetime
) -> dict[date, float]:
    """The return of a bill held ``horizon`` sessions, ``rate x horizon / 252``, at the par rate
    of the curve's tenor nearest ``BILL_DAYS`` that D itself saw; a D with no stored curve (or a
    curve only from after it) is left out, never filled."""
    out: dict[date, float] = {}
    for day in sorted(set(decisions)):
        try:
            seen = curve(reader, day, as_of)
        except MissingDataError:
            continue
        if seen.pre_snapshot or seen.frame.empty:
            continue
        frame = seen.frame
        near = frame.iloc[(frame["tenor_days"] - BILL_DAYS).abs().argmin()]
        out[day] = float(near["rate_par"]) * horizon / TRADING_DAYS
    return out
