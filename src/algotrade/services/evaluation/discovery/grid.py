"""The session grid and the names eligible at each (ED6 winners study, definition 1).

A grid session S is every ``step_sessions`` from the first session with ``min_history_sessions``
of bars, while the window that starts at S (``horizon_sessions``) closes before ``frozen_from``
(S before ``training.frame.purge_cutoff``). Each S belongs to a block of ``block_sessions``
sessions from the first S: the blocks are what the study counts (not strictly independent:
a block's last windows overlap the next block's).

The eligible at S are the stocks of ``universe_asof(S)`` (survivors and the delisted alike; its
membership identity read, never a feature) with a bar at S, a close of at least ``min_price`` and a
20-session dollar volume of at least ``min_adv_usd_20d``, both read from the rollup partition of
S only. A grid session whose rollup partition is missing is ``MissingDataError`` (ADR 0008).
"""

from dataclasses import dataclass
from datetime import date

import pandas as pd

from algotrade.config.edges.winners import WinnersStudySettings
from algotrade.core.model.errors import MissingDataError
from algotrade.core.time.calendar import sessions_between
from algotrade.data import StoreReader
from algotrade.data.feature_inputs import first_stored_session
from algotrade.data.listings.universe import universe_asof
from algotrade.features.expressions.feature_set import FeatureSet
from algotrade.services.evaluation.training.frame import purge_cutoff
from algotrade.services.features import entity_field_view

BARS = "bars/1d"
PRICE_GROUP = "price_stats"
STOCK = "STOCK"
DAYS_PER_YEAR = 365.25
HINT = "run `algotrade-ingest run rollups --from ... --to ...` for the session"


@dataclass(frozen=True)
class GridSession:
    session: date
    block: int  # 0-based, of ``block_sessions`` sessions from the first grid session


def first_bar_session(reader: StoreReader) -> date:
    """The first session with a stored bar partition; ``MissingDataError`` when there is none."""
    first = first_stored_session(reader, BARS)
    if first is None:
        raise MissingDataError(BARS, "no bars stored", "run `algotrade-ingest run bars-history`")
    return first


def grid_sessions(first_bar: date, settings: WinnersStudySettings) -> list[GridSession]:
    """The grid sessions, ascending: every ``step_sessions`` from the ``min_history_sessions``-th
    session after ``first_bar``, each one before the purge cutoff of ``frozen_from`` (so its
    window closes before the frozen period)."""
    cutoff = purge_cutoff(settings.frozen_from, settings.horizon_sessions)
    days = sessions_between(first_bar, cutoff)
    out: list[GridSession] = []
    for offset in range(0, len(days), settings.step_sessions):
        at = settings.min_history_sessions + offset
        if at >= len(days) or days[at] >= cutoff:
            break
        out.append(GridSession(days[at], offset // settings.block_sessions))
    return out


def price_fields(features: FeatureSet) -> tuple[str, str]:
    """The selection fields of the close and the 20-session dollar volume (``price_stats``)."""
    found = {
        f.name: f.field
        for f in features.features.values()
        if f.group.startswith(f"{PRICE_GROUP}@") and f.name in ("close", "adv_usd_20d")
    }
    if len(found) != 2:
        raise MissingDataError("price_stats", "close or adv_usd_20d is not in the catalogue", "")
    return found["close"], found["adv_usd_20d"]


def pick_eligible(
    listings: pd.DataFrame, prices: pd.DataFrame, session: date, settings: WinnersStudySettings
) -> pd.DataFrame:
    """The eligible at ``session``: ``listings`` (``instrument_id``, ``asset_type``,
    ``start_date``) the stocks among them, joined to ``prices`` (``instrument_id``, ``close``,
    ``adv``; NaN is UNKNOWN: no bar), with a close and dollar volume at the floors. Columns
    ``instrument_id``, ``adv``, ``age_years`` (from the listing's start date); sorted by id."""
    stocks = listings[listings["asset_type"].astype(str).str.upper() == STOCK]
    stocks = stocks.drop_duplicates("instrument_id")
    joined = stocks.merge(prices, on="instrument_id", how="inner")
    close = pd.to_numeric(joined["close"], errors="coerce")
    adv = pd.to_numeric(joined["adv"], errors="coerce")
    kept = joined[(close >= settings.min_price) & (adv >= settings.min_adv_usd_20d)]
    age = (pd.Timestamp(session) - pd.to_datetime(kept["start_date"])).dt.days / DAYS_PER_YEAR
    out = pd.DataFrame(
        {
            "instrument_id": kept["instrument_id"].astype(str).to_numpy(),
            "adv": pd.to_numeric(kept["adv"]).to_numpy(dtype=float),
            "age_years": age.to_numpy(dtype=float),
        }
    )
    return out.sort_values("instrument_id", kind="stable").reset_index(drop=True)


def read_eligible(
    reader: StoreReader, session: date, settings: WinnersStudySettings, features: FeatureSet
) -> pd.DataFrame:
    """``pick_eligible`` over the stored universe and the rollup partition of ``session``;
    ``MissingDataError`` when the session has no ``price_stats`` partition."""
    listed = universe_asof(reader, session).instruments
    close, adv = price_fields(features)
    ids = sorted(listed["instrument_id"].astype(str).unique())
    frame, missing = entity_field_view(reader, session, [close, adv], ids, features=features)
    if missing:
        raise MissingDataError(missing[0], f"no partition for the grid session {session}", HINT)
    prices = frame.rename(columns={close: "close", adv: "adv"})[["instrument_id", "close", "adv"]]
    return pick_eligible(listed, prices, session, settings)
