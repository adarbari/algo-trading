"""Parse one session's HistoricalOptionData files into frames (ADR 0086).

``options``: every listed contract of every underlying at 16:00 New York: ``UnderlyingSymbol,
UnderlyingPrice, Exchange, OptionSymbol, Blank, Type, Expiration, DataDate, Strike, Last, Bid, Ask,
Volume, OpenInterest, IV, Delta, Gamma, Theta, Vega, Alias`` (the ``DataDate`` header carries a
leading space in the vendor's files). A monthly zip's files differ: ``OptionExt`` / ``AKA`` in
place of ``Blank`` / ``Alias`` and no time in ``DataDate`` (the same 16:00 snapshot, measured on
the 2019-08 samples). ``stockquotes``: ``symbol,quotedate,open,high,low,close,volume`` (a
monthly file adds ``adjustedclose``, never stored: it depends on the download date).
``optionstats``: ``symbol,quotedate,iv30call,iv30put,iv30mean,callvol,putvol,calloi,putoi``
(monthly: also ``totalvol`` and ``comment``).

Nothing is filtered but the non-standard series (a root other than its underlying, ``AAPL1``
after a split: excluded and counted, as the Cboe pull does): a zero bid, a one-sided quote, vendor
IV above 12 all stay (the vendor's IV and delta are kept as a cross-check only; we compute ours
from bid and ask). The counts a reader needs to judge a day come back in ``notes``. The contract
id is built from the explicit expiry, type and strike columns (the OSI form the Cboe pull uses);
the vendor symbol's own suffix is compared with them (``osi_mismatch``) and never trusted.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from typing import IO, cast

import pandas as pd

from algotrade.core.model.instruments import AssetClass
from algotrade.core.time.calendar import EXCHANGE_TZ

OSI_TAIL = 15  # yymmdd + C/P + 8 digits of strike x 1000
_OPTION_COLUMNS = {
    "UnderlyingSymbol": "string",
    "UnderlyingPrice": "float64",
    "OptionSymbol": "string",
    "Type": "string",
    "Expiration": "string",
    "DataDate": "string",
    "Strike": "float64",
    "Last": "float64",
    "Bid": "float64",
    "Ask": "float64",
    "Volume": "float64",
    "OpenInterest": "float64",
    "IV": "float64",
    "Delta": "float64",
}


@dataclass(frozen=True)
class ParsedSession:
    session: date
    options: pd.DataFrame  # history/option_quotes columns (minus the ids and common columns)
    notes: Mapping[str, int] = field(default_factory=dict)
    excluded_roots: pd.DataFrame = field(default_factory=pd.DataFrame)  # root, rows (top ten)


def _read(stream: IO[bytes], **kwargs: object) -> pd.DataFrame:
    frame: pd.DataFrame = pd.read_csv(stream, **kwargs)  # type: ignore[call-overload]
    frame.columns = [str(c).strip() for c in frame.columns]
    return frame


def _stamps(data_date: pd.Series) -> pd.Series:
    """The snapshot instants (New York local): a daily file's ``DataDate`` is ``MM/DD/YYYY
    16:00``, a monthly file's has no time (the same 16:00 snapshot, measured on the 2019-08
    samples), so a missing time is 16:00."""
    text = data_date.str.strip()
    full = text.where(text.str.len() > 10, text + " 16:00")
    return cast(pd.Series, pd.to_datetime(full, format="%m/%d/%Y %H:%M"))


def parse_options(stream: IO[bytes]) -> ParsedSession | None:
    """One ``options`` file. ``None`` when it holds no rows. Raises ``ValueError`` when the file
    spans more than one ``DataDate`` day (a session is one day)."""
    raw = _read(stream, usecols=lambda c: c.strip() in _OPTION_COLUMNS, dtype=str)
    if raw.empty:
        return None
    stamps = _stamps(raw["DataDate"])
    days = stamps.dt.date.unique()
    if len(days) != 1:
        raise ValueError(f"options file spans {len(days)} days: {sorted(days)[:3]}")
    session = days[0]
    typed = raw.astype({k: v for k, v in _OPTION_COLUMNS.items() if v == "float64"})
    symbol = typed["UnderlyingSymbol"].str.strip().str.upper()
    vendor_osi = typed["OptionSymbol"].str.strip().str.upper()
    right = typed["Type"].str.strip().str.lower().map({"call": "C", "put": "P"})
    expiry = pd.to_datetime(typed["Expiration"], format="%m/%d/%Y")
    strike_digits = (typed["Strike"] * 1000).round().astype("Int64").astype(str).str.zfill(8)
    tail = expiry.dt.strftime("%y%m%d") + right + strike_digits
    suffix_ok = vendor_osi.str[-OSI_TAIL:] == tail
    # The contract id is built from the explicit columns, never trusted from the vendor's symbol;
    # a symbol whose suffix disagrees (a pre-2010 style, a typo) takes the underlying as its root.
    root = vendor_osi.str[:-OSI_TAIL].str.strip().where(suffix_ok, symbol)
    ts = stamps.dt.tz_localize(EXCHANGE_TZ).dt.tz_convert("UTC")
    standard = root == symbol
    frame = pd.DataFrame(
        {
            "instrument_id": AssetClass.OPTION.value + ":" + root + tail,
            "symbol": symbol,
            "ts": ts,
            "root": root,
            "expiry": expiry.dt.date,
            "right": right,
            "strike": typed["Strike"],
            "bid": typed["Bid"],
            "ask": typed["Ask"],
            "last": typed["Last"],
            "volume": typed["Volume"],
            "open_interest": typed["OpenInterest"],
            "iv": typed["IV"],
            "delta": typed["Delta"],
            "underlying_price": typed["UnderlyingPrice"],
        }
    )[standard & right.notna()].reset_index(drop=True)
    excluded = root[~standard].value_counts().head(10)
    notes = {
        "file_rows": len(raw),
        "rows": len(frame),
        "underlyings": int(frame["symbol"].nunique()),
        "zero_bid": int((frame["bid"] == 0).sum()),
        "crossed": int((frame["bid"] > frame["ask"]).sum()),
        "osi_mismatch": int((~suffix_ok).sum()),
        "unknown_right": int(right.isna().sum()),
        "nonstandard_series": int((~standard).sum()),  # an adjusted root (AAPL1): excluded
        "assumed_time": int(typed["DataDate"].str.strip().str.len().le(10).sum()),
        "off_hours": int((stamps.dt.hour.ne(16) | stamps.dt.minute.ne(0)).sum()),
        "duplicate_contracts": int(frame["instrument_id"].duplicated().sum()),
    }
    roots = excluded.rename_axis("root").reset_index(name="rows")  # a pre-2010 index root shows
    return ParsedSession(session, frame, notes, roots)


def parse_stock_quotes(stream: IO[bytes]) -> pd.DataFrame:
    """One ``stockquotes`` file -> ``symbol, open, high, low, close, volume`` (the underlying's
    day; the file's ``quotedate`` is not trusted over the options file's ``DataDate``)."""
    raw = _read(stream)
    out = pd.DataFrame({"symbol": raw["symbol"].astype("string").str.strip().str.upper()})
    for column in ("open", "high", "low", "close", "volume"):
        out[column] = pd.to_numeric(raw[column], errors="coerce")
    return out.drop_duplicates("symbol", keep="last").reset_index(drop=True)


def parse_option_stats(stream: IO[bytes]) -> pd.DataFrame:
    """One ``optionstats`` file -> ``symbol`` and the vendor's 30-day IV and the volume and open
    interest by side."""
    raw = _read(stream)
    out = pd.DataFrame({"symbol": raw["symbol"].astype("string").str.strip().str.upper()})
    for column in ("iv30call", "iv30put", "iv30mean", "callvol", "putvol", "calloi", "putoi"):
        out[column] = pd.to_numeric(raw[column], errors="coerce")
    return out.drop_duplicates("symbol", keep="last").reset_index(drop=True)


# Index options: the vendor's underlying symbol -> the index key of ``IDX:<key>``. SPX (AM
# settlement) and SPXW (PM) are one index; ``root`` keeps them apart on every contract.
INDEX_UNDERLYINGS = {
    "SPX": "SPX", "SPXW": "SPX", "XSP": "XSP", "RUT": "RUT", "RUTW": "RUT", "NDX": "NDX",
    "NDXP": "NDX", "VIX": "VIX", "VIXW": "VIX", "OEX": "OEX", "XEO": "XEO", "DJX": "DJX",
    "BKX": "BKX", "SOX": "SOX", "OSX": "OSX",
}  # fmt: skip
