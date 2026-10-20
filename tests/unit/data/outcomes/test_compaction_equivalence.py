"""ADR 0078: after a partition's runs are compacted (``compact_runs`` + ``sweep_orphans``), every
outcome reader answers as before. The same nightly history (a window re-written value-identically
by later runs, a revised value, a new key, a DELISTED change, distinct ``knowledge_ts``) is stored
twice in a real local store, one copy compacted; at every ``as_of`` that matters (none, before the
first run, between runs, each run's ``visible_from`` +/- 1 ms, after the last) the values, the
partition sequences, ``dates`` and the stamped key sets are identical, and a returned
``knowledge_ts`` is equal or earlier, never later (decision 3)."""

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from algotrade.data.outcomes import (
    outcome_known,
    outcome_seqs,
    outcome_stamps,
    read_outcomes,
    read_residuals,
    read_stored,
    select_outcomes,
    stored_sessions,
)
from algotrade.data.outcomes.residuals import residual_known, residual_seqs
from algotrade.storage.backends.local import LocalBackend
from algotrade.storage.tables.readers import StoreReader
from algotrade.storage.tables.schemas import FORWARD_RETURNS, RESIDUAL_RETURNS
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.stored_frames import stamped

S1, S2, S3 = date(2026, 9, 1), date(2026, 9, 2), date(2026, 9, 3)
SESSIONS = [S1, S2, S3]
T0 = datetime(2026, 10, 5, 22, tzinfo=UTC)
MS = timedelta(milliseconds=1)
KEY = ["session_date", "instrument_id", "horizon_sessions", "benchmark"]


def known(k: int) -> datetime:
    return T0 + timedelta(hours=2 * k)


def commit_at(k: int) -> datetime:
    return known(k) + timedelta(minutes=10)


Row = dict[str, Any]


def fwd(iid: str, ret: float, h: int = 2, bm: str = "SPY", status: str = "COMPLETE") -> Row:
    return {
        "instrument_id": iid, "ts": pd.Timestamp("2026-09-01T20:00Z"), "horizon_sessions": h,
        "window_end": date(2026, 9, 10), "benchmark": bm, "fwd_return": ret,
        "fwd_excess_return": ret / 2, "fwd_max_return": max(ret, 0.0), "fwd_max_drawdown": 0.0,
        "fwd_realised_vol": 0.2, "outcome_status": status,
    }  # fmt: skip


def res(iid: str, ret: float, h: int = 2, status: str = "COMPLETE") -> Row:
    return {
        "instrument_id": iid, "ts": pd.Timestamp("2026-09-01T20:00Z"), "horizon_sessions": h,
        "window_end": date(2026, 9, 10), "fwd_residual_return": ret, "fwd_factor_return": 0.01,
        "outcome_status": status,
    }  # fmt: skip


def forward_runs(delisted: str = "COMPLETE") -> list[list[Row]]:
    """The nightly's runs of one partition: a first write, a value-identical re-write, a revision
    and a new key, a re-write, a DELISTED change, a last re-write."""
    base = [fwd("EQ:A", 0.1), fwd("EQ:B", 0.2), fwd("EQ:C", 0.3), fwd("EQ:A", 0.5, 6),
            fwd("EQ:A", 0.4, bm="QQQ")]  # fmt: skip
    revised = [fwd("EQ:B", 0.25), fwd("EQ:D", 0.4)]
    now = [fwd("EQ:A", 0.1), fwd("EQ:B", 0.25), fwd("EQ:C", 0.3), fwd("EQ:D", 0.4)]
    after = [*now[:2], fwd("EQ:C", 0.3, status="DELISTED"), now[3]]
    return [base, base, revised, now, [after[2]], after]


def residual_runs() -> list[list[Row]]:
    base = [res("EQ:A", 0.01), res("EQ:B", 0.02), res("EQ:A", 0.03, 6)]
    return [base, base, [res("EQ:B", 0.05)], [*base[:1], res("EQ:B", 0.05)]]


def put(
    writer: StoreWriter, table: str, day: date, run: str, k: int, rows: list[dict[str, Any]]
) -> None:
    frame = stamped(rows, day, run, known(k), "outcomes")
    writer.write_table(table, day, run, frame, pending=True)
    writer.backend.tables.commit_run(run, commit_at(k))


def build(root: Path) -> LocalBackend:
    """A real local store with a published sequence: S1 six runs, S2 three identical re-writes,
    S3 one run; the residual table on S1 and S2; commits interleave across partitions."""
    backend = LocalBackend(root)
    writer = StoreWriter(backend)
    k = 0
    for i, rows in enumerate(forward_runs()):
        put(writer, FORWARD_RETURNS, S1, f"f1-{i}", k := k + 1, rows)
        if i < 3:
            put(writer, FORWARD_RETURNS, S2, f"f2-{i}", k := k + 1, forward_runs()[0])
    put(writer, FORWARD_RETURNS, S3, "f3-0", k := k + 1, forward_runs()[0])
    for i, rows in enumerate(residual_runs()):
        put(writer, RESIDUAL_RETURNS, S1, f"r1-{i}", k := k + 1, rows)
        if i < 2:
            put(writer, RESIDUAL_RETURNS, S2, f"r2-{i}", k := k + 1, residual_runs()[0])
    return backend


def compact(backend: LocalBackend) -> int:
    backend.tables.swap_grace_s = 0.0
    dropped = 0
    for table, days in ((FORWARD_RETURNS, SESSIONS), (RESIDUAL_RETURNS, [S1, S2])):
        for day in days:
            report = backend.tables.compact_runs(table, day)
            assert report.skipped is None, report
            dropped += report.runs_dropped
            backend.tables.sweep_orphans(table, day)
    return dropped


@pytest.fixture(scope="module")
def stores(tmp_path_factory: pytest.TempPathFactory) -> tuple[StoreReader, StoreReader]:
    root = tmp_path_factory.mktemp("compaction")
    plain, packed = build(root / "plain"), build(root / "packed")
    assert compact(packed) == 4  # the rewrites are gone from the compacted copy only
    return StoreReader(plain), StoreReader(packed)


def cuts() -> list[datetime | None]:
    runs = range(1, 16)
    edges = [t for k in runs for t in (known(k), commit_at(k))]
    around = [t + d for t in edges for d in (-MS, MS)]
    mid = [commit_at(k) + (known(k + 1) - commit_at(k)) / 2 for k in runs]
    return [None, T0 - timedelta(days=1), *edges, *around, *mid, known(20) + timedelta(days=9)]


def values(frame: pd.DataFrame | None, keys: list[str]) -> pd.DataFrame | None:
    """The rows without their stamps, in key order (None: not stored / nothing)."""
    if frame is None:
        return None
    frame = frame.drop(columns=["knowledge_ts", "run_id"], errors="ignore")
    return frame.sort_values(keys, ignore_index=True).astype(object).where(frame.notna(), None)


def never_later(a: pd.DataFrame | None, b: pd.DataFrame | None, keys: list[str]) -> None:
    """Each row of ``b`` (compacted) was known at or before the same row of ``a``."""
    if a is None or b is None or a.empty:
        return
    both = a.merge(b, on=keys, suffixes=("_a", "_b"))
    stamp_a = pd.to_datetime(both["knowledge_ts_a"], utc=True)
    stamp_b = pd.to_datetime(both["knowledge_ts_b"], utc=True)
    assert (stamp_b <= stamp_a).all()


def same_values(a: pd.DataFrame | None, b: pd.DataFrame | None, keys: list[str]) -> None:
    left, right = values(a, keys), values(b, keys)
    if left is None or right is None:
        assert left is None and right is None
        return
    pd.testing.assert_frame_equal(left, right, check_exact=True)


def test_the_partition_set_and_sequences_do_not_move(
    stores: tuple[StoreReader, StoreReader],
) -> None:
    plain, packed = stores
    assert stored_sessions(plain) == stored_sessions(packed) == SESSIONS
    assert list(plain.dates(RESIDUAL_RETURNS)) == list(packed.dates(RESIDUAL_RETURNS))
    for residuals in (False, True):
        want = outcome_seqs(plain, [*SESSIONS, date(2020, 1, 1)], residuals)
        assert want and want == outcome_seqs(packed, [*SESSIONS, date(2020, 1, 1)], residuals)
    assert residual_seqs(plain, SESSIONS) == residual_seqs(packed, SESSIONS) != {}
    assert plain._backend.tables.visible_seq() == packed._backend.tables.visible_seq()


@pytest.mark.parametrize("as_of", cuts(), ids=lambda c: "none" if c is None else c.isoformat())
def test_readers_return_the_same_values_at_every_as_of(
    stores: tuple[StoreReader, StoreReader], as_of: datetime | None
) -> None:
    plain, packed = stores
    stored: dict[str, Any] = {}
    for name, reader in (("plain", plain), ("packed", packed)):
        frame = read_stored(reader, SESSIONS, as_of)
        stored[name] = frame
    # the stored view, by key (a key is latest-run-wins, so the rewrites cannot show)
    keys = [*KEY, "window_end"]
    same_values(stored["plain"], stored["packed"], keys)
    never_later(stored["plain"], stored["packed"], keys)
    for horizon, benchmark in ((2, "SPY"), (6, "SPY"), (2, "QQQ")):
        outs: list[Any] = []
        for reader in (plain, packed):
            try:
                outs.append(read_outcomes(reader, horizon, SESSIONS, benchmark, as_of=as_of))
            except Exception as error:
                outs.append(type(error).__name__)
        if isinstance(outs[0], str):
            assert outs[0] == outs[1]
            continue
        same_values(outs[0], outs[1], KEY)
        never_later(outs[0], outs[1], KEY)
        if stored["plain"] is not None:
            sel = [select_outcomes(stored[n], horizon, SESSIONS, benchmark, as_of)
                   for n in ("plain", "packed")]  # fmt: skip
            same_values(sel[0], sel[1], KEY)
            never_later(sel[0], sel[1], KEY)
    if as_of is None:
        return
    for residuals in (False, True):
        a, na = outcome_stamps(plain, SESSIONS, as_of, names_for=(2, 6), residuals=residuals)
        b, nb = outcome_stamps(packed, SESSIONS, as_of, names_for=(2, 6), residuals=residuals)
        assert set(a) == set(b) and na == nb
        assert all(b[k] <= a[k] for k in a)
    ka, kb = outcome_known(plain, SESSIONS, as_of), outcome_known(packed, SESSIONS, as_of)
    assert set(ka) == set(kb) and all(kb[k] <= ka[k] for k in ka)
    ra, rb = residual_known(plain, SESSIONS, as_of), residual_known(packed, SESSIONS, as_of)
    assert set(ra) == set(rb) and all(rb[k] <= ra[k] for k in ra)


@pytest.mark.parametrize("as_of", cuts(), ids=lambda c: "none" if c is None else c.isoformat())
def test_residual_rows_are_the_same_at_every_as_of(
    stores: tuple[StoreReader, StoreReader], as_of: datetime | None
) -> None:
    plain, packed = stores
    a, b = read_residuals(plain, SESSIONS, as_of), read_residuals(packed, SESSIONS, as_of)
    keys = ["session_date", "instrument_id", "horizon_sessions"]
    same_values(a, b, keys)
    never_later(a, b, keys)


def test_a_compacted_partition_really_dropped_runs_and_a_second_pass_is_a_no_op(
    tmp_path: Path,
) -> None:
    backend = build(tmp_path)
    assert compact(backend) == 4
    assert backend.tables.partition_runs(FORWARD_RETURNS, S1) != [f"f1-{i}" for i in range(6)]
    assert compact(backend) == 0


def test_a_value_identical_rewrite_no_longer_restamps_its_rows(
    stores: tuple[StoreReader, StoreReader],
) -> None:
    """Decision 3: S2 was only ever re-written identically, so its rows are first-known at run 1."""
    plain, packed = stores
    late = known(30)
    assert outcome_known(plain, [S2], late)[(S2, 2)] > outcome_known(packed, [S2], late)[(S2, 2)]
    assert outcome_known(packed, [S2], late)[(S2, 2)] == known(2)
