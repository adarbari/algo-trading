"""Option chain snapshots for one session: option quotes, underlying quotes and fetch status;
the stale chains the chains acceptance check tolerated (``tolerated_stale``, ADR 0054); and the
live quotes the API recorded for a session (``live/option_quotes``, ADR 0028).

Option quote rows are keyed by the contract (``instrument_id``) and carry their
``underlying_id``; ``option_quotes`` filters on the underlying, which is how consumers ask
("the chain of EQ:AAPL").
"""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime

import pandas as pd

from algotrade.config.site.settings import SourcesSettings
from algotrade.core.model.errors import MissingDataError
from algotrade.core.time.calendar import sessions_to
from algotrade.storage.tables.readers import StoreReader

OPTION_QUOTES = "chains/option_quotes"
UNDERLYING_QUOTES = "chains/underlying_quotes"
CHAIN_STATUS = "chains/status"
LIVE_OPTION_QUOTES = "live/option_quotes"

# Chain statuses (``tasks/market/option_chains``) by what they say about the night's fetch: a
# failed or missing fetch is a source problem; a stale chain is the feed serving an older session.
# A chain stale for more than ``max_chain_stale_sessions`` is labelled CHRONIC (never stored): the
# feed is not late for the name, it has stopped serving it, which is a fetch failure.
STALE = "STALE_DATA"
CHRONIC = "STALE_CHRONIC"
FETCH_FAILURES = ("FETCH_ERROR", "NOT_ATTEMPTED", CHRONIC)  # FETCH_ERROR includes an open circuit
_CHAIN_DAY = re.compile(r"chain is for (\d{4}-\d{2}-\d{2})")  # option_chains' STALE_DATA text


def option_quotes(
    reader: StoreReader,
    session: date,
    underlying_ids: Sequence[str] | None = None,
    as_of: datetime | None = None,
) -> pd.DataFrame | None:
    """Option quotes for ``session``, limited to the chains of ``underlying_ids``."""
    return _of_underlyings(reader.table(OPTION_QUOTES, session, as_of), underlying_ids)


def _of_underlyings(
    frame: pd.DataFrame | None, underlying_ids: Sequence[str] | None
) -> pd.DataFrame | None:
    if frame is None or underlying_ids is None:
        return frame
    wanted = frame["underlying_id"].astype(str).isin(list(underlying_ids))
    return frame[wanted].reset_index(drop=True)


def chain_expiries(
    reader: StoreReader,
    session: date,
    underlying_ids: Sequence[str],
    as_of: datetime | None = None,
) -> dict[str, list[date]]:
    """Distinct listed expiries (sorted) per underlying in ``session``'s stored chains, in one
    column-pruned read; an underlying without a stored chain is absent."""
    frame = reader.table_range(
        OPTION_QUOTES, session, session, as_of, columns=["underlying_id", "expiry"]
    )
    if frame is None or frame.empty:
        return {}
    frame = frame[frame["underlying_id"].astype(str).isin(list(underlying_ids))]
    expiry = pd.to_datetime(frame["expiry"]).dt.date
    found = pd.DataFrame({"u": frame["underlying_id"].astype(str), "e": expiry}).drop_duplicates()
    return {str(u): sorted(g["e"]) for u, g in found.groupby("u")}


def underlying_quotes(
    reader: StoreReader,
    session: date,
    underlying_ids: Sequence[str] | None = None,
    as_of: datetime | None = None,
) -> pd.DataFrame | None:
    """The underlying's quote captured with each chain (keyed by the underlying's id)."""
    return reader.table(UNDERLYING_QUOTES, session, as_of, underlying_ids)


def chain_status(
    reader: StoreReader,
    session: date,
    underlying_ids: Sequence[str] | None = None,
    as_of: datetime | None = None,
    hint: str | None = None,
) -> pd.DataFrame | None:
    """Per-underlying fetch status (``OK``, ``NO_STANDARD_SERIES``, errors).

    With a ``hint``, a missing partition raises ``MissingDataError`` instead of ``None``."""
    frame = reader.table(CHAIN_STATUS, session, as_of, underlying_ids)
    if frame is None and hint is not None:
        raise MissingDataError(CHAIN_STATUS, f"no chain status for {session}", hint)
    return frame


def live_option_quotes(
    reader: StoreReader,
    session: date,
    underlying_ids: Sequence[str] | None = None,
    as_of: datetime | None = None,
) -> pd.DataFrame | None:
    """The live quotes the API took during ``session`` (every snapshot: one row per contract
    and ``ts``), limited to the chains of ``underlying_ids``. Personal-use licence (IBKR)."""
    return _of_underlyings(reader.table(LIVE_OPTION_QUOTES, session, as_of), underlying_ids)


def chain_labels(status_frame: pd.DataFrame, session: date, max_stale_sessions: int) -> pd.Series:
    """Each status row's label (``STALE_DATA``, ``OK``, ...: the text before any ``:``), with a
    ``STALE_DATA`` chain for a day more than ``max_stale_sessions`` sessions before ``session``
    labelled ``CHRONIC`` (a fetch failure). A stale status without a day keeps its label."""
    status = status_frame["status"].astype(str)
    labels = status.str.split(":", n=1).str[0].str.strip()
    days = status.str.extract(_CHAIN_DAY, expand=False).where(labels == STALE)
    ages = {d: sessions_to(date.fromisoformat(d), session) for d in days.dropna().unique()}
    return labels.mask(days.map(ages).fillna(0) > max_stale_sessions, CHRONIC)


def fetch_failure_share(labels: pd.Series) -> float:
    """The share of statuses that are a failed or missing fetch (``FETCH_FAILURES``)."""
    return float(labels.isin(FETCH_FAILURES).sum()) / len(labels) if len(labels) else 0.0


@dataclass(frozen=True)
class TierStale:
    """The stale chains of one tier (``core`` or ``rest``) of a chain status."""

    tier: str
    total: int  # chains in the tier
    stale: pd.Series  # boolean mask over the status frame: in the tier and STALE_DATA
    untiered_core: bool = False  # a tiered status with no core name: the tier inputs were missing

    @property
    def count(self) -> int:
        return int(self.stale.sum())

    @property
    def share(self) -> float:
        return self.count / self.total if self.total else 0.0


def stale_in_tier(frame: pd.DataFrame, labels: pd.Series, tier: str) -> TierStale:
    """The tier's stale chains. The tier is the one stored with each status row at fetch time
    (rows from before the column existed count as rest). The one share the chains acceptance
    check grades and ``tolerated_stale`` reads."""
    stored = frame["tier"] if "tier" in frame.columns else pd.Series("rest", index=frame.index)
    in_tier = stored.fillna("rest").astype(str) == tier
    total = int(in_tier.sum())
    untiered = tier == "core" and total == 0 and "tier" in frame.columns
    return TierStale(tier, total, in_tier & (labels == STALE), untiered)


def tolerated_stale(
    status_frame: pd.DataFrame | None, session: date, sources: SourcesSettings
) -> Mapping[str, str]:
    """The ``STALE_DATA`` underlyings of ``session``'s chain status whose stale share the chains
    acceptance check tolerated, as instrument id -> its stored status text (the exclusion
    reason, e.g. ``STALE_DATA: chain is for 2026-10-05``): every tier within its limit
    (``max_chain_stale_share_core`` / ``max_chain_stale_share``), fetch failures (chronically
    stale chains included, ``max_chain_stale_sessions``) within ``max_chain_fetch_failures``.
    Empty otherwise (fail closed: a chains run that failed its check excludes nobody); a
    chronically stale chain is never excluded. The same helpers as ``check_chains``, so gate and
    screens agree."""
    if status_frame is None or status_frame.empty:
        return {}
    labels = chain_labels(status_frame, session, sources.max_chain_stale_sessions)
    if fetch_failure_share(labels) > sources.max_chain_fetch_failures:
        return {}
    core = stale_in_tier(status_frame, labels, "core")
    rest = stale_in_tier(status_frame, labels, "rest")
    if core.untiered_core or core.share > sources.max_chain_stale_share_core:
        return {}
    if rest.share > sources.max_chain_stale_share:
        return {}
    stale = status_frame.loc[core.stale | rest.stale]
    return dict(zip(stale["instrument_id"].astype(str), stale["status"].astype(str), strict=True))
