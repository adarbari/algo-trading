"""Option chain snapshots for one session: option quotes, underlying quotes and fetch status.

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


def option_quotes(
    reader: StoreReader,
    session: date,
    underlying_ids: Sequence[str] | None = None,
    as_of: datetime | None = None,
) -> pd.DataFrame | None:
    """Option quotes for ``session``, limited to the chains of ``underlying_ids``."""
    frame = reader.table(OPTION_QUOTES, session, as_of)
    if frame is None or underlying_ids is None:
        return frame
    wanted = frame["underlying_id"].astype(str).isin(list(underlying_ids))
    return frame[wanted].reset_index(drop=True)


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
