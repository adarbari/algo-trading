"""Market-side table schemas: the universe, option chains and quotes, IBKR volatility and futures
curves, live quotes, Treasury rates, verification and the bar interval vocabulary.
"""

from algotrade.core.views.series import FIELDS
from algotrade.storage.tables.spec import (
    fixed,
    floats,
    strings,
)

UNIVERSE = fixed(
    "universe",
    "universe",
    ("instrument_id", "symbol", "security_type", "optionable", "status", "universe_version"),
    "instrument_id string!",
    "optionable bool",
    *strings("symbol", "company_name", "security_type", "asset_class", "exchange", "status"),
    *strings("universe_version", "last_verified", "source_crosscheck", "notes"),
    # CSV import mode keeps the master file's leverage columns as written (typed in L1).
    *strings("is_leveraged", "is_inverse", "leverage", "tracks"),
)

UNDERLYING_QUOTES = fixed(
    "chains/underlying_quotes",
    "chain_snapshot",
    ("instrument_id", "symbol", "ts", "price", "close", "volume", "iv30"),
    "instrument_id string!",
    "ts timestamp_utc!",
    *strings("symbol", "security_type"),
    *floats("price", "open", "high", "low", "close", "prev_close", "volume", "iv30"),
)

OPTION_QUOTES = fixed(
    "chains/option_quotes",
    "chain_snapshot",
    (
        "instrument_id",
        "underlying_id",
        "ts",
        "expiry",
        "right",
        "strike",
        "bid",
        "ask",
        "volume",
        "open_interest",
        "iv",
        "delta",
    ),
    "instrument_id string!",
    "ts timestamp_utc!",
    "expiry date",
    *strings("underlying_id", "root", "right"),
    *floats("strike", "bid", "ask", "bid_size", "ask_size", "last", "volume", "open_interest"),
    *floats("iv", "delta", "gamma", "theta", "vega", "rho", "theo"),
)

CHAIN_STATUS = fixed(
    "chains/status",
    "chain_snapshot",
    ("instrument_id", "status"),
    "instrument_id string!",
    *strings("symbol", "status", "tier"),
)

# L1: each instrument's IBKR stock contract (ADR 0028): conid and primary exchange from IB's
# contract lookup, one full snapshot per run (rows not refreshed are carried forward).
IBKR_CONTRACTS = fixed(
    "instruments/ibkr_contracts",
    "reference",
    ("instrument_id", "symbol", "conid", "resolved_at"),
    "instrument_id string!",
    "symbol string!",
    "conid int64!",
    *strings("primary_exchange", "sec_type", "currency"),
    "resolved_at date!",
)

# L2: IBKR's 30-day implied and historical vol of each underlying, one partition per session
# (ADR 0028). Runs merge per instrument (a backfill writes many sessions, the nightly one):
# the latest run's row wins. ``source_kind``: ``history`` (IB's daily bar) or ``snapshot``
# (the streamed value after the close). ``vol_reject``: why a vol IB sent is null (zero, or an
# IV above 5; ``tasks/market/ibkr_iv.py``, ADR 0028), null when both were kept.
# Licence: personal use (IBKR market data).
IBKR_IV30 = fixed(
    "volatility/ibkr_iv30",
    "volatility",
    ("instrument_id", "iv30_ibkr", "source_kind"),
    "instrument_id string!",
    "symbol string",
    *floats("iv30_ibkr", "hv30_ibkr"),
    "source_kind string!",
    "vol_reject string",
    runs="merge",
)

# L2: the futures curve, one partition per session (``futures-curves``, IB Gateway, read-only;
# personal licence): a row per front-month contract, ``instrument_id`` ``FUT:<root>:<YYYY-MM
# delivery month>``, ``parent_id`` ``FUT:<root>`` (ADR 0009). ``price`` is ONE ``price_kind`` per
# root and session by the read clock against ``next_open`` (IB ``tradingHours``): ``last`` before
# it, ``settle`` (IB close) from it to 12:00 New York next weekday, else nothing: see
# ``tasks/market/futures/curves.py``. ``ts``: when the stream was read; a run is the partition.
FUTURES_CURVE = fixed(
    "rates/futures_curve", "curve", ("instrument_id", "ts", "root", "contract_month"),
    "instrument_id string!", "ts timestamp_utc!", "parent_id string!", "root string!",
    "contract_month string!", "expiry date", "next_open timestamp_utc", "conid int64",
    "local_symbol string", "price_kind string",
    *floats("price", "last", "close", "bid", "ask", "volume", "open_interest", "multiplier"),
    key=("instrument_id",),
)  # fmt: skip

# L2: Cboe VIX futures (EB D3): a partition per trade date, a row per contract (``FUT:VX-<expiry>``,
# monthly and weekly), so a session's rows by ``expiry`` are its curve. A file price of 0 is null.
# ``known_from``: the session the row was knowable on (next session after the trade date; later for
# a restated value, ADR 0050), in the key so a restatement is a second version.
VX_FUTURES = fixed(
    "volatility/vx_futures", "volatility", ("instrument_id", "expiry"),
    "instrument_id string!", "root string!", "expiry date!", "known_from date!", "contract string",
    *floats("open", "high", "low", "close", "settle", "change"),
    *("volume int64", "efp int64", "open_interest int64"),
    runs="merge", key=("instrument_id", "session_date", "known_from"),
)  # fmt: skip
# Live option quotes the API read from IB Gateway (ADR 0028, the API's one write exception):
# every answer it served, one partition per session, a row per contract and time taken. Runs
# merge (each is a few snapshots; all are kept, keyed by contract and ``ts``). Written only
# through ``LiveWriter`` (``live/*``), never read by backtests. Licence: personal use.
LIVE_OPTION_QUOTES = fixed(
    "live/option_quotes",
    "live",
    ("instrument_id", "underlying_id", "ts", "expiry", "right", "strike"),
    "instrument_id string!",
    "ts timestamp_utc!",
    "underlying_id string!",
    "symbol string",
    "expiry date!",
    "right string!",
    "strike float64!",
    *floats("bid", "ask", "last", "close", "volume", "iv", "delta"),
    "conid int64",
    "market_data_type int64",
    runs="merge",
    retention_days=7,  # [sources] live_retention_days overrides the window
)

# L2: the Treasury par yield curve, one partition per curve date, one row per tenor
# (``instrument_id`` = ``RATE:UST-<tenor>``). Rates are decimals; ADR 0021 has the conventions.
TREASURY_RATES = fixed(
    "rates/treasury",
    "curve",
    ("instrument_id", "ts", "tenor", "tenor_days", "rate_par", "rate_cont"),
    "instrument_id string!",
    "ts timestamp_utc!",
    "tenor string!",
    "tenor_days int64!",
    "rate_par float64!",
    "rate_cont float64!",
)

# Live verification (ADR 0026): our values vs another source's, one row per instrument and
# check for a session. ``status`` is PASS / WARN / FAIL / NA; ``diff`` is in the check's
# tolerance unit (relative or absolute, per ``note``).
VERIFICATION_IBKR = fixed(
    "verification/ibkr",
    "verification",
    ("instrument_id", "symbol", "check", "status"),
    "instrument_id string!",
    *strings("symbol", "note"),
    "check string!",
    "status string!",
    *floats("ours", "theirs", "diff", "tolerance"),
    key=("instrument_id", "check"),
)

# L2: OHLCV bars; the table name carries the interval, e.g. "bars/1d", "bars/5m".
BAR_INTERVALS = frozenset({"1d", "1h", "30m", "15m", "5m", "1m"})

BAR_COLUMNS = ("instrument_id", "ts", "open", "high", "low", "close", "volume")

_BAR_TYPES = (
    "instrument_id string!",
    "ts timestamp_utc!",
    *(f"{c} float64!" for c in FIELDS),
    *floats("vwap", "trades"),
)
