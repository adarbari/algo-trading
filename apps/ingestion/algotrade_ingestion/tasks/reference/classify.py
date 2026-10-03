"""Classify listings into security types and apply the leverage rule (site coverage inputs).

Nasdaq Trader gives only an ETF flag, so the rest comes from the security name and the ACT
symbol. Order matters: preferred depositary shares are preferred, not ADRs; SPAC units are
units, but partnership "Common Units" are common equity. Every rule is tested on real names.
"""

import re
from collections.abc import Iterable

import pandas as pd

from algotrade.config.site.settings import UniverseSettings

_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("ETN", re.compile(r"\bETNs?\b|exchange[- ]traded notes?", re.I)),
    ("PREFERRED", re.compile(r"preferred|\bpfd\b", re.I)),
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
