"""Site settings for macro series and index levels (``config/site/macro.toml``, ADR 0048): the
registry of every series the ``macro/series`` table stores, typed and validated here (split from
``settings.py``, which loads it through ``load_macro``, to keep that file under the length limit).

Each ``[[series]]`` is one stored series: where it comes from (``source``: the FRED / ALFRED
API, or a ``published`` file at ``url``), what it is (``kind``: an economic ``macro`` series or
an ``index`` level), how its point in time is known (``pit``: ALFRED vintages, or
``obs_date + release_lag_days`` for unrevised series) and the terms it is used under. The
series' instrument id (``MACRO:<KEY>`` / ``IDX:<KEY>``) comes from ``kind`` and ``key``.
"""

import re
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from algotrade.config.site.fields import Table, reject_secrets
from algotrade.core.model.errors import ConfigurationError
from algotrade.core.model.instruments import index_id, macro_id

WHERE = "macro.toml"
SOURCES = ("fred", "published")
KINDS = ("macro", "index")
CADENCES = ("daily", "weekly", "monthly", "quarterly")
CADENCE_DAYS = {"daily": 1, "weekly": 7, "monthly": 31, "quarterly": 92}  # a release's period
STALE_MARGIN_DAYS = 2  # a series may run this long past its cadence plus its release lag
PITS = ("alfred", "lag")
TRANSFORMS = ("level", "yoy", "diff")
LICENCES = ("open", "personal")  # as a feature's licence (ADR 0028)
FILE_KEYS = ("url", "date_column", "value_column", "parser")
KEYS = (
    "key",
    "code",
    "source",
    "kind",
    "cadence",
    "release_lag_days",
    "pit",
    "transform",
    "licence",
    "terms",
    *FILE_KEYS,
)
_KEY = re.compile(r"^[A-Z0-9][A-Z0-9_]*$")


@dataclass(frozen=True)
class MacroSeries:
    """One ``[[series]]``. ``key``: the series' name here (``series:<KEY>`` in feature inputs);
    ``code``: the vendor's code when it differs (FRED ``NASDAQCOM`` for ``COMP``; default the
    key); ``release_lag_days``: calendar days from an observation to its publication (a
    ``lag`` series' vintage date, and how stale a series may get); ``transform``: how the
    macro group reads the level (as is, year-over-year change, or difference); a ``published``
    file names its ``date_column`` and ``value_column`` and the ``parser`` that reads it
    (default ``csv``; named parsers live with the adapter, ``vendors/published``)."""

    key: str
    source: str
    kind: str
    cadence: str
    pit: str
    terms: str
    code: str = ""
    release_lag_days: int = 0
    transform: str = "level"
    licence: str = "open"
    url: str = ""
    date_column: str = ""
    value_column: str = ""
    parser: str = ""

    @property
    def instrument_id(self) -> str:
        """``IDX:<KEY>`` for an index level, ``MACRO:<KEY>`` otherwise."""
        return index_id(self.key) if self.kind == "index" else macro_id(self.key)

    @property
    def vendor_code(self) -> str:
        return self.code or self.key

    @property
    def cadence_days(self) -> int:
        return CADENCE_DAYS[self.cadence]

    @property
    def stale_after_days(self) -> int:
        """How old the newest observation may be, in calendar days, before the series counts as
        stale: its cadence + ``release_lag_days`` + ``STALE_MARGIN_DAYS`` (ADR 0048)."""
        return self.cadence_days + self.release_lag_days + STALE_MARGIN_DAYS


@dataclass(frozen=True)
class MacroSettings:
    """``macro.toml``: the series in file order (none without the file)."""

    series: tuple[MacroSeries, ...] = ()

    @property
    def keys(self) -> frozenset[str]:
        return frozenset(s.key for s in self.series)

    def by_key(self, key: str) -> MacroSeries:
        found = next((s for s in self.series if s.key == key), None)
        if found is None:
            raise KeyError(f"no series {key!r} in {WHERE}")
        return found

    @classmethod
    def from_document(cls, doc: Mapping[str, Any] | None) -> "MacroSettings":
        reject_secrets(doc or {}, WHERE)
        root = Table(doc, WHERE)
        root.only(("series",))
        raw = root.raw("series") or []
        if not isinstance(raw, list) or not all(isinstance(e, Mapping) for e in raw):
            raise ConfigurationError(f"{WHERE} series: expected a list of tables ([[series]])")
        series = tuple(_series(entry, i) for i, entry in enumerate(raw))
        repeated = sorted(k for k, n in Counter(s.key for s in series).items() if n > 1)
        if repeated:
            raise ConfigurationError(f"{WHERE}: keys declared more than once: {repeated}")
        return cls(series)


def _required(t: Table, key: str, choices: tuple[str, ...] | None = None) -> str:
    if t.raw(key) is None:
        raise ConfigurationError(f"{t.where} {key}: required")
    return t.choice(key, "", choices) if choices else t.text(key, "")


def _series(doc: Mapping[str, Any], index: int) -> MacroSeries:
    key = _required(Table(doc, f"{WHERE} [[series]][{index}]"), "key")
    if not _KEY.match(key):
        raise ConfigurationError(f"{WHERE} [[series]][{index}] key: expected {_KEY.pattern}")
    where = f"{WHERE} [[series]] {key}"
    t = Table(doc, where)
    t.only(KEYS)
    source = _required(t, "source", SOURCES)
    s = MacroSeries(
        key=key,
        source=source,
        kind=_required(t, "kind", KINDS),
        cadence=_required(t, "cadence", CADENCES),
        pit=_required(t, "pit", PITS),
        terms=_required(t, "terms"),
        code=t.text("code", ""),
        release_lag_days=t.integer("release_lag_days", 0, 0),
        transform=t.choice("transform", "level", TRANSFORMS),
        licence=t.choice("licence", "open", LICENCES),
        url=t.text("url", ""),
        date_column=t.text("date_column", ""),
        value_column=t.text("value_column", ""),
        parser=t.text("parser", "csv" if source == "published" else ""),
    )
    _check_source(s, where)
    return s


def _check_source(s: MacroSeries, where: str) -> None:
    """A ``fred`` series has no file keys; a ``published`` one has a URL and its columns;
    ALFRED vintages exist only for FRED series."""
    if s.source == "fred":
        given = [k for k in FILE_KEYS if getattr(s, k)]
        if given:
            raise ConfigurationError(f"{where}: a fred series takes no {given}")
        return
    if s.pit == "alfred":
        raise ConfigurationError(f'{where} pit: "alfred" needs source = "fred"; use "lag"')
    missing = [k for k in ("url", "date_column", "value_column") if not getattr(s, k)]
    if missing:
        raise ConfigurationError(f"{where}: a published series needs {missing}")
    parts = urlsplit(s.url)
    if parts.scheme != "https" or not parts.hostname:
        raise ConfigurationError(f"{where} url: expected an https URL, got {s.url!r}")
