"""Published series files, written from the documented formats (no network).

Stooq daily CSV (``Date,Open,High,Low,Close,Volume``), the Fed's ``ebp_csv.csv`` (monthly, dated
``m/d/yyyy`` on the first of the month) and the OFR financial stress index CSV (daily, one column
per component. Trimmed copies of the real files are in ``tests/fixtures/sources/published``.

The S&P 500 membership file (``membership_csv``) is RECORDED: a 77-row slice of
``sp500_ticker_start_end.csv`` of https://github.com/fja05680/sp500 (MIT licence, by fja05680),
downloaded 2026-10-08 (1,262 rows), rows exactly as published: the tickers of the Tiingo slice's
names and a seeded sample, with ones that left and came back (``H``), renamed (``FB`` then
``META``) and still open (``AAPL``).
"""

from tests.conftest import REPO_ROOT

MEMBERSHIP = REPO_ROOT / "tests/fixtures/sources/sp500_history/sp500_ticker_start_end_slice.csv"


def membership_csv() -> bytes:
    return MEMBERSHIP.read_bytes()


STOOQ = b"""Date,Open,High,Low,Close,Volume
2026-09-28,5710.12,5735.40,5698.77,5721.33,2845000000
2026-09-29,5721.33,5740.01,5702.50,5709.91,2701000000
2026-09-30,5709.91,5718.44,5655.20,5666.64,3012000000
2026-10-01,5666.64,5702.88,5660.01,5698.20,2655000000
"""

EBP = b"""date,gz_spread,ebp,est_prob
1/1/1973,0.6893,0.1131,0.1219
2/1/1973,0.7024,0.1524,0.1306
10/1/2008,3.9501,2.2183,0.7120
8/1/2026,1.1034,-0.0214,0.1850
"""

OFR_FSI = b"""Date,OFR FSI,Credit,Equity valuation,Safe assets,Funding,Volatility
2000-01-03,-1.2,-0.3,-0.2,-0.1,-0.4,-0.2
2008-10-10,29.6,9.1,5.0,0.3,6.1,9.1
2026-10-02,-2.5,-0.7,-0.6,-0.2,-0.5,-0.5
"""

NO_DATA = b"No data"

# What stooq.com/q/d/l now answers a script: a 200 with a browser-verification page.
JS_CHALLENGE = (
    b'<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="robots" content="noindex">'
    b"</head><body><noscript>This site requires JavaScript to verify your browser.</noscript>"
    b"<script>(async()=>{})()</script></body></html>"
)
