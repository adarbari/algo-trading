"""The schema of Cboe's VIX futures table (EB D3): ``volatility/vx_futures``. Declared here,
registered in ``schemas.KNOWN``."""

from algotrade.storage.tables.spec import fixed, floats

# L2: Cboe VIX futures by expiry (EB D3): one partition per TRADE DATE, one row per listed contract
# (``instrument_id`` = ``FUT:VX-<expiry YYYYMMDD>``, monthly and Wednesday weekly alike), so the
# curve of a session (roll yield, contango) is its rows ordered by ``expiry``. Prices are index
# points; a price the file gives as 0 (no trade, or no settlement published before 2013-05-20)
# is null, never 0. ``contract`` is Cboe's month label (``F (Jan 2025)``, shared by the weeklies
# of that month: the expiry is the identity). ``known_from`` is the session the row was knowable on:
# the next session after the trade date (the file of a session is published the next morning,
# ``vendors/cboe/vx_futures.py``), later for a restated value (ADR 0050 pattern). Runs merge on
# (contract, session, known_from), so a restatement is a second version, not an overwrite; readers
# take the latest version known by their session. ``knowledge_ts`` is the write instant.
# Licence: Cboe, personal use.
VX_FUTURES = fixed(
    "volatility/vx_futures",
    "volatility",
    ("instrument_id", "expiry"),
    "instrument_id string!",
    "root string!",
    "expiry date!",
    "known_from date!",
    "contract string",
    *floats("open", "high", "low", "close", "settle", "change"),
    *("volume int64", "efp int64", "open_interest int64"),
    runs="merge",
    key=("instrument_id", "session_date", "known_from"),
)
