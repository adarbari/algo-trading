"""Instrument tiers: which underlyings are "core" (important) and which are "rest".

One rule shared by the chain fetch order (``option_chains.prioritise``) and the chain
acceptance check (``maintenance.quality.check_chains``, graded on the tier stored with each
status row at fetch time): core is the S&P 500 members, the configured ``[cboe]
priority_symbols`` and the names whose latest ``feature.liquidity_class`` is HIGH; everything
else is rest (ADR 0043).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd

from algotrade.core.model.fields import REFERENCE_TABLE
from algotrade.data import StoreReader
from algotrade.data.reference import snapshot
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
    reference_date: date | None = None  # the reference snapshot the members came from
    liquidity_date: date | None = None  # the price_stats session the liquidity came from

    def sources(self) -> dict[str, str | None]:
        """The snapshot dates used (for the run record)."""
        return {
            "reference": self.reference_date.isoformat() if self.reference_date else None,
            "liquidity": self.liquidity_date.isoformat() if self.liquidity_date else None,
        }

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
    members, reference_date = _sp500(reader, session_date)
    liquidity, liquidity_date = _liquidity(reader, session_date, site_features(site_store(configs)))
    return Tiers(pinned, members, liquidity, reference_date, liquidity_date)


def _sp500(reader: StoreReader, session_date: date) -> tuple[set[str], date | None]:
    """Instrument ids in the S&P 500 per the reference snapshot on or before ``session_date``
    (never a later one: a backfill must not tier on future membership), and its date. Empty
    when there is none."""
    snap = snapshot(reader, REFERENCE_TABLE, session_date)
    if snap is None or snap.pre_snapshot:
        return set(), None
    frame = reader.table(REFERENCE_TABLE, snap.snapshot_date)
    if frame is None or "in_sp500" not in frame.columns:
        return set(), snap.snapshot_date
    members = frame[frame["in_sp500"].fillna(False).astype(bool)]
    return set(members["instrument_id"].astype(str)), snap.snapshot_date


def _liquidity(
    reader: StoreReader, session_date: date, features: FeatureSet
) -> tuple[dict[str, tuple[int, float]], date | None]:
    """instrument id -> (class rank, -chain OI) from the expression features
    ``liquidity_class`` and ``option_chain_oi`` on the latest session strictly before
    ``session_date`` with ``price_stats`` rows (the session's own rollups, which exist once
    chains are re-run later, would make the tier circular and change it run to run), and
    that session. Instruments with neither are left out."""
    snap = snapshot(reader, features.table(PRICE_GROUP), session_date - timedelta(days=1))
    if snap is None or snap.pre_snapshot:
        return {}, None
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
    return out, snap.snapshot_date
