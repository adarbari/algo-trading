"""ProShares ETF holdings: one daily CSV for every ProShares fund (``HoldingsSource``).

ProShares' data-downloads page (``proshares.com/resources/data-downloads``) links
``https://accounts.profunds.com/etfdata/psdlyhld.csv`` (about 1.8 MB, 170 funds, replaced
daily). It starts with ``PORTFOLIO HOLDINGS INFORMATION`` and ``AS OF 10/2/2026``, a blank line,
then a header row (``Fund Ticker, Fund Name, Security Ticker, Security Sedol, Security
Description, Coupon, Maturity Date, Shares/Contracts, Exposure Value (Notional + G/L), Market
Value``) and one row per line of each fund. It covers what N-PORT cannot: the volatility futures
funds (UVXY, SVXY, VIXY), the leveraged and inverse funds, with their futures and swaps, daily
instead of 60 to 240 days late.

The file has **no weight column**. A line's weight here is its **share of the fund's gross
exposure**: the line's value (its market value, else its exposure value: the notional of a
future or swap) over the sum of the absolute values of the fund's lines. It is not a share of
net assets (a leveraged fund's lines add up to several times its assets, and the file has no net
assets). A long-only fund's weights add up to 100%; a fund with short lines or swaps can add up to
anything, which is why the task does not check the sum for geared funds.

The file is one request, so the adapter reads it once (the ``directory`` request, saved as raw)
and answers each fund's request with that fund's rows as a small CSV (the preamble, the header
and its rows) so a fund's raw record normalises on its own.
"""

import csv
import io
import re
from datetime import date

from algotrade_sources.framework.base import FetchRequest, Normalized
from algotrade_sources.framework.holdings import (
    clean_text,
    funds_frame,
    holding_ticker,
    holdings_frame,
    number,
)
from algotrade_sources.framework.http import Http

SOURCE = "proshares_holdings"
DATASET = "etf_holdings"
DIRECTORY = "directory"
FILE_URL = "https://accounts.profunds.com/etfdata/psdlyhld.csv"
FUND, NAME, TICKER, SHARES = "Fund Ticker", "Fund Name", "Security Ticker", "Shares/Contracts"
DESCRIPTION, EXPOSURE, MARKET = (
    "Security Description",
    "Exposure Value (Notional + G/L)",
    "Market Value",
)
HEADER_ROW = 3  # rows before the table: title, as-of date, a blank line
_AS_OF = re.compile(r"AS OF\s+(\d{1,2})/(\d{1,2})/(\d{4})", re.IGNORECASE)
_SWAP = re.compile(r"\bSWAPS?\b", re.IGNORECASE)
_FUTURE = re.compile(r"\bFUT(?:URE)?S?\b|\bFUTR\b|FUTURE", re.IGNORECASE)
_CASH = re.compile(r"NET OTHER ASSETS", re.IGNORECASE)
_MONEY_MARKET = re.compile(r"MONEY MARKET|MNY MKT", re.IGNORECASE)
_TREASURY = re.compile(r"TREASURY|T-BILL|\bBILLS?\b", re.IGNORECASE)
_FX = re.compile(r"\bFORWARD\b|\bFX\b|CURRENCY", re.IGNORECASE)


def parse_file(payload: bytes) -> tuple[date, dict[str, tuple[str, list[dict[str, str]]]]]:
    """The download -> (the as-of date, fund ticker -> (fund name, its rows keyed by header))."""
    rows = list(csv.reader(io.StringIO(payload.decode("utf-8-sig", errors="replace"), newline="")))
    found = _AS_OF.search(" ".join(rows[1]) if len(rows) > 1 else "")
    if found is None:  # a changed "AS OF" line is a layout change
        raise ValueError("the file does not say what date it is as of")
    as_of = date(int(found.group(3)), int(found.group(1)), int(found.group(2)))
    if len(rows) <= HEADER_ROW:
        raise ValueError("the file has no table")
    names = [cell.strip() for cell in rows[HEADER_ROW]]
    missing = [c for c in (FUND, NAME, DESCRIPTION, EXPOSURE, MARKET) if c not in names]
    if missing:
        raise ValueError(f"the file's table has no column {missing}")
    funds: dict[str, tuple[str, list[dict[str, str]]]] = {}
    for row in rows[HEADER_ROW + 1 :]:
        if len(row) < len(names) or not row[0].strip():
            continue
        line = dict(zip(names, row, strict=False))
        ticker = line[FUND].strip().upper()
        funds.setdefault(ticker, (line[NAME].strip(), []))[1].append(line)
    if not funds:
        raise ValueError("the file's table has no lines")
    return as_of, funds


def asset_class(line: dict[str, str]) -> str:
    """The file has no asset class column: a line with a security ticker is an ``Equity`` (a stock
    or an ETF), the rest is told by its description (swaps, futures, net other assets, ...)."""
    text = line.get(DESCRIPTION, "")
    if clean_text(line.get(TICKER)):
        return "Equity"
    for kind, pattern in (
        ("Derivative", _SWAP),
        ("Futures", _FUTURE),
        ("Cash", _CASH),
        ("Money Market", _MONEY_MARKET),
        ("FX", _FX),
        ("Bond", _TREASURY),
    ):
        if pattern.search(text):
            return kind
    return "Other"


def line_value(line: dict[str, str]) -> float | None:
    """The line's size: its market value, else its exposure value (the notional of a future or
    swap, signed); ``None`` when neither reads."""
    market = number(line.get(MARKET))
    return market if market is not None else number(line.get(EXPOSURE))


def _slice(as_of_row: list[str], header: list[str], lines: list[dict[str, str]]) -> bytes:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerows([["PORTFOLIO HOLDINGS INFORMATION"], as_of_row, [], header])
    for line in lines:
        writer.writerow([line.get(c, "") for c in header])
    return out.getvalue().encode()


class ProsharesHoldings:
    """Implements ``base.HoldingsSource``. Request keys: ``directory``, or a ProShares ticker."""

    name = SOURCE
    dataset = DATASET
    directory_key = DIRECTORY
    scope_limited = False
    cadence_days = 1

    def __init__(self, http: Http) -> None:
        self._http = http
        self._funds: dict[str, tuple[str, list[dict[str, str]]]] = {}
        self._as_of_row: list[str] = []

    def _load(self, payload: bytes) -> None:
        as_of, self._funds = parse_file(payload)
        self._as_of_row = [f"AS OF {as_of.month}/{as_of.day}/{as_of.year}"]

    def fetch(self, request: FetchRequest) -> bytes | None:
        if request.key == DIRECTORY:
            payload = self._http.get(FILE_URL)
            if payload is not None:
                self._load(payload)
            return payload
        if not self._funds:
            self.fetch(FetchRequest(DIRECTORY))
        found = self._funds.get(request.key.upper())
        if found is None:
            return None
        header = [FUND, NAME, TICKER, "Security Sedol", DESCRIPTION, "Coupon", "Maturity Date"]
        header += [SHARES, EXPOSURE, MARKET]
        return _slice(self._as_of_row, header, found[1])

    def normalize(self, request: FetchRequest, payload: bytes) -> Normalized | None:
        as_of, funds = parse_file(payload)
        if request.key == DIRECTORY:
            frame = funds_frame((ticker, name) for ticker, (name, _) in funds.items())
            return Normalized(None, {}, parsed={"funds": frame})
        _, lines = funds[request.key.upper()]
        values = [line_value(line) for line in lines]
        gross = sum(abs(v) for v in values if v is not None)
        if gross <= 0:
            raise ValueError("no line of the fund has a readable value")
        rows = []
        for line, value in zip(lines, values, strict=True):
            kind = asset_class(line)
            ticker = holding_ticker(line.get(TICKER))
            rows.append(
                {
                    "holding_symbol": ticker,
                    "holding_name": clean_text(line.get(DESCRIPTION)),
                    "weight": None if value is None else round(value / gross, 12),
                    "asset_class": kind,
                    "sector": None,
                    "shares": number(line.get(SHARES)),
                    "identifier": clean_text(line.get("Security Sedol")),
                    "us_listed": ticker is not None and kind == "Equity",
                    "filed": None,
                }
            )
        holdings = holdings_frame(rows)
        if holdings.empty:
            raise ValueError("no line of the file has a readable weight")
        notes = {"unreadable_lines": len(rows) - len(holdings)}
        return Normalized(as_of, {}, notes=notes, parsed={"holdings": holdings})
