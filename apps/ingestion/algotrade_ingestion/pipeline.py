"""The nightly pipeline: chains -> features -> screens -> exports, each step audited."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from algotrade.services.configs import scheduled
from algotrade.services.exports import run_exports
from algotrade.services.jobs import JobContext
from algotrade.services.screening import ScreenOutcome, run_screener
from algotrade.services.views import load_universe
from algotrade.storage.config_store import ConfigStore
from algotrade.storage.readers import StoreReader
from algotrade.storage.runs import RunRecord
from algotrade.storage.writers import StoreWriter
from algotrade_ingestion.jobs.features import compute_option_liquidity
from algotrade_ingestion.jobs.option_chains import (
    ChainJobConfig,
    Underlying,
    ingest_option_chains,
)
from algotrade_ingestion.jobs.universe_build import (
    UniverseSettings,
    UniverseSources,
    build_universe,
)
from algotrade_ingestion.sources.base import Source


@dataclass(frozen=True)
class NightlyResult:
    universe: RunRecord | None
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
) -> NightlyResult:
    universe = None
    mode, settings = universe_settings(configs)
    if mode == "nasdaq_trader" and universe_sources is not None:
        universe = build_universe(writer, reader, universe_sources, settings, session_date)
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
    return NightlyResult(universe, chains, features, tuple(screens), tuple(exports))


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
    )
    universe_partial = result.universe is not None and result.universe.status != "complete"
    partial = (
        universe_partial
        or result.chains.status != "complete"
        or any(s.audit["coverage"] != "COMPLETE" for s in result.screens)
    )
    return {
        "universe": result.universe.stats if result.universe else "skipped (csv_import)",
        "chains": result.chains.stats,
        "features": result.features.stats,
        "screens": [s.audit for s in result.screens],
        "exports": [str(e) for e in result.exports],
        "_partial": partial,
    }
