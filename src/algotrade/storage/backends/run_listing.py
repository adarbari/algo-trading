"""The runs directory's file stems, listed once per generation of the directory.

``LocalRuns.find`` and ``find_many`` each used to scan the directory (``find_many``: one glob per
job, 92 globs over 28 000 files = 1.8 s on the screener-runs page). One sorted listing of
``(stem, session)`` serves every call until the directory changes: ``save`` is an atomic rename
into it, which moves its mtime (the ``generation`` stamp), so a listing is valid exactly while the
stamp is unchanged. A prefix is found by bisection, not by a scan of every stem.
"""

from __future__ import annotations

import threading
from bisect import bisect_left
from collections.abc import Callable, Iterator
from datetime import date
from pathlib import Path


class RunListing:
    """Sorted ``(stem, session)`` of every ``.json`` file in ``root``, listed again only when
    ``generation()`` changes. Thread-safe; the list is shared, never mutated, never handed out."""

    def __init__(
        self,
        root: Path,
        generation: Callable[[], tuple[int, int]],
        session_of: Callable[[str], date | None],
    ) -> None:
        self._root = root
        self._generation = generation
        self._session_of = session_of
        self._lock = threading.Lock()
        self._held: tuple[tuple[int, int], list[tuple[str, date | None]]] | None = None
        self.scans = 0  # directory listings made (a test reads it)

    def _entries(self) -> list[tuple[str, date | None]]:
        """The stamp is read before the listing, so a save during it leaves a stale stamp and the
        next call lists again. The lock spans the scan: concurrent callers share one."""
        stamp = self._generation()
        with self._lock:
            held = self._held
            if held is not None and held[0] == stamp:
                return held[1]
            entries = sorted(
                (stem, self._session_of(stem))
                for path in self._root.iterdir()
                if path.suffix == ".json" and (stem := path.stem)
            )
            self._held = (stamp, entries)
            self.scans += 1
            return entries

    def all(self) -> Iterator[tuple[str, date | None]]:
        return iter(self._entries())

    def prefixed(self, prefix: str) -> Iterator[tuple[str, date | None]]:
        """The entries whose stem starts with ``prefix``."""
        entries = self._entries()
        i = bisect_left(entries, prefix, key=lambda e: e[0])
        while i < len(entries) and entries[i][0].startswith(prefix):
            yield entries[i]
            i += 1
