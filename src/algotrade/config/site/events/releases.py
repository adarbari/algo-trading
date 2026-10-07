"""The macro release registry (``config/site/events/releases.toml``, ADR 0050): the releases the
event study calendars (CPI, employment, FOMC, ...) and where each one's dates come from.

Each ``[[release]]`` is a ``key`` (its instrument id is ``MACRO:<key>``), a ``name``, a
``source`` (``fred``: the dates of FRED release ``release_id``; ``rule``: the
``nth_business_day`` of the month, computed with the exchange calendar), the release time of
day ``time_et`` (New York) and its ``terms``. The loader checks shape and uniqueness; the
dates, and the UTC instant of ``time_et``, are the ``macro-calendar`` task's.
"""

import re
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import time
from typing import Any, Protocol

from algotrade.config.site.fields import Table, reject_secrets
from algotrade.core.model.errors import ConfigurationError
from algotrade.core.model.instruments import macro_id

FOLDER = "events"
NAME = "releases"
SOURCES = ("fred", "rule")
KEYS = ("key", "name", "source", "release_id", "nth_business_day", "time_et", "terms")
MAX_BUSINESS_DAY = 23  # a month has at least 20 sessions; 23 is the most it can hold
_KEY = re.compile(r"^[A-Z][A-Z0-9_]*$")
_TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class Documents(Protocol):
    """What the loader needs from a config store (``ConfigStore``)."""

    def load(self, scope: str, kind: str, name: str) -> Mapping[str, Any] | None: ...


@dataclass(frozen=True)
class MacroRelease:
    """One ``[[release]]``. ``release_id`` is set for ``source = "fred"``, ``nth_business_day``
    for ``source = "rule"``; ``time_et`` is ``"HH:MM"`` in America/New_York."""

    key: str
    name: str
    source: str
    time_et: str
    terms: str
    release_id: int | None = None
    nth_business_day: int | None = None

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
    )


def _source_keys(t: Table, source: str) -> tuple[int | None, int | None]:
    """``(release_id, nth_business_day)``: the one a source needs, and not the other."""
    own, other = (
        ("release_id", "nth_business_day")
        if source == "fred"
        else ("nth_business_day", "release_id")
    )
    if t.raw(other) is not None:
        raise ConfigurationError(f"{t.where} {other}: not used by source = {source!r}")
    _required(t, own)
    value = t.integer(own, 0, 1)
    if own == "nth_business_day" and value > MAX_BUSINESS_DAY:
        raise ConfigurationError(
            f"{t.where} nth_business_day: expected 1 to {MAX_BUSINESS_DAY}, got {value}"
        )
    return (value, None) if source == "fred" else (None, value)
