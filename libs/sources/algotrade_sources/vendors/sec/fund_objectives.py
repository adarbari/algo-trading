"""SEC fund prospectuses: the investment objective of an ETF, from public SEC data (free, no key).

Massive describes stocks but not ETFs, so ETFs get their prospectus's "investment objective"
instead. Two SEC files, both official bulk data:

- ``https://www.sec.gov/files/company_tickers_mf.json``: every fund share class with its
  ticker, series id (``S000...``) and class id (one request; ``SecFundTickerMap``).
- ``https://www.sec.gov/files/dera/data/mutual-fund-prospectus-risk/return-summary-data-sets/
  <year>q<n>_rr1.zip``: the Mutual Fund Prospectus Risk/Return Summary Data Sets, one zip per
  calendar quarter (~80 MB; checked 2026-10-04: 2026q2 holds 638k text and number facts of
  prospectus XBRL exhibits). Its ``txt.tsv`` has the text blocks per series: we keep
  ``ObjectivePrimaryTextBlock`` (``SecFundObjectives``), the sentence or two that opens a
  prospectus ("The Fund seeks to track the performance of ..."). ``sub.tsv`` gives the filing
  date and form of each accession.

A fund appears in a quarter only if it filed a prospectus then (most funds once a year, at
different months), so several quarters are read and the latest filing per series wins. Funds
that do not file this exhibit (grantor trusts such as GLD, unit trusts such as SPY) have no
objective here.

The texts carry XBRL escaping (``&amp;``), stray spaces before punctuation, spaces inside
hyphenated words, curly quotes turned into ``?`` and some dropped apostrophes; ``clean_text``
repairs the common cases (a few apostrophes stay lost). Same contact ``User-Agent``, ``sec``
limiter and ``[sec_edgar]`` section as the other SEC sources.
"""

import csv
import html
import io
import json
import re
import zipfile
from datetime import date

import pandas as pd

from algotrade_sources.framework.base import FetchRequest, Normalized
from algotrade_sources.framework.http import Http
from algotrade_sources.vendors.sec.edgar import SOURCE, act_symbol

FUND_TICKERS_URL = "https://www.sec.gov/files/company_tickers_mf.json"
QUARTER_URL = (
    "https://www.sec.gov/files/dera/data/mutual-fund-prospectus-risk/"
    "return-summary-data-sets/{quarter}_rr1.zip"
)
QUARTER = re.compile(r"^\d{4}q[1-4]$")
SERIES = re.compile(r"^S\d{9}$")
OBJECTIVE_TAG = "ObjectivePrimaryTextBlock"
FUND_COLUMNS = ("symbol", "series_id", "class_id", "cik")
OBJECTIVE_COLUMNS = ("series_id", "objective", "accn", "form", "filed")
MIN_LENGTH = 30  # shorter texts are headings or placeholders, not an objective
MAX_LENGTH = 1200  # cut at a sentence end below this, so the Overview stays short


def _quoted(match: re.Match[str]) -> str:
    """``?Fund?`` (curly quotes the XBRL export lost) -> ``"Fund"``, spaced from a word after."""
    after = match.string[match.end() : match.end() + 1]
    return f'"{match.group(1).strip()}"' + (" " if after.isalnum() else "")


def clean_text(raw: str) -> str:
    """XBRL text block -> plain text. Undone: quotes written as ``\\"`` or ``""`` and a wrapping
    pair of quotes, HTML entities (``&amp;``, sometimes twice) and tags, stray spaces (before
    closing punctuation, inside ``long -term``). Repaired: the glyphs the export turned into
    ``?`` (``Fund?s`` -> ``Fund's``, ``?Fund?`` -> ``"Fund"``; any other ``?`` is a lost mark or
    bullet and goes: an objective is never a question). An apostrophe lost without a ``?`` is
    restored only for an opening ``The Funds investment objective``."""
    text = raw.replace('\\"', '"').replace('""', '"')
    if len(text) > 1 and text.startswith('"') and text.endswith('"'):
        text = text[1:-1]
    for _ in range(2):  # some exhibits are escaped twice
        unescaped = html.unescape(text)
        if unescaped == text:
            break
        text = unescaped
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"(?<=[A-Za-z.])\?(?=(?:s|t|re|ve|ll|d)\b)", "'", text)
    text = re.sub(r"(?<!\w)\?(?=\w)((?:(?!\. )[^?()]){1,40}?)\s*\?", _quoted, text)
    text = re.sub(r"\s*\?\s*", " ", text)
    text = " ".join(text.split())
    text = re.sub(r"\s+([),.;:])", r"\1", text)
    text = re.sub(r"\(\s+", "(", text)
    text = re.sub(r"([A-Za-z]) -(?=[A-Za-z])", r"\1-", text)  # "long -term"
    return re.sub(
        r"^The Funds (?=investment|primary|principal|objective|goal)", "The Fund's ", text
    )


def shorten(text: str, limit: int = MAX_LENGTH) -> str:
    """``text`` cut after the last full sentence that fits ``limit`` (else at a word)."""
    if len(text) <= limit:
        return text
    head = text[:limit]
    end = head.rfind(". ")
    if end >= limit // 2:
        return head[: end + 1]
    return head[: head.rfind(" ")].rstrip(",;:") + "..."


def parse_fund_tickers(payload: bytes) -> pd.DataFrame:
    """``company_tickers_mf.json`` -> one row per fund ticker (``FUND_COLUMNS``)."""
    doc = json.loads(payload)
    fields = list(doc.get("fields") or [])
    rows = []
    for values in doc.get("data") or []:
        r = dict(zip(fields, values, strict=False))
        symbol, series = str(r.get("symbol") or "").strip(), str(r.get("seriesId") or "")
        if symbol and SERIES.match(series):
            cik = r.get("cik")
            rows.append(
                {
                    "symbol": act_symbol(symbol),
                    "series_id": series,
                    "class_id": r.get("classId") or None,
                    "cik": f"{int(cik):010d}" if cik is not None else None,
                }
            )
    frame = pd.DataFrame(rows, columns=list(FUND_COLUMNS))
    # A ticker can sit under two series (a reorganised fund): keep both, the objectives decide
    # (the task takes the series with the latest filing).
    return frame.drop_duplicates(["symbol", "series_id"]).reset_index(drop=True)


def _is_day(text: str) -> bool:
    return len(text) == 8 and text.isdigit()


def _filings(archive: zipfile.ZipFile) -> dict[str, tuple[date | None, str | None]]:
    """accession -> (filing date, form) from ``sub.tsv``."""
    with archive.open("sub.tsv") as raw:
        rows = csv.reader(io.TextIOWrapper(raw, encoding="utf-8", newline=""), delimiter="\t")
        head = next(rows)
        adsh, form, filed = head.index("adsh"), head.index("form"), head.index("filed")
        out: dict[str, tuple[date | None, str | None]] = {}
        for row in rows:
            day = row[filed]
            parsed = date(int(day[:4]), int(day[4:6]), int(day[6:])) if _is_day(day) else None
            out[row[adsh]] = (parsed, row[form] or None)
        return out


def parse_objectives(payload: bytes) -> pd.DataFrame:
    """A quarterly data-set zip -> the latest investment objective per series
    (``OBJECTIVE_COLUMNS``), cleaned and shortened; empty when the quarter has none."""
    csv.field_size_limit(1 << 28)  # risk text blocks run to megabytes
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        filings = _filings(archive)
        found: dict[str, tuple[date, str, str, str | None]] = {}
        with archive.open("txt.tsv") as raw:
            text = io.TextIOWrapper(raw, encoding="utf-8", newline="")
            rows = csv.reader(text, delimiter="\t")  # fields with a quote are CSV-quoted
            head = next(rows)
            adsh, tag, series, value = (head.index(c) for c in ("adsh", "tag", "series", "value"))
            for row in rows:
                if len(row) != len(head) or row[tag] != OBJECTIVE_TAG:
                    continue
                if not SERIES.match(row[series]):
                    continue
                objective = clean_text(row[value])
                if len(objective) < MIN_LENGTH:
                    continue
                day, form = filings.get(row[adsh], (None, None))
                latest = (day or date.min, row[adsh])
                if row[series] not in found or latest > found[row[series]][:2]:
                    found[row[series]] = (latest[0], latest[1], objective, form)
    rows_out = [
        {
            "series_id": s,
            "objective": shorten(objective),
            "accn": accn,
            "form": form,
            "filed": None if day == date.min else day,
        }
        for s, (day, accn, objective, form) in sorted(found.items())
    ]
    return pd.DataFrame(rows_out, columns=list(OBJECTIVE_COLUMNS)).astype(object)


class _Sec:
    name = SOURCE
    dataset = ""

    def __init__(self, http: Http) -> None:
        self._http = http


class SecFundTickerMap(_Sec):
    """Fund ticker -> series and class ids. Request key: ``fund_tickers``."""

    dataset = "company_tickers_mf"

    def fetch(self, request: FetchRequest) -> bytes | None:
        return self._http.get(FUND_TICKERS_URL)

    def normalize(self, request: FetchRequest, payload: bytes) -> Normalized | None:
        frame = parse_fund_tickers(payload)
        if frame.empty:
            return None
        return Normalized(session_date=None, tables={}, parsed={"funds": frame})


class SecFundObjectives(_Sec):
    """One quarter's investment objectives per series. Request key: ``<year>q<n>``
    (``2026q2``). A quarter not published yet answers 404 (``None``)."""

    dataset = "fund_objectives"

    def fetch(self, request: FetchRequest) -> bytes | None:
        if not QUARTER.match(request.key):
            raise ValueError(f"not a quarter like 2026q2: {request.key!r}")
        return self._http.get(QUARTER_URL.format(quarter=request.key))

    def normalize(self, request: FetchRequest, payload: bytes) -> Normalized | None:
        return Normalized(
            session_date=None, tables={}, parsed={"objectives": parse_objectives(payload)}
        )
