"""Option chain snapshots for one session: option quotes, underlying quotes and fetch status;
the stale chains the chains acceptance check tolerated (``tolerated_stale``, ADR 0054); and the
live quotes the API recorded for a session (``live/option_quotes``, ADR 0028).

Option quote rows are keyed by the contract (``instrument_id``) and carry their
``underlying_id``; ``option_quotes`` filters on the underlying, which is how consumers ask
("the chain of EQ:AAPL").
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime

import pandas as pd

from algotrade.config.site.settings import SourcesSettings
from algotrade.core.model.errors import MissingDataError
from algotrade.storage.tables.readers import StoreReader

OPTION_QUOTES = "chains/option_quotes"
UNDERLYING_QUOTES = "chains/underlying_quotes"
CHAIN_STATUS = "chains/status"
LIVE_OPTION_QUOTES = "live/option_quotes"

# Chain statuses (``tasks/market/option_chains``) by what they say about the night's fetch: a
# failed or missing fetch is a source problem; a stale chain is the feed serving an older session.
FETCH_FAILURES = ("FETCH_ERROR", "NOT_ATTEMPTED")  # FETCH_ERROR includes an open circuit
STALE = "STALE_DATA"
STALE_REASON = "stale chain (within the chains gate's tolerance)"


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


def chain_labels(status_frame: pd.DataFrame) -> pd.Series:
    """Each status row's label (``STALE_DATA``, ``OK``, ...: the text before any ``:``)."""
    return status_frame["status"].astype(str).str.split(":", n=1).str[0].str.strip()


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
    status_frame: pd.DataFrame | None, sources: SourcesSettings
) -> Mapping[str, str]:
    """The ``STALE_DATA`` underlyings (instrument id -> reason) of a chain status whose stale
    share the chains acceptance check tolerated: every tier within its limit
    (``max_chain_stale_share_core`` / ``max_chain_stale_share``), fetch failures within
    ``max_chain_fetch_failures``. Empty otherwise (fail closed: a chains run that failed its
    check excludes nobody). The same helpers as ``check_chains``, so gate and screens agree."""
    if status_frame is None or status_frame.empty:
        return {}
    labels = chain_labels(status_frame)
    if fetch_failure_share(labels) > sources.max_chain_fetch_failures:
        return {}
    core = stale_in_tier(status_frame, labels, "core")
    rest = stale_in_tier(status_frame, labels, "rest")
    if core.untiered_core or core.share > sources.max_chain_stale_share_core:
        return {}
    if rest.share > sources.max_chain_stale_share:
        return {}
    ids = status_frame.loc[core.stale | rest.stale, "instrument_id"].astype(str)
    return dict.fromkeys(ids, STALE_REASON)
