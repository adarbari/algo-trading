"""A listing's ``end_date`` is the vendor's last trading day, known only for names that have since
delisted: read for a session S it leaks the future unless it is compared ``<= S``. Only the modules
below read it (the listing reads, the identity resolver, the listing writers, the winners
sample and the bars-history clip); anything else, e.g. a feature or the outcomes task, goes through
``data.listings.delisted_by(reader, T)``.

``events/delisting`` (ADR 0087 decision 4) is quarantined the same way: only ``data.listings``
reads it. An AST scan finds every import of ``algotrade.data.listings.delistings`` (by module or
by ``from algotrade.data.listings import delistings``) and every string naming the table outside
the allowed files: the reader, the schema, the ``delistings`` task (its reason rules and registry
entry), the outcomes task (PR6a: the delisting return) and ``services/evaluation`` (PR6b: the
label). Another reader would read a delisting without its point-in-time rule (``known_by`` for a
feature, the (S, T] window for the label)."""

import ast
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
    "apps/ingestion/algotrade_ingestion/tasks/events/filings.py",  # delisted names: who left
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


DELISTINGS_MODULE = "algotrade.data.listings.delistings"
IMPORTERS = (
    "src/algotrade/data/listings/",  # the reader itself
    "apps/ingestion/algotrade_ingestion/tasks/listings/delistings.py",  # the writer
    "apps/ingestion/algotrade_ingestion/tasks/listings/delisting_reason.py",  # its reason rules
    "apps/ingestion/algotrade_ingestion/tasks/derived/outcomes.py",  # PR6a: the delisting return
    "src/algotrade/services/evaluation/",  # PR6b: the outcome label
)
TABLE_NAMED = (
    "src/algotrade/data/listings/",  # the reader
    "src/algotrade/storage/tables/schemas/events.py",  # declares the table
    "apps/ingestion/algotrade_ingestion/tasks/listings/delistings.py",  # the one writer
    "apps/ingestion/algotrade_ingestion/tasks/framework/entries_reference.py",  # its registry entry
)
TABLE_NAME = re.compile(r"events/delisting(?![a-z_])")


def _imports_reader(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and any(
            a.name == DELISTINGS_MODULE or a.name.startswith(f"{DELISTINGS_MODULE}.")
            for a in node.names
        ):
            return True
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module == DELISTINGS_MODULE or node.module.startswith(f"{DELISTINGS_MODULE}."):
                return True
            parent, _, leaf = DELISTINGS_MODULE.rpartition(".")
            if node.module == parent and any(a.name == leaf for a in node.names):
                return True
    return False


def _names_table(tree: ast.AST) -> bool:
    return any(
        isinstance(n, ast.Constant) and isinstance(n.value, str) and TABLE_NAME.search(n.value)
        for n in ast.walk(tree)
    )


def _scan(source: str) -> tuple[bool, bool]:
    tree = ast.parse(source)
    return _imports_reader(tree), _names_table(tree)


def test_only_the_allowed_modules_read_the_delisting_table() -> None:
    importers, named = [], []
    for root in SCANNED:
        for path in sorted((REPO_ROOT / root).rglob("*.py")):
            rel = path.relative_to(REPO_ROOT).as_posix()
            if "node_modules" in rel:
                continue
            imports, names = _scan(path.read_text())
            if imports and not rel.startswith(IMPORTERS):
                importers.append(rel)
            if names and not rel.startswith(TABLE_NAMED):
                named.append(rel)
    assert not importers, f"{DELISTINGS_MODULE} is imported only by {IMPORTERS}: {importers}"
    assert not named, f"events/delisting is named only in {TABLE_NAMED}: {named}"


def test_the_scan_sees_each_way_to_the_reader() -> None:
    assert _scan("from algotrade.data.listings.delistings import read_delistings")[0]
    assert _scan("import algotrade.data.listings.delistings as d")[0]
    assert _scan("from algotrade.data.listings import delistings")[0]
    assert _scan("from algotrade.data.listings import universe")[0] is False
    assert _scan("T = 'events/delisting'")[1] and _scan("T = f('events/delisting')")[1]
    assert _scan("T = 'events/delisting_x'")[1] is False
