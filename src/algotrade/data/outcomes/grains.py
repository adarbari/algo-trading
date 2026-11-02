"""The outcome grains a harness reads and the one dispatch between them: the price windows
(``STOCK``, ``forward_returns@v2``), the option trades (``CHAIN``, ``structure_pnl@v2``) and the
share paths (``SHARE_PATH``, ``share_path@v1``), each behind the same ``GrainReads`` (the commit
sequences, the stamps, the stored rows, their selection at a hold, the missing-data error, the
licence columns and the columns a leg keeps). A run reads one grain for its own plans and, for a
position baseline valued on another, one more; ``reads_of`` picks the reads by grain name, so no
caller switches on a kind. Which grain an outcome is on is the config's (``grain_of`` in
``services/evaluation/cross_section/baselines/variant.py``); this module only reads.

``keys``: the (``position_key``, benchmark) of the run's share setups, read by the share path
grain alone (see ``share_path.py``); the other grains hold one row per name and ignore it.
"""

from abc import ABC, abstractmethod
from collections.abc import Collection, Iterable, Sequence
from datetime import date, datetime

import pandas as pd

from algotrade.core.model.errors import MissingDataError
from algotrade.data.outcomes.chain import (
    CHAIN_COLUMNS,
    chain_seqs,
    chain_stamps,
    licence_frames,
    missing_chain,
    read_chain_stored,
    select_chain,
)
from algotrade.data.outcomes.reading import (
    OUTCOME_FIELDS,
    missing_outcomes,
    outcome_seqs,
    outcome_stamps,
    read_stored,
    select_outcomes,
)
from algotrade.data.outcomes.share_path import (
    SHARE_COLUMNS,
    ShareKeys,
    missing_share_path,
    read_share_path_stored,
    select_share_path,
    share_path_licences,
    share_path_seqs,
    share_path_stamps,
)
from algotrade.storage.tables.readers import StoreReader

STOCK, CHAIN, SHARE_PATH = "stock", "chain", "share_path"
GRAINS = (STOCK, CHAIN, SHARE_PATH)
STOCK_COLUMNS = ("instrument_id", "horizon_sessions", *OUTCOME_FIELDS)
BENCHMARK = "SPY"  # the stock grain's rows are read over SPY for every edge

Stamps = tuple[dict[tuple[date, int], datetime], dict[tuple[date, int], frozenset[str]]]


class GrainReads(ABC):
    """One grain's reads under the signatures every caller uses."""

    grain: str
    columns: tuple[str, ...]  # what a leg keeps of each selected row

    @abstractmethod
    def seqs(
        self, reader: StoreReader, sessions: Iterable[date], residuals: bool = False
    ) -> dict[date, int]:
        """The commit sequence of each start session's partition (``residuals``: stock only)."""

    @abstractmethod
    def stamps(
        self,
        reader: StoreReader,
        sessions: Iterable[date],
        as_of: datetime,
        names_for: Collection[int] = (),
        residuals: bool = False,
    ) -> Stamps:
        """Per (S, hold) the latest ``knowledge_ts`` known by ``as_of`` and the names asked for."""

    @abstractmethod
    def read_stored(
        self, reader: StoreReader, sessions: Sequence[date], as_of: datetime | None = None
    ) -> pd.DataFrame | None:
        """The stored rows of the sessions' partitions, every hold (None: none stored)."""

    @abstractmethod
    def at_hold(
        self,
        frame: pd.DataFrame,
        horizon: int,
        sessions: Sequence[date],
        as_of: datetime | None = None,
    ) -> pd.DataFrame:
        """The ``horizon`` rows of ``frame`` for ``sessions``, shaped as the price outcomes."""

    @abstractmethod
    def missing(self, sessions: Sequence[date]) -> MissingDataError:
        """The error of sessions none of which has a stored row."""

    @abstractmethod
    def licence(
        self, reader: StoreReader, sessions: Iterable[date], as_of: datetime | None = None
    ) -> list[pd.DataFrame]:
        """The ``licence`` column of the grain's partitions over the span of ``sessions``."""


class _Stock(GrainReads):
    grain, columns = STOCK, STOCK_COLUMNS

    def seqs(
        self, reader: StoreReader, sessions: Iterable[date], residuals: bool = False
    ) -> dict[date, int]:
        return outcome_seqs(reader, sessions, residuals)

    def stamps(
        self,
        reader: StoreReader,
        sessions: Iterable[date],
        as_of: datetime,
        names_for: Collection[int] = (),
        residuals: bool = False,
    ) -> Stamps:
        return outcome_stamps(reader, sessions, as_of, BENCHMARK, names_for, residuals)

    def read_stored(
        self, reader: StoreReader, sessions: Sequence[date], as_of: datetime | None = None
    ) -> pd.DataFrame | None:
        return read_stored(reader, sessions, as_of)

    def at_hold(
        self, frame: pd.DataFrame, horizon: int, sessions: Sequence[date],
        as_of: datetime | None = None,
    ) -> pd.DataFrame:  # fmt: skip
        return select_outcomes(frame, horizon, sessions, BENCHMARK, as_of)

    def missing(self, sessions: Sequence[date]) -> MissingDataError:
        return missing_outcomes(sessions)

    def licence(
        self, reader: StoreReader, sessions: Iterable[date], as_of: datetime | None = None
    ) -> list[pd.DataFrame]:
        return licence_frames(reader, False, sessions, as_of)


class _Chain(GrainReads):
    grain, columns = CHAIN, tuple(CHAIN_COLUMNS)

    def seqs(
        self, reader: StoreReader, sessions: Iterable[date], residuals: bool = False
    ) -> dict[date, int]:
        return chain_seqs(reader, sessions)

    def stamps(
        self,
        reader: StoreReader,
        sessions: Iterable[date],
        as_of: datetime,
        names_for: Collection[int] = (),
        residuals: bool = False,
    ) -> Stamps:
        return chain_stamps(reader, sessions, as_of, names_for)

    def read_stored(
        self, reader: StoreReader, sessions: Sequence[date], as_of: datetime | None = None
    ) -> pd.DataFrame | None:
        return read_chain_stored(reader, sessions, as_of)

    def at_hold(
        self, frame: pd.DataFrame, horizon: int, sessions: Sequence[date],
        as_of: datetime | None = None,
    ) -> pd.DataFrame:  # fmt: skip
        return select_chain(frame, horizon, sessions, as_of)

    def missing(self, sessions: Sequence[date]) -> MissingDataError:
        return missing_chain(sessions)

    def licence(
        self, reader: StoreReader, sessions: Iterable[date], as_of: datetime | None = None
    ) -> list[pd.DataFrame]:
        return licence_frames(reader, True, sessions, as_of)


class _SharePath(GrainReads):
    grain, columns = SHARE_PATH, SHARE_COLUMNS

    def __init__(self, keys: ShareKeys) -> None:
        self.keys = keys

    def seqs(
        self, reader: StoreReader, sessions: Iterable[date], residuals: bool = False
    ) -> dict[date, int]:
        return share_path_seqs(reader, sessions)

    def stamps(
        self,
        reader: StoreReader,
        sessions: Iterable[date],
        as_of: datetime,
        names_for: Collection[int] = (),
        residuals: bool = False,
    ) -> Stamps:
        return share_path_stamps(reader, sessions, as_of, self.keys, names_for)

    def read_stored(
        self, reader: StoreReader, sessions: Sequence[date], as_of: datetime | None = None
    ) -> pd.DataFrame | None:
        return read_share_path_stored(reader, sessions, self.keys, as_of)

    def at_hold(
        self, frame: pd.DataFrame, horizon: int, sessions: Sequence[date],
        as_of: datetime | None = None,
    ) -> pd.DataFrame:  # fmt: skip
        return select_share_path(frame, horizon, sessions, as_of)

    def missing(self, sessions: Sequence[date]) -> MissingDataError:
        return missing_share_path(sessions)

    def licence(
        self, reader: StoreReader, sessions: Iterable[date], as_of: datetime | None = None
    ) -> list[pd.DataFrame]:
        return share_path_licences(reader, sessions, self.keys, as_of)


def reads_of(grain: str, keys: ShareKeys = ()) -> GrainReads:
    """The reads of ``grain`` (``keys``: the share setups' of the run, for ``SHARE_PATH``)."""
    if grain == SHARE_PATH:
        return _SharePath(keys)
    if grain == CHAIN:
        return _Chain()
    if grain == STOCK:
        return _Stock()
    raise ValueError(f"no outcome grain {grain!r}: one of {GRAINS}")
