"""Canonical table schemas: the data contract every writer must satisfy.

Every row carries the point-in-time columns (ADR 0007). Market tables also carry ``ts``.
Fixed tables declare every column with an abstract type (``COLUMN_TYPES``) and nullability;
storage backends cast writes to those types (and fail on uncastable data), stamp
``SCHEMA_VERSION`` and the table name into each file, and cast older files on read.
Feature, event, catalogue and result tables are open-ended: they need the common columns
plus ``instrument_id`` (+ ``ts`` for events), which are typed; the rest is defined by the
feature, event source or screener that produces them.

Each table also declares how its runs combine (``TableSpec.runs``, ``RUN_MODES``): a
``snapshot`` run is the partition's full contents (the latest run known at ``as_of`` replaces
the others); a ``merge`` run is a window or increment (reads union every run known at
``as_of``, the latest run's row winning per ``table_key``). Backends apply it
(``storage/backends/run_selection.py``).
"""

from collections.abc import Iterable

import numpy as np
import pandas as pd

from algotrade.core.model.errors import DataValidationError
from algotrade.core.validation.bars import ohlcv_problems
from algotrade.core.views.series import FIELDS
from algotrade.storage.tables.edge_schemas import (
    EDGE_EVAL,
    EDGE_LEGS,
    EDGE_PAPER,
    EDGE_SERIES,
    EDGE_TRADES,
    WINNERS_STUDY,
)
from algotrade.storage.tables.spec import (
    COMMON,
    TableSpec,
    columns_of,
    fixed,
    floats,
    strings,
)
from algotrade.storage.tables.vx_schemas import VX_FUTURES

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

# L1: what each instrument is (one full snapshot per date). See docs/design/phase-0.md.
INSTRUMENT_REFERENCE = fixed(
    "instruments/reference",
    "reference",
    ("instrument_id", "symbol", "asset_class", "security_type", "multiplier", "status"),
    "instrument_id string!",
    *strings("symbol", "name", "asset_class", "security_type", "security_type_source"),
    *strings("exchange", "currency", "financial_status", "status", "vendor_type"),
    *strings("figi", "share_class_figi", "cik", "tracks", "leverage_source"),
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
    "fy int64",
    "value float64",
    "fetched_on date!",
    runs="merge",
    key=("instrument_id", "concept", "tag", "period_start", "period_end", "filed"),
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
# The text-model usage log (ADR 0058, the API's fifth write): one row per provider
# attempt of a call (the failed and the budget-skipped ones too), one partition per exchange
# calendar date of the call. Runs merge (each is a batch of attempts; all kept). Tokens, cost
# and ``fell_back_from`` are null when unknown or not applicable, never 0: ``cost_basis`` says
# where ``cost_usd`` came from (``price`` tokens x the model's [[price]], ``reported`` a
# subscription's notional total, ``bound`` the upper bound reserved when the cost is unknown or
# the attempt failed, ``free`` 0 for a free provider, ``unknown`` null: a skipped attempt or a
# ``rejected`` one). A failure also carries ``error``, ``stage`` (``provider`` / ``answer``), the
# prompt (``sentence``, clipped), the raw ``answer`` (clipped) and ``prompt_chars``: null on
# every other row and on partitions written before they existed. Metering (ADR 0058 amended
# 2026-10-11): ``input_tokens`` is the regular (uncached) input as reported, ``cache_read_tokens``
# / ``cache_write_tokens`` the cached prompt (null: not reported), ``call_id`` ties the attempts
# of one call and its ``rejected`` row, ``prompt_version`` and ``call_stage`` (``first`` /
# ``repair`` / ``escalate``) are the caller's tags; null on older partitions. Written
# only through ``UsageWriter`` (``usage/*``); read across a date range by ``data.usage``.
USAGE_LLM_CALLS = fixed(
    "usage/llm_calls",
    "usage",
    ("ts", "provider", "use_case", "outcome"),
    "ts timestamp_utc!",
    "provider string!",
    "model string!",
    "use_case string!",
    "user string",
    "input_tokens int64",
    "output_tokens int64",
    "latency_s float64!",
    "cost_usd float64",
    "cost_basis string!",
    "outcome string!",
    "fell_back_from string",
    "error string",
    "stage string",
    "sentence string",
    "answer string",
    "prompt_chars int64",
    "cache_read_tokens int64",
    "cache_write_tokens int64",
    "call_id string",
    "prompt_version string",
    "call_stage string",
    runs="merge",
    key=("ts", "provider", "use_case", "user", "outcome"),
)
# The Describe-it feedback events (ADR 0066, the API's sixth write): one row per event of a
# drafting session (``draft_requested``, ``draft_returned``, ``choice_made``,
# ``formula_accepted``, ``formula_skipped``, ``draft_saved``, ``screen_finalised``,
# ``edge_revised``), one partition per exchange calendar date of the event. Runs merge (each is
# a batch of events; all kept). ``draft_session_id`` ties the events of one draft to the screen
# saved from it; ``call_ids`` is a comma-delimited list of ``usage/llm_calls.call_id``;
# ``draft_hash`` / ``saved_hash`` are content hashes (the draft the model returned, the document
# saved); ``sentence`` is the trader's text (<= 1,000 characters, personal data: ADR 0066 has the
# retention) and ``payload`` a JSON object (the server-side diff of a save, the criteria in
# force: ``current_criteria`` / ``draft_criteria`` / ``saved_criteria``, each <= 8,000 characters;
# the choices); ``seq`` is the 1-based ordinal of the draft request in its session.
# Only the columns that are not the event's identity are nullable. Written only through
# ``FeedbackWriter`` (``feedback/*``); read across a date range by ``data.feedback``.
FEEDBACK_DRAFTING_EVENTS = fixed(
    "feedback/drafting_events",
    "feedback",
    ("event_id", "ts", "event"),
    "event_id string!",
    "draft_session_id string!",
    "ts timestamp_utc!",
    "user string!",
    "doc_kind string!",
    "doc_id string!",
    "event string!",
    "call_ids string",
    "catalogue_version string",
    "prompt_version string",
    "draft_hash string",
    "saved_hash string",
    "sentence string",
    "payload string",
    "seq int64",
    runs="merge",
    key=("draft_session_id", "event_id", "event"),
)
# The missing-feature requests of Describe it (ADR 0066 amendment 2026-10-11): one row per
# (user, backlog key or new slug, exchange day), the span of the sentence the request covers
# (never the sentence). ``ref`` is the key or the slug (the identity); ``key`` is set for a backlog
# item, ``new_slug`` for a request the backlog does not know. Written through ``FeedbackWriter``,
# read across a date range by ``data.feedback``; the viewer-scoped loader decides who sees what.
FEEDBACK_FEATURE_REQUESTS = fixed(
    "feedback/feature_requests",
    "feedback",
    ("ts", "user", "ref"),
    "ts timestamp_utc!",
    "user string!",
    "ref string!",
    "key string",
    "new_slug string",
    "feasibility string",
    "span string",
    "closest string",
    "call_id string",
    "draft_session_id string",
    runs="merge",
    key=("user", "ref", "session_date"),
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
# Rule screens (ADR 0029): one fixed schema for every rule-screen config, so pages and Ideas
# query across screens. Many configs and users share a session's partition, so runs merge
# on (user, config, instrument): readers take a config's rows of its latest run (``run_id``
# from the run record), since a later run never removes rows an earlier one wrote.
RULE_SCREEN = fixed(
    "results/rule_screen",
    "results",
    ("instrument_id", "user_id", "config_id", "config_hash", "decision", "rank"),
    "instrument_id string!",
    "user_id string!",
    "config_id string!",
    "config_version int64",
    "config_hash string!",
    "decision string!",
    "score float64",
    "rank int64!",
    "tie_break float64",
    *strings("flags", "reasons", "failed", "near_missed", "missing"),
    "regime string",  # the session's regime label (ADR 0049); null: gate off or unknown
    "size_multiplier float64",  # the regime's size for the screener; null in runs before it
    runs="merge",
    key=("user_id", "config_id", "instrument_id"),
)
# One row per (instrument, criterion), per display column (``mode = "column"``, ``outcome =
# "INFO"``) and per criterion group (``mode = "group"``, ADR 0071: ``field`` the kind, the
# verdict's outcome and penalty, ``value_str`` the deciding member's id): the value, PASS / NEAR /
# FAIL / MISSING, distance and penalty. ``group_id`` is the row's parent group (null: a gate, or
# a partition from before groups).
DISPLAY_COLUMN_MODE = "column"
GROUP_MODE = "group"


def is_display_column(mode: object) -> bool:
    """Whether a ``results/rule_screen_values`` row of ``mode`` is one of the screen's display
    columns (``[columns]``) rather than a criterion's outcome: the one predicate its writer
    and its readers share."""
    return mode == DISPLAY_COLUMN_MODE


def is_group_row(mode: object) -> bool:
    """Whether a ``results/rule_screen_values`` row of ``mode`` is a criterion group's verdict
    (ADR 0071), not a criterion's outcome: a reader of criteria skips it as it skips display
    columns (``is_display_column``)."""
    return mode == GROUP_MODE


def is_criterion_row(mode: object) -> bool:
    """Whether a row of ``mode`` is a criterion's outcome (neither a display column nor a
    group): what every criterion reader keeps."""
    return not (is_display_column(mode) or is_group_row(mode))


RULE_SCREEN_VALUES = fixed(
    "results/rule_screen_values",
    "results",
    ("instrument_id", "user_id", "config_id", "criterion_id", "field", "mode", "outcome"),
    "instrument_id string!",
    "user_id string!",
    "config_id string!",
    "criterion_id string!",
    "field string!",
    "mode string!",
    "value_num float64",
    "value_str string",
    "outcome string!",
    *floats("distance", "normalised", "penalty"),
    "group_id string",  # the parent group (ADR 0071); null: a gate, or a partition before groups
    runs="merge",
    key=("user_id", "config_id", "instrument_id", "mode", "criterion_id"),
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

KNOWN: dict[str, TableSpec] = {
    t.name: t
    for t in (
        UNIVERSE,
        UNDERLYING_QUOTES,
        OPTION_QUOTES,
        CHAIN_STATUS,
        INSTRUMENT_REFERENCE,
        SYMBOL_HISTORY,
        ID_MAP,
        LISTING_HISTORY,
        INDEX_MEMBERSHIP,
        INSTRUMENT_COMPANY,
        INSTRUMENT_SHARES,
        INSTRUMENT_STATEMENTS,
        INSTRUMENT_DESCRIPTION,
        TREASURY_RATES,
        VERIFICATION_IBKR,
        IBKR_CONTRACTS,
        IBKR_IV30,
        VX_FUTURES,
        RULE_SCREEN,
        RULE_SCREEN_VALUES,
        EDGE_EVAL,
        EDGE_SERIES,
        WINNERS_STUDY,
        EDGE_PAPER,
        EDGE_LEGS,
        EDGE_TRADES,
        LIVE_OPTION_QUOTES,
        USAGE_LLM_CALLS,
        FEEDBACK_DRAFTING_EVENTS,
        FEEDBACK_FEATURE_REQUESTS,
        ETF_HOLDINGS,
        ETF_SHARES,
        MACRO_SERIES,
        ANALYST_VENDOR_ACCESS,
        ANALYST_ESTIMATE_SNAPSHOTS,
        EARNINGS_EVENTS,
        MACRO_RELEASE_EVENTS,
        FILING_EVENTS,
    )
}
# Open-ended tables: the producing rollup, event source, catalogue or screener defines the
# columns beyond instrument_id (+ ts for events). Event runs are windows (a backfill, then
# nightly -7..+30-day windows into the same session), so they merge; rollups, catalogues and
# results are full snapshots per run. Bars and chains (fixed, above) are snapshots too: a
# re-fetched session replaces the earlier fetch.
OPEN_PREFIXES = {
    "rollups/daily/": "rollup",
    "rollups/instrument/": "rollup",
    "rollups/market/": "rollup",  # market-entity feature groups: one MKT:<market> row (ADR 0047)
    "events/": "event",
    "results/": "results",
    "catalog/": "catalog",
}


# Outcomes (ADR 0053): what happened after a start session S, read only by the harness
# (``algotrade.data.outcomes``). One family of fixed tables ``outcomes/instrument/<name>@v<N>``;
# the partition is S. Each night T writes the windows it closes (S = T - h sessions), so one
# partition receives one run per horizon on different nights: runs merge, the latest run's row
# winning per (instrument, horizon, benchmark). ``knowledge_ts`` is the write time, never before
# the close of ``window_end`` (the writer refuses a window that has not closed).
# v2 (ADR 0061): a window that needs a bar the ``bar-quality`` task flagged is UNMEASURED, a row
# with a reason and no returns, instead of a return computed over a bad price.
OUTCOMES_PREFIX = "outcomes/instrument/"
FORWARD_RETURNS = f"{OUTCOMES_PREFIX}forward_returns@v2"  # the outcomes task's table
OUTCOME_STATUSES = frozenset({"COMPLETE", "DELISTED", "UNMEASURED"})
UNMEASURED = "UNMEASURED"
_OUTCOME_TYPES = (
    "instrument_id string!",
    "ts timestamp_utc!",  # the close of S
    "horizon_sessions int64!",
    "window_end date!",  # T: the h-th exchange session after S
    "benchmark string!",  # the benchmark ticker of fwd_excess_return
    "fwd_return float64",  # close(T) / close(S) - 1, split-adjusted, price return; null: UNMEASURED
    "fwd_excess_return float64",  # fwd_return - the benchmark's (null: no benchmark bar)
    "fwd_max_return float64",  # max high over (S, T] / close(S) - 1 (favourable); null: UNMEASURED
    "fwd_max_drawdown float64",  # 1 - min low over (S, T] / close(S), >= 0; null: UNMEASURED
    "fwd_realised_vol float64",  # annualised stdev of daily log close returns over (S, T]
    "outcome_status string!",  # OUTCOME_STATUSES; DELISTED: measured to the last bar
    "outcome_reason string",  # UNMEASURED only: why (BAD_BAR: a flagged bar in S..T, ADR 0061)
)


def outcomes_spec(table: str) -> TableSpec:
    """The spec of one ``outcomes/instrument/`` table (they share one schema)."""
    return fixed(
        table, "outcome", ("instrument_id", "ts", "horizon_sessions", "window_end", "benchmark"),
        *_OUTCOME_TYPES, runs="merge", key=("instrument_id", "horizon_sessions", "benchmark"),
    )  # fmt: skip


def result_table(name: str) -> str:
    """The table a result named ``name`` (a screener, a backtest output) is stored in."""
    return f"results/{name}"


def spec_for(table: str) -> TableSpec:
    if table in KNOWN:
        return KNOWN[table]
    if table.startswith("bars/"):
        interval = table.removeprefix("bars/")
        if interval not in BAR_INTERVALS:
            raise DataValidationError(table, [f"unknown bar interval {interval!r}"])
        return fixed(table, "bar", BAR_COLUMNS, *_BAR_TYPES)
    if table.startswith(OUTCOMES_PREFIX) and len(table) > len(OUTCOMES_PREFIX):
        return outcomes_spec(table)
    for prefix, grain in OPEN_PREFIXES.items():
        if table.startswith(prefix) and len(table) > len(prefix):
            required = ("instrument_id", "ts") if grain == "event" else ("instrument_id",)
            keys = ("instrument_id string!", "ts timestamp_utc!")[: len(required)]
            event = grain == "event"
            typed = (*keys, f"{KNOWN_FROM} date") if event else keys
            runs = "merge" if event else "snapshot"
            return TableSpec(
                table, grain, required, open_ended=True, columns=columns_of(*typed), runs=runs
            )
    raise DataValidationError(
        table, ["unknown table; add a TableSpec to storage/tables/schemas.py"]
    )


def validate_frame(table: str, frame: pd.DataFrame) -> None:
    spec = spec_for(table)
    missing = [c for c in (*COMMON, *spec.required) if c not in frame.columns]
    problems = [f"missing columns: {missing}"] if missing else []
    if not spec.open_ended:
        undeclared = [c for c in frame.columns if spec.column(str(c)) is None]
        if undeclared:
            problems.append(
                f"undeclared columns {undeclared}: declare them in storage/tables/schemas.py"
            )
    if not missing:
        if frame[list(COMMON)].isna().to_numpy().any():
            problems.append("point-in-time columns contain nulls")
        if "instrument_id" in spec.required and frame["instrument_id"].isna().any():
            problems.append("null instrument_id")
        if frame.duplicated(subset=table_key(spec, frame.columns)).any():
            problems.append("duplicate rows for the table key")
        if spec.grain == "bar":
            problems.extend(bar_problems(frame))
        if spec.name in VALUE_CHECKS:
            problems.extend(VALUE_CHECKS[spec.name](frame))
        if spec.grain == "outcome":
            bad = sorted({str(v) for v in frame["outcome_status"]} - OUTCOME_STATUSES)
            if bad:
                problems.append(f"outcome_status must be one of {sorted(OUTCOME_STATUSES)}: {bad}")
            problems.extend(outcome_problems(frame))
    if problems:
        raise DataValidationError(table, problems)


def outcome_problems(frame: pd.DataFrame) -> list[str]:
    """An UNMEASURED outcome has a reason and no return; every other status has its returns."""
    unmeasured = (frame["outcome_status"] == UNMEASURED).to_numpy()
    problems = []
    reason = frame["outcome_reason"] if "outcome_reason" in frame.columns else None
    if unmeasured.any() and (reason is None or reason[unmeasured].isna().any()):
        problems.append("an UNMEASURED outcome needs an outcome_reason")
    measured = ~unmeasured
    for column in ("fwd_return", "fwd_max_return", "fwd_max_drawdown"):
        values = frame[column]
        if values[unmeasured].notna().any():
            problems.append(f"{column} must be null when UNMEASURED")
        if values[measured].isna().any():
            problems.append(f"{column} is null on a measured outcome")
    return problems


def table_key(spec: TableSpec, columns: Iterable[object]) -> list[str]:
    """The columns that identify a row: unique within a run (checked on write) and, for
    ``merge`` tables, the key the latest run wins on across runs. A spec's own ``key`` wins
    over the grain's default (``instrument_id``, + ``ts``, + ``change`` for events)."""
    if spec.key:
        return list(spec.key)
    present = {str(c) for c in columns}
    key = ["instrument_id"]
    if "ts" in present and spec.grain != "universe":  # history rows: one per (id, from)
        key.append("ts")
    if spec.grain == "event" and "change" in present:  # several kinds of change per day
        key.append("change")
    return key


def bar_problems(frame: pd.DataFrame) -> list[str]:
    """OHLCV sanity checks on a bars frame (``core.validation.bars.ohlcv_problems``)."""
    return ohlcv_problems(*(frame[col].to_numpy(dtype=np.float64) for col in FIELDS))


def vintage_problems(frame: pd.DataFrame) -> list[str]:
    """``macro/series`` rows whose ``vintage_kind`` is not one of ``VINTAGE_KINDS``."""
    kinds = frame["vintage_kind"]
    bad = sorted({str(v) for v in kinds.dropna()} - VINTAGE_KINDS)
    if kinds.isna().any():
        bad.append("null")
    return [f"vintage_kind must be one of {sorted(VINTAGE_KINDS)}, got {bad}"] if bad else []


def release_status_problems(frame: pd.DataFrame) -> list[str]:
    """``events/macro_release`` rows whose ``status`` is not one of ``RELEASE_STATUSES``."""
    bad = sorted({str(v) for v in frame["status"]} - RELEASE_STATUSES)
    return [f"status must be one of {sorted(RELEASE_STATUSES)}, got {bad}"] if bad else []


def access_status_problems(frame: pd.DataFrame) -> list[str]:
    """``analyst/vendor_access`` rows whose ``status`` is not one of ``ACCESS_STATUSES``."""
    bad = sorted({str(v) for v in frame["status"]} - ACCESS_STATUSES)
    return [f"status must be one of {sorted(ACCESS_STATUSES)}, got {bad}"] if bad else []


def snapshot_kind_problems(frame: pd.DataFrame) -> list[str]:
    """``analyst/estimate_snapshots``: a known ``kind``; ``status`` only on ``coverage`` rows."""
    bad = sorted({str(v) for v in frame["kind"]} - SNAPSHOT_KINDS)
    problems = [f"kind must be one of {sorted(SNAPSHOT_KINDS)}, got {bad}"] if bad else []
    status = frame["status"] if "status" in frame.columns else pd.Series(None, index=frame.index)
    coverage = frame["kind"] == "coverage"
    wrong = sorted({str(v) for v in status[coverage]} - COVERAGE_STATUSES)
    if wrong:
        problems.append(f"coverage status must be one of {sorted(COVERAGE_STATUSES)}, got {wrong}")
    if status[~coverage].notna().any():
        problems.append("status is set only on coverage rows")
    return problems


# The value rules of the tables that restrict a column to a vocabulary, by table name.
VALUE_CHECKS = {
    MACRO_SERIES.name: vintage_problems,
    MACRO_RELEASE_EVENTS.name: release_status_problems,
    ANALYST_VENDOR_ACCESS.name: access_status_problems,
    ANALYST_ESTIMATE_SNAPSHOTS.name: snapshot_kind_problems,
}


def require_retention(table: str) -> int:
    """``table``'s retention window; ``DataValidationError`` for a table kept forever (only
    tables that declare ``retention_days`` may have partitions purged)."""
    days = spec_for(table).retention_days
    if days is None:
        raise DataValidationError(table, ["no retention declared: its partitions are never purged"])
    return days
