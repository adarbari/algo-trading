"""The nightly pipeline: chains -> features -> screens -> exports, each step audited."""

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from algotrade.config.resolve import ResolvedConfig
from algotrade.config.user import SITE_USER
from algotrade.services.configs import scheduled
from algotrade.services.exports import EXPORTS
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
from algotrade_ingestion.sources.base import Source


@dataclass(frozen=True)
class NightlyResult:
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


def run_exports(
    outcome: ScreenOutcome, config: ResolvedConfig, export_dir: Path
) -> tuple[Path, ...]:
    """The config's declared exports; site runs at the top level, users in a subfolder."""
    user = config.user.user_id
    target = export_dir if user == SITE_USER else export_dir / user
    paths: list[Path] = []
    for name in config.config.exports:
        paths.extend(EXPORTS[name](outcome, target, outcome.session_date.isoformat()))
    return tuple(paths)


def run_nightly(
    reader: StoreReader,
    writer: StoreWriter,
    source: Source,
    configs: ConfigStore,
    session_date: date,
    export_dir: Path | None = None,
    chain_config: ChainJobConfig | None = None,
) -> NightlyResult:
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
    return NightlyResult(chains, features, tuple(screens), tuple(exports))
