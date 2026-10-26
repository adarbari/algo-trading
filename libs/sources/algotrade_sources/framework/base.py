"""The source contract every vendor adapter implements (roadmap phase 0.4).

A source does two things, kept separate so raw payloads can be stored before parsing and
replayed later without the network:

    fetch(request)              -> raw bytes exactly as received, or None ("nothing there")
    normalize(request, payload) -> canonical frames keyed by storage table, or None

Most sources are stateless HTTP clients. A ``SessionSource`` (IB Gateway) holds a stateful
connection instead: built unconnected by the registry, ``probe``d cheaply before a workflow
runs it, and ``opened`` / closed around the work by the task (``opened``), whatever happens.

Tasks own everything else (through ``tasks/framework/run.py``): scheduling, rate-limit-aware
fan-out, raw storage, stamping the point-in-time columns, staging, publishing and run records.
"""

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
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


class Access(StrEnum):
    """What a vendor lets one key do with an endpoint (``framework/access.py`` classifies it)."""

    ALLOWED = "ALLOWED"
    DENIED = "DENIED"
    LIMITED = "LIMITED"


@dataclass(frozen=True)
class Verdict:
    access: Access
    http_code: int
    rows: int  # records in the payload (0 when there was none)
    note: str  # why, in fixed words, never the vendor's body


@runtime_checkable
class ProbeSource(Source, Protocol):
    """A vendor's access probe (``AccessProbe``): ``endpoints`` names what it asks (the name
    stored in ``analyst/vendor_access``), ``probe`` makes ONE un-retried request for it."""

    endpoints: Mapping[str, str]

    def probe(self, endpoint: str) -> Verdict: ...


@runtime_checkable
class WindowedSource(Source, Protocol):
    """A source whose data for a date window takes several requests (e.g. one per event kind).

    ``window_requests`` -> ``(label, request)`` pairs; the label names the item and raw key."""

    def window_requests(
        self, start: date, end: date, session: date
    ) -> list[tuple[str, FetchRequest]]: ...


@runtime_checkable
class DirectorySource(Source, Protocol):
    """A symbol directory published as several files: ``listing_keys`` (request keys whose
    parsed frames, keyed the same, are concatenated into all listings) and ``options_key``
    (the parsed frame of symbols with listed options)."""

    listing_keys: tuple[str, ...]
    options_key: str


@runtime_checkable
class HoldingsSource(Source, Protocol):
    """An issuer's published ETF holdings: one adapter per issuer behind one shape.

    The request ``directory_key`` returns ``parsed["funds"]`` (``symbol``, ``name``): the ETFs
    the issuer publishes today. Any other request key is one of those tickers; it returns
    ``parsed["holdings"]`` (columns ``HOLDING_COLUMNS`` in ``framework/holdings.py``, weights
    as fractions of the fund) with ``session_date`` set to the issuer's as-of date. A fund the
    issuer has no file for is ``fetch`` -> ``None``. ``cadence_days`` is how often the issuer's
    data changes (1: daily files; SEC N-PORT: quarterly), so tasks never reread sooner.
    ``scope_limited`` marks a universe-wide fallback that costs a lot to read for every fund
    (N-PORT: thousands of funds, megabytes each): tasks read it only for the funds in scope."""

    directory_key: str
    cadence_days: int
    scope_limited: bool


@runtime_checkable
class Throttled(Protocol):
    """A source whose vendor can be asked to pause (all processes share the pause)."""

    def cool_down(self, seconds: float) -> None: ...


class SessionUnavailableError(ConnectionError):
    """A session source cannot connect (gateway down, refused, handshake timed out)."""


class TransientFetchError(RuntimeError):
    """The vendor did not answer this request (a timeout, a pacing or connectivity error):
    NOT "no data". Retrying later may succeed; a task never records it as an empty answer."""


@runtime_checkable
class SessionSource(Source, Protocol):
    """A source over a stateful session (a socket to a local gateway), not HTTP requests.

    ``probe`` -> why the session cannot be opened now (``None``: it can), without opening it
    (a TCP check; workflows skip the task with that reason). ``open`` connects, raising
    ``SessionUnavailableError``; ``close`` disconnects and never raises."""

    def probe(self) -> str | None: ...

    def open(self) -> None: ...

    def close(self) -> None: ...


@contextmanager
def opened[S: SessionSource](source: S) -> Iterator[S]:
    """Open ``source`` for the block and always close it afterwards (the one lifecycle)."""
    source.open()
    try:
        yield source
    finally:
        source.close()


class FixtureDataset(Protocol):
    """One committed fixture dataset: its name, what it is, its symbols and tags."""

    @property
    def name(self) -> str: ...

    @property
    def description(self) -> str: ...

    @property
    def symbols(self) -> tuple[str, ...]: ...

    @property
    def shares(self) -> Mapping[str, float]:
        """Shares outstanding per symbol, for the datasets that declare them (else empty)."""
        ...

    @property
    def tags(self) -> tuple[str, ...]: ...


@runtime_checkable
class FixtureSource(Source, Protocol):
    """A source over committed fixture files (the golden datasets), not a vendor: what the
    files hold, an integrity check, and how to regenerate them."""

    def datasets(self) -> Mapping[str, FixtureDataset]: ...

    def verify(self) -> list[str]:
        """Integrity problems; empty when every file matches its checksum."""
        ...

    def build(self) -> list[str]: ...


@dataclass(frozen=True)
class HistorySession:
    """One session of a folder of bought history files: where it is and a checksum of its main
    file (the zip member's CRC and size), so an import knows a session it already holds."""

    session: date
    location: str  # the zip's name
    checksum: str
    complete: bool  # every kind of file the vendor ships for a session is there


@runtime_checkable
class HistoryFileSource(Source, Protocol):
    """A source over bought files in a folder (ADR 0084), not a vendor API: the sessions the
    folder holds, one session's frames, and the one-off stock history."""

    def sessions(self) -> list[HistorySession]: ...

    def read(self, session: date) -> Normalized:
        """One session's frames by table, with the day's quality counts in ``notes``."""
        ...

    def stock_history(self) -> Normalized | None:
        """The vendor's dividends and splits (frames carry ``ex_date``), or ``None``."""
        ...
