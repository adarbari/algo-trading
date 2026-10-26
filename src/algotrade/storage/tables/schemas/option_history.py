"""Schemas of the bought option history (ADR 0086, HistoricalOptionData Level 2): the contract
quotes and the underlying's day and option statistics of one session, and the vendor's dividends
and splits. A separate grain from ``chains/*`` and a separate store root
(``ALGOTRADE_OPTION_HISTORY_URL``); licence personal; kept forever.
"""

from algotrade.storage.tables.spec import fixed, floats, strings

# One partition per session (the ``DataDate`` day); an import of a session is the whole partition
# (snapshot runs, a re-import is a newer run). ``instrument_id`` is the OSI id the Cboe pull
# uses; ``symbol`` the vendor's underlying symbol; ``underlying_id`` is null where no id was known
# for the symbol on the session (counted by the importer). ``ts`` is 16:00 New York as UTC.
# ``iv`` and ``delta`` are the vendor's (a cross-check only, junk at the extremes). Files are
# sorted and clustered by ``symbol`` so a read of one underlying skips most row groups.
OPTION_HISTORY_QUOTES = fixed(
    "option_history/quotes",
    "option_history",
    ("instrument_id", "symbol", "expiry", "right", "strike"),
    "instrument_id string!",
    "symbol string!",
    "ts timestamp_utc!",
    "expiry date!",
    "right string!",
    "strike float64!",
    *strings("underlying_id", "root"),
    *floats("bid", "ask", "last", "underlying_price"),
    *floats("volume", "open_interest"),
    "iv float32",
    "delta float32",
    key=("instrument_id",),
    cluster_by=("symbol",),
    row_group_rows=65536,
)

# The underlying's day (the vendor's ``stockquotes``: OHLCV, never the adjusted close) and its
# ``optionstats`` (30-day IV by side, volume and open interest by side), one row per symbol.
OPTION_HISTORY_UNDERLYING = fixed(
    "option_history/underlying",
    "option_history",
    ("symbol",),
    "symbol string!",
    "underlying_id string",
    *floats("open", "high", "low", "close", "volume"),
    key=("symbol",),
)
OPTION_HISTORY_STATS = fixed(
    "option_history/stats",
    "option_history",
    ("symbol",),
    "symbol string!",
    "underlying_id string",
    *floats("iv30call", "iv30put", "iv30mean", "callvol", "putvol", "calloi", "putoi"),
    key=("symbol",),
)

# The vendor's stock history files (``dividends.csv``, ``stocksplits.csv``): partition = ex-date,
# runs merge (a re-import adds or replaces rows). Compared with events/dividend and events/split;
# never merged into them.
OPTION_HISTORY_DIVIDENDS = fixed(
    "option_history/dividends",
    "option_history",
    ("symbol", "ex_date"),
    "symbol string!",
    "ex_date date!",
    "amount float64!",
    runs="merge",
    key=("symbol", "ex_date"),
)
OPTION_HISTORY_SPLITS = fixed(
    "option_history/splits",
    "option_history",
    ("symbol", "ex_date"),
    "symbol string!",
    "ex_date date!",
    "ratio float64!",
    "text string",
    runs="merge",
    key=("symbol", "ex_date"),
)

OPTION_HISTORY_TABLES = (
    OPTION_HISTORY_QUOTES,
    OPTION_HISTORY_UNDERLYING,
    OPTION_HISTORY_STATS,
    OPTION_HISTORY_DIVIDENDS,
    OPTION_HISTORY_SPLITS,
)
