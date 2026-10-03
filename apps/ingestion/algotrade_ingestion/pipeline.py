"""The nightly pipeline: chains -> features -> screens -> exports, each step audited."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from algotrade.data import StoreReader
from algotrade.data.reference import load_universe
from algotrade.services.configs import scheduled
from algotrade.services.exports import run_exports
from algotrade.services.jobs import JobContext
from algotrade.services.screening import ScreenOutcome, run_screener
from algotrade.storage.config_store import ConfigStore
from algotrade.storage.runs import RunRecord
from algotrade.storage.writers import StoreWriter
from algotrade_ingestion.jobs.bars import ingest_corporate_actions, ingest_daily_bars
from algotrade_ingestion.jobs.company_details import CompanySources, ingest_company_details
from algotrade_ingestion.jobs.earnings import ingest_earnings
from algotrade_ingestion.jobs.features import compute_option_liquidity
from algotrade_ingestion.jobs.option_chains import (
    ChainJobConfig,
    Underlying,
    ingest_option_chains,
)
from algotrade_ingestion.jobs.quality import run_quality
from algotrade_ingestion.jobs.universe_build import (
    UniverseSettings,
    UniverseSources,
    build_universe,
)
from algotrade_ingestion.settings import SourcesSettings
from algotrade_ingestion.sources.base import Source


@dataclass(frozen=True)
class NightlyResult:
    universe: RunRecord | None
    company: RunRecord | None
    earnings: RunRecord | None
    bars: RunRecord | None
    actions: RunRecord | None
    quality: RunRecord | None
    chains: RunRecord
    features: RunRecord
    screens: tuple[ScreenOutcome, ...]
    exports: tuple[Path, ...]


def universe_underlyings(reader: StoreReader, session_date: date) -> list[Underlying]:
    """Option-chain coverage (a site rule, not a user choice): every active, optionable
    instrument in the universe. Strategies narrow this further with their selections."""
    frame = load_universe(reader, session_date).frame
    covered = frame[(frame["status"].str.upper() == "ACTIVE") & frame["optionable"].astype(bool)]
    return [Underlying(str(r.instrument_id), str(r.symbol)) for r in covered.itertuples()]


def universe_settings(configs: ConfigStore) -> tuple[str, UniverseSettings]:
    """``config/site/universe.toml`` -> (source, settings). Missing file: CSV import mode."""
    doc = configs.load("site", "settings", "universe")
    settings = UniverseSettings.from_documents(doc, configs.overrides("leveraged_etfs"))
    return str((doc or {}).get("source", "csv_import")), settings


def run_nightly(
    reader: StoreReader,
    writer: StoreWriter,
    source: Source,
    configs: ConfigStore,
    session_date: date,
    export_dir: Path | None = None,
    chain_config: ChainJobConfig | None = None,
    universe_sources: UniverseSources | None = None,
    earnings_source: Source | None = None,
    bars_source: Source | None = None,
    actions_source: Source | None = None,
    sources_settings: SourcesSettings | None = None,
    company_sources: CompanySources | None = None,
) -> NightlyResult:
    """universe -> company details -> earnings -> bars -> corporate actions -> chains ->
    rollups -> screens -> data-quality checks -> raw purge. Optional steps run only when
    their source is given."""
    s = sources_settings or SourcesSettings()
    universe = None
    mode, settings = universe_settings(configs)
    if mode == "nasdaq_trader" and universe_sources is not None:
        universe = build_universe(writer, reader, universe_sources, settings, session_date)
    company = None
    if company_sources is not None:
        company = ingest_company_details(writer, reader, company_sources, session_date)
    earnings = None
    if earnings_source is not None:
        earnings = ingest_earnings(
            writer, reader, earnings_source, session_date, days=s.earnings_days
        )
    bars = ingest_daily_bars(writer, reader, bars_source, [session_date]) if bars_source else None
    actions = None
    if actions_source is not None:
        window = (
            session_date + timedelta(s.actions_window[0]),
            session_date + timedelta(s.actions_window[1]),
        )
        actions = ingest_corporate_actions(writer, reader, actions_source, session_date, *window)
    chains = ingest_option_chains(
        writer, source, universe_underlyings(reader, session_date), session_date, chain_config
    )
    features = compute_option_liquidity(reader, writer, session_date)
    screens: list[ScreenOutcome] = []
    exports: list[Path] = []
    for config in scheduled(configs, "nightly"):
        if config.config.kind != "screener":
            continue
        outcome = run_screener(reader, writer, config, session_date)
        screens.append(outcome)
        if export_dir is not None:
            exports.extend(run_exports(outcome, config, export_dir))
    quality = run_quality(reader, writer, session_date, s)
    writer.raw.purge_before(session_date - timedelta(s.raw_retention_days))
    writer.staging.purge_before(session_date - timedelta(s.staging_retention_days))
    return NightlyResult(
        universe,
        company,
        earnings,
        bars,
        actions,
        quality,
        chains,
        features,
        tuple(screens),
        tuple(exports),
    )


def nightly_job(params: Mapping[str, Any], ctx: JobContext) -> Mapping[str, Any]:
    """Job handler for the whole nightly pipeline. params: ``session``, ``export_dir``,
    ``workers``. Resources: ``reader``, ``writer``, ``configs``, ``source``."""
    r = ctx.resources
    export_dir = Path(params["export_dir"]) if params.get("export_dir") else None
    result = run_nightly(
        r["reader"],
        r["writer"],
        r["source"],
        r["configs"],
        date.fromisoformat(params["session"]),
        export_dir,
        ChainJobConfig(int(params.get("workers", 4))),
        r.get("universe_sources"),
        r.get("earnings_source"),
        r.get("bars_source"),
        r.get("actions_source"),
        r.get("sources_settings"),
        r.get("company_sources"),
    )
    universe_partial = result.universe is not None and result.universe.status != "complete"
    optional = (result.company, result.earnings, result.bars, result.actions, result.quality)
    earnings_partial = any(r is not None and r.status != "complete" for r in optional)
    partial = (
        universe_partial
        or earnings_partial
        or result.chains.status != "complete"
        or any(s.audit["coverage"] != "COMPLETE" for s in result.screens)
    )
    return {
        "universe": result.universe.stats if result.universe else "skipped (csv_import)",
        "company_details": (
            result.company.stats if result.company else "skipped (disabled or no contact)"
        ),
        "earnings": result.earnings.stats if result.earnings else "skipped",
        "bars": result.bars.stats if result.bars else "skipped (no ALGOTRADE_MASSIVE_API_KEY)",
        "corporate_actions": result.actions.stats if result.actions else "skipped",
        "quality": result.quality.stats if result.quality else "skipped",
        "chains": result.chains.stats,
        "features": result.features.stats,
        "screens": [s.audit for s in result.screens],
        "exports": [str(e) for e in result.exports],
        "_partial": partial,
    }
