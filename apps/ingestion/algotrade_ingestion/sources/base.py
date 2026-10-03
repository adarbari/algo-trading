"""The source contract every vendor adapter implements (roadmap phase 0.4).

A source does two things, kept separate so raw payloads can be stored before parsing and
replayed later without the network:

    fetch(request)              -> raw bytes exactly as received, or None ("nothing there")
    normalize(request, payload) -> canonical frames keyed by storage table, or None

Jobs own everything else: scheduling, rate-limit-aware fan-out, raw storage, stamping the
point-in-time columns, staging, publishing and run records.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from typing import Protocol, runtime_checkable

import pandas as pd


@dataclass(frozen=True)
class FetchRequest:
    """What to fetch. ``key`` is source-specific: a symbol, a date, ``dataset/SYMBOL``…"""

    key: str
    instrument_id: str | None = None
    session_date: date | None = None


@dataclass(frozen=True)
class Normalized:
    """Canonical rows for one payload, without point-in-time columns (jobs add those).

    ``session_date`` is the single session a snapshot payload describes (an option chain, a
    grouped-daily file). It is ``None`` for multi-session payloads (a price history), whose
    frames carry a ``ts`` per row instead.
    """

    session_date: date | None
    # Storage-ready, except that tables keyed by a vendor ticker carry ``symbol`` instead of
    # ``instrument_id``: the job resolves ids through the reference (ADR 0018).
    tables: Mapping[str, pd.DataFrame]
    notes: Mapping[str, int] = field(default_factory=dict)  # e.g. {"nonstandard_series": 3}
    # Intermediate frames a job composes into storage tables (e.g. listings + option
    # underlyings + index members -> instruments/reference). Not stored as-is.
    parsed: Mapping[str, pd.DataFrame] = field(default_factory=dict)


@runtime_checkable
class Source(Protocol):
    name: str  # stored in the ``source`` column and the raw-store path
    dataset: str  # raw-store dataset name, e.g. "option_chain"

    def fetch(self, request: FetchRequest) -> bytes | None: ...

    def normalize(self, request: FetchRequest, payload: bytes) -> Normalized | None: ...
