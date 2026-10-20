"""The ETF category rules of ``universe.toml [etf_category]`` and their curated overrides, typed
and validated (ADR 0076). One responsibility: turn the TOML phrases and the CSV rows into frozen
settings that ``tasks/reference/classify.py`` resolves a name against; no resolving here."""

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from algotrade.config.site.fields import Table
from algotrade.core.model.errors import ConfigurationError

# ``etf_category`` values an ETF can carry (``None`` = UNKNOWN, with a source saying why).
CATEGORIES = ("thematic", "sector", "broad", "excluded")
# ``etf_category_source`` values, in resolution order (``not_etf`` applies to every non-ETF).
CATEGORY_SOURCES = ("override", "name_rule", "needs_review", "unclassified", "not_etf")
OVERRIDE_COLUMNS = ("symbol", "category", "theme", "notes")
GROUPS = ("exclusions", "themes", "sectors")

Phrases = tuple[tuple[str, tuple[str, ...]], ...]  # group name -> regular expressions, in order


@dataclass(frozen=True)
class EtfCategoryRules:
    """``[etf_category]``: ``broad`` phrases, and ``exclusions`` / ``themes`` / ``sectors`` as
    named groups of phrases (the first matching group names ``etf_theme``)."""

    broad: tuple[str, ...] = ()
    exclusions: Phrases = ()
    themes: Phrases = ()
    sectors: Phrases = ()

    @classmethod
    def from_document(cls, doc: Mapping[str, Any] | None, where: str) -> "EtfCategoryRules":
        root = Table(doc, f"{where} [etf_category]")
        root.only(["broad", *GROUPS])
        return cls(
            broad=_patterns(root, root.strings("broad", ()), "broad"),
            **{g: _groups(root, g) for g in GROUPS},
        )


def _patterns(root: Table, values: Iterable[str], key: str) -> tuple[str, ...]:
    out = tuple(values)
    for i, value in enumerate(out):
        try:
            re.compile(value)
        except re.error as exc:
            raise ConfigurationError(f"{root.where} {key}[{i}]: {exc}") from exc
    return out


def _groups(root: Table, key: str) -> Phrases:
    """``[[etf_category.<key>]]`` entries ``{name, phrases}`` (order kept; a name once)."""
    value = root.raw(key)
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ConfigurationError(f"{root.where} {key}: expected a list of {{name, phrases}} tables")
    out: list[tuple[str, tuple[str, ...]]] = []
    for i, entry in enumerate(value):
        item = Table(entry if isinstance(entry, Mapping) else None, f"{root.where} {key}[{i}]")
        item.only(["name", "phrases"])
        name = item.line("name")
        if any(name == seen for seen, _ in out):
            raise ConfigurationError(f"{item.where} name: {name!r} is listed twice")
        out.append((name, _patterns(item, item.strings("phrases", ()), "phrases")))
    return tuple(out)


def etf_overrides(rows: Iterable[Mapping[str, str]]) -> dict[str, tuple[str, str | None]]:
    """``overrides/thematic_etfs.csv`` rows -> symbol -> (category, theme). Fails on an unknown
    column, a category outside ``CATEGORIES``, a missing symbol or a symbol listed twice."""
    where = "overrides/thematic_etfs.csv"
    out: dict[str, tuple[str, str | None]] = {}
    for n, row in enumerate(rows, start=2):  # line 1 is the header
        unknown = sorted(str(k) for k in set(row) - set(OVERRIDE_COLUMNS))
        if unknown:
            raise ConfigurationError(
                f"{where} line {n}: unknown column(s) {unknown}; expected {list(OVERRIDE_COLUMNS)}"
            )
        symbol = (row.get("symbol") or "").strip().upper()
        category = (row.get("category") or "").strip().lower()
        if not symbol:
            raise ConfigurationError(f"{where} line {n}: symbol is required")
        if category not in CATEGORIES:
            raise ConfigurationError(
                f"{where} line {n}: category {category!r} is not one of {list(CATEGORIES)}"
            )
        if symbol in out:
            raise ConfigurationError(f"{where} line {n}: {symbol} is listed twice")
        out[symbol] = (category, (row.get("theme") or "").strip() or None)
    return out
