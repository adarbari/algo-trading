"""Event, macro and analyst table schemas: earnings, macro releases, filings, macro series and the
analyst-data snapshots, with their ``known_from`` convention and value vocabularies.
"""

from algotrade.storage.tables.spec import (
    TableSpec,
    columns_of,
    fixed,
    floats,
    strings,
)

# L1: economic series and index levels (ADR 0048), one row per series x observation date x
# vintage. ``instrument_id`` is ``MACRO:<KEY>`` or ``IDX:<KEY>`` (``core.model.instruments``);
# ``series`` is the vendor's code (FRED ``NASDAQCOM``, Stooq ``^SPX``). ``vintage_date`` is the
# day the value became public: ALFRED's ``realtime_start`` (``vintage_kind`` ``alfred``), or
# ``obs_date`` plus the series' release lag for unrevised series and observations before
# ALFRED's first vintage (``lagged``, ``data.macro.vintages``). It is not ``knowledge_ts``,
# which stays the storage stamp (ADR 0007: when we stored it; the stamping step overwrites
# it): a 2008 vintage a 2026 backfill stored was public in 2008, exactly as
# ``instruments/shares`` keeps ``filed``. ``value`` is null where FRED prints ".". The
# partition is the run's session; runs are increments, so they merge on the key; readers union
# every partition and keep the vintages on or before their session (``data.macro.series``).
# Event rows say when the fact became knowable (ADR 0050 decision 3): ``known_from``, the
# session it was knowable on (a backfilled report: its report date); ``data.events`` applies
# it. Every event table with a spec of its own REQUIRES it, non-null (``EARNINGS_EVENTS``; a
# new event table declares it the same way). The generic event grain keeps it optional (null:
# the session that stored it) for the facts of record (``data.events.FACTS_OF_RECORD``:
# splits, dividends, reference and index changes).
KNOWN_FROM = "known_from"

# A calendar row copied forward over a day the fetch failed: the session of the snapshot that
# fetched it (null on fetched rows), so a failed fetch never cancels knowledge (ADR 0050).
CARRIED_FROM = "carried_from"

# ``events/earnings`` rows come from two sources (``source``): the Nasdaq calendar (``ts`` the
# report date at midnight UTC, ``time`` ``pre_market`` / ``after_hours`` / ``unknown``) and SEC
# 8-K Item 2.02 results releases (``sec_8k``, ADR 0050: ``ts`` the ACCEPTANCE instant, ``time``
# also ``intraday`` for an acceptance during the session, ``reported`` true). The merge key is
# (``instrument_id``, ``ts``): the 8-K row's ``ts`` is the acceptance instant (an acceptance at
# exactly midnight UTC, 20:00 EDT, is written one second later), so a Nasdaq row and an 8-K row
# of the same day never share a key, and the per-quarter precedence between them belongs
# to the rollup that reads them (``earnings@v1`` and its ADR 0050 successors), not to a writer.
EARNINGS_8K_SOURCE = "sec_8k"  # the ``source`` of the 8-K Item 2.02 rows (tasks/events/filings.py)

EARNINGS_EVENTS = TableSpec(
    "events/earnings",
    "event",
    ("instrument_id", "ts", KNOWN_FROM),
    open_ended=True,
    columns=columns_of(
        "instrument_id string!", "ts timestamp_utc!", f"{KNOWN_FROM} date!", f"{CARRIED_FROM} date"
    ),
    runs="merge",
)

# L1: the macro release calendar (ADR 0050), one row per release and date: ``ts`` is the release
# moment in UTC (the date with ``time_et``, New York), ``instrument_id`` ``MACRO:<release_key>``.
# ``status`` is ``scheduled`` (the date is after the session that stored the row), ``released``
# or ``moved`` (a later fetch no longer lists the date: rescheduled or withdrawn); a change of
# status is a new version of the row, with its own ``known_from``: the session it was knowable
# on (the session that fetched the calendar, or the release date for a past row). A rescheduled
# release is a new key; runs merge on it, the latest version known by a session wins.
RELEASE_STATUSES = frozenset({"scheduled", "released", "moved"})

MACRO_RELEASE_EVENTS = fixed(
    "events/macro_release",
    "event",
    ("instrument_id", "ts", KNOWN_FROM, "release_key", "release_date", "status"),
    "instrument_id string!",
    "ts timestamp_utc!",
    f"{KNOWN_FROM} date!",
    "release_key string!",
    "release_name string!",
    "release_date date!",
    "time_et string!",
    "status string!",
    runs="merge",
)

# L1: the 8-K and 8-K/A filings of the scoped companies (ADR 0050), one row per instrument and
# filing (a CIK's share classes each get the row). ``ts`` is SEC's acceptance instant in UTC;
# ``filing_date`` is the date SEC files it under (an evening acceptance is dated the next
# business day); ``items`` is SEC's comma list ("2.02,9.01", empty when none); ``report_date``
# the date of the earliest event reported (null when SEC gives none). ``known_from`` is the
# session of the acceptance time in America/New_York: an acceptance after the close is public
# that evening, so it is that day's session. Runs rewrite the filings they read again, so they
# merge on (``instrument_id``, ``accession``): a rerun is idempotent.
FILING_EVENTS = fixed(
    "events/filing",
    "event",
    ("instrument_id", "ts", KNOWN_FROM, "cik", "form", "accession", "filing_date", "items"),
    "instrument_id string!",
    "ts timestamp_utc!",
    f"{KNOWN_FROM} date!",
    "cik string!",
    "form string!",
    "accession string!",
    "filing_date date!",
    "items string!",
    "report_date date",
    "primary_document string",
    runs="merge",
    key=("instrument_id", "accession"),
)

# L1: the IPO facts and lock-up expiry of each 424B4 prospectus (ADR 0050, edge build D8; rules in
# ``tasks/events/ipo_lockups.py``): one row per (``cik``, ``accession``), keyed by the ISSUER's CIK
# (a new issuer is in no universe yet: ``instrument_id`` is null until a run finds it). ``ts`` is
# the acceptance instant, ``known_from`` its session; a re-extraction that changed a value is a
# new version with a later ``known_from``, part of the merge key so it never replaces the version
# an earlier session read (readers: ``data.events.latest_versions``).
IPO_LOCKUP_EVENTS = fixed(
    "events/ipo_lockup",
    "event",
    ("ts", KNOWN_FROM, "cik", "accession", "extraction"),
    "ts timestamp_utc!",
    f"{KNOWN_FROM} date!",
    "cik string!",
    "accession string!",
    "extraction string!",
    "rules_version string!",
    "filing_date date!",
    "is_ipo bool!",
    "early_release bool!",
    "prospectus_date date",
    "lockup_expiry date",
    "offer_price float64",
    "lockup_days int64",
    *strings("instrument_id", "issuer_name", "primary_document", "ticker"),
    *strings("exchange", "lockup_terms", "early_release_text", "reason"),
    runs="merge",
    key=("cik", "accession", KNOWN_FROM),
)

MACRO_SERIES = fixed(
    "macro/series",
    "reference",
    ("instrument_id", "obs_date", "vintage_date", "vintage_kind"),
    "instrument_id string!",
    "series string",
    "obs_date date!",
    "vintage_date date!",
    "value float64",
    "vintage_kind string!",
    runs="merge",
    key=("instrument_id", "obs_date", "vintage_date"),
)

# L1: what each analyst-data vendor's key may call (ADR 0068), one row per (vendor, endpoint):
# ``source`` is the vendor (``fmp``, ``finnhub``), ``endpoint`` the probe's name for the call
# (``estimates_quarter``). ``status`` is ALLOWED / DENIED / LIMITED (``framework/access.py``);
# ``http_code`` the answer's (200 for an empty payload); ``rows`` the records it held; ``note``
# fixed words, never the vendor's body; ``checked_ts`` when the call was made. A probe run is a
# window (it may skip a vendor with no key, or an endpoint over budget), so runs merge on the
# key and the latest run's verdict wins; the partition is the run's session, and the task carries
# the latest earlier partition's rows (their ``checked_ts`` kept) for what a run got no verdict for.
ANALYST_VENDOR_ACCESS = fixed(
    "analyst/vendor_access",
    "reference",
    ("source", "endpoint"),
    "endpoint string!",
    "status string!",
    "http_code int64",
    "rows int64",
    "note string",
    "checked_ts timestamp_utc!",
    runs="merge",
    key=("source", "endpoint"),
)

ACCESS_STATUSES = frozenset({"ALLOWED", "DENIED", "LIMITED"})

# L1: our own point-in-time history of analyst data (ADR 0068; track D2 of the edge build). Both
# vendors serve only today's value and restate their history, so each night's fetch is stored as
# rows that are never replaced by a later session's: one row per (``instrument_id``, ``source``
# (``fmp`` / ``finnhub``), ``kind``, ``period``) in the partition of the session the fetch is for.
# ``kind``: ``estimates_annual`` (FMP, ``period`` the fiscal year end, ISO date), ``price_target``
# and ``grades`` (FMP consensus, ``period`` ``current``) and ``recommendation`` (Finnhub, ``period``
# the month's first day). ``ts`` is the fetch instant of the row; ``knowledge_ts`` is the publish
# instant of its run (>= ``ts``, never a vendor date), so a read as of T sees only what we held at
# T. The measure columns are those of the kind, the others null: estimates the ``<measure>_<side>``
# floats and the two analyst counts; targets the four prices; grades and recommendation the five
# counts (grades also the label ``consensus``). A run is a window (a rotation slice of the names),
# so runs merge on the key; one session holds each name at most once, a later session adds new rows.
# ``coverage`` rows (``period`` ``current``, measure columns null) record each ATTEMPT of a vendor
# for a name in ``status``: ``OK`` (it returned data), ``EMPTY`` (answered, no data),
# ``NOT_COVERED`` (it refused the name: not on the free plan) or ``FAILED`` (a transport, 5xx or
# other error: a transient failure is not "not covered"), so a feature reads NOT_COVERED or
# NOT_FETCHED from the store, not from run items. ``status`` is null on every other kind.
SNAPSHOT_KINDS = frozenset(
    {"estimates_annual", "price_target", "grades", "recommendation", "coverage"}
)

COVERAGE_STATUSES = frozenset({"OK", "EMPTY", "NOT_COVERED", "FAILED"})

ANALYST_ESTIMATE_SNAPSHOTS = fixed(
    "analyst/estimate_snapshots",
    "reference",
    ("instrument_id", "ts", "source", "kind", "period"),
    "instrument_id string!",
    "ts timestamp_utc!",
    "kind string!",
    "period string!",
    *floats(
        *(
            f"{m}_{side}"
            for m in ("revenue", "ebitda", "ebit", "net_income", "sga_expense", "eps")
            for side in ("low", "high", "avg")
        )
    ),
    "num_analysts_revenue int64",
    "num_analysts_eps int64",
    *floats("target_high", "target_low", "target_consensus", "target_median"),
    "strong_buy int64",
    "buy int64",
    "hold int64",
    "sell int64",
    "strong_sell int64",
    "consensus string",
    "status string",
    runs="merge",
    key=("instrument_id", "source", "kind", "period"),
)

# ``macro/series`` ``vintage_kind``: ALFRED's realtime_start, or obs_date + the release lag.
ALFRED, LAGGED = "alfred", "lagged"

VINTAGE_KINDS = frozenset({ALFRED, LAGGED})
