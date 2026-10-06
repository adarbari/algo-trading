"""``fund_reference@v1``: which stock or index a leveraged or inverse fund tracks (ADR 0050).

A leveraged or inverse fund has no events of its own: it inherits its reference's, scaled by its
leverage. One row per fund (``is_leveraged`` or ``is_inverse`` in the reference snapshot the
session sees); every other instrument has no row and reads NOT_APPLICABLE (ADR 0042).

Inputs: ``instruments/reference`` (the fund's name and flags, and every instrument's security
type), ``holdings/etf`` (each such fund's latest stored holdings, ADR 0035) and
``instruments/symbol_ids`` (the ticker -> id map of the reference snapshot, ADR 0018: an id is
read from it, never built). Nothing but the reference is required: a fund with no holdings
stored is read by its name.

The link, in order:

1. **Holdings.** A fund whose holdings name exactly one equity (money-market sweeps and cash
   aside) tracks it; so does one that holds no equity but whose swap lines name exactly one
   listed ticker, when that is the ticker the name states, or the name states no kind and the
   line is no index, bullion, futures, trust or ETF line (a line that is one is a basket
   signal: "DOW JONES INDUSTRIAL AVERAGE SWAP" is the Dow, not Dow Inc). Two or more equities
   (or swaps naming two stocks) are a basket: the reference is not one stock.
2. **The name** when the holdings are absent or silent (``fund_names``: ``Daily TSLA Bull 2X``,
   ``2x Long TSLA Daily``): the ticker must be a listed stock (an ETF is a basket).
3. The kind of a basket (``index``, ``sector``, ``commodity``) from the name's keywords, else
   from the holdings: futures over half of the gross weight is a commodity fund, four sectors
   or more (or none stated) an index, fewer a sector.

    reference_instrument_id  the one stock tracked (null: a basket, none found, or a ticker the
                             reference does not list)
    reference_kind           single_stock, index, sector, commodity or none (none: no stock or
                             basket found, or a volatility fund)
    reference_source         holdings or name_rule: what settled the link, or for a basket its
                             kind (null when the kind is none)
    reference_status         LINKED (one stock), BASKET (a kind, no one stock), UNLISTED (a stock
                             named, not in the reference), NO_REFERENCE (neither holdings nor a
                             name say anything)

A leveraged fund whose holdings are not stored yet reads NO_REFERENCE unless its name says
what it tracks; run ``etf-holdings`` for it. Never a guess: a fund the rules cannot settle has
status NO_REFERENCE, not the nearest ticker.
"""

import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import date
from typing import Any

import pandas as pd

from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import OPERATING_TYPES, Feature
from algotrade.features.rollups.reference.fund_names import name_kind, name_ticker

NAME = "fund_reference"
VERSION = 1
REFERENCE = "instruments/reference"
HOLDINGS = "holdings/etf"
SYMBOLS = "instruments/symbol_ids"
KINDS = ("single_stock", "index", "sector", "commodity", "none")
SOURCES = ("holdings", "name_rule")
LINKED, BASKET, UNLISTED, NO_REFERENCE = "LINKED", "BASKET", "UNLISTED", "NO_REFERENCE"
STATUSES = (LINKED, BASKET, UNLISTED, NO_REFERENCE)
SECTORS_FOR_INDEX = 4  # equity holdings spanning this many sectors are an index, fewer a sector
FUTURES_SHARE = 0.5  # futures over this share of the gross weight make a commodity fund

_SWEEP = re.compile(
    r"money market|mny mkt|\bmmf\b|treasury|t-bill|\bbills?\b|\bcash\b|government|repurchase",
    re.IGNORECASE,
)
_SWAP = re.compile(r"\bswaps?\b", re.IGNORECASE)
# Words of a swap line that say the underlying is a basket or a commodity, not one stock.
_BASKET_WORDS = re.compile(r"\b(?:INDEX|AVERAGE|BULLION|FUTURES?|TRUST|ETF)\b")
_COMMODITY_WORDS = frozenset({"BULLION", "FUTURE", "FUTURES"})
_WORDS = re.compile(r"[A-Z][A-Z0-9]*(?:\.[A-Z])?")
# Words of a swap line that are also listed tickers or counterparties: never a reference.
_STOP = (
    "A AN AND ALL ARE AT BE BY FOR IN IS IT NA NO OF ON OR SO THE TO UP US USD INC CORP CO LTD "
    "PLC LLC LP SWAP SWAPS TOTAL RETURN INDEX BANK NATIONAL ASSOCIATION TRUST FUND ETF LONG SHORT "
    "BULL BEAR DAILY FUTURE CASH AMERICA SECURITIES CAPITAL MARKETS INTL INTERNATIONAL LIMITED "
    "FINANCIAL GROUP HOLDINGS GOLDMAN SACHS MORGAN STANLEY CITIBANK CITI BARCLAYS NOMURA WELLS "
    "FARGO SOCIETE GENERALE PARIBAS CREDIT SUISSE DEUTSCHE UBS BNP GS JPM MS BAC C CS DB BARC SG "
    "HSBC RBC TD BMO BOFA MUFG"
)
_NOT_TICKERS = frozenset(_STOP.split())

FEATURES = (
    Feature(
        "reference_instrument_id", "str", "text",
        "The one stock the fund tracks (an instrument id from the reference snapshot, found "
        "through the symbol resolver): the single equity in its holdings or named by its swaps, "
        "else the ticker its name states",
        "the fund tracks a basket (see reference_kind), no holdings are stored and its name "
        "names none (NO_REFERENCE), or the stock is not in the reference (UNLISTED); not a "
        "leveraged or inverse fund (NOT_APPLICABLE)",
        "label", inputs=(f"{HOLDINGS}.holding_id", f"{HOLDINGS}.holding_name", f"{REFERENCE}.name"),
    ),
    Feature(
        "reference_kind", "str", "category",
        "What the fund tracks: a single stock, an index, a sector, a commodity, or none "
        "(volatility funds, rates funds, funds nothing is known of)",
        "never (none is a value)", "label", categories=KINDS,
        inputs=(f"{HOLDINGS}.asset_class", f"{HOLDINGS}.sector", f"{REFERENCE}.name"),
    ),
    Feature(
        "reference_source", "str", "category",
        "What settled the link, or for a basket its kind: the holdings table or the name rule",
        "reference_kind is none: nothing settled it", "label", categories=SOURCES,
        inputs=(f"{HOLDINGS}.holding_id", f"{REFERENCE}.name"),
    ),
    Feature(
        "reference_status", "str", "category",
        "LINKED: one stock found; BASKET: an index, sector or commodity fund; UNLISTED: a "
        "stock is named that the reference does not list; NO_REFERENCE: neither holdings nor "
        "the name say what it tracks",
        "never", "label", categories=STATUSES, inputs=(f"{HOLDINGS}.holding_id",),
    ),
)  # fmt: skip
COLUMNS = column_types(FEATURES)


@dataclass(frozen=True)
class Link:
    """One fund's result: the columns of its row."""

    reference_instrument_id: str | None
    reference_kind: str
    reference_source: str | None
    reference_status: str


def _present(value: Any) -> str | None:
    return None if value is None or pd.isna(value) else str(value)


def _is_stock(instrument_id: str, types: Mapping[str, str]) -> bool:
    """An operating company (stock or ADR); a security type that is not stored is not "no"."""
    kind = types.get(instrument_id)
    return kind is None or kind in OPERATING_TYPES


def _holding_id(line: pd.Series, symbols: Mapping[str, str]) -> str | None:
    """The instrument a holding line names: its stored id, else its ticker's id."""
    return _present(line["holding_id"]) or symbols.get(_present(line["holding_symbol"]) or "")


def _equities(lines: pd.DataFrame) -> pd.DataFrame:
    """The lines that are a company's shares: not cash, a money-market sweep or a Treasury."""
    equity = lines["asset_class"].astype(str).str.lower().eq("equity")
    sweep = lines["holding_name"].astype(str).map(lambda n: bool(_SWEEP.search(n)))
    return lines[equity & ~sweep]


def _swap_tickers(
    lines: pd.DataFrame, name: str, symbols: Mapping[str, str]
) -> tuple[set[str], str | None]:
    """The listed tickers the swap lines name as the fund's reference, and the kind a line that
    names none signals (``commodity``, ``index``; ``None``: no line did).

    A word of a swap line that is a listed ticker is the reference only when it is the ticker
    the name states, or when the name states no kind and the line is no index, bullion, futures,
    trust or ETF line: "DOW JONES INDUSTRIAL AVERAGE SWAP" is the Dow, not Dow Inc, and
    "GOLD BULLION SWAP" is gold, not Barrick. Such a line is a basket signal instead."""
    swaps = lines["asset_class"].astype(str).str.lower().eq("derivative")
    swaps |= lines["holding_name"].astype(str).map(lambda n: bool(_SWAP.search(n)))
    own, kind = name_ticker(name), name_kind(name)
    found: set[str] = set()
    signal: str | None = None
    for text in lines.loc[swaps, "holding_name"].dropna().astype(str):
        words = {w for w in _WORDS.findall(text.upper()) if len(w) > 1 and w not in _NOT_TICKERS}
        words = {w for w in words if w in symbols}
        basket = _BASKET_WORDS.search(text.upper())
        if own in words:
            found.add(str(own))
        elif kind is None and not basket:
            found |= words
        elif basket:
            signal = "commodity" if basket.group() in _COMMODITY_WORDS else (signal or "index")
    return found, signal


def _basket_kind(lines: pd.DataFrame) -> str:
    """index or sector from the sectors of the equity lines (none stated: an index)."""
    sectors = lines["sector"].dropna().astype(str)
    return "sector" if 0 < sectors.nunique() < SECTORS_FOR_INDEX else "index"


def _futures_fund(lines: pd.DataFrame) -> bool:
    weight = lines["weight"].abs()
    futures = lines["asset_class"].astype(str).str.lower().isin(["futures", "commodity"])
    return bool(weight.sum() > 0 and weight[futures].sum() / weight.sum() >= FUTURES_SHARE)


def _single(instrument_id: str | None, source: str, types: Mapping[str, str]) -> Link | None:
    """A single-stock link, UNLISTED without an id; ``None`` for an id that is not a stock (a
    fund holding one ETF tracks a basket)."""
    if instrument_id is None:
        return Link(None, "single_stock", source, UNLISTED)
    if not _is_stock(instrument_id, types):
        return None
    return Link(instrument_id, "single_stock", source, LINKED)


def _basket(kind: str, source: str = "name_rule") -> Link:
    return Link(None, kind, None if kind == "none" else source, BASKET)


def _from_holdings(
    lines: pd.DataFrame, name: str, symbols: Mapping[str, str], types: Mapping[str, str]
) -> Link | None:
    """What the holdings settle, or ``None`` when they say nothing (no equity and swaps naming
    no ticker)."""
    equities = _equities(lines)
    distinct = {
        _holding_id(r, symbols) or _present(r["holding_symbol"]) or _present(r["holding_name"])
        for _, r in equities.iterrows()
    } - {None}
    if len(distinct) == 1:
        found = _single(_holding_id(equities.iloc[0], symbols), "holdings", types)
        if found is not None:
            return found
    elif not distinct:
        named, signal = _swap_tickers(lines, name, symbols)
        if len(named) == 1:
            found = _single(symbols[next(iter(named))], "holdings", types)
            if found is not None:
                return found
        elif not named:
            if signal is None:
                return None
            named_kind = name_kind(name)
            return _basket(named_kind, "name_rule") if named_kind else _basket(signal, "holdings")
    # Two or more stocks (or one that is an ETF): a basket; the name's keywords name it first.
    kind = name_kind(name)
    return _basket(kind) if kind else _basket(_basket_kind(equities), "holdings")


def _from_name(name: str, symbols: Mapping[str, str], types: Mapping[str, str]) -> Link | None:
    ticker, kind = name_ticker(name), name_kind(name)
    if ticker is not None:
        instrument_id = symbols.get(ticker)
        if instrument_id is not None and _is_stock(instrument_id, types):
            return Link(instrument_id, "single_stock", "name_rule", LINKED)
        if (
            instrument_id is not None
        ):  # a listed ETF ("2X Long SPY"): a basket, an index unless said
            return _basket(kind or "index")
        if kind is None:  # an unlisted ticker yields to a kind its name states ("Daily NASDAQ")
            return Link(None, "single_stock", "name_rule", UNLISTED)
    return None if kind is None else _basket(kind)


def link(
    name: str, lines: pd.DataFrame | None, symbols: Mapping[str, str], types: Mapping[str, str]
) -> Link:
    """The fund's row from its name, its stored holdings (``None``: none) and the ticker and
    security-type maps of the reference snapshot."""
    found = None if lines is None or lines.empty else _from_holdings(lines, name, symbols, types)
    found = found or _from_name(name, symbols, types)
    if found is not None:
        return found
    if lines is not None and not lines.empty and _futures_fund(lines):
        return Link(None, "commodity", "holdings", BASKET)
    return Link(None, "none", None, NO_REFERENCE)


def _flag(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(False, index=frame.index)
    return frame[column].fillna(False).astype(bool)


def compute(inputs: Inputs, session: date, params: None) -> pd.DataFrame:
    reference = inputs[REFERENCE]
    assert reference is not None  # a required input
    funds = reference[_flag(reference, "is_leveraged") | _flag(reference, "is_inverse")]
    symbols_frame = inputs.get(SYMBOLS)
    symbols = (
        {}
        if symbols_frame is None
        else dict(zip(symbols_frame["symbol"], symbols_frame["instrument_id"], strict=True))
    )
    types = dict(zip(reference["instrument_id"], reference["security_type"], strict=True))
    holdings = inputs.get(HOLDINGS)
    by_fund = {} if holdings is None else dict(iter(holdings.groupby("instrument_id")))
    names = funds["name"] if "name" in funds.columns else pd.Series("", index=funds.index)
    rows = []
    for instrument_id, name in zip(funds["instrument_id"], names.fillna(""), strict=True):
        found = link(str(name), by_fund.get(instrument_id), symbols, types)
        rows.append({"instrument_id": instrument_id, **asdict(found)})
    return pd.DataFrame(rows, columns=["instrument_id", *COLUMNS])


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "Which stock or basket a leveraged or inverse fund tracks, from its holdings and its name",
    (Input(REFERENCE), Input(HOLDINGS, required=False), Input(SYMBOLS, required=False)),
    FEATURES,
    compute,
    applies_to="leveraged_fund",
)
