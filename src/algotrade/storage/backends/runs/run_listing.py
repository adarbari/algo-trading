"""The runs directory's file stems, listed once per generation of the directory.

``LocalRuns.find`` and ``find_many`` each used to scan the directory (``find_many``: one glob per
job, 92 globs over 28 000 files = 1.8 s on the screener-runs page). One sorted listing of
``(stem, session)`` serves every call until the directory changes: ``save`` is an atomic rename
into it, which moves its mtime (the ``generation`` stamp), so a listing is valid exactly while the
stamp is unchanged. A prefix is found by bisection, not by a scan of every stem, and the stems
that carry no session (``services/jobs`` records) are indexed by the job their name implies once
per listing, so one job's lookup (``for_job``) costs O(log n + its matches), not a decode of every
name (the harness-runs page made 322 finds, 246 000 ``job_of_name`` calls, 1.4 s).
"""

from __future__ import annotations

import threading
from bisect import bisect_left
from collections.abc import Callable, Iterator
from datetime import date
from pathlib import Path

from algotrade.storage.runs import job_of_name

_Entries = list[tuple[str, date | None]]


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
        self._held: tuple[tuple[int, int], _Entries, dict[str | None, list[str]]] | None = None
        self.scans = 0  # directory listings made (a test reads it)

    def _held_listing(self) -> tuple[_Entries, dict[str | None, list[str]]]:
        """The sorted entries and, of those without a session, the stems by implied job (``None``
        for a name that implies no job). The stamp is read before the listing, so a save during it
        leaves a stale stamp and the next call lists again. The lock spans the scan: concurrent
        callers share one."""
        stamp = self._generation()
        with self._lock:
            held = self._held
            if held is not None and held[0] == stamp:
                return held[1], held[2]
            entries = sorted(
                (stem, self._session_of(stem))
                for path in self._root.iterdir()
                if path.suffix == ".json" and (stem := path.stem)
            )
            undated: dict[str | None, list[str]] = {}
            for stem, day in entries:
                if day is None:
                    undated.setdefault(job_of_name(stem), []).append(stem)
            self._held = (stamp, entries, undated)
            self.scans += 1
            return entries, undated

    def _entries(self) -> _Entries:
        return self._held_listing()[0]

    def all(self) -> Iterator[tuple[str, date | None]]:
        return iter(self._entries())

    def prefixed(self, prefix: str) -> Iterator[tuple[str, date | None]]:
        """The entries whose stem starts with ``prefix``."""
        entries = self._entries()
        i = bisect_left(entries, prefix, key=lambda e: e[0])
        while i < len(entries) and entries[i][0].startswith(prefix):
            yield entries[i]
            i += 1

    def for_job(self, job: str, prefix: str, session_date: date | None) -> list[str]:
        """The stems ``find(job, session_date)`` must open, in sorted order: the job's own dated
        stems (``prefix`` = ``safe(job)-``; of ``session_date`` when given) and the undated ones
        implying ``job`` or no job at all."""
        entries, undated = self._held_listing()
        i = bisect_left(entries, prefix, key=lambda e: e[0])
        stems: list[str] = []
        while i < len(entries) and entries[i][0].startswith(prefix):
            stem, day = entries[i]
            if day is not None and session_date in (None, day):
                stems.append(stem)
            i += 1
        stems.extend(undated.get(None, ()))
        stems.extend(undated.get(job, ()))
        return sorted(stems)
