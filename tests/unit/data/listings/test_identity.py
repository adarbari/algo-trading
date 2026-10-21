"""``memoised_identity``: the identity of a session is computed once per (reader, published
sequence, session, as_of) and again after a publish; the memo stays small."""

import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date

import pandas as pd

from algotrade.data.listings import identity
from algotrade.data.listings.identity import HistoricalIdentity, memoised_identity

S = date(2012, 6, 1)


@dataclass
class _Reader:
    seq: int = 1
    own_run: str | None = None

    def version(self) -> tuple[str, int]:
        return ("live", self.seq)


def _computer(calls: list[int]):  # type: ignore[no-untyped-def]
    def compute() -> HistoricalIdentity | None:
        calls.append(1)
        return HistoricalIdentity(S, pd.DataFrame(), frozenset())

    return compute


def test_one_computation_per_published_sequence_and_session() -> None:
    reader, calls = _Reader(), []
    compute = _computer(calls)
    first = memoised_identity(reader, S, None, compute)  # type: ignore[arg-type]
    assert memoised_identity(reader, S, None, compute) is first  # type: ignore[arg-type]
    assert len(calls) == 1
    memoised_identity(reader, date(2012, 6, 4), None, compute)  # type: ignore[arg-type]
    assert len(calls) == 2  # another session
    reader.seq = 2  # a commit published: the earlier entry is unreachable
    assert memoised_identity(reader, S, None, compute) is not first  # type: ignore[arg-type]
    assert len(calls) == 3
    mine = _Reader(own_run="r")  # pending writes do not move visible_seq: never memoised
    memoised_identity(mine, S, None, compute)  # type: ignore[arg-type]
    memoised_identity(mine, S, None, compute)  # type: ignore[arg-type]
    assert len(calls) == 5


def test_the_memo_is_bounded_and_keeps_none() -> None:
    reader, calls = _Reader(), []
    for k in range(identity._MEMO_SIZE + 3):
        memoised_identity(reader, date(2012, 1, 1 + k), None, _computer(calls))  # type: ignore[arg-type]
    assert len(identity._memo) == identity._MEMO_SIZE
    assert memoised_identity(reader, S, None, lambda: None) is None  # type: ignore[arg-type]
    assert memoised_identity(reader, S, None, _computer(calls)) is None  # type: ignore[arg-type]


def test_the_memo_is_guarded_by_a_lock() -> None:
    assert isinstance(identity._lock, type(threading.Lock()))
    reader, calls = _Reader(), []
    with ThreadPoolExecutor(4) as pool:
        list(
            pool.map(
                lambda k: memoised_identity(
                    reader, date(2012, 1, 1 + k % 5), None, _computer(calls)
                ),
                range(40),
            )
        )  # type: ignore[arg-type]
    assert len(identity._memo) <= identity._MEMO_SIZE
