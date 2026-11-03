"""The deep-dive dossier of each name as of a session (ADR 0050 decision 6 and its amendment
2026-11-03, EV5).

Every ``dossier-import`` run stores the WHOLE dossier of a name: its factors
(``instruments/factors``, a retired one kept with ``status = retired``), their dated occurrences
and undated watch windows (``events/factor_occurrence``), all ``known_from`` the import's
session. So the reader applies the one read rule first (keep rows with ``known_from <= S``) and
then, per instrument, takes the rows of the latest import RUN among them: the newest
``knowledge_ts`` of its factor rows (ties: the greater ``run_id``). A session before the first
import sees nothing; a later import that dropped a date removes it; a corrected re-import on the
same session replaces the first (its ``knowledge_ts`` is newer). Never a union of runs.

``DossierRead.known`` says whether the factor table has any row known by the session at all: no
row means "no dossier was ever imported by then" (a gap for the calendar), while a name absent
from ``dossiers`` of a populated table simply has no dossier yet.
"""

import datetime as dt
from dataclasses import dataclass

import pandas as pd

from algotrade.data.events import ALL_TIME, known_from
from algotrade.storage.tables.readers import StoreReader
from algotrade.storage.tables.schemas import FACTOR_OCCURRENCE_EVENTS, FACTOR_REFERENCE

FACTORS = FACTOR_REFERENCE.name
OCCURRENCES = FACTOR_OCCURRENCE_EVENTS.name
DATED, WINDOW = "dated", "window"
RETIRED = "retired"


@dataclass(frozen=True)
class Factor:
    """A driver of the name: ``kind`` (peer, macro, ...), ``status`` active | retired."""

    factor_id: str
    kind: str
    status: str
    description: str


@dataclass(frozen=True)
class Occurrence:
    """A dated occurrence of a factor: a past instance it explains or the next date."""

    factor_id: str
    date: dt.date
    label: str


@dataclass(frozen=True)
class Watch:
    """An undated item of a factor: expected in ``expected_from..expected_to``."""

    factor_id: str
    label: str
    expected_from: dt.date
    expected_to: dt.date


@dataclass(frozen=True)
class Dossier:
    """The dossier of ``instrument_id`` from import run ``run_id`` (known from ``known_from``,
    the owner's review date ``reviewed_on``)."""

    instrument_id: str
    run_id: str
    known_from: dt.date
    reviewed_on: dt.date
    factors: tuple[Factor, ...]
    occurrences: tuple[Occurrence, ...]
    watch: tuple[Watch, ...]


@dataclass(frozen=True)
class DossierRead:
    """``dossiers`` by instrument id; ``known``: some dossier row was known by the session."""

    dossiers: dict[str, Dossier]
    known: bool


def _latest_runs(factors: pd.DataFrame) -> dict[str, str]:
    """Per instrument, the run of the newest ``knowledge_ts`` (ties: the greater run id)."""
    runs = factors.groupby(["instrument_id", "run_id"], sort=False)["knowledge_ts"].max()
    ranked = runs.reset_index().sort_values(["knowledge_ts", "run_id"], kind="stable")
    latest = ranked.drop_duplicates("instrument_id", keep="last")
    return dict(zip(latest["instrument_id"].astype(str), latest["run_id"].astype(str), strict=True))


def _known(reader: StoreReader, table: str, session: dt.date) -> pd.DataFrame:
    """Every stored row of ``table`` known on or before ``session`` (the one read rule), with
    ``known_from`` set to each row's effective date; no columns checked: empty when none."""
    frame = reader.table_range(table, *ALL_TIME)
    if frame is None or frame.empty:
        return pd.DataFrame()
    frame = frame[known_from(frame) <= pd.Timestamp(session)]
    return frame.assign(known_from=known_from(frame).dt.date)


def _day(value: object) -> dt.date:
    return pd.Timestamp(value).date()  # type: ignore[arg-type]


def dossiers_as_of(reader: StoreReader, session: dt.date) -> DossierRead:
    """The dossier of every name with one known on or before ``session`` (module doc)."""
    factors = _known(reader, FACTORS, session)
    if factors.empty:
        return DossierRead({}, False)
    occurrences = _known(reader, OCCURRENCES, session)
    if occurrences.empty:  # a dossier may list no date: the same columns, no rows
        occurrences = pd.DataFrame(
            columns=[
                "instrument_id",
                "run_id",
                "ts",
                "factor_id",
                "label",
                "date_kind",
                "window_end",
            ]
        )
    out: dict[str, Dossier] = {}
    for instrument_id, run_id in _latest_runs(factors).items():
        mine = factors[(factors["instrument_id"] == instrument_id) & (factors["run_id"] == run_id)]
        rows = occurrences[
            (occurrences["instrument_id"] == instrument_id) & (occurrences["run_id"] == run_id)
        ]
        records = rows.sort_values(["ts", "factor_id"], kind="stable").to_dict("records")
        dated = [r for r in records if r["date_kind"] != WINDOW]
        windows = [r for r in records if r["date_kind"] == WINDOW and pd.notna(r["window_end"])]
        out[instrument_id] = Dossier(
            instrument_id=instrument_id,
            run_id=run_id,
            known_from=_day(mine["known_from"].max()),
            reviewed_on=_day(mine["reviewed_on"].max()),
            factors=tuple(
                Factor(str(r["factor_id"]), str(r["kind"]), str(r["status"]), str(r["description"]))
                for r in mine.sort_values("factor_id", kind="stable").to_dict("records")
            ),
            occurrences=tuple(
                Occurrence(str(r["factor_id"]), _day(r["ts"]), str(r["label"])) for r in dated
            ),
            watch=tuple(
                Watch(str(r["factor_id"]), str(r["label"]), _day(r["ts"]), _day(r["window_end"]))
                for r in windows
            ),
        )
    return DossierRead(out, True)
