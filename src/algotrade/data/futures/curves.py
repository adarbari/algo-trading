"""The futures curves of the nightly snapshots (``rates/futures_curve``, personal licence).

One partition per session, a row per listed contract among a root's front months (the
``futures-curves`` task, IB Gateway, read-only). ``futures_curve`` reads a range through the
store's point-in-time rule (``as_of``: only rows stored by then) and returns the rows sorted
by session, root and expiry; ``curve_of`` is one root's curve for one session, from which the
basis (back price over front price) and the annualised roll yield are rebuilt. A session
without a stored snapshot has no curve: nothing is carried from an older one (history accrues
from the first night, it is not backfilled).
"""

from collections.abc import Sequence
from datetime import date, datetime

import numpy as np
import pandas as pd

from algotrade.storage.tables.readers import StoreReader

FUTURES_CURVE = "rates/futures_curve"
COLUMNS = (
    "session_date", "instrument_id", "parent_id", "root", "contract_month", "expiry", "conid",
    "local_symbol", "price_kind", "price", "last", "close", "bid", "ask", "volume",
    "open_interest", "multiplier", "ts", "knowledge_ts", "source", "run_id",
)  # fmt: skip


def futures_curve(
    reader: StoreReader,
    start: date,
    end: date,
    roots: Sequence[str] | None = None,
    as_of: datetime | None = None,
) -> pd.DataFrame:
    """Rows with ``start <= session_date <= end`` (only ``roots``' when given), sorted by
    session, root and expiry (``expiry`` as dates); an empty frame when none."""
    frame = reader.table_range(FUTURES_CURVE, start, end, as_of)
    if frame is None or frame.empty:
        return pd.DataFrame({c: [] for c in COLUMNS})
    out = frame.reindex(columns=list(COLUMNS))
    if roots is not None:
        out = out[out["root"].isin(list(roots))]
    out["session_date"] = pd.to_datetime(out["session_date"]).dt.date
    out["expiry"] = pd.to_datetime(out["expiry"]).dt.date
    by = ["session_date", "root", "expiry", "contract_month"]
    return out.sort_values(by, kind="stable").reset_index(drop=True)


def curve_of(frame: pd.DataFrame, root: str, session: date) -> pd.DataFrame:
    """One root's curve on one session: its rows by expiry with a price, plus ``days`` (to
    expiry) and ``roll_yield`` (annualised, ``ln(front / this) / years``, 0 on the front
    contract: positive in backwardation, negative in contango)."""
    rows = frame[(frame["root"] == root) & (frame["session_date"] == session)]
    rows = rows[rows["price"].notna() & rows["expiry"].notna()].sort_values("expiry")
    rows = rows.reset_index(drop=True)
    if rows.empty:
        return rows.assign(days=pd.Series(dtype=float), roll_yield=pd.Series(dtype=float))
    days = pd.Series([(e - session).days for e in rows["expiry"]], dtype=float)
    gap = days - days.iloc[0]
    front = float(rows["price"].iloc[0])
    roll = (np.log(front / rows["price"].astype(float)) / (gap / 365.0)).where(gap > 0, 0.0)
    return rows.assign(days=days, roll_yield=roll)
