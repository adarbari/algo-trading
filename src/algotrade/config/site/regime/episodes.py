"""The reference crash episodes (``config/site/regime/episodes.toml``, ADR 0047;
docs/market-regime-plan.md section 2): the twelve S&P 500 drawdowns of 19% or more since 1970,
each with its closing-basis ``peak`` and ``trough`` sessions, the S&P 500 and Nasdaq
drawdowns, the NBER recession months when there was one, what caused it, and ``known_from``
(the trough: the earliest session a feature about the episode may be non-null, since no
feature may know an episode's depth before it ended).

The loader checks shape, ordering (peak before trough, ``known_from`` not before the trough),
unique keys and non-empty text. ``name`` is the plain name a page shows and ``recovered`` the
reviewed session the S&P 500 regained the pre-episode peak (absent while it has not).

``[[recession]]`` tables are the NBER recession chronology since 1969: ``start`` / ``end``
(the first day of the peak and trough months) and the days the committee announced them
(``announced_start`` / ``announced_end``, absent where NBER published none). The loader checks
the order (start before end, an announcement not before the month it announces, recessions
in order and not overlapping). That the dates agree with the dating in ``quant`` and with the
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
    "name",
    "peak",
    "trough",
    "recovered",
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
RECESSION_KEYS = ("start", "end", "announced_start", "announced_end")


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
    name: str
    nber_start: date | None = None
    nber_end: date | None = None
    recovered: date | None = None


@dataclass(frozen=True)
class Recession:
    """One NBER recession: ``start`` / ``end`` are the first days of its peak and trough
    months; ``announced_start`` / ``announced_end`` the days the committee announced them
    (``None``: none published, so a page falls back to the month itself)."""

    start: date
    end: date
    announced_start: date | None = None
    announced_end: date | None = None


@dataclass(frozen=True)
class Episodes:
    """``episodes.toml``: the episodes and the recessions in file order (none without the
    file)."""

    episodes: tuple[Episode, ...] = ()
    recessions: tuple[Recession, ...] = ()

    @classmethod
    def from_document(cls, doc: Mapping[str, Any] | None) -> "Episodes":
        where = f"{FOLDER}/{NAME}.toml"
        reject_secrets(doc or {}, where)
        root = Table(doc, where)
        root.only(("episode", "recession"))
        found = tuple(
            _episode(Table(e, f"{where} [[episode]][{i}]"))
            for i, e in enumerate(_tables(root, "episode", where))
        )
        recessions = _recessions(
            tuple(
                Table(e, f"{where} [[recession]][{i}]")
                for i, e in enumerate(_tables(root, "recession", where))
            )
        )
        repeated = sorted(k for k, n in Counter(e.key for e in found).items() if n > 1)
        if repeated:
            raise ConfigurationError(f"{where}: keys declared more than once: {repeated}")
        return cls(found, recessions)

    def by_key(self, key: str) -> Episode:
        found = next((e for e in self.episodes if e.key == key), None)
        if found is None:
            raise KeyError(f"no episode {key!r} in {FOLDER}/{NAME}.toml")
        return found


def load_episodes(configs: Documents) -> Episodes:
    """``config/site/regime/episodes.toml``; missing: no episodes."""
    return Episodes.from_document(configs.load("site", FOLDER, NAME))


def _tables(root: Table, key: str, where: str) -> list[Mapping[str, Any]]:
    raw = root.raw(key) or []
    if not isinstance(raw, list) or not all(isinstance(e, Mapping) for e in raw):
        raise ConfigurationError(f"{where} {key}: expected a list of tables ([[{key}]])")
    return raw


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


def _optional_date(t: Table, key: str) -> date | None:
    return None if t.raw(key) is None else _date(t, key)


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
        name=_line(t, "name"),
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
        recovered=_optional_date(t, "recovered"),
    )
    if e.peak >= e.trough:
        raise ConfigurationError(f"{t.where}: peak {e.peak} is not before trough {e.trough}")
    if e.known_from < e.trough:
        raise ConfigurationError(f"{t.where}: known_from {e.known_from} is before the trough")
    if e.recovered is not None and e.recovered <= e.trough:
        raise ConfigurationError(f"{t.where}: recovered {e.recovered} is not after the trough")
    return e


def _recession(t: Table) -> Recession:
    t.only(RECESSION_KEYS)
    r = Recession(
        start=_date(t, "start"),
        end=_date(t, "end"),
        announced_start=_optional_date(t, "announced_start"),
        announced_end=_optional_date(t, "announced_end"),
    )
    if r.start >= r.end:
        raise ConfigurationError(f"{t.where}: start {r.start} is not before end {r.end}")
    if r.announced_start is not None and r.announced_start < r.start:
        raise ConfigurationError(f"{t.where}: announced_start is before the start")
    if r.announced_end is not None and r.announced_end < r.end:
        raise ConfigurationError(f"{t.where}: announced_end is before the end")
    return r


def _recessions(tables: tuple[Table, ...]) -> tuple[Recession, ...]:
    found = tuple(_recession(t) for t in tables)
    for i in range(1, len(found)):
        if found[i].start <= found[i - 1].end:
            raise ConfigurationError(
                f"{tables[i].where}: recessions must be in order and not overlap"
            )
    return found
