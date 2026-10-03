"""Build the universe from the Nasdaq Trader symbol directory + SPY holdings (phase 1.2).

Writes, for the session:
- ``instruments/reference`` (L1): **every** listed security (all types), classified, with
  optionable / S&P 500 / leverage flags. Instruments seen before but no longer listed are kept
  with ``status = DELISTED`` and ``delisted_on``, so history never silently disappears.
- ``universe``: the **coverage** defined by ``config/site/universe.toml`` (types, test
  issues, include / exclude lists). Strategies narrow it further with selections.
- ``events/reference_change`` and ``events/index_change`` from the previous session's
  snapshot.
- ``instruments/id_map`` when a symbol id becomes a FIGI id, or an owner override in
  ``config/site/overrides/figi.csv`` changes one (ADR 0018, ``instrument_ids``). A FIGI id
  never changes otherwise: a different vendor FIGI for a held listing, and a FIGI several
  listings share, are kept out of the ids and listed by ``write_figi_review`` instead.

Cumulative state (ids, ``first_seen``, delistings carried, ``symbol_history``, ``id_map``)
builds on the latest snapshot **known** at build time (``_known``): an earlier run of the same
session when there is one, else the latest earlier session. A same-session re-run therefore
keeps what the earlier run recorded (2026-10-03: a re-run that started from nothing wrote an
id map of 3 upgrades that hid the 10,817 before it). Events compare against the previous
session (``_previous``) with the session's upgrades applied, so a re-run emits the same rows
under the same keys, which the merged event tables absorb. A run writes at most one event per
key (``reference_diff.one_per_key``): several id changes into one id on a session (DFAC,
2026-10-02: a FIGI upgrade, then an override back after a vendor flip) are one ``id_changed``.

Leverage (``classify.leverage_flags``): a curated row in
``config/site/overrides/leveraged_etfs.csv`` wins, then the leverage the name states, then the
name rules of ``universe.toml``; ETFs still UNKNOWN are listed by ``review_rows`` for curation.
"""

import csv
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd

from algotrade.config.site.settings import UniverseSettings
from algotrade.core.model.instruments import AssetClass
from algotrade.data import StoreReader
from algotrade.storage.runs import RunRecord
from algotrade_ingestion.sources.framework.base import DirectorySource, FetchRequest, Source
from algotrade_ingestion.tasks.framework.run import IngestRun, TaskContext
from algotrade_ingestion.tasks.reference.classify import (
    LEVERAGE_SOURCES,
    leverage_flags,
    security_type,
)
from algotrade_ingestion.tasks.reference.instrument_ids import (
    FIGI_REVIEW_COLUMNS,
    ID_MAP,
    Assigned,
    assign_ids,
    cumulative_map,
    figi_review_rows,
    rename_ids,
)
from algotrade_ingestion.tasks.reference.reference_diff import (
    diff_reference,
    id_change_rows,
    one_per_key,
)
from algotrade_ingestion.tasks.reference.symbol_history import update_history

TASK = "universe_build"
HISTORY = "instruments/symbol_history"
REFERENCE = "instruments/reference"


@dataclass(frozen=True)
class UniverseSources:
    nasdaq_trader: DirectorySource
    spy_holdings: Source
    tickers: Source | None = None  # Massive ticker list: FIGI, CIK, vendor security type


def _fetch(run: IngestRun, source: Source, key: str) -> dict[str, pd.DataFrame]:
    normalized = run.fetch(source, FetchRequest(key, session_date=run.session))
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
) -> tuple[pd.DataFrame, int, Assigned]:
    """Every listing (+ carried-forward delistings); -> (reference, vendor-type
    disagreements, id assignment). ``previous`` is the latest reference known (``_known``):
    ids, ``first_seen`` and delistings build on it."""
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
    assigned = assign_ids(ref, previous, session, settings.figi_overrides)
    ref, previous = assigned.reference, rename_ids(previous, assigned.upgrades)
    ref["is_etf"] = ref["is_etf"] | ref["security_type"].eq("ETF")
    ref = pd.concat([ref, leverage_flags(ref, settings)], axis=1)
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
    """UNKNOWN leverage to curate, in ``leveraged_etfs.csv`` format. The name states no
    leverage the rules can parse, so ``leverage`` is left for the curator."""
    pending = reference[
        reference["leverage_source"].eq("needs_review") & reference["status"].eq("ACTIVE")
    ]
    return [
        {"symbol": symbol, "leverage": "", "tracks": "", "notes": str(name)}
        for symbol, name in zip(pending["symbol"], pending["name"], strict=True)
    ]


def write_review(reader: StoreReader, session: date, path: Path) -> None:
    """Write ``review_rows`` for the session's reference to ``path`` (CSV) for curation."""
    reference = reader.table(REFERENCE, session)
    rows = review_rows(reference) if reference is not None else []
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        out = csv.DictWriter(fh, fieldnames=["symbol", "leverage", "tracks", "notes"])
        out.writeheader()
        out.writerows(rows)


def write_figi_review(reader: StoreReader, session: date, path: Path) -> int:
    """Write ``figi_review_rows`` for the session's reference to ``path`` (CSV: symbol,
    held_figi, vendor_figi, first_seen, note); -> the number of rows."""
    reference = reader.table(REFERENCE, session)
    rows = figi_review_rows(reference) if reference is not None else []
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        out = csv.DictWriter(fh, fieldnames=FIGI_REVIEW_COLUMNS)
        out.writeheader()
        out.writerows(rows)
    return len(rows)


def _known(reader: StoreReader, table: str, session: date) -> pd.DataFrame | None:
    """Cumulative state as known now: ``table`` for ``session`` itself when an earlier run
    wrote it (a re-run builds on it), else the latest earlier session."""
    days = [d for d in reader.dates(table) if d <= session]
    return reader.table(table, days[-1]) if days else None


def _previous(reader: StoreReader, table: str, session: date) -> pd.DataFrame | None:
    """The latest snapshot of ``table`` strictly before ``session``: what events diff
    against, so every run of a session emits the same changes."""
    days = [d for d in reader.dates(table) if d < session]
    return reader.table(table, days[-1]) if days else None


def session_upgrades(id_map: pd.DataFrame, session: date) -> pd.DataFrame:
    """The id map's upgrades effective on ``session``, from this run or an earlier one."""
    if id_map.empty:
        return id_map
    effective = pd.to_datetime(id_map["effective"]).dt.date
    return id_map[effective.eq(session)].reset_index(drop=True)


def build_universe(
    ctx: TaskContext, sources: UniverseSources, settings: UniverseSettings, session: date
) -> RunRecord:
    with IngestRun(ctx, TASK, session) as run:
        trader = sources.nasdaq_trader
        parsed: dict[str, pd.DataFrame] = {}
        for key in (*trader.listing_keys, trader.options_key):
            parsed.update(_fetch(run, trader, key))
        parsed.update(_fetch(run, sources.spy_holdings, "SPY"))
        if sources.tickers is not None:
            parsed.update(_fetch(run, sources.tickers, "active"))
        listings = pd.concat([parsed[k] for k in trader.listing_keys], ignore_index=True)
        _build(run, ctx.reader, listings, parsed[trader.options_key], parsed, settings, trader.name)
    return run.record


def _build(
    run: IngestRun,
    reader: StoreReader,
    listings: pd.DataFrame,
    optionable: pd.DataFrame,
    parsed: dict[str, pd.DataFrame],
    settings: UniverseSettings,
    source: str,
) -> None:
    session = run.session
    sp500 = set(parsed["sp500"]["symbol"])
    reference, disagreements, assigned = build_reference(
        listings,
        set(optionable["symbol"]),
        sp500,
        settings,
        _known(reader, REFERENCE, session),
        session,
        parsed.get("tickers"),
    )
    history, ticker_changes = update_history(_known(reader, HISTORY, session), reference, session)
    known_at = run.record.started_at
    id_map = cumulative_map(_known(reader, ID_MAP, session), assigned.upgrades, known_at)
    upgraded = session_upgrades(id_map, session)
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
    previous = rename_ids(_previous(reader, REFERENCE, session), upgraded)
    changes, index = diff_reference(previous, reference, session)
    extra = [frame for frame in (
        pd.DataFrame(ticker_changes).assign(ts=pd.Timestamp(session, tz="UTC")),
        id_change_rows(upgraded, session),
    ) if not frame.empty]  # fmt: skip
    if extra:
        changes = pd.concat([changes, *extra], ignore_index=True)
    changes, duplicates = one_per_key(changes)
    for table, frame in (
        (REFERENCE, reference),
        ("universe", universe),
        (HISTORY, history),
        (ID_MAP, id_map),
        ("events/reference_change", changes),
        ("events/index_change", index),
    ):
        if table in (REFERENCE, "universe") or not frame.empty:
            run.write(table, frame, source)
    unmatched = sorted(sp500 - set(listings["symbol"]))
    run.stats.update({
        "listed": int(reference["status"].eq("ACTIVE").sum()),
        "delisted_carried": int(reference["status"].eq("DELISTED").sum()),
        "by_security_type": reference.loc[reference["status"].eq("ACTIVE"), "security_type"]
        .value_counts()
        .to_dict(),
        "covered": len(universe),
        "optionable_covered": int(universe["optionable"].sum()),
        "sp500_members": len(sp500),
        "sp500_unmatched": unmatched,
        "leverage": {
            s: int(reference["leverage_source"].eq(s).sum()) for s in LEVERAGE_SOURCES
        },
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
        "figi_review": figi_review_rows(reference),
        "events": {
            "reference_change": changes["change"].value_counts().to_dict(),
            "index_change": index["change"].value_counts().to_dict(),
            "reference_change_duplicates_dropped": duplicates,
        },
    })  # fmt: skip
    if unmatched:
        run.partial(f"{len(unmatched)} S&P 500 members not listed")
