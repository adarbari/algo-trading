"""A listing's ``end_date`` is the vendor's last trading day, known only for names that have since
delisted: read for a session S it leaks the future unless it is compared ``<= S``. Only the modules
below read it (the listing reads, the identity resolver, the listing writers, the winners
sample and the bars-history clip); anything else, e.g. a feature or the outcomes task, goes through
``data.listings.delisted_by(reader, T)``.

``events/delisting`` (ADR 0087 decision 4) is quarantined the same way: only ``data.listings``
reads it; its name appears as a string only in its schema, its reader and its one writer (the
``delistings`` task and its registry entry), and ``read_delistings`` is imported by no feature,
screener or page read (PR6 adds the harness). Another reader would read a delisting without its
point-in-time rule (``known_by`` for a feature, the (S, T] window for the label)."""

import re

from tests.conftest import REPO_ROOT

SCANNED = ("src/algotrade", "apps/api", "apps/backtest", "apps/ingestion", "libs")
ALLOWED = (
    # universe_asof, delisted_by, read_listings, S&P 500; delisted.py (ADR 0087: Massive's
    # delisted tickers, for the id merge and the quality report only)
    "src/algotrade/data/listings/",
    "src/algotrade/data/resolver.py",  # is this listing alive on S
    "src/algotrade/storage/tables/schemas/reference.py",  # declares the columns
    "apps/ingestion/algotrade_ingestion/tasks/reference/instrument_ids.py",  # listing -> id
    # winners sample, coverage, delisted, the merge into the listing history (listing_merge)
    "apps/ingestion/algotrade_ingestion/tasks/listings/",
    "apps/ingestion/algotrade_ingestion/tasks/market/bars_history.py",  # listings_over: clip
    "libs/sources/",  # the vendor adapters that write the column (Tiingo, Massive inactive)
)
READ = re.compile(r"(?<![A-Za-z0-9_])end_date(?![A-Za-z0-9_])")


def test_only_the_listing_reads_use_end_date() -> None:
    offenders = []
    for root in SCANNED:
        for path in sorted((REPO_ROOT / root).rglob("*.py")):
            rel = path.relative_to(REPO_ROOT).as_posix()
            if rel.startswith(ALLOWED) or "node_modules" in rel:
                continue
            if READ.search(path.read_text()):
                offenders.append(rel)
    assert not offenders, (
        f"read a listing end_date outside data.listings (leaks the future): {offenders}"
    )


DELISTING_ALLOWED = (
    "src/algotrade/data/listings/",  # the reader
    "src/algotrade/storage/tables/schemas/events.py",  # declares the table
    "apps/ingestion/algotrade_ingestion/tasks/listings/delistings.py",  # the one writer
    "apps/ingestion/algotrade_ingestion/tasks/framework/entries_reference.py",  # its registry entry
)
DELISTING_NAME = re.compile(r"events/delisting(?![a-z_])")
DELISTING_IMPORT = re.compile(r"data\.listings\.delistings import[^\n]*\bread_delistings\b")


def test_only_data_listings_reads_the_delisting_table() -> None:
    named, importers = [], []
    for root in SCANNED:
        for path in sorted((REPO_ROOT / root).rglob("*.py")):
            rel = path.relative_to(REPO_ROOT).as_posix()
            if "node_modules" in rel:
                continue
            text = path.read_text()
            if not rel.startswith(DELISTING_ALLOWED) and DELISTING_NAME.search(text):
                named.append(rel)
            if not rel.startswith("src/algotrade/data/listings/") and DELISTING_IMPORT.search(text):
                importers.append(rel)
    assert not named, f"read events/delisting outside data.listings: {named}"
    assert not importers, f"import read_delistings only from services/evaluation: {importers}"
