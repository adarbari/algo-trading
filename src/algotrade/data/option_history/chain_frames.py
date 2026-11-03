"""The bought history's quotes in the shape of a stored Cboe chain (ADR 0084, ADR 0088 decision 11):
the one adapter both derivations of the history read through, so the engine (``structure_pnl@v2``
rows) and the chain feature groups see a history session as they see a Cboe one and nothing else
differs.

``chain_option_quotes`` renames nothing the vendor kept under the same name and leaves the columns
a Cboe row has and the history lacks (``bid_size``, our-side Greeks, the feed's ``iv`` and
``delta``) null: the vendor's IV and delta are a cross-check only, never fed where a group expects
Cboe's. ``chain_underlying_quotes`` takes the underlying's day from ``option_history/underlying``
and, for an underlying the vendor has no stock quote for (SPXW, every index), the spot the option
rows themselves carry (``underlying_price``, one per underlying); a name with no ``underlying_id``
is not in a chain (the importer counted it).
"""

import numpy as np
import pandas as pd

from algotrade.storage.tables.schemas.market import OPTION_QUOTES, UNDERLYING_QUOTES
from algotrade.storage.tables.spec import COMMON

OPTION_COLUMNS = tuple(c.name for c in OPTION_QUOTES.columns if c.name not in COMMON)
UNDERLYING_COLUMNS = tuple(c.name for c in UNDERLYING_QUOTES.columns if c.name not in COMMON)
SPOT_COLUMNS = ("underlying_id", "symbol", "ts", "underlying_price")


def chain_option_quotes(quotes: pd.DataFrame) -> pd.DataFrame:
    """``option_history/quotes`` rows as ``chains/option_quotes`` rows (rows of a name with no
    ``underlying_id`` dropped); every column the Cboe table declares is present, in its order."""
    kept = quotes[quotes["underlying_id"].notna()]
    out = pd.DataFrame(index=kept.index)
    for column in OPTION_COLUMNS:
        out[column] = kept[column] if column in kept.columns else np.nan
    for column in ("iv", "delta"):  # the vendor's, a cross-check only (ADR 0084 decision 4)
        out[column] = np.nan
    for column in COMMON:  # the partition's own stamps (session, write instant, run)
        if column in kept.columns:
            out[column] = kept[column]
    return out.reset_index(drop=True)


def chain_underlying_quotes(
    underlying: pd.DataFrame | None, quotes: pd.DataFrame | None
) -> pd.DataFrame:
    """The underlyings of a session as ``chains/underlying_quotes`` rows: the vendor's day where
    it has one (``price`` = ``close``), else the spot the option rows carry. One row per id."""
    frames = []
    if underlying is not None and not underlying.empty:
        have = underlying[underlying["underlying_id"].notna()]
        frames.append(
            pd.DataFrame(
                {
                    "instrument_id": have["underlying_id"].astype(str),
                    "symbol": have["symbol"],
                    "ts": pd.NaT,
                    "price": have["close"],
                    **{c: have[c] for c in COMMON if c in have.columns},
                    **{c: have[c] for c in ("open", "high", "low", "close", "volume")},
                }
            )
        )
    if quotes is not None and not quotes.empty:
        spot = quotes[quotes["underlying_id"].notna() & (quotes["underlying_price"] > 0)]
        # one price per underlying: the median of the rows' (deterministic if they differ)
        first = (
            spot.groupby("underlying_id", sort=True)
            .agg(
                symbol=("symbol", "first"),
                ts=("ts", "min"),
                underlying_price=("underlying_price", "median"),
                **{c: (c, "first") for c in COMMON if c in spot.columns},
            )
            .reset_index()
        )
        frames.append(
            pd.DataFrame(
                {
                    "instrument_id": first["underlying_id"].astype(str),
                    "symbol": first["symbol"],
                    "ts": first["ts"],
                    "price": first["underlying_price"],
                    "close": first["underlying_price"],
                    **{c: first[c] for c in COMMON if c in first.columns},
                }
            )
        )
    if not frames:
        return pd.DataFrame(columns=[*UNDERLYING_COLUMNS, *COMMON])
    both = pd.concat(frames, ignore_index=True).drop_duplicates("instrument_id", keep="first")
    if quotes is not None and not quotes.empty:  # the vendor's day has no time: the snapshot's
        both["ts"] = both["ts"].fillna(quotes["ts"].min())
    for column in (*UNDERLYING_COLUMNS, *COMMON):
        if column not in both.columns:
            both[column] = np.nan
    return both[[*UNDERLYING_COLUMNS, *COMMON]].reset_index(drop=True)


def chain_status(quotes: pd.DataFrame) -> pd.DataFrame:
    """The ``chains/status`` rows of a session: every underlying with quotes is ``OK`` (a history
    has no feed to be stale or to fail), tier ``core``."""
    named = quotes[quotes["underlying_id"].notna()]
    first = named.drop_duplicates("underlying_id")
    out = pd.DataFrame(
        {
            "instrument_id": first["underlying_id"].astype(str),
            "symbol": first["symbol"],
            "status": "OK",
            "tier": "core",
        }
    )
    for column in COMMON:
        if column in first.columns:
            out[column] = first[column]
    return out.reset_index(drop=True)
