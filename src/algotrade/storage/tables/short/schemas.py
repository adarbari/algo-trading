"""Schemas of the FINRA tables (EB D9; split from ``tables/schemas.py``, at its length cap).

Event tables like ``events/filing``: ``known_from`` (``schemas.KNOWN_FROM``) is required and set by
the task (``data.events`` applies it). Re-exported by ``tables/schemas.py``, which registers them.
"""

from algotrade.storage.tables.spec import fixed, strings

KNOWN_FROM = "known_from"  # ``schemas.KNOWN_FROM`` (not imported: schemas imports this module)

# L1: FINRA short interest, twice a month (EB D9), one row per (``instrument_id``, settlement date):
# ``ts`` the settlement date at midnight UTC, ``published`` the date FINRA publishes it (the 7th
# business day after), ``known_from`` the first session that may read it (the one after
# ``published``: the time of day is not stated, so it is taken as after any nightly run). FINRA
# keeps only the latest revision of a date, so a stored date is never refetched: the first-seen
# value is the point-in-time one. ``no_ml`` in tables.toml: FINRA's website terms bar machine
# learning over the data, so no learned scorer reads it (``tests/architecture``).
# The tables no learned scorer may read (``no_ml = true`` in architecture/tables.toml, the same
# set: ``tests/architecture/data/test_no_ml_tables.py``): a source whose terms bar machine learning
# over its data. Rule screens may read them; ``services.evaluation.training`` refuses a scorer
# feature computed from one.
NO_ML_TABLES = frozenset({"events/short_interest", "events/short_volume"})
SHORT_INTEREST_EVENTS = fixed(
    "events/short_interest",
    "event",
    ("instrument_id", "ts", KNOWN_FROM),
    "instrument_id string!",
    "ts timestamp_utc!",
    f"{KNOWN_FROM} date!",
    "published date!",
    "short_position int64!",
    "previous_short_position int64",
    "change_shares int64",
    "change_percent float64",
    "average_daily_volume int64",
    "days_to_cover float64",
    *strings("market_class", "revision_flag", "split_flag"),
    runs="merge",
    key=("instrument_id", "ts"),
)
# L1: FINRA Reg SHO daily short-sale volume (EB D9), one row per (``instrument_id``, trade date):
# the reporting facilities summed (off-exchange prints only, so the short share is a venue-biased
# proxy, not short interest). ``ts`` the trade date at midnight UTC, ``known_from`` the session
# after it (the file is posted by 18:00 New York and sometimes re-posted). ``no_ml``, as above.
SHORT_VOLUME_EVENTS = fixed(
    "events/short_volume",
    "event",
    ("instrument_id", "ts", KNOWN_FROM),
    "instrument_id string!",
    "ts timestamp_utc!",
    f"{KNOWN_FROM} date!",
    "short_volume int64!",
    "short_exempt_volume int64",
    "total_volume int64!",
    "facilities int64",
    runs="merge",
    key=("instrument_id", "ts"),
)
