"""``ScreenCache``: a screener's run at a session, computed once for a whole multi-edge
evaluation and read back by every other edge that screens the same config (the baselines
``size_small`` and ``momentum_12_1`` are in dozens of edges). One file per (owner, config hash,
session) in a scratch directory the run's caller creates and deletes, so it is shared by the
worker processes of ``--jobs`` and bounded by the disk, not by memory. An entry is the ranked
run, the reads the screen logged for its session and the commit sequence it started at
(``RecordingReader.capture`` / ``replay``): a hit logs what the computation would have, so leg
reuse (ADR 0063) cannot tell it from a computed screen. Only configs more than one edge of the
run uses are kept (``shared_screens``); a session lost to a missing table is never cached.

The pickles are the run's own scratch files, written atomically (rename) in a directory only
its caller can read: they are not a store, never outlive the run and are never read by another."""

import os
import pickle
import tempfile
from collections import Counter
from collections.abc import Collection, Iterable
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from algotrade.data import CapturedReads
from algotrade.services.evaluation.cross_section.picks import RankedRun


@dataclass(frozen=True)
class CachedScreen:
    run: RankedRun
    reads: CapturedReads


class ScreenCache:
    """The cached screens under ``root`` for the (owner, config hash) pairs in ``shared``."""

    def __init__(self, root: Path, shared: Collection[tuple[str, str]]) -> None:
        self._root = root
        self._shared = frozenset(shared)

    def wants(self, owner: str, config_hash: str) -> bool:
        return (owner, config_hash) in self._shared

    def _path(self, owner: str, config_hash: str, day: date) -> Path:
        return self._root / owner / config_hash[:24] / f"{day.isoformat()}.pkl"

    def get(self, owner: str, config_hash: str, day: date) -> CachedScreen | None:
        if not self.wants(owner, config_hash):
            return None
        try:
            found = pickle.loads(self._path(owner, config_hash, day).read_bytes())
        except (OSError, EOFError, pickle.UnpicklingError):
            return None  # not computed yet (or a stray partial file): compute it
        return found if isinstance(found, CachedScreen) else None

    def put(self, owner: str, config_hash: str, day: date, screen: CachedScreen) -> None:
        if not self.wants(owner, config_hash):
            return
        path = self._path(owner, config_hash, day)
        scratch: str | None = None
        try:  # optional: a full disk or a pickling error costs a recompute, never the edge
            path.parent.mkdir(parents=True, exist_ok=True)
            handle, scratch = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
            with os.fdopen(handle, "wb") as out:
                pickle.dump(screen, out, protocol=pickle.HIGHEST_PROTOCOL)
            Path(scratch).replace(path)
        except (OSError, pickle.PicklingError):
            if scratch is not None:
                Path(scratch).unlink(missing_ok=True)


def shared_screens(uses: Iterable[tuple[str, str]]) -> frozenset[tuple[str, str]]:
    """The (owner, config hash) pairs that more than one use names: what is worth caching."""
    return frozenset(pair for pair, n in Counter(uses).items() if n > 1)
