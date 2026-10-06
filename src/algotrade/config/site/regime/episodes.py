"""The reference crash episodes (``config/site/regime/episodes.toml``, ADR 0047;
docs/market-regime-plan.md section 2): the twelve S&P 500 drawdowns of 19% or more since 1970,
each with its closing-basis ``peak`` and ``trough`` sessions, the S&P 500 and Nasdaq
drawdowns, the NBER recession months when there was one, what caused it, and ``known_from``
(the trough: the earliest session a feature about the episode may be non-null, since no
feature may know an episode's depth before it ended).

The loader checks shape, ordering (peak before trough, ``known_from`` not before the trough),
unique keys and non-empty text. That the dates agree with the dating in ``quant`` and with the
episode feature columns is a fitness test."""

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Protocol

from algotrade.config.site.fields import Table, reject_secrets
from algotrade.core.model.errors import ConfigurationError

FOLDER = "regime"
NAME = "episodes"
KINDS = ("recession", "shock")
KEYS = (
    "key",
    "peak",
    "trough",
    "spx_drawdown",
    "nasdaq_drawdown",
    "recession",
    "nber_start",
    "nber_end",
    "kind",
    "cause",
    "known_from",
    "notes",
)


class Documents(Protocol):
    """What the loader needs from a config store (``ConfigStore``)."""

    def load(self, scope: str, kind: str, name: str) -> Mapping[str, Any] | None: ...


@dataclass(frozen=True)
class Episode:
    """One drawdown. ``spx_drawdown`` / ``nasdaq_drawdown``: peak-to-trough fractions (zero or
    negative); ``recession``: an NBER recession overlaps it (``nber_start`` / ``nber_end``: its
    first and last months, as the first day of the month); ``kind``: ``recession`` or
    ``shock``."""

    key: str
    peak: date
    trough: date
    spx_drawdown: float
    nasdaq_drawdown: float
    recession: bool
    kind: str
    cause: str
    known_from: date
    notes: str
    nber_start: date | None = None
    nber_end: date | None = None


@dataclass(frozen=True)
class Episodes:
    """``episodes.toml``: the episodes in file order (none without the file)."""

    episodes: tuple[Episode, ...] = ()

    @classmethod
    def from_document(cls, doc: Mapping[str, Any] | None) -> "Episodes":
        where = f"{FOLDER}/{NAME}.toml"
        reject_secrets(doc or {}, where)
        root = Table(doc, where)
        root.only(("episode",))
        raw = root.raw("episode") or []
        if not isinstance(raw, list) or not all(isinstance(e, Mapping) for e in raw):
            raise ConfigurationError(f"{where} episode: expected a list of tables ([[episode]])")
        found = tuple(_episode(Table(e, f"{where} [[episode]][{i}]")) for i, e in enumerate(raw))
        repeated = sorted(k for k, n in Counter(e.key for e in found).items() if n > 1)
        if repeated:
            raise ConfigurationError(f"{where}: keys declared more than once: {repeated}")
        return cls(found)

    def by_key(self, key: str) -> Episode:
        found = next((e for e in self.episodes if e.key == key), None)
        if found is None:
            raise KeyError(f"no episode {key!r} in {FOLDER}/{NAME}.toml")
        return found


def load_episodes(configs: Documents) -> Episodes:
    """``config/site/regime/episodes.toml``; missing: no episodes."""
    return Episodes.from_document(configs.load("site", FOLDER, NAME))


def _line(t: Table, key: str) -> str:
    if t.raw(key) is None:
        raise ConfigurationError(f"{t.where} {key}: required")
    value = " ".join(t.text(key, "").split())
    if not value:
        raise ConfigurationError(f"{t.where} {key}: expected a non-empty string")
    return value


def _date(t: Table, key: str) -> date:
    value = t.raw(key)
    if not isinstance(value, date) or isinstance(value, datetime):
        raise ConfigurationError(f"{t.where} {key}: expected a date (YYYY-MM-DD), got {value!r}")
    return value


def _fraction(t: Table, key: str) -> float:
    if t.raw(key) is None:
        raise ConfigurationError(f"{t.where} {key}: required")
    value = t.number(key, 0.0)
    if not -1.0 <= value <= 0.0:
        raise ConfigurationError(f"{t.where} {key}: expected a fraction in [-1, 0], got {value!r}")
    return value


def _episode(t: Table) -> Episode:
    t.only(KEYS)
    recession = t.raw("recession")
    if not isinstance(recession, bool):
        raise ConfigurationError(f"{t.where} recession: expected true or false, got {recession!r}")
    nber = {k: _date(t, k) for k in ("nber_start", "nber_end") if t.raw(k) is not None}
    if recession != (len(nber) == 2) or (not recession and nber):
        raise ConfigurationError(f"{t.where}: a recession episode names nber_start and nber_end")
    e = Episode(
        key=_line(t, "key"),
        peak=_date(t, "peak"),
        trough=_date(t, "trough"),
        spx_drawdown=_fraction(t, "spx_drawdown"),
        nasdaq_drawdown=_fraction(t, "nasdaq_drawdown"),
        recession=recession,
        kind=t.choice("kind", "", KINDS),
        cause=_line(t, "cause"),
        known_from=_date(t, "known_from"),
        notes=_line(t, "notes"),
        nber_start=nber.get("nber_start"),
        nber_end=nber.get("nber_end"),
    )
    if e.peak >= e.trough:
        raise ConfigurationError(f"{t.where}: peak {e.peak} is not before trough {e.trough}")
    if e.known_from < e.trough:
        raise ConfigurationError(f"{t.where}: known_from {e.known_from} is before the trough")
    return e
