"""ETF holdings (``holdings/etf``, ADR 0035): what a fund held on the issuer's latest date.

Rows are stored by the run that read each fund's file (a few funds per run), keyed by fund,
the issuer's ``as_of`` date and the holding's ``rank``. A fund's holdings are the rows of
its latest ``as_of`` on or before the date asked, taken from the run that stored that date
last: a re-read of the same date may hold fewer lines, and the earlier run's extra ranks
must not survive it. Weights are fractions of the fund.
"""

from datetime import date, datetime, timedelta

import pandas as pd

from algotrade.storage.tables.readers import StoreReader

TABLE = "holdings/etf"
LOOKBACK = timedelta(days=550)  # N-PORT funds report quarterly, with a ~60-day filing lag
COLUMNS = (
    "instrument_id",
    "as_of",
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
    return frame[frame["as_of"] <= through].reset_index(drop=True)


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
    """One row per fund with stored holdings: ``instrument_id``, ``as_of`` (the issuer's
    latest date) and ``fetched_on`` (the latest session a run stored it in)."""
    frame = _stored(reader, through, None)
    if frame is None or frame.empty:
        return pd.DataFrame({"instrument_id": [], "as_of": [], "fetched_on": []})
    frame = frame.assign(fetched_on=pd.to_datetime(frame["session_date"]).dt.date)
    grouped = frame.groupby("instrument_id").agg(
        as_of=("as_of", "max"), fetched_on=("fetched_on", "max")
    )
    return grouped.reset_index()


def cusip_of(identifier: object) -> str | None:
    """The 9-character CUSIP inside a CUSIP or a U.S./Canadian ISIN (``US0378331005``)."""
    text = str(identifier or "").strip().upper()
    if len(text) == 9 and text.isalnum():
        return text
    if len(text) == 12 and text[:2] in ("US", "CA") and text.isalnum():
        return text[2:11]
    return None


def known_cusips(reader: StoreReader, through: date) -> dict[str, str]:
    """CUSIP -> ticker for every holding stored with both (issuers that print tickers and
    CUSIPs, State Street's equity funds): the bridge to tickers for issuers that print only
    CUSIPs and ISINs (SEC N-PORT)."""
    frame = _stored(reader, through, None)
    if frame is None or frame.empty:
        return {}
    known = frame[frame["identifier"].notna() & frame["holding_symbol"].notna()]
    out: dict[str, str] = {}
    for identifier, symbol in zip(known["identifier"], known["holding_symbol"], strict=True):
        cusip = cusip_of(identifier)
        if cusip is not None:
            out[cusip] = str(symbol)
    return out
