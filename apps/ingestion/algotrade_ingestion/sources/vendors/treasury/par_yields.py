"""U.S. Treasury daily par yield curve rates: one CSV per calendar year.

``https://home.treasury.gov/resource-center/data-chart-center/interest-rates/
daily-treasury-rates.csv/<year>/all?type=daily_treasury_yield_curve&field_tdr_date_value=
<year>&page&_format=csv`` (official, free, no key; see docs/data/vendors.md). One row per
date the bond market was open, newest first: ``Date`` (MM/DD/YYYY) then one column per
constant maturity in PERCENT (``"1 Mo"``, ``"1.5 Month"``, ``"6 Mo"``, ``"1 Yr"``,
``"30 Yr"``). Tenors were added over time (2 Mo in 2018, 4 Mo in 2022, 1.5 Month in 2025),
so a cell or a whole column may be missing. A year with no data yet returns an empty body.

``normalize`` emits storage-ready ``rates/treasury`` rows in long form: one per date and
tenor (``1.5M``, ``10Y``), the par yield as a DECIMAL, its days and the continuously
compounded rate (conventions: ``algotrade.quant.rates``, ADR 0021), keyed by
``RATE:UST-<tenor>``. Several dates per payload: the task writes one partition per date.
"""

import csv
import io
import re
from datetime import UTC, datetime

import pandas as pd

from algotrade.core.model.instruments import AssetClass, instrument_id
from algotrade.quant.rates import par_to_continuous, tenor_days
from algotrade_ingestion.sources.framework.base import FetchRequest, Normalized
from algotrade_ingestion.sources.framework.http import Http

SOURCE = "treasury"
DATASET = "par_yield_curve"
TABLE = "rates/treasury"
URL = (
    "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
    "daily-treasury-rates.csv/{year}/all?type=daily_treasury_yield_curve"
    "&field_tdr_date_value={year}&page&_format=csv"
)
COLUMNS = ("instrument_id", "ts", "tenor", "tenor_days", "rate_par", "rate_cont")
_HEADER = re.compile(r"^(\d+(?:\.\d+)?)\s*(mo|month|months|yr|year|years)$", re.IGNORECASE)


def tenor_of(header: str) -> str | None:
    """``"1 Mo"`` -> ``"1M"``, ``"1.5 Month"`` -> ``"1.5M"``, ``"30 Yr"`` -> ``"30Y"``."""
    match = _HEADER.match(header.strip())
    if match is None:
        return None
    unit = "M" if match.group(2).lower().startswith("mo") else "Y"
    return f"{match.group(1)}{unit}"


def curve_rows(records: list[dict[str, object]]) -> pd.DataFrame:
    """``ts``, ``tenor``, ``rate_par`` records -> table rows (``COLUMNS``) by date and days."""
    frame = pd.DataFrame(records, columns=["ts", "tenor", "rate_par"])
    frame["tenor_days"] = [tenor_days(str(t)) for t in frame["tenor"]]
    frame["rate_cont"] = par_to_continuous(
        frame["rate_par"].to_numpy(dtype=float), frame["tenor_days"].to_numpy(dtype=float)
    )
    frame["instrument_id"] = [instrument_id(AssetClass.RATE, f"UST-{t}") for t in frame["tenor"]]
    frame = frame.sort_values(["ts", "tenor_days"], kind="stable").reset_index(drop=True)
    return frame[list(COLUMNS)]


def parse_curve(payload: bytes) -> tuple[pd.DataFrame, int]:
    """Table rows (``COLUMNS``) and the number of unrecognised columns."""
    text = payload.decode("utf-8-sig").strip()
    if not text:
        return curve_rows([]), 0
    rows = list(csv.reader(io.StringIO(text)))
    header, body = rows[0], rows[1:]
    if not header or header[0].strip().lower() != "date":
        raise ValueError(f"unexpected Treasury CSV header: {header[:3]}")
    tenors = [tenor_of(h) for h in header[1:]]
    records = []
    for row in body:
        if not row or not row[0].strip():
            continue
        day = datetime.strptime(row[0].strip(), "%m/%d/%Y").replace(tzinfo=UTC)
        for tenor, cell in zip(tenors, row[1:], strict=False):
            if tenor is None or not cell.strip() or cell.strip().upper() == "N/A":
                continue
            records.append({"ts": pd.Timestamp(day), "tenor": tenor, "rate_par": float(cell) / 100})
    return curve_rows(records), tenors.count(None)


class TreasuryParYields:
    """Implements ``sources.base.Source``. Request key: a calendar year (``"2025"``)."""

    name = SOURCE
    dataset = DATASET

    def __init__(self, http: Http) -> None:
        self._http = http  # paced by the shared ``treasury`` limiter (sources.toml)

    def fetch(self, request: FetchRequest) -> bytes | None:
        year = int(request.key)
        return self._http.get(URL.format(year=year))

    def normalize(self, request: FetchRequest, payload: bytes) -> Normalized | None:
        frame, unknown = parse_curve(payload)
        notes = {"unknown_columns": unknown} if unknown else {}
        return Normalized(session_date=None, tables={TABLE: frame}, notes=notes)
