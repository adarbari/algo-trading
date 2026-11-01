"""Site settings for macro series and index levels (``config/site/macro.toml``, ADR 0048): the
registry of every series the ``macro/series`` table stores, typed and validated here (split from
``settings.py``, which loads it through ``load_macro``, to keep that file under the length limit).

Each ``[[series]]`` is one stored series: where it comes from (``source``: the FRED / ALFRED
API, or a ``published`` file at ``url``), what it is (``kind``: an economic ``macro`` series or
an ``index`` level), how its point in time is known (``pit``: ALFRED vintages, or
``obs_date + release_lag_days`` for unrevised series) and the terms it is used under. The
series' instrument id (``MACRO:<KEY>`` / ``IDX:<KEY>``) comes from ``kind`` and ``key``.

A published file with many columns of one table (Kenneth French's factor and industry files) is
declared once, not per column: a family file of ``config/site/series/`` holds ``[defaults]`` for the
series fields and a ``[[file]]`` per file (``prefix``, ``url``, ``parser``, ``section``, the
``columns`` it takes). Each column expands into an ordinary ``MacroSeries`` keyed
``<prefix>_<COLUMN>`` (upper case, anything outside ``A-Z0-9`` an underscore) with the column as
its ``value_column``, so the task, the source and the table see plain series. Columns are listed,
never ``"*"``: the registry must name every stored series without reading the file.
"""

import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
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
# A series may run this long past its cadence plus its release lag. A daily series gets a day
# more: a Monday holiday leaves a lag-0 close 4 days old on Tuesday.
STALE_MARGIN_DAYS = 2
DAILY_MARGIN_DAYS = 3
RUN_BUDGET_S = 900  # [macro] run_budget_s: the macro task stops fetching series after this long
PITS = ("alfred", "lag")
TRANSFORMS = ("level", "yoy", "diff")
LICENCES = ("open", "personal")  # as a macro series' licence (ADR 0028)
HELD_LICENCES = (
    *LICENCES,
    "yahoo",
)  # a vendor's or a user's: ``yahoo`` is the owner's alone (ADR 0080)
FILE_KEYS = ("url", "date_column", "value_column", "parser")
FAMILY = "series/*.toml"  # config/site/series/<family>.toml: [[series]] and [[file]] blocks
BLOCK_KEYS = ("prefix", "columns")  # a [[file]]'s own keys; the rest are series fields
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
    "revised",
    "refetch_days",
    "section",
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
    section: int = 1  # a file of several tables: which one (``french_zip``), from 1
    revised: bool = False
    refetch_days: int = 0  # a published file: read again after this many days (0: by cadence)
    research: bool = (
        False  # expanded from a ``series/<family>.toml`` [[file]] (ADR 0089), not an entry
    )

    @property
    def is_revised(self) -> bool:
        """Its history is revised after publication: ALFRED vintages, or ``revised = true`` (a
        published file re-estimated in place, stored through the lagged rule: EBP, OFR FSI)."""
        return self.pit == "alfred" or self.revised

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
        stale: its cadence + ``release_lag_days`` + 2 days (3 for a daily series, ADR 0048)."""
        margin = DAILY_MARGIN_DAYS if self.cadence == "daily" else STALE_MARGIN_DAYS
        return self.cadence_days + self.release_lag_days + margin


@dataclass(frozen=True)
class MacroSettings:
    """``macro.toml``: the series in file order (none without the file); ``run_budget_s``
    (``[macro]``): seconds a run of the ``macro`` task may keep fetching series before it stops
    and records the rest as skipped (a FRED outage must not hold the nightly up)."""

    series: tuple[MacroSeries, ...] = ()
    run_budget_s: int = RUN_BUDGET_S

    @property
    def keys(self) -> frozenset[str]:
        return frozenset(s.key for s in self.series)

    def by_key(self, key: str) -> MacroSeries:
        found = next((s for s in self.series if s.key == key), None)
        if found is None:
            raise KeyError(f"no series {key!r} in {WHERE}")
        return found

    @classmethod
    def from_documents(
        cls, main: Mapping[str, Any] | None, families: Sequence[Mapping[str, Any] | None]
    ) -> "MacroSettings":
        """``main`` (``macro.toml``) with each family file (``site/series/<family>.toml``) after
        it: its own ``[[series]]``, then the series its ``[[file]]`` blocks expand into."""
        base = cls.from_document(main)
        series = list(base.series)
        for family in families:
            doc = family or {}
            reject_secrets(doc, FAMILY)
            Table(doc, FAMILY).only(("series", "defaults", "file"))
            extra = doc.get("series") or []
            if not isinstance(extra, list) or not all(isinstance(e, Mapping) for e in extra):
                raise ConfigurationError(f"{FAMILY} series: expected a list of tables")
            series += [_series(e, i, f"{FAMILY} [[series]]") for i, e in enumerate(extra)]
            series += _expand(doc)
        _unique(series)
        return cls(tuple(series), base.run_budget_s)

    @classmethod
    def from_document(cls, doc: Mapping[str, Any] | None) -> "MacroSettings":
        reject_secrets(doc or {}, WHERE)
        root = Table(doc, WHERE)
        root.only(("macro", "series"))
        budget = root.table("macro", ("run_budget_s",)).integer("run_budget_s", RUN_BUDGET_S, 1)
        raw = root.raw("series") or []
        if not isinstance(raw, list) or not all(isinstance(e, Mapping) for e in raw):
            raise ConfigurationError(f"{WHERE} series: expected a list of tables ([[series]])")
        series = tuple(_series(entry, i) for i, entry in enumerate(raw))
        _unique(series)
        return cls(series, budget)


def _unique(series: Sequence[MacroSeries]) -> None:
    repeated = sorted(k for k, n in Counter(s.key for s in series).items() if n > 1)
    if repeated:
        raise ConfigurationError(f"{WHERE}: keys declared more than once: {repeated}")


def _required(t: Table, key: str, choices: tuple[str, ...] | None = None) -> str:
    if t.raw(key) is None:
        raise ConfigurationError(f"{t.where} {key}: required")
    return t.choice(key, "", choices) if choices else t.text(key, "")


def _expand(doc: Mapping[str, Any]) -> tuple[MacroSeries, ...]:
    """The series of a family file's ``[[file]]`` blocks, each over ``[defaults]``, one a column."""
    where = FAMILY
    root = Table(doc, where)
    defaults = root.raw("defaults") or {}
    if not isinstance(defaults, Mapping):
        raise ConfigurationError(f"{where} defaults: expected a table")
    Table(defaults, f"{where} [defaults]").only(
        (*(k for k in KEYS if k not in ("key", "value_column")), *BLOCK_KEYS)
    )
    raw = root.raw("file") or []
    if not isinstance(raw, list) or not all(isinstance(e, Mapping) for e in raw):
        raise ConfigurationError(f"{where} file: expected a list of tables ([[file]])")
    series: list[MacroSeries] = []
    for i, block in enumerate(raw):
        label = f"{where} [[file]][{i}]"
        merged = {**defaults, **block}
        prefix, columns = merged.get("prefix"), merged.get("columns")
        if not isinstance(prefix, str) or not prefix:
            raise ConfigurationError(f"{label} prefix: required text")
        if (
            not isinstance(columns, list)
            or not columns
            or not all(isinstance(c, str) and c.strip() for c in columns)
        ):
            raise ConfigurationError(f'{label} columns: list the file\'s columns (not "*")')
        for column in columns:
            entry = {k: v for k, v in merged.items() if k not in BLOCK_KEYS}
            entry |= {"key": series_key(prefix, column), "value_column": column}
            built = _series(entry, i, f"{where} [[file]] {prefix}")
            series.append(replace(built, research=True))
    return tuple(series)


def series_key(prefix: str, column: str) -> str:
    """``<prefix>_<COLUMN>``: upper case, a run of other characters one underscore."""
    return f"{prefix}_{re.sub('[^A-Z0-9]+', '_', column.upper()).strip('_')}"


def _series(doc: Mapping[str, Any], index: int, origin: str = f"{WHERE} [[series]]") -> MacroSeries:
    key = _required(Table(doc, f"{origin}[{index}]"), "key")
    if not _KEY.match(key):
        raise ConfigurationError(f"{origin}[{index}] key: expected {_KEY.pattern}")
    where = f"{origin} {key}"
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
        section=t.integer("section", 1, 1),
        revised=t.boolean("revised", False),
        refetch_days=t.integer("refetch_days", 0, 0),
    )
    _check_source(s, where)
    return s


def _check_source(s: MacroSeries, where: str) -> None:
    """A ``fred`` series has no file keys; a ``published`` one has a URL and its columns;
    ALFRED vintages exist only for FRED series."""
    if s.source == "fred":
        given = [k for k in (*FILE_KEYS, "section") if getattr(s, k) not in ("", 1)]
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
