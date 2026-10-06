"""Point in time for macro series (ADR 0048): whatever vintages are stored, in whatever runs on
whatever dates (a key re-stored with another value by a later run), no row ``series_as_of`` or
the feature input returns for a session has a ``vintage_date`` after it, and each observation's
value is its latest vintage known by then, as last stored."""

from datetime import UTC, date, datetime, timedelta

from hypothesis import given, settings
from hypothesis import strategies as st

from algotrade.data import StoreReader
from algotrade.data.feature_inputs import load_input
from algotrade.data.macro.series import TABLE, series_as_of
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.stored_frames import stamped

START = date(2008, 1, 1)
STORED = date(2026, 10, 1)
IDS = ("MACRO:A", "IDX:B")
type Key = tuple[str, date, date]
days = st.integers(0, 120).map(lambda n: START + timedelta(days=n))
vintage = st.tuples(st.sampled_from(IDS), days, st.integers(0, 60), st.floats(-10, 10))


def write(writer: StoreWriter, run: int, rows: dict[Key, float]) -> None:
    """``rows`` as run ``run``: its own partition (a later date) and a later stamp."""
    day = STORED + timedelta(days=run)
    part = [
        {"instrument_id": iid, "obs_date": obs, "vintage_date": vin, "value": v,
         "vintage_kind": "alfred"}
        for (iid, obs, vin), v in sorted(rows.items())
    ]  # fmt: skip
    if part:
        at = datetime(day.year, day.month, day.day, 22, tzinfo=UTC)
        writer.write_table(TABLE, day, f"r{run}", stamped(part, day, f"r{run}", at))


@settings(max_examples=60, deadline=None)
@given(
    rows=st.lists(vintage, max_size=25),
    session=days,
    runs=st.integers(1, 3),
    restate=st.lists(st.tuples(st.integers(0, 24), st.floats(-10, 10)), max_size=6),
)
def test_no_session_sees_a_later_vintage(
    rows: list[tuple[str, date, int, float]],
    session: date,
    runs: int,
    restate: list[tuple[int, float]],
) -> None:
    by_key: dict[Key, float] = {(i, o, o + timedelta(days=lag)): v for i, o, lag, v in rows}
    keys = sorted(by_key)
    writer = StoreWriter(MemoryBackend())
    for run in range(runs):  # the vintages spread over runs, as a backfill and nightlies
        write(writer, run, {k: by_key[k] for n, k in enumerate(keys) if n % runs == run})
    if keys and restate:  # a later run re-stores some keys with another value: it wins
        again = {keys[n % len(keys)]: v for n, v in restate}
        write(writer, runs, again)
        by_key.update(again)
    reader = StoreReader(writer._backend)

    seen = series_as_of(reader, None, session, 200)
    assert (seen["vintage_date"] <= session).all()
    assert not seen.duplicated(["instrument_id", "obs_date"]).any()
    expected = {k[:2] for k in by_key if k[2] <= session}
    assert set(zip(seen["instrument_id"], seen["obs_date"], strict=True)) == expected
    for iid, obs, vin, value in seen[["instrument_id", "obs_date", "vintage_date", "value"]].values:
        known = [k for k in by_key if k[:2] == (iid, obs) and k[2] <= session]
        assert vin == max(k[2] for k in known)
        assert value == by_key[(str(iid), obs, vin)]

    loaded = load_input(reader, TABLE, [session], 0).at(session, 0)
    if loaded is None:
        assert not expected
    else:
        assert max(loaded["vintage_date"]) <= session
        assert len(loaded) == sum(1 for k in by_key if k[2] <= session)
