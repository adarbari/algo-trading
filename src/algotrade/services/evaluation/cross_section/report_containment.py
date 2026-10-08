"""Did the event windows contain the real report? (ADR 0053; an evaluation diagnostic.)

An edge on ``on_event:earnings_expected`` builds each window from the EXPECTED report date known
at D (SCHEDULED, or PRIOR_YEAR: the year-ago date plus 364 days), which can miss the real
report. This module counts, per edge variant and horizon, the share of the measured windows
(a name's event at D with an outcome row at the entry session S, closing h sessions later)
whose real report date fell in ``S..S+h``.

The real date is known only afterwards: it is read from the stored earnings events whose
``known_from`` is later than D, as of the run's ``as_of``. That read is legitimate here because
this is a **diagnostic over windows that have already closed**, never an input to a pick, a
filter, a weight or a statistic: ``harness.py`` computes it after the measures, from the event
names it already measured, and a test pins that the picks and hits are identical with and without
it. A window whose real report is outside it (or not stored) is in the denominator, never the
numerator.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime

import pandas as pd

from algotrade.core.time.calendar import next_session
from algotrade.data import StoreReader
from algotrade.data.events import stored_events
from algotrade.features.rollups.corporate.earnings import EVENTS, valid_events
from algotrade.storage.tables.schemas import KNOWN_FROM


@dataclass(frozen=True)
class ReportContainment:
    """``windows`` measured event windows, ``contained`` of them with the real report date in
    ``S..S+h``, ``no_report`` of them with no real report stored after D (not contained)."""

    windows: int
    contained: int
    no_report: int

    @property
    def share(self) -> float | None:
        return self.contained / self.windows if self.windows else None


def reports_after(reader: StoreReader, as_of: datetime) -> dict[str, list[tuple[date, date]]]:
    """Per instrument the stored report days with the date each became known:
    ``[(known_from, report_day)]``, the valid rows (``earnings.valid_events``) as of ``as_of``."""
    today = as_of.date()
    stored = stored_events(reader, EVENTS, today, as_of)
    if stored.empty:
        return {}
    rows = valid_events(stored, today)
    if "reported" in rows.columns:
        rows = rows[rows["reported"].fillna(False).astype(bool)]
    out: dict[str, list[tuple[date, date]]] = {}
    for iid, known, report in zip(
        rows["instrument_id"], rows[KNOWN_FROM], rows["report"], strict=True
    ):
        out.setdefault(str(iid), []).append((_day(known), _day(report)))
    return out


def window_end(entry: date, horizon: int) -> date:
    """The session ``horizon`` sessions after the entry session S."""
    day = entry
    for _ in range(horizon):
        day = next_session(day)
    return day


def containment(
    windows: Iterable[tuple[str, date, date]],
    horizon: int,
    reports: Mapping[str, list[tuple[date, date]]],
) -> ReportContainment:
    """The share of ``windows`` (name, D, S) containing a real report: one known after D (a
    row with ``known_from`` later than D) on a day in ``S..S+horizon``."""
    total = contained = missing = 0
    for iid, decision, entry in windows:
        total += 1
        later = [day for known, day in reports.get(iid, ()) if known > decision]
        if not later:
            missing += 1
        elif any(entry <= day <= window_end(entry, horizon) for day in later):
            contained += 1
    return ReportContainment(total, contained, missing)


def _day(value: object) -> date:
    return pd.Timestamp(str(value)).date()
