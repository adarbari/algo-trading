"""Point in time for macro series (ADR 0048): whatever vintages are stored, in whatever runs,
no row ``series_as_of`` returns for a session has a ``vintage_date`` after it, and each
observation's value is its latest vintage known by then."""

from datetime import UTC, date, datetime, timedelta

from hypothesis import given, settings
from hypothesis import strategies as st

from algotrade.data import StoreReader
from algotrade.data.macro.series import TABLE, series_as_of
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.stored_frames import stamped

START = date(2008, 1, 1)
IDS = ("MACRO:A", "IDX:B")
days = st.integers(0, 120).map(lambda n: START + timedelta(days=n))
vintage = st.tuples(st.sampled_from(IDS), days, st.integers(0, 60), st.floats(-10, 10))


@settings(max_examples=60, deadline=None)
@given(rows=st.lists(vintage, max_size=25), session=days, runs=st.integers(1, 3))
def test_no_session_sees_a_later_vintage(
    rows: list[tuple[str, date, int, float]], session: date, runs: int
) -> None:
    by_key = {(iid, obs, obs + timedelta(days=lag)): v for iid, obs, lag, v in rows}
    writer = StoreWriter(MemoryBackend())
    stored = date(2026, 10, 6)
    for run in range(runs):  # the same vintages spread over runs, as a backfill and nightlies
        part = [
            {"instrument_id": iid, "obs_date": obs, "vintage_date": vin, "value": v,
             "vintage_kind": "alfred"}
            for i, ((iid, obs, vin), v) in enumerate(sorted(by_key.items())) if i % runs == run
        ]  # fmt: skip
        if part:
            at = datetime(2026, 10, 6, 22, tzinfo=UTC) + timedelta(minutes=run)
            writer.write_table(TABLE, stored, f"r{run}", stamped(part, stored, f"r{run}", at))
    seen = series_as_of(StoreReader(writer._backend), None, session, 200)
    assert (seen["vintage_date"] <= session).all()
    assert not seen.duplicated(["instrument_id", "obs_date"]).any()
    expected = {k[:2] for k in by_key if k[2] <= session}
    assert set(zip(seen["instrument_id"], seen["obs_date"], strict=True)) == expected
    for iid, obs, vin, value in seen[["instrument_id", "obs_date", "vintage_date", "value"]].values:
        known = [k for k in by_key if k[:2] == (iid, obs) and k[2] <= session]
        assert vin == max(k[2] for k in known)
        assert value == by_key[(str(iid), obs, vin)]
