"""Small synthetic payloads in the Nasdaq Trader and SPY-holdings formats."""

import io
from collections.abc import Iterable

NASDAQ_HEADER = (
    "Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares"
)
OTHER_HEADER = (
    "ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue|NASDAQ Symbol"
)
OPTIONS_HEADER = (
    "Root Symbol|Options Closing Type|Options Type|Expiration Date|Explicit Strike Price|"
    "Underlying Symbol|Underlying Issue Name|Pending"
)
FOOTER = "File Creation Time: 1002202621:31|||||||"


def nasdaq(rows: Iterable[tuple[str, str, str, str]]) -> bytes:
    """rows: (symbol, name, etf Y/N, test issue Y/N)."""
    lines = [NASDAQ_HEADER] + [f"{s}|{n}|Q|{t}|N|100|{e}|N" for s, n, e, t in rows] + [FOOTER]
    return "\n".join(lines).encode()


def other(rows: Iterable[tuple[str, str, str, str]]) -> bytes:
    """rows: (symbol, name, exchange code, etf Y/N)."""
    lines = [OTHER_HEADER] + [f"{s}|{n}|{x}|{s}|{e}|100|N|{s}" for s, n, x, e in rows] + [FOOTER]
    return "\n".join(lines).encode()


def options(underlyings: Iterable[str]) -> bytes:
    lines = (
        [OPTIONS_HEADER] + [f"{u}|N|C|01/15/2027|100.000|{u}|X|N" for u in underlyings] + [FOOTER]
    )
    return "\n".join(lines).encode()


def spy(tickers: Iterable[str], as_of: str = "01-Oct-2026") -> bytes:
    import openpyxl  # noqa: PLC0415

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Fund Name:", "SPDR S&P 500 ETF Trust"])
    ws.append(["Holdings:", f"As of {as_of}"])
    ws.append([])
    ws.append(
        [
            "Name",
            "Ticker",
            "Identifier",
            "SEDOL",
            "Weight",
            "Sector",
            "Shares Held",
            "Local Currency",
        ]
    )
    for t in tickers:
        ws.append([f"{t} INC", t, "X", "Y", 1.0, "-", 1.0, "USD"])
    ws.append(["US DOLLAR", "-", "", "", 0.1, "-", 1.0, "USD"])
    ws.append([])
    ws.append(["Past performance is not a reliable indicator of future performance."])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
