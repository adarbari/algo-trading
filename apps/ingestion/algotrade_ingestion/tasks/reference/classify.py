"""Classify listings into security types and apply the leverage and ETF category rules (site
coverage inputs).

Nasdaq Trader gives only an ETF flag, so the rest comes from the security name and the ACT
symbol. Order matters: preferred depositary shares are preferred, not ADRs; SPAC units are
units, but partnership "Common Units" are common equity. Every rule is tested on real names.
"""

import re
from collections.abc import Iterable

import pandas as pd

from algotrade.config.site.settings import UniverseSettings
from algotrade.config.site.universe.etf_category import Phrases

_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("ETN", re.compile(r"\bETNs?\b|exchange[- ]traded notes?", re.I)),
    # not a name that ends "Common Stock" / "Ordinary Shares" ("Preferred Bank - Common Stock")
    (
        "PREFERRED",
        re.compile(r"^(?!.*(?:common stock|ordinary shares)\s*$).*(?:preferred|\bpfd\b)", re.I),
    ),
    # Units first: SPAC unit names mention the warrants and rights they contain.
    ("UNIT", re.compile(r"\bunits?, each consisting\b|\bunits? \(each", re.I)),
    ("WARRANT", re.compile(r"\bwarrants?\b", re.I)),
    ("RIGHT", re.compile(r"\brights?\b(?! offering)", re.I)),
    ("NOTE", re.compile(r"\bnotes? due\b|\bdebentures?\b|\bsenior notes\b|% notes\b", re.I)),
    ("ADR", re.compile(r"american depositary|\bADSs?\b|\bADRs?\b", re.I)),
)
_SYMBOL_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("PREFERRED", re.compile(r"\$")),
    ("WARRANT", re.compile(r"\.W[S]?$")),
    ("UNIT", re.compile(r"\.U$")),
    ("RIGHT", re.compile(r"\.R[T]?$")),
)


def security_type(name: str, symbol: str, is_etf: bool) -> str:
    for kind, pattern in _RULES:
        if (kind == "ETN" or not is_etf) and pattern.search(name):
            return kind
    if is_etf:
        return "ETF"
    for kind, pattern in _SYMBOL_RULES:
        if pattern.search(symbol):
            return kind
    return "COMMON_STOCK"


# ``leverage_source`` values, in resolution order (``not_etf`` applies before all of them).
LEVERAGE_SOURCES = ("override", "name_parsed", "name_rule", "needs_review", "not_etf")


class LeverageRules:
    """The name rules of ``config/site/universe.toml``, compiled (case-insensitive).

    ``resolve(name)`` -> (leverage, source) for an ETF without a curated override:

    1. a fund-family convention (``leverage_conventions``, e.g. "ProShares UltraShort" = -2)
       or a stated multiple (``leverage_patterns``: "Bull 3X", "2X Short", "-3 Inverse
       Leveraged"), negative when the number is or an ``inverse_markers`` word appears
       -> ``name_parsed``
    2. no leverage marker, once ``leverage_exclusions`` phrases ("Short Duration", "Ultra
       Buffer", "Option Income", ...) are blanked out -> 1.0, ``name_rule``
    3. otherwise -> ``None``, ``needs_review`` (UNKNOWN: fails closed)
    """

    def __init__(self, settings: UniverseSettings) -> None:
        def any_of(patterns: Iterable[str]) -> re.Pattern[str]:
            return re.compile("|".join(f"(?:{p})" for p in patterns) or r"(?!)", re.I)

        self.markers = any_of(settings.leverage_markers)
        self.conventions = tuple(
            (re.compile(p, re.I), lev) for p, lev in settings.leverage_conventions
        )
        self.patterns = tuple(re.compile(p, re.I) for p in settings.leverage_patterns)
        self.inverse = any_of(settings.inverse_markers)
        self.exclusions = any_of(settings.leverage_exclusions)

    def parse(self, name: str) -> float | None:
        """The leverage the name states (signed), or ``None``."""
        for pattern, leverage in self.conventions:
            if pattern.search(name):
                return leverage
        for pattern in self.patterns:
            match = pattern.search(name)
            if match:
                n = float(match.group("n"))
                inverse = n < 0 or self.inverse.search(self.exclusions.sub(" ", name))
                return -abs(n) if inverse else n
        return None

    def resolve(self, name: str) -> tuple[float | None, str]:
        if not self.markers.search(name):
            return 1.0, "name_rule"
        parsed = self.parse(name)
        if parsed is not None:
            return parsed, "name_parsed"
        if not self.markers.search(self.exclusions.sub(" ", name)):
            return 1.0, "name_rule"
        return None, "needs_review"


def leverage_flags(frame: pd.DataFrame, settings: UniverseSettings) -> pd.DataFrame:
    """``is_leveraged``, ``is_inverse``, ``leverage``, ``tracks``, ``leverage_source`` per row.

    - non-ETFs: not leveraged (source ``not_etf``)
    - curated override (``config/site/overrides/leveraged_etfs.csv``): its values (``override``)
    - otherwise ``LeverageRules.resolve`` on the name: ``name_parsed``, ``name_rule`` or
      ``needs_review`` (UNKNOWN: every flag ``None``)
    """
    curated = {o["symbol"].upper(): o for o in settings.overrides if o.get("symbol")}
    rules = LeverageRules(settings)
    rows: list[tuple[bool | None, bool | None, float | None, str | None, str]] = []
    for symbol, name, is_etf in zip(frame["symbol"], frame["name"], frame["is_etf"], strict=True):
        if not is_etf:
            rows.append((False, False, 1.0, None, "not_etf"))
            continue
        if symbol in curated:
            o = curated[symbol]
            leverage: float | None = float(o.get("leverage") or 1.0)
            tracks, source = o.get("tracks") or None, "override"
        else:
            leverage, source = rules.resolve(str(name))
            tracks = None
        if leverage is None:
            rows.append((None, None, None, None, source))
        else:
            rows.append((leverage != 1.0, leverage < 0, leverage, tracks, source))
    return pd.DataFrame(
        rows,
        columns=["is_leveraged", "is_inverse", "leverage", "tracks", "leverage_source"],
        index=frame.index,
    )


class EtfCategoryResolver:
    """The ``[etf_category]`` rules of ``config/site/universe.toml``, compiled (case-insensitive).

    ``resolve(name)`` -> (category, theme, source) for an ETF that is not leveraged / inverse and
    has no curated override (ADR 0076):

    1. an ``exclusions`` phrase (bond, spot commodity, option income, allocation) -> ``excluded``
    2. a ``themes`` phrase and no ``broad`` phrase -> ``thematic``; else a ``sectors`` phrase and
       no ``broad`` phrase -> ``sector``; else a ``broad`` phrase alone -> ``broad`` (all
       ``name_rule``, ``theme`` = the first matching group)
    3. a theme or sector phrase next to a ``broad`` one -> UNKNOWN, ``needs_review``
    4. no phrase at all -> UNKNOWN, ``unclassified``
    """

    def __init__(self, settings: UniverseSettings) -> None:
        rules = settings.etf_category
        self.broad = _any_of(rules.broad)
        self.exclusions = _groups(rules.exclusions)
        self.themes = _groups(rules.themes)
        self.sectors = _groups(rules.sectors)

    def resolve(self, name: str) -> tuple[str | None, str | None, str]:
        excluded = _first(self.exclusions, name)
        if excluded:
            return "excluded", excluded, "name_rule"
        broad = bool(self.broad.search(name))
        theme, sector = _first(self.themes, name), _first(self.sectors, name)
        if (theme or sector) and broad:
            return None, None, "needs_review"
        if theme:
            return "thematic", theme, "name_rule"
        if sector:
            return "sector", sector, "name_rule"
        if broad:
            return "broad", None, "name_rule"
        return None, None, "unclassified"


def _any_of(patterns: Iterable[str]) -> re.Pattern[str]:
    return re.compile("|".join(f"(?:{p})" for p in patterns) or r"(?!)", re.I)


def _groups(phrases: Phrases) -> tuple[tuple[str, re.Pattern[str]], ...]:
    return tuple((group, _any_of(patterns)) for group, patterns in phrases)


def _first(groups: tuple[tuple[str, re.Pattern[str]], ...], name: str) -> str | None:
    return next((group for group, pattern in groups if pattern.search(name)), None)


def etf_category_flags(frame: pd.DataFrame, settings: UniverseSettings) -> pd.DataFrame:
    """``etf_category``, ``etf_theme``, ``etf_category_source`` per row (``frame`` carries the
    ``leverage_flags`` columns):

    - non-ETFs: no category (source ``not_etf``)
    - curated override (``config/site/overrides/thematic_etfs.csv``): its values (``override``)
    - a leveraged or inverse fund: ``excluded``, theme ``leveraged`` (``name_rule``); a fund
      whose leverage is itself UNKNOWN (``leverage_source`` ``needs_review``): UNKNOWN too, never
      read by its name (a geared fund the leverage rules missed must not become thematic)
    - otherwise ``EtfCategoryResolver.resolve`` on the name
    """
    resolver = EtfCategoryResolver(settings)
    rows: list[tuple[str | None, str | None, str]] = []
    unknown_leverage = frame.get("leverage_source", pd.Series("", index=frame.index)).eq(
        "needs_review"
    )
    for symbol, name, is_etf, geared, gear_unknown in zip(
        frame["symbol"],
        frame["name"],
        frame["is_etf"].fillna(False),
        frame["is_leveraged"].fillna(False) | frame["is_inverse"].fillna(False),
        unknown_leverage,
        strict=True,
    ):
        if not is_etf:
            rows.append((None, None, "not_etf"))
        elif symbol in settings.etf_overrides:
            category, theme = settings.etf_overrides[symbol]
            rows.append((category, theme, "override"))
        elif geared:
            rows.append(("excluded", "leveraged", "name_rule"))
        elif gear_unknown:
            rows.append((None, None, "needs_review"))
        else:
            rows.append(resolver.resolve(str(name)))
    return pd.DataFrame(
        rows, columns=["etf_category", "etf_theme", "etf_category_source"], index=frame.index
    )
