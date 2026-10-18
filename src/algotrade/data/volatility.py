"""IBKR's implied and historical vol per underlying and session (``volatility/ibkr_iv30``).

One partition per session; runs merge (a history backfill writes many sessions, the nightly
snapshot one), the latest run's row winning per instrument (``storage/backends``). Rows carry
``iv30_ibkr`` / ``hv30_ibkr`` (decimals, IB's 30-day vols) and ``source_kind`` (``history``:
IB's daily bar, ``snapshot``: the streamed value after the close) and ``vol_reject`` (why a vol
IB sent is null: zero, or an IV above 5; null when both were kept). ADR 0028.

Also Cboe's VIX futures by expiry (``volatility/vx_futures``, EB D3): one row per listed contract
and trade date, so a session's rows ordered by ``expiry`` are its futures curve. A read at
``session`` sees only the rows known by it (``known_from``: the next session after the trade
date, the file being published the morning after), so the curve a session reads never holds a
settle it could not have had.
"""

from collections.abc import Sequence
from datetime import date, datetime

import pandas as pd

from algotrade.storage.tables.readers import StoreReader

IBKR_IV30 = "volatility/ibkr_iv30"
VX_FUTURES = "volatility/vx_futures"
VX_COLUMNS = (
    "session_date", "instrument_id", "expiry", "contract", "known_from", "open", "high", "low",
    "close", "settle", "change", "volume", "efp", "open_interest",
)  # fmt: skip
COLUMNS = (
    "session_date", "instrument_id", "symbol", "iv30_ibkr", "hv30_ibkr", "source_kind", "vol_reject"
)  # fmt: skip


def ibkr_iv30(
    reader: StoreReader,
    start: date,
    end: date,
    instruments: Sequence[str] | None = None,
    as_of: datetime | None = None,
) -> pd.DataFrame:
    """Rows with ``start <= session_date <= end`` (only ``instruments``' when given), sorted
    by session then instrument, ``session_date`` as dates; an empty frame when none."""
    frame = reader.table_range(IBKR_IV30, start, end, as_of, instruments)
    if frame is None or frame.empty:
        return pd.DataFrame({c: [] for c in COLUMNS})
    out = frame.reindex(columns=list(COLUMNS))
    out["session_date"] = pd.to_datetime(out["session_date"]).dt.date
    out["instrument_id"] = out["instrument_id"].astype(str)
    return out.sort_values(["session_date", "instrument_id"], kind="stable").reset_index(drop=True)


def ibkr_stored_hv(
    reader: StoreReader, start: date, end: date, instruments: Sequence[str]
) -> dict[tuple[str, date], float]:
    """``(instrument id, session) -> hv30_ibkr`` of the stored rows with an HV in
    ``start..end``, for ``instruments`` (one column read), whatever their ``source_kind``:
    what an IV-only history backfill keeps when its row replaces one (a snapshot's tick 104,
    or IB's HV on history rows from before the backfill dropped it, cannot be fetched again)."""
    if not instruments:
        return {}
    frame = reader.table_range(IBKR_IV30, start, end, None, instruments, ["hv30_ibkr"])
    if frame is None or frame.empty:
        return {}
    kept = frame[frame["hv30_ibkr"].notna()]
    days = pd.to_datetime(kept["session_date"]).dt.date
    return {
        (str(i), d): float(hv)
        for i, d, hv in zip(kept["instrument_id"], days, kept["hv30_ibkr"], strict=True)
    }


def vx_futures(
    reader: StoreReader,
    start: date,
    end: date,
    session: date | None = None,
    as_of: datetime | None = None,
) -> pd.DataFrame:
    """VIX futures rows with ``start <= session_date <= end`` (``VX_COLUMNS``), sorted by
    trade date then expiry, dates as dates; an empty frame when none.

    ``session`` is the session the read serves (ADR 0050): only rows with ``known_from <=
    session`` are kept (a trade date's settle is known from the next session), and per contract
    and trade date the latest version known by then. ``None`` keeps every row, the latest
    version. ``as_of`` pins the stored run (ADR 0007). ``settle`` is null where Cboe published
    none (before 2013-05-20)."""
    frame = reader.table_range(VX_FUTURES, start, end, as_of)
    if frame is None or frame.empty:
        return pd.DataFrame({c: [] for c in VX_COLUMNS})
    frame = frame.assign(known_from=pd.to_datetime(frame["known_from"]).dt.date)
    if session is not None:
        frame = frame[frame["known_from"] <= session]
    frame = frame.sort_values("known_from", kind="stable").drop_duplicates(
        ["instrument_id", "session_date"], keep="last"
    )
    out = frame.reindex(columns=list(VX_COLUMNS))
    out["session_date"] = pd.to_datetime(out["session_date"]).dt.date
    out["expiry"] = pd.to_datetime(out["expiry"]).dt.date
    return out.sort_values(["session_date", "expiry"], kind="stable").reset_index(drop=True)
