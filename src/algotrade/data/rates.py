"""Risk-free rates: the Treasury curve a date sees (``rates/treasury``, ADR 0021).

``curve(reader, on)`` reads the latest stored curve on or before ``on`` through the one
snapshot rule (``data.reference.snapshot``): the bond market has holidays the stock market
does not (and the curve is published after the close), so an exchange session without its
own curve uses the previous one. Before the first stored curve it falls back to the
EARLIEST and flags it (``pre_snapshot``), like every snapshot read. ``Curve.rate(t)`` gives
the continuous rate for a time to expiry in years (``quant.rates.YieldCurve``).
"""

from dataclasses import dataclass
from datetime import date, datetime

import numpy.typing as npt
import pandas as pd

from algotrade.core.model.errors import MissingDataError
from algotrade.data.reference import Snapshot, read_snapshot
from algotrade.quant.rates import Array, YieldCurve
from algotrade.storage.tables.readers import StoreReader

TABLE = "rates/treasury"
HINT = "run `algotrade-ingest rates --from <start> --to <end>` to load the Treasury curve"
COLUMNS = ["tenor", "tenor_days", "rate_par", "rate_cont"]


@dataclass(frozen=True)
class Curve:
    """One stored curve: rows sorted by ``tenor_days`` (``COLUMNS``) and where it came from."""

    frame: pd.DataFrame
    snapshot: Snapshot

    @property
    def curve_date(self) -> date:
        return self.snapshot.snapshot_date

    @property
    def pre_snapshot(self) -> bool:
        """True when the date asked for is before the first stored curve."""
        return self.snapshot.pre_snapshot

    def yield_curve(self) -> YieldCurve:
        return YieldCurve.from_days(self.frame["tenor_days"], self.frame["rate_cont"])

    def rate(self, t: npt.ArrayLike) -> Array:
        """Continuous rate for time to expiry ``t`` in years (linear, flat outside)."""
        return self.yield_curve().rate(t)


def curve(reader: StoreReader, on: date, as_of: datetime | None = None) -> Curve:
    """The Treasury curve for ``on`` (latest on or before, else the earliest, flagged).

    Raises ``MissingDataError`` when no curve is stored."""
    frame, snap = read_snapshot(reader, TABLE, on, HINT, as_of)
    rows = frame.sort_values("tenor_days", kind="stable")[COLUMNS].reset_index(drop=True)
    return Curve(rows, snap)


def curve_as_rows(
    reader: StoreReader, on: date, as_of: datetime | None = None
) -> pd.DataFrame | None:
    """The curve ``on`` sees as rows (``COLUMNS`` plus ``curve_date`` and ``pre_snapshot``),
    or ``None`` when no curve is stored: the feature input ``rates/treasury``."""
    try:
        seen = curve(reader, on, as_of)
    except MissingDataError:
        return None
    return seen.frame.assign(curve_date=seen.curve_date, pre_snapshot=seen.pre_snapshot)


def tenor_history(
    reader: StoreReader, tenor: str, start: date, end: date, as_of: datetime | None = None
) -> pd.DataFrame:
    """The par yield of ``tenor`` on each stored curve dated ``start..end``, oldest first
    (``session_date``, ``rate_par``; empty when none is stored): the feature input
    ``rates/treasury_10y``. A curve is known on its own date, so a session reads those on or
    before it."""
    frame = reader.table_range(TABLE, start, end, as_of, None, ("tenor", "rate_par"))
    if frame is None or frame.empty:
        return pd.DataFrame({"session_date": [], "rate_par": []})
    rows = frame[frame["tenor"] == tenor]
    return (
        rows[["session_date", "rate_par"]]
        .sort_values("session_date", kind="stable")
        .reset_index(drop=True)
    )
