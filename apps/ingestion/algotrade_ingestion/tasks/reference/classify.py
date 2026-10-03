"""Classify listings into security types and apply the leverage rule (site coverage inputs).

Nasdaq Trader gives only an ETF flag, so the rest comes from the security name and the ACT
symbol. Order matters: preferred depositary shares are preferred, not ADRs; SPAC units are
units, but partnership "Common Units" are common equity. Every rule is tested on real names.
"""

import re
from collections.abc import Iterable, Mapping

import pandas as pd

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


def leverage_flags(
    frame: pd.DataFrame, overrides: Iterable[Mapping[str, str]], markers: Iterable[str]
) -> pd.DataFrame:
    """``is_leveraged``, ``is_inverse``, ``leverage``, ``tracks``, ``leverage_source`` per row.

    - non-ETFs: not leveraged (source ``not_etf``)
    - curated override (``config/site/overrides/leveraged_etfs.csv``): its values (``override``)
    - ETF whose name has no leverage marker: leverage 1, not inverse (``name_rule``)
    - ETF whose name has a marker but no override: UNKNOWN (``needs_review``) - fails closed
    """
    curated = {o["symbol"].upper(): o for o in overrides if o.get("symbol")}
    pattern = re.compile("|".join(markers), re.I)
    rows: list[tuple[bool | None, bool | None, float | None, str | None, str]] = []
    for symbol, name, is_etf in zip(frame["symbol"], frame["name"], frame["is_etf"], strict=True):
        if not is_etf:
            rows.append((False, False, 1.0, None, "not_etf"))
        elif symbol in curated:
            o = curated[symbol]
            leverage = float(o.get("leverage") or 1.0)
            rows.append(
                (
                    abs(leverage) != 1.0 or leverage < 0,
                    leverage < 0,
                    leverage,
                    o.get("tracks") or None,
                    "override",
                )
            )
        elif not pattern.search(str(name)):
            rows.append((False, False, 1.0, None, "name_rule"))
        else:
            rows.append((None, None, None, None, "needs_review"))
    return pd.DataFrame(
        rows,
        columns=["is_leveraged", "is_inverse", "leverage", "tracks", "leverage_source"],
        index=frame.index,
    )
