"""Reference-side table schemas (L1): instrument reference, symbol and listing history, id maps,
index membership, company, description, shares, statements, and ETF holdings and shares.
"""

from algotrade.storage.tables.spec import (
    fixed,
    floats,
    strings,
)

# L1: what each instrument is (one full snapshot per date). See docs/design/phase-0.md.
INSTRUMENT_REFERENCE = fixed(
    "instruments/reference",
    "reference",
    ("instrument_id", "symbol", "asset_class", "security_type", "multiplier", "status"),
    "instrument_id string!",
    *strings("symbol", "name", "asset_class", "security_type", "security_type_source"),
    *strings("exchange", "currency", "financial_status", "status", "vendor_type"),
    *strings("figi", "share_class_figi", "cik", "tracks", "leverage_source"),
    # ETF category (ADR 0076): thematic / sector / broad / excluded (null = UNKNOWN), the theme
    # group (the exclusion kind for excluded), and how it was resolved (override / name_rule /
    # needs_review / unclassified / not_etf).
    *strings("etf_category", "etf_theme", "etf_category_source"),
    # FIGI review (ADR 0018): the vendor's FIGI when the build kept a different one or the
    # FIGI is shared, and the session that was first seen.
    "vendor_figi string",
    "figi_review_since date",
    *floats("multiplier", "tick_size", "round_lot", "leverage"),
    "is_etf bool",
    "is_test_issue bool",
    "optionable bool",
    "in_sp500 bool",
    "is_leveraged bool",
    "is_inverse bool",
    "listed_on date",
    "first_seen date",
    "delisted_on date",
)

# L1: which symbol each FIGI used and when (the full history per snapshot date). Each build
# only opens and closes rows, so a session's runs merge per (figi, symbol, valid_from): a
# re-run that sees less can close a row (latest run wins) but never hide one.
SYMBOL_HISTORY = fixed(
    "instruments/symbol_history",
    "reference",
    ("instrument_id", "ts", "figi", "symbol", "valid_from"),
    "instrument_id string!",
    "ts timestamp_utc!",
    *strings("figi", "symbol"),
    "valid_from date",
    "valid_to date",
    runs="merge",
    key=("figi", "symbol", "valid_from"),
)

# L1: symbol id -> FIGI id upgrades (ADR 0018); cumulative, the full map per snapshot date.
# A session's runs merge per (old_id, new_id), so a run holding only its own upgrades can
# never hide the earlier ones (2026-10-03). Keyed on the pair, not old_id alone: a reused
# symbol id can upgrade again to another FIGI, and ``known_at`` tells the two apart.
ID_MAP = fixed(
    "instruments/id_map",
    "reference",
    ("instrument_id", "ts", "old_id", "new_id", "symbol", "effective", "known_at"),
    "instrument_id string!",
    "ts timestamp_utc!",
    *strings("old_id", "new_id", "symbol"),
    "effective date",
    "known_at timestamp_utc",
    runs="merge",
    key=("old_id", "new_id"),
)

# L1: every US-listed stock / ETF a vendor ever listed, with its listing dates (ADR 0018
# amendment, 2026-10-08; edges ED6): the universe as it was, for the winners study. One full
# copy per pull session (snapshot). ``instrument_id`` is null until a trusted id exists (a
# symbol_history match or a permaTicker); ``end_date`` is the vendor's last trading day and is
# read only by ``data.listings.universe_asof``. knowledge_ts is the pull time (2026 for a
# 2010 listing), so only the identity reads (resolver, universe_asof) may use it for an old S.
LISTING_HISTORY = fixed(
    "instruments/listing_history",
    "reference",
    ("ticker", "start_date", "ts"),
    "instrument_id string",
    "ts timestamp_utc!",
    *strings("ticker", "exchange", "asset_type", "price_currency", "perma_ticker"),
    "start_date date!",
    "end_date date",
    key=("source", "ticker", "start_date"),
)

# L1: every US ticker Massive lists as INACTIVE (delisted), one row per (ticker, last trading
# day) from ``/v3/reference/tickers?active=false`` (ADR 0084): the names the active universe
# lacks, with the vendor's CIK and FIGIs where it has them. A full copy per pull session
# (snapshot). Identity only: ``end_date`` is the vendor's last trading day (null
# for ~2% of the rows, where Massive gives none), ``vendor_type`` is null before 2017 and
# ``security_type`` is ``MASSIVE_TYPES`` of it. No ``instrument_id`` yet: the merge into
# ``instruments/listing_history`` is a later PR. knowledge_ts is the pull time.
DELISTED_TICKERS = fixed(
    "instruments/delisted_tickers",
    "reference",
    ("ticker", "ts"),
    "ts timestamp_utc!",
    *strings("ticker", "name", "exchange", "vendor_type", "security_type"),
    *strings("cik", "figi", "share_class_figi"),
    "end_date date",
    key=("source", "ticker", "end_date"),
)

# L1: who was in an index when (ADR 0013's S&P 500 rule over history; edges ED6b-3): one row per
# (index, ticker, membership interval) from the fja05680/sp500 history, a full copy per pull
# session (snapshot). Keyed by ticker, not by id: the history predates our ids, and
# ``data.listings.universe_asof`` joins it to the listing alive on S. ``end_date`` is null while
# the ticker is still a member. knowledge_ts is the pull time (2026 for a 2010 interval): an
# identity read like the listing history, never a point-in-time fact.
INDEX_MEMBERSHIP = fixed(
    "instruments/index_membership",
    "reference",
    ("index_name", "ticker", "start_date", "ts"),
    "ts timestamp_utc!",
    *strings("index_name", "ticker"),
    "start_date date!",
    "end_date date",
    key=("source", "index_name", "ticker", "start_date"),
)

# L1: company details from SEC EDGAR, per instrument (one full snapshot per date).
INSTRUMENT_COMPANY = fixed(
    "instruments/company",
    "reference",
    ("instrument_id", "symbol", "cik", "name", "sic", "sector", "fetched_on"),
    "instrument_id string!",
    *strings("symbol", "cik", "cik_source", "name", "entity_type", "sic", "sic_description"),
    *strings("sic_division", "sector", "industry", "state_of_incorporation", "fiscal_year_end"),
    *strings("website", "former_names", "exchanges", "tickers"),
    "fetched_on date",
)

# L1: a short plain-text description of what an instrument is about (ADR 0034): a stock's from
# Massive's ticker overview, an ETF's investment objective from its SEC prospectus. Runs are
# increments (the rows fetched or changed that run), so they merge; one row per instrument,
# the latest wins. A row without text is a marker that the vendor was asked on ``fetched_on``.
INSTRUMENT_DESCRIPTION = fixed(
    "instruments/description",
    "reference",
    ("instrument_id", "description_source", "fetched_on"),
    "instrument_id string!",
    *strings("symbol", "description", "homepage_url", "accn"),
    "description_source string!",
    "total_employees int64",
    "filed date",
    "fetched_on date!",
    runs="merge",
    key=("instrument_id",),
)

# L1: share counts and basic financials (revenue, net income, diluted EPS: ``value`` in
# ``unit``) from SEC company facts, per instrument (every class of a CIK gets the CIK's
# facts). Runs are increments (new facts + a ``checked`` marker per fetched CIK), so they
# merge; a fact is identified by (instrument, concept, tag, period start, period end, filed
# date): a year-to-date and a quarterly fact share an end date, and several us-gaap tags of one
# concept report the same period (a null ``tag``, a ``checked`` marker's, equals a null).
# ``accepted_ts`` is the instant SEC accepted the fact's filing (UTC, from the submissions
# document, ADR 0067 amendment): when it became public. Null for a row stored before the column
# existed or whose accession the submissions do not list: a reader then counts the fact from the
# session after ``filed``.
INSTRUMENT_SHARES = fixed(
    "instruments/shares",
    "reference",
    ("instrument_id", "cik", "concept", "period_start", "fetched_on"),
    "instrument_id string!",
    *strings("symbol", "tag", "form", "accn", "fp", "unit"),
    "cik string!",
    "concept string!",
    "period_start date",
    "period_end date",
    "filed date",
    "accepted_ts timestamp_utc",
    "fy int64",
    "shares float64",
    "class_values int64",
    "value float64",
    "fetched_on date!",
    runs="merge",
    key=("instrument_id", "concept", "tag", "period_start", "period_end", "filed"),
)

# L1: the financial statement lines (income statement, cash flow, balance sheet) from the same SEC
# company facts document, per instrument (every class of a CIK gets the CIK's facts; ADR 0067).
# Merging increments like ``instruments/shares``; a fact is identified by (instrument, concept,
# tag, period start, period end, filed date): a null ``period_start`` (an instant, a ``checked``
# marker) equals a null, and every us-gaap tag of a concept is its own row.
INSTRUMENT_STATEMENTS = fixed(
    "instruments/statements",
    "reference",
    ("instrument_id", "cik", "concept", "period_start", "fetched_on"),
    "instrument_id string!",
    *strings("symbol", "tag", "period_type", "form", "accn", "fp", "unit"),
    "cik string!",
    "concept string!",
    "period_start date",
    "period_end date",
    "filed date",
    "accepted_ts timestamp_utc",
    "fy int64",
    "value float64",
    "fetched_on date!",
    runs="merge",
    key=("instrument_id", "concept", "tag", "period_start", "period_end", "filed"),
)

# L2: what an ETF holds (ADR 0035): one row per fund x holding x as-of date, the largest
# ``[etf_holdings] keep_top`` holdings of the fund's file, ranked by the size of the weight
# (1 = largest). ``as_of`` is the issuer's holdings date; the partition is the session of the
# run that read it; ``filed`` is when the data became public if later (an N-PORT filing), and
# readers never show a row before it. Runs are increments (a few funds each), so they merge on
# (fund, as_of, rank); a later run of the same as_of may hold fewer holdings, so readers take
# each fund's rows from its latest run (``data.funds.holdings``). ``weight`` is a fraction of
# the fund (negative for shorts); ``holding_id`` is the holding's instrument when its ticker
# resolves to a universe instrument (null otherwise, so it also marks a line as a U.S. listing);
# ``holdings_count`` counts the issuer's positions in securities, not cash, futures or FX lines.
ETF_HOLDINGS = fixed(
    "holdings/etf",
    "holdings",
    ("instrument_id", "as_of", "rank", "holding_name", "weight", "holdings_count"),
    "instrument_id string!",
    "symbol string",
    "as_of date!",
    "filed date",
    "rank int64!",
    *strings("holding_symbol", "holding_id"),
    "holding_name string!",
    "weight float64!",
    *strings("asset_class", "sector", "identifier"),
    "shares float64",
    "holdings_count int64!",
    runs="merge",
    key=("instrument_id", "as_of", "rank"),
)

# L2: an ETF's shares outstanding as its issuer's daily file states them (EB D4; ADR 0035's ``etf-
# holdings`` task reads the file, so there is no second download): one row per fund x issuer as-of
# date. Only iShares' file carries the count (its header block); State Street's and ProShares'
# files do not. ``as_of`` is the file's date, ``ts`` that date at UTC midnight (a count as of a
# session's close, not an instant). ``known_from`` is the first session the row was knowable (ADR
# 0050): the session of the New York date of the fetch instant (``knowledge_ts``; the next session
# on a weekend or holiday), never before ``as_of``; readers apply ``known_from <= S``
# (``data.funds.shares``). A file read again for the same ``as_of`` writes a row with a later
# ``known_from``; readers take the latest they may see. Counts are rounded to creation units by
# the issuer. History accrues from the first nightly that stores it; nothing is backfilled. Flows
# are NOT stored: the change in shares times the stored close approximates them (it ignores the
# intraday NAV and the creation / redemption price). Runs are increments (a few funds each), so
# they merge on (fund, as_of).
ETF_SHARES = fixed(
    "holdings/etf_shares",
    "holdings",
    ("instrument_id", "ts", "as_of", "shares_outstanding", "known_from"),
    "instrument_id string!",
    "symbol string",
    "ts timestamp_utc!",
    "as_of date!",
    "shares_outstanding float64!",
    "known_from date!",
    runs="merge",
    key=("instrument_id", "as_of"),
)
