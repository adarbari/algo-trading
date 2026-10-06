"""The vintage rule and the diff against what is stored (``tasks/macro/plan.py``)."""

from datetime import date

import pandas as pd

from algotrade.config.site.macro import MacroSettings
from algotrade_ingestion.tasks.macro.plan import COLUMNS, rows_to_write, vintage_count, vintage_rows
from algotrade_sources.framework.series import SERIES_COLUMNS

D = date(2026, 10, 5)


def spec(**kw: object) -> object:
    entry = {
        "key": "S", "source": "fred", "kind": "macro", "cadence": "daily", "pit": "lag",
        "release_lag_days": 2, "terms": "t", **kw,
    }  # fmt: skip
    return MacroSettings.from_document({"series": [entry]}).series[0]


def fetched(*rows: tuple[str, str | None, float | None]) -> pd.DataFrame:
    """(obs, vintage, value) as an adapter returns them."""
    frame = pd.DataFrame(rows, columns=["obs_date", "vintage_date", "value"])
    frame["series"], frame["code"] = "S", "S"
    for column in ("obs_date", "vintage_date"):
        frame[column] = pd.to_datetime(frame[column])
    return frame.reindex(columns=list(SERIES_COLUMNS))


def held(*rows: tuple[date, date, str, float | None]) -> pd.DataFrame:
    """Stored rows (obs, vintage, kind, value) as ``stored_vintages`` returns them."""
    frame = pd.DataFrame(rows, columns=["obs_date", "vintage_date", "vintage_kind", "value"])
    frame["instrument_id"], frame["series"] = "MACRO:S", "S"
    return frame.reindex(columns=COLUMNS)


def triples(frame: pd.DataFrame) -> list[tuple[date, date, str, float | None]]:
    return [
        (o, v, k, None if pd.isna(x) else x)
        for o, v, k, x in zip(
            frame["obs_date"], frame["vintage_date"], frame["vintage_kind"], frame["value"],
            strict=True,
        )
    ]  # fmt: skip


def test_a_lag_series_takes_its_current_value_a_release_lag_after_the_observation() -> None:
    frame = fetched(
        ("2026-10-01", "2026-09-01", 1.0),
        ("2026-10-01", "2026-10-03", 1.5),
        ("2026-10-02", None, 2.0),
    )  # the first observation was revised: only the current value is kept
    rows = vintage_rows(spec(pit="lag", release_lag_days=2), frame)
    assert triples(rows) == [
        (date(2026, 10, 1), date(2026, 10, 3), "lagged", 1.5),
        (date(2026, 10, 2), date(2026, 10, 4), "lagged", 2.0),
    ]
    assert list(rows.columns) == COLUMNS and set(rows["instrument_id"]) == {"MACRO:S"}


def test_an_alfred_series_keeps_realtime_start_except_before_its_first_vintage() -> None:
    frame = fetched(
        ("2019-01-01", "2019-06-01", 1.0),  # first vintage; public 2 days after 2019-01-01: lagged
        ("2019-06-01", "2019-06-01", 1.1),  # first vintage, but only 0 days old: really that day
        ("2019-06-01", "2019-07-01", 1.2),  # a revision
    )
    rows = vintage_rows(spec(pit="alfred", release_lag_days=2), frame)
    assert triples(rows) == [
        (date(2019, 1, 1), date(2019, 1, 3), "lagged", 1.0),
        (date(2019, 6, 1), date(2019, 6, 1), "alfred", 1.1),
        (date(2019, 6, 1), date(2019, 7, 1), "alfred", 1.2),
    ]


def test_an_alfred_row_without_a_vintage_date_is_lagged_and_an_empty_fetch_is_empty() -> None:
    rows = vintage_rows(spec(pit="alfred"), fetched(("2019-01-01", None, 1.0)))
    assert triples(rows) == [(date(2019, 1, 1), date(2019, 1, 3), "lagged", 1.0)]
    assert vintage_rows(spec(pit="alfred"), fetched()).empty
    assert vintage_rows(spec(pit="lag"), fetched()).empty


def test_rows_to_write_is_everything_when_nothing_is_stored_and_nothing_when_all_is() -> None:
    target = vintage_rows(
        spec(pit="lag"), fetched(("2026-10-01", None, 1.0), ("2026-10-02", None, None))
    )
    everything = rows_to_write(target, held(), D)
    assert triples(everything) == triples(target)
    assert rows_to_write(target, everything, D).empty  # a null value equals a null value


def test_a_changed_lagged_value_is_a_new_vintage_dated_the_session() -> None:
    old = held((date(2026, 10, 1), date(2026, 10, 3), "lagged", 1.0))
    target = vintage_rows(spec(pit="lag"), fetched(("2026-10-01", None, 1.5)))
    new = rows_to_write(target, old, D)
    assert triples(new) == [(date(2026, 10, 1), D, "lagged", 1.5)]
    both = pd.concat([old, new], ignore_index=True)
    assert rows_to_write(target, both, D + pd.Timedelta(days=1)).empty  # now the newest is 1.5
    assert vintage_count(old, new) == 2


def test_a_value_corrected_before_its_vintage_is_public_takes_that_key() -> None:
    """The stored vintage (obs + lag) is after the session: no session has read it."""
    old = held((date(2026, 10, 5), date(2026, 10, 7), "lagged", 1.0))
    target = vintage_rows(spec(pit="lag"), fetched(("2026-10-05", None, 1.25)))
    new = rows_to_write(target, old, D)
    assert triples(new) == [(date(2026, 10, 5), date(2026, 10, 7), "lagged", 1.25)]
    assert vintage_count(old, new) == 1  # an overwrite adds no vintage


def test_alfred_rows_are_written_once_per_key_and_a_correction_overwrites_the_key() -> None:
    target = vintage_rows(
        spec(pit="alfred", release_lag_days=1),
        fetched(("2026-06-01", "2026-06-02", 1.0), ("2026-06-01", "2026-07-01", 1.1)),
    )
    stored = held((date(2026, 6, 1), date(2026, 6, 2), "alfred", 1.0))
    assert triples(rows_to_write(target, stored, D)) == [
        (date(2026, 6, 1), date(2026, 7, 1), "alfred", 1.1)
    ]
    corrected = held((date(2026, 6, 1), date(2026, 6, 2), "alfred", 0.9))
    assert len(rows_to_write(target, corrected, D)) == 2  # the vintage's value differs


def test_a_lagged_row_is_compared_with_the_stored_lagged_vintage_not_an_alfred_one() -> None:
    stored = held(
        (date(2019, 1, 1), date(2019, 1, 3), "lagged", 1.0),
        (date(2019, 1, 1), date(2019, 8, 1), "alfred", 2.0),
    )
    target = vintage_rows(
        spec(pit="alfred", release_lag_days=2),
        fetched(("2019-01-01", "2019-06-01", 1.0), ("2019-01-01", "2019-08-01", 2.0)),
    )
    assert rows_to_write(target, stored, D).empty


def test_a_null_never_replaces_a_stored_number() -> None:
    old = held((date(2026, 10, 1), date(2026, 10, 3), "lagged", 1.0))
    target = vintage_rows(spec(pit="lag"), fetched(("2026-10-01", None, None)))
    assert rows_to_write(target, old, D).empty  # the number the series was known by stays
    alfred = vintage_rows(
        spec(pit="alfred", release_lag_days=1), fetched(("2026-06-01", "2026-06-02", None))
    )
    stored = held((date(2026, 6, 1), date(2026, 6, 2), "alfred", 1.0))
    assert rows_to_write(alfred, stored, D).empty
    # a number replacing a stored null is a change
    nulls = held((date(2026, 10, 1), date(2026, 10, 3), "lagged", None))
    number = vintage_rows(spec(pit="lag"), fetched(("2026-10-01", None, 2.0)))
    assert triples(rows_to_write(number, nulls, D)) == [(date(2026, 10, 1), D, "lagged", 2.0)]
