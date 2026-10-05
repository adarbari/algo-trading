"""ETF holdings (``holdings/etf``, ADR 0035): what a fund held on the issuer's latest date.

Rows are stored by the run that read each fund's file (a few funds per run), keyed by fund,
the issuer's ``as_of`` date and the holding's ``rank``. A fund's holdings are the rows of
its latest ``as_of`` on or before the date asked, taken from the run that stored that date
last: a re-read of the same date may hold fewer lines, and the earlier run's extra ranks
must not survive it. A row with a ``filed`` date (an N-PORT report, public months after its
period) is invisible before that date, whatever session it was stored under. Weights are
fractions of the fund.
"""

from collections.abc import Collection
from datetime import date, datetime, timedelta

import pandas as pd

from algotrade.storage.tables.readers import StoreReader

TABLE = "holdings/etf"
LOOKBACK = timedelta(days=550)  # N-PORT funds report quarterly, with a ~60-day filing lag
COLUMNS = (
    "instrument_id",
    "as_of",
    "filed",
    "rank",
    "holding_symbol",
    "holding_id",
    "holding_name",
    "weight",
    "asset_class",
    "sector",
    "shares",
    "identifier",
    "holdings_count",
    "source",
)


def _stored(
    reader: StoreReader,
    through: date,
    as_of: datetime | None,
    instruments: list[str] | None = None,
) -> pd.DataFrame | None:
    frame = reader.table_range(TABLE, through - LOOKBACK, through, as_of, instruments)
    if frame is None or frame.empty:
        return None
    frame = frame.copy()
    frame["as_of"] = pd.to_datetime(frame["as_of"]).dt.date
    public = frame["as_of"] <= through
    if "filed" in frame.columns:  # not yet filed on ``through``: the row did not exist for a reader
        filed = pd.to_datetime(frame["filed"]).dt.date
        public &= pd.Series([pd.isna(f) or f <= through for f in filed], index=frame.index)
    return frame[public].reset_index(drop=True)


def _latest_per_fund(frame: pd.DataFrame) -> pd.DataFrame:
    """Each fund's rows of its latest ``as_of``, from the latest run that stored that date
    (ties on ``knowledge_ts`` go to the later run id)."""
    frame = frame[frame["as_of"] == frame.groupby("instrument_id")["as_of"].transform("max")]
    frame = frame.reset_index(drop=True)
    order = frame.sort_values(["knowledge_ts", "run_id"], kind="stable")
    newest = order.groupby("instrument_id")["run_id"].transform("last")
    return frame[frame["run_id"] == newest.reindex(frame.index)].reset_index(drop=True)


def etf_holdings(
    reader: StoreReader,
    instrument_id: str,
    on: date,
    as_of: datetime | None = None,
) -> pd.DataFrame:
    """The fund's latest stored holdings on or before ``on`` (``COLUMNS``), by rank; an empty
    frame when none are stored (not an ETF, or an issuer we have no file for)."""
    frame = _stored(reader, on, as_of, [instrument_id])
    if frame is None or frame.empty:
        return pd.DataFrame({c: [] for c in COLUMNS})
    out = _latest_per_fund(frame).reindex(columns=list(COLUMNS))
    return out.sort_values("rank", kind="stable").reset_index(drop=True)


def holdings_status(reader: StoreReader, through: date) -> pd.DataFrame:
    """One row per fund with stored holdings: ``instrument_id``, ``as_of`` and
    ``holdings_count`` (of its latest stored read) and ``fetched_on`` (the latest session any
    run stored it in)."""
    frame = _stored(reader, through, None)
    columns = ["instrument_id", "as_of", "holdings_count", "fetched_on"]
    if frame is None or frame.empty:
        return pd.DataFrame({c: [] for c in columns})
    fetched = pd.to_datetime(frame["session_date"]).dt.date.groupby(frame["instrument_id"]).max()
    latest = _latest_per_fund(frame).groupby("instrument_id").first()
    out = latest[["as_of", "holdings_count"]].assign(fetched_on=fetched).reset_index()
    return out[columns]


def cusip_of(identifier: object) -> str | None:
    """The 9-character CUSIP inside a CUSIP or a U.S./Canadian ISIN (``US0378331005``)."""
    text = str(identifier or "").strip().upper()
    if len(text) == 9 and text.isalnum() and text[0].isdigit():  # letters first: a CINS, foreign
        return text
    if len(text) == 12 and text[:2] in ("US", "CA") and text.isalnum():
        return text[2:11]
    return None


def known_cusips(
    reader: StoreReader, through: date, exclude_sources: Collection[str] = ()
) -> dict[str, str]:
    """CUSIP -> ticker for stored equity lines that resolved to a universe instrument
    (``holding_id``) and came from an issuer that prints tickers with its CUSIPs (State
    Street's equity funds, not ``exclude_sources``, the ones that borrow tickers): the bridge to
    tickers for issuers that print only CUSIPs and ISINs (SEC N-PORT). A foreign line (the
    local ticker T of Telus is not AT&T) never resolves, so it never enters the map."""
    frame = _stored(reader, through, None)
    if frame is None or frame.empty:
        return {}
    known = frame[
        frame["identifier"].notna()
        & frame["holding_symbol"].notna()
        & frame["holding_id"].notna()
        & (frame["asset_class"] == "Equity")
        & ~frame["source"].isin(list(exclude_sources))
    ]
    out: dict[str, str] = {}
    for identifier, symbol in zip(known["identifier"], known["holding_symbol"], strict=True):
        cusip = cusip_of(identifier)
        if cusip is not None:
            out[cusip] = str(symbol)
    return out
