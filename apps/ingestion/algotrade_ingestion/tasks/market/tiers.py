"""Instrument tiers: which underlyings are "core" (important) and which are "rest".

One rule shared by the chain fetch order (``option_chains.prioritise``) and the chain
acceptance check (``maintenance.quality.check_chains``, graded on the tier stored with each
status row at fetch time): core is the S&P 500 members, the configured ``[cboe]
priority_symbols`` and the names whose latest ``feature.liquidity_class`` is HIGH; everything
else is rest (ADR 0043).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

import pandas as pd

from algotrade.core.model.errors import MissingDataError
from algotrade.data import StoreReader
from algotrade.data.reference import instruments, snapshot
from algotrade.features.expressions.feature_set import FeatureSet
from algotrade.services.features import read_expressions, site_features, site_store
from algotrade.storage.configs.store import ConfigStore

# Expression features (config/site/features/liquidity.toml), read through services.features
LIQUIDITY_CLASS, CHAIN_OI = "liquidity_class", "option_chain_oi"
PRICE_GROUP = "price_stats"  # the class is computed for the latest session this group has
CLASS_RANK = {"HIGH": 0, "MEDIUM": 1, "LOW": 2, "UNKNOWN": 3}
CORE, REST = "core", "rest"


@dataclass(frozen=True)
class Tiers:
    """The inputs of the tier rule for one session."""

    pinned: dict[str, int]  # upper-case priority symbol -> its position
    members: set[str]  # S&P 500 instrument ids
    liquidity: dict[str, tuple[int, float]]  # instrument id -> (class rank, -chain OI)

    def tier(self, instrument_id: str, symbol: str) -> str:
        """``CORE`` or ``REST`` for one instrument."""
        high = self.liquidity.get(instrument_id, (CLASS_RANK["UNKNOWN"], 0.0))[0]
        core = (
            symbol.upper() in self.pinned
            or instrument_id in self.members
            or high == CLASS_RANK["HIGH"]
        )
        return CORE if core else REST


def load_tiers(
    reader: StoreReader,
    session_date: date,
    priority_symbols: Sequence[str] = (),
    configs: ConfigStore | None = None,
) -> Tiers:
    """The tier inputs for ``session_date`` (an empty store: only the pinned symbols are core)."""
    pinned = {s.upper(): n for n, s in enumerate(dict.fromkeys(priority_symbols))}
    return Tiers(
        pinned,
        _sp500(reader, session_date),
        _liquidity(reader, session_date, site_features(site_store(configs))),
    )


def _sp500(reader: StoreReader, session_date: date) -> set[str]:
    """Instrument ids in the S&P 500 per the reference snapshot (none when there is none)."""
    try:
        frame = instruments(reader, session_date)
    except MissingDataError:
        return set()
    if "in_sp500" not in frame.columns:
        return set()
    members = frame[frame["in_sp500"].fillna(False).astype(bool)]
    return set(members["instrument_id"].astype(str))


def _liquidity(
    reader: StoreReader, session_date: date, features: FeatureSet
) -> dict[str, tuple[int, float]]:
    """instrument id -> (class rank, -chain OI) from the expression features
    ``liquidity_class`` and ``option_chain_oi`` on the latest session on or before
    ``session_date`` with ``price_stats`` rows (chains are fetched before the session's
    rollups, so usually the previous session). Instruments with neither are left out."""
    snap = snapshot(reader, features.table(PRICE_GROUP), session_date)
    if snap is None or snap.pre_snapshot:
        return {}
    frame = read_expressions(
        reader, [LIQUIDITY_CLASS, CHAIN_OI], snap.snapshot_date, features=features
    ).frame
    unknown = CLASS_RANK["UNKNOWN"]
    out: dict[str, tuple[int, float]] = {}
    for row in frame.itertuples(index=False):
        label, oi = getattr(row, LIQUIDITY_CLASS), getattr(row, CHAIN_OI)
        has_label, has_oi = isinstance(label, str), not pd.isna(oi)
        if has_label or has_oi:
            rank = CLASS_RANK.get(label.upper(), unknown) if has_label else unknown
            out[str(row.instrument_id)] = (rank, -float(oi) if has_oi else 0.0)
    return out
