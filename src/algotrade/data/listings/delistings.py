"""``read_delistings``: why and how each name left the market, the snapshot written on or before
a session (ADR 0087 decisions 4 and 5).

``events/delisting`` is a FULL snapshot per run session (every delisted instrument each run), so
a reason that changes when filings arrive is a new snapshot. The read takes the latest snapshot
**on or before** ``as_of_write`` (None: the latest) and says which, ADR 0036's rule for snapshot
tables; a later snapshot never stands in (it would carry what was learned after). ``as_of`` pins
what was stored by an instant (``knowledge_ts``), so a replay before a write does not see it. The
table is quarantined like the outcomes: only this module reads it, and only the writer, the
outcomes task (PR6a) and ``services/evaluation`` (PR6b) import this module (AST scan in
``tests/architecture/data/test_listing_end_date_readers.py``).

Two point-in-time uses, which differ on purpose (ADR 0087 decision 4):

- a **feature** reads a delisting only when ``known_from <= S``: ``known_by(frame, S)``;
- the **outcome label** reads the delistings with a last session in (S, T] whatever their
  ``known_from`` (0053's one exception to the one-session rule): the frame as read, as stored when
  the row was written (``knowledge_ts`` is the write time, never the delisting day).

This module also owns the vocabulary of the table (``REASONS``, ``BASES``) and the return a
basis stands for when no OTC price exists (``CONVENTION``): the replacement returns are the
owner's decision of 2026-11-01, after Shumway (1997) and Shumway and Warther (1999), who find the
missing delisting returns of performance-related NASDAQ delistings average about -55% and of
NYSE / AMEX ones about -30%; the zero return of every other basis is shown beside the verdict
(PR6), never hidden.
"""

from datetime import date, datetime

import pandas as pd

from algotrade.core.model.errors import MissingDataError
from algotrade.storage.tables.readers import StoreReader

TABLE = "events/delisting"
HINT = "algotrade-ingest run delistings"

ACQUIRED, BANKRUPTCY, STANDARDS, VOLUNTARY, UNKNOWN = (
    "ACQUIRED",
    "BANKRUPTCY",
    "STANDARDS",
    "VOLUNTARY",
    "UNKNOWN",
)
REASONS = (ACQUIRED, BANKRUPTCY, STANDARDS, VOLUNTARY, UNKNOWN)

OTC_CLOSE, ZERO_ACQUIRED, REPLACEMENT, ZERO_UNKNOWN = (
    "OTC_CLOSE",
    "ZERO_ACQUIRED",
    "REPLACEMENT",
    "ZERO_UNKNOWN",
)
BASES = (OTC_CLOSE, ZERO_ACQUIRED, REPLACEMENT, ZERO_UNKNOWN)

NASDAQ = "NASDAQ"
REPLACEMENT_NASDAQ = -0.55  # Shumway and Warther (1999): a performance delisting on NASDAQ
REPLACEMENT_OTHER = -0.30  # Shumway (1997): NYSE / AMEX (and any other final exchange)
OTC_SESSIONS = 10  # the first OTC close within this many sessions after the last bar (CRSP)


def convention(reason: str, exchange: str | None) -> tuple[str, float]:
    """The ``(terminal_basis, delisting_return)`` of a delisting with no OTC price: ACQUIRED counts
    as 0; BANKRUPTCY and STANDARDS take the replacement return of the final exchange; any other
    reason is 0, counted as ``ZERO_UNKNOWN``."""
    if reason == ACQUIRED:
        return ZERO_ACQUIRED, 0.0
    if reason in (BANKRUPTCY, STANDARDS):
        return REPLACEMENT, REPLACEMENT_NASDAQ if exchange == NASDAQ else REPLACEMENT_OTHER
    return ZERO_UNKNOWN, 0.0


def read_delistings(
    reader: StoreReader, as_of_write: date | None = None, as_of: datetime | None = None
) -> tuple[pd.DataFrame, date]:
    """Every row of the latest ``events/delisting`` snapshot written on or before ``as_of_write``
    (None: the latest) and that snapshot's date; ``MissingDataError`` with none. ``as_of`` (a UTC
    instant) pins what was STORED then (``knowledge_ts <= as_of``): a replay before a write does
    not see it, and a snapshot with nothing known by then is skipped for the one before."""
    days = [d for d in reader.dates(TABLE) if as_of_write is None or d <= as_of_write]
    for day in reversed(days):
        frame = reader.table(TABLE, day, as_of)
        if frame is not None and not frame.empty:
            return frame, day
    when = f" on or before {as_of_write}" if as_of_write else ""
    known = f" known at {as_of}" if as_of else ""
    raise MissingDataError(TABLE, f"no snapshot stored{when}{known}", HINT)


def known_by(frame: pd.DataFrame, session: date) -> pd.DataFrame:
    """The delistings a feature may read on ``session``: ``known_from <= session``."""
    return frame[pd.to_datetime(frame["known_from"]) <= pd.Timestamp(session)]
