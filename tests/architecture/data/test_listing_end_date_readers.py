"""A listing's ``end_date`` is the vendor's last trading day, known only for names that have since
delisted: read for a session S it leaks the future unless it is compared ``<= S``. Only the modules
below read it (the listing reads, the identity resolver, the listing writers, the winners
sample and the bars-history clip); anything else, e.g. a feature or the outcomes task, goes through
``data.listings.delisted_by(reader, T)``."""

import re

from tests.conftest import REPO_ROOT

SCANNED = ("src/algotrade", "apps/api", "apps/backtest", "apps/ingestion", "libs")
ALLOWED = (
    "src/algotrade/data/listings/",  # universe_asof, delisted_by, read_listings, S&P 500
    "src/algotrade/data/resolver.py",  # is this listing alive on S
    "src/algotrade/storage/tables/schemas.py",  # declares the columns
    "apps/ingestion/algotrade_ingestion/tasks/reference/instrument_ids.py",  # listing -> id
    "apps/ingestion/algotrade_ingestion/tasks/listings/",  # the winners sample and its coverage
    "apps/ingestion/algotrade_ingestion/tasks/market/bars_history.py",  # listings_over: clip
    "libs/sources/",  # the vendor adapters that write the column
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
