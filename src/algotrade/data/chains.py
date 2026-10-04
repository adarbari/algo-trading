"""Option chain snapshots for one session: option quotes, underlying quotes and fetch status;
and the live quotes the API recorded for a session (``live/option_quotes``, ADR 0028).

Option quote rows are keyed by the contract (``instrument_id``) and carry their
``underlying_id``; ``option_quotes`` filters on the underlying, which is how consumers ask
("the chain of EQ:AAPL").
"""

from collections.abc import Sequence
from datetime import date, datetime

import pandas as pd

from algotrade.core.model.errors import MissingDataError
from algotrade.storage.tables.readers import StoreReader

OPTION_QUOTES = "chains/option_quotes"
UNDERLYING_QUOTES = "chains/underlying_quotes"
CHAIN_STATUS = "chains/status"
LIVE_OPTION_QUOTES = "live/option_quotes"


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
