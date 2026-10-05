"""ETFs the SEC fund ticker map misses, matched to their SEC fund series (ADR 0034).

``company_tickers_mf.json`` leaves out about 970 of the ~5,760 ETFs, yet most of them file a
prospectus whose investment objective is in the Risk/Return Summary data sets already read. The
yearly series / class file (``SecFundSeries``) lists every registered series, so an ETF the map
misses is matched to one:

1. by **ticker**: the file's ``Class Ticker`` names exactly one series;
2. else by **name**: the ETF's name equals the name of exactly one series (or one of its share
   classes) once case, ``&`` and punctuation are ignored. No word is dropped from the name and a
   name that fits two series is not matched, so a wrong match needs two different funds sharing
   one name.

The map's own rows always win. The result has the map's columns, so ``fund_rows`` and nothing
else changes. Unit trusts and commodity or crypto trusts (SPY, GLD, ...) are in neither file and
stay without an objective.
"""

import re

import pandas as pd

FUND_COLUMNS = ["symbol", "series_id", "class_id", "cik"]  # the fund ticker map's columns
_NON_ALNUM = re.compile(r"[^A-Z0-9]+")


def normalize_name(name: object) -> str:
    """``name`` in upper case with ``&`` as AND and every other non-alphanumeric run as one
    space (``Innovator U.S. Equity Power Buffer ETF - October`` -> the same words, spaced)."""
    text = str(name or "").upper().replace("&", " AND ")
    return _NON_ALNUM.sub(" ", text).strip()


def _only_series(frame: pd.DataFrame, key: pd.Series) -> pd.DataFrame:
    """One row per ``key`` that names exactly one series (the first of its classes)."""
    keyed = frame.assign(key=key)[lambda f: f["key"].astype(bool)]
    series_per_key = keyed.groupby("key")["series_id"].nunique()
    unique = keyed[keyed["key"].isin(series_per_key[series_per_key == 1].index)]
    only: pd.DataFrame = unique.drop_duplicates("key").set_index("key")
    return only


def _name_keys(series: pd.DataFrame) -> pd.DataFrame:
    """``series`` once under its series name and once under its class name (``key`` column)."""
    names = [
        series.assign(key=series[c].map(normalize_name)) for c in ("series_name", "class_name")
    ]
    both = pd.concat(names, ignore_index=True)
    return both[both["key"] != ""].drop_duplicates(["key", "series_id"])


def extend_fund_map(
    funds: pd.DataFrame, series: pd.DataFrame, etfs: pd.DataFrame
) -> tuple[pd.DataFrame, dict[str, int]]:
    """``funds`` (the SEC ticker map: ``FUND_COLUMNS``) plus a row for each ETF in ``etfs``
    (``symbol``, ``name``) that the map lacks and ``series`` (the yearly series / class file)
    matches by ticker, else by name. -> (the extended map, ``by_ticker`` / ``by_name`` /
    ``ambiguous`` counts)."""
    missing = etfs[~etfs["symbol"].isin(set(funds["symbol"]))]
    counts = {"by_ticker": 0, "by_name": 0, "ambiguous": 0}
    if missing.empty or series.empty:
        return funds, counts
    by_ticker = _only_series(series, series["class_ticker"].fillna(""))
    names = _name_keys(series)
    by_name = _only_series(names, names["key"])
    named = set(names["key"])
    added: list[dict[str, object]] = []
    for symbol, name in zip(missing["symbol"], missing["name"], strict=True):
        key = normalize_name(name)
        if symbol in by_ticker.index:
            found, route = by_ticker.loc[symbol], "by_ticker"
        elif key in by_name.index:
            found, route = by_name.loc[key], "by_name"
        else:
            counts["ambiguous"] += int(key in named)  # the name fits two or more series
            continue
        counts[route] += 1
        added.append({c: (symbol if c == "symbol" else found[c]) for c in FUND_COLUMNS})
    if not added:
        return funds, counts
    extra = pd.DataFrame(added, columns=FUND_COLUMNS)
    return pd.concat([funds, extra], ignore_index=True), counts
