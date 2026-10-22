"""``market_macro_asof@v1``: per series the regime cards rest on, the latest observation the
session knew with its vintage date and kind, and the first ALFRED vintage, equal to what
``data.macro.series`` gives today (the rule the provenance panel was computed by): a revision
stored after the session is never seen, a series with no observation by it is null (not zero),
the first ALFRED vintage counts only when it is on or before the session, and a lagged
personal series carries its licence."""

from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from algotrade.config.site.regime.cards import load_cards
from algotrade.config.site.settings import load_macro
from algotrade.data import StoreReader
from algotrade.data.macro.series import first_alfred_vintages, latest_known, stored_vintages
from algotrade.features.framework.runner import compute_one, compute_sessions
from algotrade.features.rollups.market import macro_asof
from algotrade.features.rollups.market.macro_asof import GROUP, ID, column
from algotrade.services.features import catalogue
from algotrade.services.read.regime.sources import leaves, series_of
from algotrade.storage.configs.files import FileConfigStore
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.rollup_store import END, store
from tests.helpers.stored_frames import stamped

REPO = Path(__file__).resolve().parents[5]
FIELDS = ("last_obs_date", "vintage_date", "vintage_kind", "first_vintage")


def vintage(key: str, obs: date, seen: date, kind: str) -> dict[str, object]:
    return {"instrument_id": ID[key], "series": key, "obs_date": obs, "vintage_date": seen,
            "value": 4.0, "vintage_kind": kind}  # fmt: skip


def written() -> tuple[StoreWriter, StoreReader]:
    writer, reader = store()
    later = END + timedelta(days=18)
    rows = [
        vintage("UNRATE", date(1960, 1, 1), date(1964, 6, 1), "alfred"),  # the first ALFRED vintage
        vintage("UNRATE", date(2026, 7, 1), date(2026, 8, 7), "alfred"),
        vintage("UNRATE", date(2026, 8, 1), date(2026, 9, 5), "alfred"),  # the newest known
        vintage("UNRATE", date(2026, 8, 1), later, "alfred"),  # a revision after END: never seen
        vintage("UNRATE", date(2026, 9, 1), later, "alfred"),  # an observation after END: unseen
        vintage("BAMLH0A0HYM2", END - timedelta(days=5), END - timedelta(days=4), "lagged"),
        vintage("BAMLH0A0HYM2", END - timedelta(days=1), END, "lagged"),  # public on END: known
        vintage("BAMLH0A0HYM2", END, END + timedelta(days=1), "lagged"),  # public after: unseen
        vintage("NFCI", date(2026, 9, 24), END + timedelta(days=8), "alfred"),  # first vintage
        # after END: no observation, no first vintage by it
    ]
    writer.write_table("macro/series", END, "macro-1", stamped(rows, END, "macro-1"))
    return writer, reader


def row(reader: StoreReader, session: date = END) -> dict[str, object]:
    frame = compute_one(reader, GROUP, session).frame
    assert frame is not None and list(frame["instrument_id"]) == ["MKT:US"]
    return frame.iloc[0].to_dict()


def today(reader: StoreReader, key: str, session: date) -> tuple[object, ...]:
    """What ``regime/sources._provenance`` computed before this group: the stored vintages."""
    frame = stored_vintages(reader, [ID[key]])
    first = first_alfred_vintages(frame).get(ID[key])
    newest = latest_known(frame, session)
    first = first if first is not None and first <= session else None
    if newest.empty:
        return (None, None, None, first)
    r = newest.iloc[0]
    return (r["obs_date"], r["vintage_date"], r["vintage_kind"], first)


def stored(got: dict[str, object], key: str) -> tuple[object, ...]:
    def d(v: object) -> object:
        return None if v is None or pd.isna(v) else v

    return tuple(d(got[column(key, f)]) for f in FIELDS)


def test_every_series_equals_the_stored_vintage_computation_at_each_session() -> None:
    _, reader = written()
    for session in (date(2026, 9, 4), date(2026, 9, 5), END - timedelta(days=1), END):
        got = row(reader, session)
        for key in macro_asof.SERIES:
            assert stored(got, key) == today(reader, key, session), (key, session)


def test_a_revision_or_observation_stored_after_the_session_is_not_seen() -> None:
    got = stored(row(written()[1]), "UNRATE")
    assert got == (date(2026, 8, 1), date(2026, 9, 5), "alfred", date(1964, 6, 1))


def test_a_series_with_no_observation_by_the_session_is_null_not_zero() -> None:
    got = row(written()[1])
    assert stored(got, "NFCI") == (None, None, None, None)  # its only vintage is after END
    assert stored(got, "VIX") == (None, None, None, None)  # nothing stored at all
    reader = store()[1]  # no macro data at all: the row is still written, every column null
    empty = row(reader)
    assert all(pd.isna(empty[column(k, f)]) for k in macro_asof.SERIES for f in FIELDS)


def test_the_first_alfred_vintage_counts_only_when_known_by_the_session() -> None:
    _, reader = written()
    assert row(reader, date(1964, 5, 31))[column("UNRATE", "first_vintage")] is None
    assert row(reader, date(2026, 9, 5))[column("UNRATE", "first_vintage")] == date(1964, 6, 1)
    # NFCI's only vintage (alfred) is dated after END: known the day it is dated, not before
    on = END + timedelta(days=8)
    assert row(reader, on)[column("NFCI", "first_vintage")] == on


def test_a_lagged_series_is_known_the_day_its_vintage_is_dated_and_has_no_first_vintage() -> None:
    got = stored(row(written()[1]), "BAMLH0A0HYM2")
    assert got == (END - timedelta(days=1), END, "lagged", None)


def test_a_backfill_equals_the_nightly_row() -> None:
    _, reader = written()
    days = [END - timedelta(days=2), END - timedelta(days=1), END]
    chunk = {r.session: r.frame.iloc[0] for r in compute_sessions(reader, GROUP, days)}  # type: ignore[union-attr]
    for day in days:
        pd.testing.assert_series_equal(chunk[day], compute_one(reader, GROUP, day).frame.iloc[0])  # type: ignore[union-attr]


def test_the_series_and_licences_follow_the_registry_and_the_cards() -> None:
    config = FileConfigStore(REPO / "config")
    registry, cards = load_macro(config), load_cards(config)
    for key, use in macro_asof.SERIES.items():
        series = registry.by_key(key)
        assert use.id(key) == series.instrument_id, key
        assert use.personal == (series.licence == "personal"), key
        assert {f.licence for f in macro_asof.FEATURES if f.inputs == (f"series:{key}",)} == {
            series.licence
        }
    site = catalogue(config)
    reached = {
        s.key
        for card in cards.cards
        for leaf in leaves(site, (card.feature, card.feature + "_on"))
        if (s := series_of(leaf, registry)) is not None
    }
    assert reached <= set(macro_asof.SERIES), "a card reaches a series macro_asof does not store"
