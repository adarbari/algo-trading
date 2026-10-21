"""The recent filings a text-comparison feature group reads, one session's view (edge build F).

For session S: the Item texts of every 10-K and 10-Q of a company that has one known in the last
``RECENT_SESSIONS`` sessions, together with that company's filings of the year before
(``LOOKBACK_DAYS`` of acceptance dates), each as ``reading.filing_text`` reads it on S: known on
or before S (a filing accepted after the close is first in the view of the next session), the
latest version per item, amendments left out by form. The rows are the companies that map to an
instrument at S (``instrument_id`` not null); a delisted company's filings have none and are not
in the view (the group has no row for it). The view is read lazily per session, never for a
chunk of them, and never beyond S.

Two reads: a scan without text for the companies with a recent filing, then one read with text
narrowed to those companies. A recent filing is found from acceptance dates ``SCAN_MARGIN_DAYS``
before the first recent session on (a filing is known the session after its acceptance); a text
re-extracted later than that, from an older filing, is not recent news and is not read.

``accepted_session`` is the session each row's filing was accepted into (``acceptance_sessions``
of ``ts``): the date a filing is recent from. ``known_from`` is only the visibility filter, since
a parser re-run gives an old filing a new ``known_from`` that must never make it recent news.
"""

from datetime import date, timedelta

import pandas as pd

from algotrade.core.time.calendar import sessions_ending
from algotrade.data.events import acceptance_sessions
from algotrade.data.filing_text.reading import TABLE, filing_text, light_memo
from algotrade.storage.tables.readers import RollingRead, StoreReader

RECENT_SESSIONS = 5  # equals features.rollups.text.comparison.RECENT_SESSIONS (tested)
LOOKBACK_DAYS = 460  # acceptance dates read: the year-ago comparator and a late filer's margin
SCAN_MARGIN_DAYS = 10
FORMS = ("10-K", "10-Q")
ITEMS = ("1", "1A", "3", "7", "I-2", "II-1A")  # equals comparison.ITEMS, all forms (tested)

__all__ = ["FORMS", "ITEMS", "TABLE", "RecentFilings", "recent_filing_texts"]


class RecentFilings:
    """The views of a run of sessions over one reader: the light read of the long window is kept
    and extended (``reading.light_memo``), so session after session re-reads only the partitions
    that are new; every view equals ``recent_filing_texts(reader, session)``."""

    def __init__(self, reader: StoreReader) -> None:
        self._reader = reader
        self._memo = light_memo()

    def at(self, session: date) -> pd.DataFrame | None:
        return recent_filing_texts(self._reader, session, self._memo)


def recent_filing_texts(
    reader: StoreReader, session: date, memo: RollingRead | None = None
) -> pd.DataFrame | None:
    """The view of ``session`` (module doc): ``COLUMNS`` rows with text and a non-null
    ``instrument_id``; ``None`` when no company has a periodic filing known in the last
    ``RECENT_SESSIONS`` sessions. ``memo``: the run's kept light read (``RecentFilings``)."""
    first = sessions_ending(session, RECENT_SESSIONS)[0]
    scan = filing_text(
        reader, None, session, ITEMS, FORMS, first - timedelta(days=SCAN_MARGIN_DAYS), None, False
    )
    if scan.empty:
        return None
    accepted = pd.to_datetime(acceptance_sessions(scan["ts"]))
    recent = scan[scan["instrument_id"].notna() & (accepted >= pd.Timestamp(first))]
    if recent.empty:
        return None
    frame = filing_text(
        reader, None, session, ITEMS, FORMS, session - timedelta(days=LOOKBACK_DAYS),
        ciks=sorted(set(recent["cik"])), light_memo=memo,
    )  # fmt: skip
    frame = frame[frame["instrument_id"].notna()]
    if frame.empty:
        return None
    frame = frame.assign(accepted_session=acceptance_sessions(frame["ts"]))
    return frame.reset_index(drop=True)
