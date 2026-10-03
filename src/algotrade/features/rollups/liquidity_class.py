"""``liquidity_class@v1``: HIGH / MEDIUM / LOW / UNKNOWN liquidity, by explicit thresholds.

Inputs: ``price_stats@v1`` (``adv_usd_20d``, ``close``) and ``option_liquidity@v1``
(``put_tier``, ``call_tier``, ``chain_oi``, ``chain_volume``, ``liq_status``) for the session.
One row per instrument with a ``price_stats@v1`` row.

A class is met when every one of its thresholds is (``rollups.toml ["liquidity_class@v1"]``):

    <class>_min_adv_usd      20-session average dollar volume
    <class>_min_price        the session's close
    <class>_option_tiers     allowed option tiers (comma list, e.g. "A,B"); the WORSE of the
                             put and call tier must be one ("": no option requirement)
    <class>_min_chain_oi     chain open interest (0: no requirement)
    <class>_min_chain_volume chain volume (0: no requirement)

``liquidity_class`` is HIGH when HIGH is met, else MEDIUM when MEDIUM is met, else LOW. A
threshold that cannot be checked (a null ADV or close; no ``option_liquidity@v1`` for the
session; a chain whose fetch failed: STALE_DATA, FETCH_ERROR, NOT_ATTEMPTED) is UNKNOWN, and
UNKNOWN propagates: the class is UNKNOWN unless it is decided without that threshold (three-
valued logic, as in selections). An instrument the session's chain run did not list has no
options: option thresholds fail. ``rule_hash`` (12 hex characters of the SHA-256 of the
thresholds) records which definition produced the row.
"""

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import date

import numpy as np
import pandas as pd

from algotrade.features.framework.declaration import Input, Inputs, Rollup

NAME = "liquidity_class"
VERSION = 1
PRICE_STATS = "rollups/instrument/price_stats@v1"
OPTIONS = "rollups/instrument/option_liquidity@v1"
CLASSES = ("HIGH", "MEDIUM")
# Chain fetch outcomes that say what the options are; any other status is unknown.
KNOWN_CHAIN = frozenset({"OK", "NO_CHAIN", "NO_STANDARD_SERIES", "NO_TARGET_EXPIRY"})
TIER_ORDER = "ABCD"

COLUMNS: dict[str, str] = {
    "liquidity_class": "str",
    "adv_usd_20d": "float",
    "close": "float",
    "option_tier": "str",
    "chain_oi": "int",
    "rule_hash": "str",
}


@dataclass(frozen=True)
class LiquidityClassParams:
    high_min_adv_usd: float = 100e6
    high_min_price: float = 10.0
    high_option_tiers: str = "A"
    high_min_chain_oi: int = 50_000
    high_min_chain_volume: int = 5_000
    medium_min_adv_usd: float = 10e6
    medium_min_price: float = 5.0
    medium_option_tiers: str = "A,B"
    medium_min_chain_oi: int = 5_000
    medium_min_chain_volume: int = 0

    def __post_init__(self) -> None:
        for cls in ("high", "medium"):
            bad = set(self.tiers(cls)) - set(TIER_ORDER)
            if bad:
                raise ValueError(f"{cls}_option_tiers: unknown tiers {sorted(bad)}")
        if self.high_min_adv_usd < self.medium_min_adv_usd:
            raise ValueError("high_min_adv_usd must be >= medium_min_adv_usd")

    def tiers(self, cls: str) -> list[str]:
        raw: str = getattr(self, f"{cls}_option_tiers")
        return [t.strip().upper() for t in raw.split(",") if t.strip()]

    @property
    def rule_hash(self) -> str:
        text = json.dumps(asdict(self), sort_keys=True)
        return hashlib.sha256(text.encode()).hexdigest()[:12]


def _and(*terms: np.ndarray) -> np.ndarray:
    """Three-valued AND over float arrays (1 true, 0 false, NaN unknown)."""
    stacked = np.vstack(terms)
    false = (stacked == 0).any(axis=0)
    unknown = np.isnan(stacked).any(axis=0)
    return np.where(false, 0.0, np.where(unknown, np.nan, 1.0))


def _at_least(values: np.ndarray, minimum: float) -> np.ndarray:
    if minimum <= 0:
        return np.ones(len(values))
    return np.where(np.isnan(values), np.nan, (values >= minimum).astype(float))


def classify(frame: pd.DataFrame, p: LiquidityClassParams) -> np.ndarray:
    """``liquidity_class`` for rows carrying ``adv_usd_20d``, ``close``, ``option_tier``
    (None: unknown, "D": no usable options), ``chain_oi`` and ``chain_volume`` (NaN: unknown)."""
    tier = frame["option_tier"]
    known_tier = tier.notna().to_numpy()
    met = {}
    for cls in ("high", "medium"):
        allowed = p.tiers(cls)
        tier_ok = (
            np.ones(len(frame))
            if not allowed
            else np.where(known_tier, tier.isin(allowed).to_numpy().astype(float), np.nan)
        )
        met[cls] = _and(
            _at_least(frame["adv_usd_20d"].to_numpy(dtype=float), getattr(p, f"{cls}_min_adv_usd")),
            _at_least(frame["close"].to_numpy(dtype=float), getattr(p, f"{cls}_min_price")),
            tier_ok,
            _at_least(frame["chain_oi"].to_numpy(dtype=float), getattr(p, f"{cls}_min_chain_oi")),
            _at_least(
                frame["chain_volume"].to_numpy(dtype=float), getattr(p, f"{cls}_min_chain_volume")
            ),
        )
    high, medium = met["high"], met["medium"]
    return np.select(
        [high == 1, np.isnan(high), medium == 1, np.isnan(medium)],
        ["HIGH", "UNKNOWN", "MEDIUM", "UNKNOWN"],
        "LOW",
    )


def _options(rows: pd.DataFrame | None, session: date, ids: list[str]) -> pd.DataFrame:
    """``option_tier`` (worse of put / call), ``chain_oi``, ``chain_volume`` per instrument;
    unknown (None / NaN) without the session's rollup or after a failed fetch."""
    unknown = pd.DataFrame(
        {"option_tier": None, "chain_oi": np.nan, "chain_volume": np.nan}, index=ids
    )
    if rows is None:
        return unknown
    today = rows[rows["session_date"] == session].set_index("instrument_id")
    known = today[today["liq_status"].astype(str).isin(KNOWN_CHAIN)]
    worse = [
        max(str(a) if pd.notna(a) else "D", str(b) if pd.notna(b) else "D", key=TIER_ORDER.index)
        for a, b in zip(known["put_tier"], known["call_tier"], strict=True)
    ]
    out = pd.DataFrame(
        {
            "option_tier": worse,
            "chain_oi": known["chain_oi"].astype(float).fillna(0.0).to_numpy(),
            "chain_volume": known["chain_volume"].astype(float).fillna(0.0).to_numpy(),
        },
        index=known.index.astype(str),
    )
    unlisted = [i for i in ids if i not in today.index]  # no chain: no options
    none = pd.DataFrame({"option_tier": "D", "chain_oi": 0.0, "chain_volume": 0.0}, index=unlisted)
    return pd.concat([out, none]).reindex(ids)


def compute(inputs: Inputs, session: date, p: LiquidityClassParams) -> pd.DataFrame:
    stats = inputs[PRICE_STATS]
    assert stats is not None  # required input
    today = stats[stats["session_date"] == session]
    ids = list(today["instrument_id"].astype(str))
    frame = today.set_index(today["instrument_id"].astype(str))[["adv_usd_20d", "close"]]
    frame = frame.join(_options(inputs.get(OPTIONS), session, ids))
    frame["liquidity_class"] = classify(frame, p)
    frame["rule_hash"] = p.rule_hash
    return frame.rename_axis("instrument_id").reset_index()[["instrument_id", *COLUMNS]]


ROLLUP = Rollup(
    NAME,
    VERSION,
    "HIGH / MEDIUM / LOW liquidity from dollar volume, price and option liquidity thresholds",
    (Input(PRICE_STATS), Input(OPTIONS, required=False)),
    COLUMNS,
    compute,
    LiquidityClassParams(),
)
