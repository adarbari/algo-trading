"""``dossiers_as_of``: per name the rows of the latest import run among those known by the
session (ADR 0050 decision 6): nothing before the first import, a later import that drops a date
removes it, a same-session corrected re-import replaces the first, a retired factor stays listed."""

from datetime import UTC, date, datetime

import pandas as pd

from algotrade.data.dossier.reading import dossiers_as_of
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.readers import StoreReader
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.stored_frames import stamped

I1, I2 = date(2026, 11, 2), date(2026, 11, 9)
MU = "EQ:MU"


def factor(factor_id: str, known: date, status: str = "active", reviewed: date = I1) -> dict:
    return {
        "instrument_id": MU, "factor_id": factor_id, "known_from": known, "kind": "commodity",
        "status": status, "description": f"why {factor_id} moves it", "reviewed_on": reviewed,
    }  # fmt: skip


def dated(factor_id: str, day: date, known: date, label: str = "SK Hynix results") -> dict:
    return {
        "instrument_id": MU, "ts": pd.Timestamp(day, tz="UTC"), "known_from": known,
        "factor_id": factor_id, "label": label, "date_kind": "dated", "window_end": None,
    }  # fmt: skip


def window(factor_id: str, first: date, last: date, known: date) -> dict:
    return {
        "instrument_id": MU, "ts": pd.Timestamp(first, tz="UTC"), "known_from": known,
        "factor_id": factor_id, "label": "Korean export data", "date_kind": "window",
        "window_end": last,
    }  # fmt: skip


def store(*runs: tuple[str, date, datetime, list[dict], list[dict]]) -> StoreReader:
    """Each run: (run id, session, knowledge_ts, factor rows, occurrence rows)."""
    backend = MemoryBackend()
    writer = StoreWriter(backend)
    for run_id, session, at, factors, occurrences in runs:
        writer.write_table(
            "instruments/factors", session, run_id, stamped(factors, session, run_id, at)
        )
        if occurrences:
            writer.write_table(
                "events/factor_occurrence",
                session,
                run_id,
                stamped(occurrences, session, run_id, at),
            )
    return StoreReader(backend)


def at(day: date, hour: int = 22) -> datetime:
    return datetime(day.year, day.month, day.day, hour, tzinfo=UTC)


def first_import() -> tuple[str, date, datetime, list[dict], list[dict]]:
    return (
        "r1", I1, at(I1),
        [factor("hbm", I1), factor("old", I1, "retired")],
        [dated("hbm", date(2026, 11, 20), I1), dated("hbm", date(2026, 10, 24), I1),
         window("hbm", date(2026, 12, 1), date(2026, 12, 20), I1)],
    )  # fmt: skip


def test_a_session_before_the_import_sees_nothing() -> None:
    found = dossiers_as_of(store(first_import()), date(2026, 11, 1))
    assert found.dossiers == {} and found.known is False


def test_the_import_session_sees_factors_dates_windows_and_the_review_date() -> None:
    found = dossiers_as_of(store(first_import()), I1)
    dossier = found.dossiers[MU]
    assert found.known and dossier.reviewed_on == I1 and dossier.run_id == "r1"
    assert [(f.factor_id, f.status) for f in dossier.factors] == [
        ("hbm", "active"),
        ("old", "retired"),
    ]
    assert [o.date for o in dossier.occurrences] == [date(2026, 10, 24), date(2026, 11, 20)]
    assert [(w.expected_from, w.expected_to) for w in dossier.watch] == [
        (date(2026, 12, 1), date(2026, 12, 20))
    ]


def test_a_later_import_dropping_a_date_removes_it_but_an_earlier_session_keeps_it() -> None:
    second = (
        "r2",
        I2,
        at(I2),
        [factor("hbm", I2, reviewed=I2)],
        [dated("hbm", date(2026, 11, 20), I2)],
    )
    reader = store(first_import(), second)
    before = dossiers_as_of(reader, date(2026, 11, 8)).dossiers[MU]
    after = dossiers_as_of(reader, I2).dossiers[MU]
    assert [o.date for o in before.occurrences] == [date(2026, 10, 24), date(2026, 11, 20)]
    assert [o.date for o in after.occurrences] == [date(2026, 11, 20)]
    assert after.watch == () and [f.factor_id for f in after.factors] == ["hbm"]
    assert after.reviewed_on == I2 and after.run_id == "r2"


def test_a_same_session_corrected_reimport_replaces_the_first() -> None:
    corrected = (
        "r1b",
        I1,
        at(I1, 23),
        [factor("hbm", I1)],
        [dated("hbm", date(2026, 11, 21), I1, "FDA date")],
    )
    found = dossiers_as_of(store(first_import(), corrected), I1).dossiers[MU]
    assert [(o.date, o.label) for o in found.occurrences] == [(date(2026, 11, 21), "FDA date")]
    assert [f.factor_id for f in found.factors] == ["hbm"] and found.watch == ()


def test_a_name_without_a_dossier_is_absent_while_the_table_is_known() -> None:
    other = dict(factor("x", I1), instrument_id="EQ:ZZ")
    found = dossiers_as_of(store(("r1", I1, at(I1), [other], [])), I1)
    assert found.known and list(found.dossiers) == ["EQ:ZZ"]
    assert found.dossiers["EQ:ZZ"].occurrences == ()


def test_each_name_takes_its_own_latest_run() -> None:
    zz = dict(factor("x", I1), instrument_id="EQ:ZZ")
    second = ("r2", I2, at(I2), [factor("hbm", I2)], [])
    found = dossiers_as_of(store(("r1", I1, at(I1), [factor("hbm", I1), zz], []), second), I2)
    assert found.dossiers[MU].run_id == "r2" and found.dossiers["EQ:ZZ"].run_id == "r1"
