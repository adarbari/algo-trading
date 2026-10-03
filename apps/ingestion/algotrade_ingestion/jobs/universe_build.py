"""Build the universe from the Nasdaq Trader symbol directory + SPY holdings (phase 1.2).

Writes, for the session:
- ``instruments/reference`` (L1): **every** listed security (all types), classified, with
  optionable / S&P 500 / leverage flags. Instruments seen before but no longer listed are kept
  with ``status = DELISTED`` and ``delisted_on``, so history never silently disappears.
- ``universe``: the **coverage** defined by ``config/site/universe.toml`` (types, test
  issues, include / exclude lists). Strategies narrow it further with selections.
- ``events/reference_change`` and ``events/index_change`` from the previous snapshot.
- ``instruments/id_map`` when a symbol id becomes a FIGI id (ADR 0018, ``instrument_ids``).

Leverage: ETFs whose names carry a leverage marker stay UNKNOWN unless curated in
``config/site/overrides/leveraged_etfs.csv``; ``review_rows`` lists them for curation.
"""

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

import pandas as pd

from algotrade.core.instruments import AssetClass
from algotrade.data import StoreReader
from algotrade.storage.runs import RunRecord, RunStatus, new_run_id
from algotrade.storage.writers import StoreWriter
from algotrade_ingestion.jobs.classify import (
    DEFAULT_LEVERAGE_MARKERS,
    leverage_flags,
    security_type,
)
from algotrade_ingestion.jobs.common import stamp
from algotrade_ingestion.jobs.instrument_ids import (
    ID_MAP,
    Assigned,
    assign_ids,
    cumulative_map,
    rename_ids,
)
from algotrade_ingestion.jobs.reference_diff import diff_reference
from algotrade_ingestion.jobs.symbol_history import update_history
from algotrade_ingestion.sources.base import FetchRequest, Source

JOB = "universe_build"
HISTORY = "instruments/symbol_history"
REFERENCE = "instruments/reference"
_SUGGESTED = re.compile(r"(-?\d(?:\.\d)?)\s*x\b", re.I)


@dataclass(frozen=True)
class UniverseSettings:
    security_types: tuple[str, ...] = ("COMMON_STOCK", "ADR", "ETF")
    exclude_test_issues: bool = True
    include_symbols: frozenset[str] = frozenset()
    exclude_symbols: frozenset[str] = frozenset()
    leverage_markers: tuple[str, ...] = DEFAULT_LEVERAGE_MARKERS
    overrides: tuple[Mapping[str, str], ...] = field(default=())

    @classmethod
    def from_documents(
        cls, doc: Mapping[str, Any] | None, overrides: list[dict[str, str]]
    ) -> "UniverseSettings":
        doc = doc or {}
        return cls(
            security_types=tuple(doc.get("security_types", cls.security_types)),
            exclude_test_issues=bool(doc.get("exclude_test_issues", True)),
            include_symbols=frozenset(s.upper() for s in doc.get("include_symbols", [])),
            exclude_symbols=frozenset(s.upper() for s in doc.get("exclude_symbols", [])),
            leverage_markers=tuple(doc.get("leverage_markers", DEFAULT_LEVERAGE_MARKERS)),
            overrides=tuple(overrides),
        )


@dataclass(frozen=True)
class UniverseSources:
    nasdaq_trader: Source
    spy_holdings: Source
    tickers: Source | None = None  # Massive ticker list: FIGI, CIK, vendor security type


def _fetch(
    source: Source, key: str, writer: StoreWriter, session: date, run_id: str
) -> dict[str, pd.DataFrame]:
    request = FetchRequest(key, session_date=session)
    payload = source.fetch(request)
    if payload is None:
        raise ValueError(f"{source.name}: {key} returned nothing")
    writer.raw.put(source.name, source.dataset, session, run_id, key, payload)
    normalized = source.normalize(request, payload)
    if normalized is None:
        raise ValueError(f"{source.name}: {key} had no rows")
    return dict(normalized.parsed)


def build_reference(
    listings: pd.DataFrame,
    optionable: set[str],
    sp500: set[str],
    settings: UniverseSettings,
    previous: pd.DataFrame | None,
    session: date,
    tickers: pd.DataFrame | None = None,
    id_basis: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, int, Assigned]:
    """Every listing (+ carried-forward delistings); -> (reference, vendor-type
    disagreements, id assignment). Ids build on ``previous``, else on ``id_basis`` (an
    earlier run for the same session)."""
    listings = listings.drop_duplicates("symbol", keep="first").reset_index(drop=True)
    ref = listings.assign(
        asset_class=AssetClass.EQUITY.value,
        currency="USD",
        multiplier=1.0,
        tick_size=0.01,
        security_type=[
            security_type(n, s, e)
            for n, s, e in zip(
                listings["name"], listings["symbol"], listings["is_etf"], strict=True
            )
        ],
        optionable=listings["symbol"].isin(optionable),
        in_sp500=listings["symbol"].isin(sp500),
        status="ACTIVE",
        first_seen=session,
        delisted_on=None,
    )
    ref, disagreements = apply_identifiers(ref, tickers)
    assigned = assign_ids(ref, previous if previous is not None else id_basis, session)
    ref, previous = assigned.reference, rename_ids(previous, assigned.upgrades)
    ref["is_etf"] = ref["is_etf"] | ref["security_type"].eq("ETF")
    ref = pd.concat(
        [ref, leverage_flags(ref, settings.overrides, settings.leverage_markers)], axis=1
    )
    if previous is not None and not previous.empty:
        seen = previous.set_index("instrument_id")
        if "first_seen" in seen.columns:
            ref["first_seen"] = [
                seen["first_seen"].get(i, session) or session for i in ref["instrument_id"]
            ]
        gone = previous[~previous["instrument_id"].isin(ref["instrument_id"])].copy()
        if not gone.empty:
            was_active = gone["status"].eq("ACTIVE")
            gone.loc[was_active, "delisted_on"] = session
            gone["status"], gone["in_sp500"] = "DELISTED", False
            keep = [c for c in ref.columns if c in gone.columns]
            ref = pd.concat([ref, gone[keep]], ignore_index=True)
    return ref.sort_values("instrument_id").reset_index(drop=True), disagreements, assigned


def apply_identifiers(
    reference: pd.DataFrame, tickers: pd.DataFrame | None
) -> tuple[pd.DataFrame, int]:
    """Add FIGI / CIK and prefer the vendor's security type over our name rules.

    -> (reference, rows where the vendor type disagreed with the name rules)."""
    if tickers is None or tickers.empty:
        return reference.assign(
            figi=None,
            share_class_figi=None,
            cik=None,
            vendor_type=None,
            security_type_source="name_rule",
        ), 0
    merged = reference.merge(tickers, on="symbol", how="left")
    vendor = merged["vendor_security_type"]
    disagree = int((vendor.notna() & vendor.ne(merged["security_type"])).sum())
    merged["security_type_source"] = vendor.notna().map({True: "vendor", False: "name_rule"})
    merged["security_type"] = vendor.where(vendor.notna(), merged["security_type"])
    return merged.drop(columns=["vendor_security_type"]), disagree


def coverage(reference: pd.DataFrame, settings: UniverseSettings) -> pd.Series:
    covered = reference["status"].eq("ACTIVE") & reference["security_type"].isin(
        settings.security_types
    )
    if settings.exclude_test_issues:
        covered &= ~reference["is_test_issue"].fillna(False).astype(bool)
    covered |= reference["symbol"].isin(settings.include_symbols) & reference["status"].eq("ACTIVE")
    return covered & ~reference["symbol"].isin(settings.exclude_symbols)


def review_rows(reference: pd.DataFrame) -> list[dict[str, str]]:
    """Leverage candidates to curate, in ``leveraged_etfs.csv`` format (leverage suggested)."""
    pending = reference[
        reference["leverage_source"].eq("needs_review") & reference["status"].eq("ACTIVE")
    ]
    rows = []
    for symbol, name in zip(pending["symbol"], pending["name"], strict=True):
        match = _SUGGESTED.search(str(name))
        suggested = match.group(1) if match else ""
        inverse = re.search(r"\b(bear|short|inverse)\b", str(name), re.I)
        if suggested and inverse and not suggested.startswith("-"):
            suggested = f"-{suggested}"
        rows.append({"symbol": symbol, "leverage": suggested, "tracks": "", "notes": str(name)})
    return rows


def _before(reader: StoreReader, table: str, session: date) -> pd.DataFrame | None:
    """The latest snapshot of ``table`` strictly before ``session``, so a re-run of a session
    builds on the same history as its first run."""
    days = [d for d in reader.dates(table) if d < session]
    return reader.table(table, days[-1]) if days else None


def build_universe(
    writer: StoreWriter,
    reader: StoreReader,
    sources: UniverseSources,
    settings: UniverseSettings,
    session: date,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> RunRecord:
    now = clock()
    run_id = new_run_id(JOB, session, now)
    parsed: dict[str, pd.DataFrame] = {}
    for key in ("nasdaqlisted", "otherlisted", "options"):
        parsed.update(_fetch(sources.nasdaq_trader, key, writer, session, run_id))
    parsed.update(_fetch(sources.spy_holdings, "SPY", writer, session, run_id))
    if sources.tickers is not None:
        parsed.update(_fetch(sources.tickers, "active", writer, session, run_id))
    listings = pd.concat([parsed["nasdaqlisted"], parsed["otherlisted"]], ignore_index=True)
    previous = _before(reader, REFERENCE, session)
    sp500 = set(parsed["sp500"]["symbol"])
    reference, disagreements, assigned = build_reference(
        listings,
        set(parsed["options"]["symbol"]),
        sp500,
        settings,
        previous,
        session,
        parsed.get("tickers"),
        reader.table(REFERENCE, session) if previous is None else None,
    )
    history, ticker_changes = update_history(_before(reader, HISTORY, session), reference, session)
    id_map = cumulative_map(_before(reader, ID_MAP, session), assigned.upgrades, now)
    covered = reference[coverage(reference, settings)]
    universe = pd.DataFrame(
        {
            "instrument_id": covered["instrument_id"],
            "symbol": covered["symbol"],
            "company_name": covered["name"],
            "security_type": covered["security_type"],
            "asset_class": covered["is_etf"].map({True: "ETF", False: "STOCK"}),
            "exchange": covered["exchange"],
            "status": covered["status"],
            "optionable": covered["optionable"],
            "universe_version": session.isoformat(),
            "last_verified": session.isoformat(),
            "source_crosscheck": "",
            "notes": "",
        }
    )
    changes, index = diff_reference(rename_ids(previous, assigned.upgrades), reference, session)
    extra = ticker_changes + [
        {"instrument_id": u.new_id, "symbol": u.symbol, "change": "id_changed",
         "old": u.old_id, "new": u.new_id}
        for u in assigned.upgrades.itertuples()
    ]  # fmt: skip
    if extra:
        rows = pd.DataFrame(extra).assign(ts=pd.Timestamp(session, tz="UTC"))
        changes = pd.concat([changes, rows], ignore_index=True)
    source = sources.nasdaq_trader.name
    writer.write_table(REFERENCE, session, run_id, stamp(reference, session, now, source, run_id))
    writer.write_table("universe", session, run_id, stamp(universe, session, now, source, run_id))
    for table, frame in ((HISTORY, history), (ID_MAP, id_map)):
        if not frame.empty:
            writer.write_table(table, session, run_id, stamp(frame, session, now, source, run_id))
    for table, frame in (("events/reference_change", changes), ("events/index_change", index)):
        if not frame.empty:
            writer.write_table(table, session, run_id, stamp(frame, session, now, source, run_id))
    unmatched = sorted(sp500 - set(listings["symbol"]))
    stats = {
        "listed": int(reference["status"].eq("ACTIVE").sum()),
        "delisted_carried": int(reference["status"].eq("DELISTED").sum()),
        "by_security_type": reference.loc[reference["status"].eq("ACTIVE"), "security_type"]
        .value_counts()
        .to_dict(),
        "covered": len(universe),
        "optionable_covered": int(universe["optionable"].sum()),
        "sp500_members": len(sp500),
        "sp500_unmatched": unmatched,
        "leverage": reference["leverage_source"].value_counts().to_dict(),
        "identifiers": {
            "with_figi": int(reference["figi"].notna().sum()),
            **assigned.stats,
            "vendor_type_disagreements": disagreements,
            "security_type_source": reference.loc[
                reference["status"].eq("ACTIVE"), "security_type_source"
            ]
            .value_counts()
            .to_dict(),
        },
        "events": {
            "reference_change": changes["change"].value_counts().to_dict(),
            "index_change": index["change"].value_counts().to_dict(),
        },
    }
    status = RunStatus.PARTIAL if unmatched else RunStatus.COMPLETE
    record = RunRecord(run_id, JOB, session, now, status, now, stats=stats)
    writer.save_run(record)
    return record
