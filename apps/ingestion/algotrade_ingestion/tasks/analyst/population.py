"""The names the analyst tasks may ask Yahoo about: the stock population of the reference.

``analyst-snapshot`` asks FMP and Finnhub about the S&P 500 plus the event-study scope list
(``snapshot.scope_names``); Yahoo, which has no daily budget and covers the small and mid caps FMP's
free plan refuses, is asked about every operating company the universe holds: the reference
snapshot's ``COMMON_STOCK`` and ``ADR`` rows (``universe.toml security_types``; ETFs and closed-end
funds have no analyst consensus, Yahoo answers 404). One reader of that population, so the nightly's
Yahoo step and the one-off ``analyst-backfill`` agree on it (ADR 0080 amendment 2026-10-23b).

``report_dates``: the report dates the Yahoo scheduler times its event pulls by, read from the
session before's ``earnings@v1`` and ``earnings_expected@v1`` partitions (ADR 0080 amendment
2026-10-23c).
"""

from dataclasses import dataclass
from datetime import date

import pandas as pd

from algotrade.core.time.calendar import previous_session
from algotrade.data import StoreReader
from algotrade.data.reference import instruments
from algotrade.data.rollups import rollup_on

TYPES = ("COMMON_STOCK", "ADR")  # the security types that report earnings and have analysts
EARNINGS = "rollups/instrument/earnings@v1"
EXPECTED = "rollups/instrument/earnings_expected@v1"


@dataclass(frozen=True)
class Name:
    instrument_id: str
    symbol: str


def listed_names(reader: StoreReader, session: date) -> list[Name]:
    """The ``COMMON_STOCK`` and ``ADR`` rows of the reference snapshot for ``session``, by symbol
    (a row without a symbol is left out)."""
    reference = instruments(reader, session)
    if "security_type" not in reference.columns:
        return []
    held = reference[reference["security_type"].isin(TYPES)]
    found = {
        str(i): str(s)
        for i, s in zip(held["instrument_id"], held["symbol"], strict=False)
        if pd.notna(s) and isinstance(s, str) and s
    }
    return sorted((Name(i, s) for i, s in found.items()), key=lambda n: (n.symbol, n.instrument_id))


def report_dates(reader: StoreReader, session: date) -> dict[str, tuple[date | None, date | None]]:
    """``instrument_id`` -> (the last report, the next report expected), as the session before
    ``session`` knew them: exactly that partition of ``earnings@v1`` (``last_earnings_date``,
    ``next_earnings_date``) and ``earnings_expected@v1`` (``expected_report_date`` where no date is
    scheduled), never the latest partition and never a date computed here. Tonight's rollups may
    not exist yet (the step needs only the universe), so nothing later than that session is read;
    a missing partition leaves a name without dates (the baseline serves it). A scheduled report
    dated that very session is already past tonight: it is the last report."""
    before = previous_session(session)
    out: dict[str, tuple[date | None, date | None]] = {}
    expected = rollup_on(reader, EXPECTED, before)
    pending = _dates(expected, "expected_report_date")
    frame = rollup_on(reader, EARNINGS, before)
    last = _dates(frame, "last_earnings_date")
    nxt = _dates(frame, "next_earnings_date")
    for instrument_id in {*last, *nxt, *pending}:
        previous, upcoming = (
            last.get(instrument_id),
            nxt.get(instrument_id) or pending.get(instrument_id),
        )
        if upcoming is not None and upcoming <= before:
            previous, upcoming = max(d for d in (previous, upcoming) if d is not None), None
        out[instrument_id] = (previous, upcoming)
    return out


def _dates(frame: pd.DataFrame | None, column: str) -> dict[str, date]:
    if frame is None or column not in frame.columns:
        return {}
    stamps = pd.to_datetime(frame[column], errors="coerce")
    return {
        str(i): d.date()
        for i, d in zip(frame["instrument_id"], stamps, strict=False)
        if pd.notna(d)
    }
