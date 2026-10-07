"""The macro release registry (``config/site/events/releases.toml``, ADR 0050): the releases the
event study calendars (CPI, employment, FOMC, ...) and where each one's dates come from.

Each ``[[release]]`` is a ``key`` (its instrument id is ``MACRO:<key>``), a ``name``, a
``source`` (``fred``: the dates of FRED release ``release_id``; ``rule``: the
``nth_business_day`` of the month, computed with the exchange calendar; ``dates``: an explicit
sorted list of release dates, FOMC's, typed from the Fed's calendar), the release time of
day ``time_et`` (New York) and its ``terms``. The loader checks shape and uniqueness; the
dates, and the UTC instant of ``time_et``, are the ``macro-calendar`` task's.
"""

import re
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Any, Protocol

from algotrade.config.site.fields import Table, reject_secrets
from algotrade.core.model.errors import ConfigurationError
from algotrade.core.model.instruments import macro_id

FOLDER = "events"
NAME = "releases"
SOURCES = ("fred", "rule", "dates")
KEYS = (
    "key",
    "name",
    "source",
    "release_id",
    "nth_business_day",
    "exceptions",
    "dates",
    "time_et",
    "terms",
)
MAX_BUSINESS_DAY = 23  # a month has at least 20 sessions; 23 is the most it can hold
_KEY = re.compile(r"^[A-Z][A-Z0-9_]*$")
_TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


class Documents(Protocol):
    """What the loader needs from a config store (``ConfigStore``)."""

    def load(self, scope: str, kind: str, name: str) -> Mapping[str, Any] | None: ...


@dataclass(frozen=True)
class MacroRelease:
    """One ``[[release]]``. ``release_id`` is set for ``source = "fred"``, ``nth_business_day``
    for ``source = "rule"``; ``time_et`` is ``"HH:MM"`` in America/New_York. ``exceptions``
    (a rule release only): ``"YYYY-MM"`` -> the date the rule misses that month (the actual
    release date, in that month). ``dates`` (``source = "dates"``): the release dates, sorted
    and unique."""

    key: str
    name: str
    source: str
    time_et: str
    terms: str
    release_id: int | None = None
    nth_business_day: int | None = None
    exceptions: Mapping[str, date] = field(default_factory=dict)
    dates: tuple[date, ...] = ()

    @property
    def instrument_id(self) -> str:
        """``MACRO:<key>``."""
        return macro_id(self.key)

    @property
    def clock(self) -> time:
        """``time_et`` as a time of day."""
        return time.fromisoformat(self.time_et)


@dataclass(frozen=True)
class MacroReleases:
    """``releases.toml``: the releases in file order (none without the file)."""

    releases: tuple[MacroRelease, ...] = ()

    @classmethod
    def from_document(cls, doc: Mapping[str, Any] | None) -> "MacroReleases":
        where = f"{FOLDER}/{NAME}.toml"
        reject_secrets(doc or {}, where)
        root = Table(doc, where)
        root.only(("release",))
        raw = root.raw("release") or []
        if not isinstance(raw, list) or not all(isinstance(r, Mapping) for r in raw):
            raise ConfigurationError(f"{where} release: expected a list of tables ([[release]])")
        found = tuple(_release(r, where, i) for i, r in enumerate(raw))
        repeated = sorted(k for k, n in Counter(r.key for r in found).items() if n > 1)
        if repeated:
            raise ConfigurationError(f"{where}: keys declared more than once: {repeated}")
        return cls(found)

    @property
    def keys(self) -> tuple[str, ...]:
        return tuple(r.key for r in self.releases)

    @property
    def fred(self) -> tuple[MacroRelease, ...]:
        """The releases whose dates are fetched from FRED."""
        return tuple(r for r in self.releases if r.source == "fred")


def load_macro_releases(configs: Documents) -> MacroReleases:
    """``config/site/events/releases.toml``; missing: no releases."""
    return MacroReleases.from_document(configs.load("site", FOLDER, NAME))


def _required(t: Table, key: str) -> None:
    if t.raw(key) is None:
        raise ConfigurationError(f"{t.where} {key}: required")


def _release(doc: Mapping[str, Any], file: str, index: int) -> MacroRelease:
    t = Table(doc, f"{file} [[release]][{index}]")
    t.only(KEYS)
    for key in ("key", "name", "source", "time_et", "terms"):
        _required(t, key)
    key = t.text("key", "")
    if not _KEY.match(key):
        raise ConfigurationError(f"{t.where} key: expected {_KEY.pattern}, got {key!r}")
    where = f"{file} [[release]] {key}"
    t = Table(doc, where)
    source = t.choice("source", "", SOURCES)
    time_et = t.text("time_et", "")
    if not _TIME.match(time_et):
        raise ConfigurationError(f"{where} time_et: expected HH:MM (New York), got {time_et!r}")
    release_id, nth = _source_keys(t, source)
    return MacroRelease(
        key=key,
        name=" ".join(t.text("name", "").split()),
        source=source,
        time_et=time_et,
        terms=" ".join(t.text("terms", "").split()),
        release_id=release_id,
        nth_business_day=nth,
        exceptions=_exceptions(t, source),
        dates=_dates(t, source),
    )


def _source_keys(t: Table, source: str) -> tuple[int | None, int | None]:
    """``(release_id, nth_business_day)``: the one a source needs, and not the other (a
    ``dates`` release needs neither)."""
    needs = {"fred": "release_id", "rule": "nth_business_day", "dates": ""}[source]
    for key in ("release_id", "nth_business_day"):
        if key != needs and t.raw(key) is not None:
            raise ConfigurationError(f"{t.where} {key}: not used by source = {source!r}")
    if not needs:
        return None, None
    _required(t, needs)
    value = t.integer(needs, 0, 1)
    if needs == "nth_business_day" and value > MAX_BUSINESS_DAY:
        raise ConfigurationError(
            f"{t.where} nth_business_day: expected 1 to {MAX_BUSINESS_DAY}, got {value}"
        )
    return (value, None) if source == "fred" else (None, value)


def _dates(t: Table, source: str) -> tuple[date, ...]:
    """``dates``: a non-empty, sorted, unique list of TOML dates, for ``source = "dates"`` only."""
    raw = t.raw("dates")
    if source != "dates":
        if raw is not None:
            raise ConfigurationError(f"{t.where} dates: not used by source = {source!r}")
        return ()
    if not isinstance(raw, list) or not raw:
        raise ConfigurationError(f"{t.where} dates: required, a non-empty list of dates")
    for day in raw:
        if not isinstance(day, date) or isinstance(day, datetime):
            raise ConfigurationError(f"{t.where} dates: expected dates (YYYY-MM-DD), got {day!r}")
    if len(set(raw)) != len(raw):
        repeated = sorted(d for d, n in Counter(raw).items() if n > 1)
        raise ConfigurationError(f"{t.where} dates: repeated {repeated}")
    if raw != sorted(raw):
        raise ConfigurationError(f"{t.where} dates: not sorted ascending")
    return tuple(raw)


def _exceptions(t: Table, source: str) -> dict[str, date]:
    """``exceptions``: ``"YYYY-MM" = <date in that month>``, for a rule release only."""
    raw = t.raw("exceptions")
    if raw is None:
        return {}
    if source != "rule":
        raise ConfigurationError(f"{t.where} exceptions: not used by source = {source!r}")
    if not isinstance(raw, Mapping):
        raise ConfigurationError(f'{t.where} exceptions: expected a table ("YYYY-MM" = date)')
    for month, day in raw.items():
        if not isinstance(month, str) or not _MONTH.match(month):
            raise ConfigurationError(f"{t.where} exceptions: expected YYYY-MM keys, got {month!r}")
        if not isinstance(day, date) or isinstance(day, datetime):
            raise ConfigurationError(f"{t.where} exceptions {month}: expected a date, got {day!r}")
        if day.strftime("%Y-%m") != month:
            raise ConfigurationError(f"{t.where} exceptions {month}: {day} is not in that month")
    return dict(sorted(raw.items()))
