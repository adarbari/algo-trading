"""The nightly pipeline: chains -> features -> screens -> exports, each step audited."""

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from algotrade.services.exports import write_legacy_exports
from algotrade.services.screening import ScreenOutcome, run_screener
from algotrade.services.views import load_universe
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

NIGHTLY_SCREENERS = ("short_premium_liquidity",)


@dataclass(frozen=True)
class NightlyResult:
    chains: RunRecord
    features: RunRecord
    screens: tuple[ScreenOutcome, ...]
    exports: tuple[Path, ...]


def universe_underlyings(reader: StoreReader, session_date: date) -> list[Underlying]:
    frame = load_universe(reader, session_date).frame
    return [Underlying(str(r.instrument_id), str(r.symbol)) for r in frame.itertuples()]


def run_nightly(
    reader: StoreReader,
    writer: StoreWriter,
    source: Source,
    session_date: date,
    export_dir: Path | None = None,
    config: ChainJobConfig | None = None,
) -> NightlyResult:
    chains = ingest_option_chains(
        writer, source, universe_underlyings(reader, session_date), session_date, config
    )
    features = compute_option_liquidity(reader, writer, session_date)
    screens = tuple(run_screener(reader, writer, name, session_date) for name in NIGHTLY_SCREENERS)
    exports: tuple[Path, ...] = ()
    if export_dir is not None:
        liquidity = screens[0]
        exports = write_legacy_exports(liquidity, export_dir, session_date.isoformat())
    return NightlyResult(chains, features, screens, exports)
