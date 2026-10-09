"""The winners-study data test: Tiingo daily bars for a seeded 200-name sample (edges ED6c).

``algotrade-ingest run winners-sample`` picks 200 listings from the latest
``instruments/listing_history`` snapshot, fetches each name's daily bars from 2010 with the
Tiingo prices adapter (one request per name, at the shared ``tiingo`` pace: ~4 hours at the free
tier's 72 s, so run it detached), and writes a coverage report. It answers one question before
the owner pays for a full backfill: does Tiingo hold the prices of names that have since
delisted? Pass (``sample_coverage.summarize``): at least 90% of the delisted names have bars to
their end date, under 2% of the sessions between a name's first and last bar are missing, and a
recycled ticker returns no bar outside its own listing's dates.

The sample (``pick_sample``, seeded: the same snapshot and seed give the same names), stocks on
NYSE / NASDAQ / AMEX / ARCA listed at least a year, one listing per ticker, so at most 200
unique Tiingo symbols (``MAX_SYMBOLS``; the free tier allows 500 a month, shared with
``bars-history``, whose own budget does not see these):

- **delisted**: ``per_year`` (10) names whose end date falls in each year 2011-2020;
- **live**: ``live`` (50) names listed since 2010 or earlier and still trading;
- **winners**: ``winners`` (50) of the hand-listed ``BIG_WINNERS`` that are live names listed
  since 2010 or earlier. The list is hand-made (from memory of 2010-2016 outperformers, not
  from prices: ranking by the close ratio needs every name's bars first), and the report shows
  each one's split-adjusted 2010-2016 price ratio so the owner can see whether the picks hold.

**Nothing is written to ``bars/1d``**: the run stores the raw payloads (``raw/source=tiingo``,
as every fetch) and the coverage report, ``var/logs/winners-sample-<session>.json`` (``--report``
changes the path); the bars enter a table only after the owner reads the report and decides.
The request asks for the ticker's whole history from 2010 and the rows are clipped to the
listing's dates afterwards, so a recycled ticker's other company shows up as ``outside_rows``.
Resumable like ``bars-history``: a name an earlier run of the same sample (seed and listing
snapshot, strata sizes) finished is not asked again, a crashed run's checkpointed items
included (each item's status carries its coverage row, so the report is rebuilt from the items
alone). The end date
is read here (through ``data.listings.read_listings``) to pick the strata, never as a feature.
"""

import json
import random
from collections import Counter
from collections.abc import Sequence
from datetime import date
from functools import partial
from pathlib import Path
from typing import Any

import pandas as pd

from algotrade.core.model.errors import MissingDataError
from algotrade.core.time.calendar import sessions_between
from algotrade.data.listings.universe import read_listings
from algotrade.storage.runs import RunRecord
from algotrade_ingestion.tasks.framework.run import (
    FETCH_ERROR,
    IngestRun,
    NoResponseError,
    TaskContext,
    status_label,
)
from algotrade_ingestion.tasks.listings.sample_coverage import (
    DELISTED,
    LIVE,
    WINNER,
    Pick,
    coverage_row,
    summarize,
)
from algotrade_sources.framework.base import FetchRequest, Source

TASK = "winners-sample"
SINCE = date(2010, 1, 1)
MAX_SYMBOLS = 200  # unique Tiingo symbols this task may ever ask for in one run
DEFAULT_SEED = 20261008
DELISTED_YEARS = range(2011, 2021)
PER_YEAR, LIVE_N, WINNERS_N = 10, 50, 50
MIN_LISTED_DAYS = 365  # shorter-lived names are warrants, rights and units
EXCHANGES = ("NYSE", "NASDAQ", "AMEX", "ARCA")
STOP_AFTER_FAILED = 3  # names Tiingo did not answer in a row (key, caps, outage)
CHECKPOINT_EVERY = 5
DONE = ("OK", "NO_DATA")  # item statuses that hold a coverage row
DEFAULT_REPORT = "var/logs/winners-sample-{session}.json"
# Hand-listed, from memory: stocks that rose a lot from 2010 to 2016 and were listed by 2010.
# The report's ``ratio_2010_2016`` is the check; names not live in the file are skipped.
BIG_WINNERS = [
    "NFLX",
    "AMZN",
    "TSLA",
    "NVDA",
    "MNST",
    "REGN",
    "ILMN",
    "ALGN",
    "AVGO",
    "LULU",
    "ULTA",
    "SWKS",
    "ISRG",
    "CMG",
    "TTWO",
    "ADBE",
    "CRM",
    "SBUX",
    "V",
    "MA",
    "UNH",
    "LMT",
    "NOC",
    "ROST",
    "ORLY",
    "AZO",
    "DPZ",
    "CHDN",
    "JBHT",
    "ODFL",
    "CSGP",
    "MKTX",
    "POOL",
    "TYL",
    "TDG",
    "STZ",
    "MU",
    "LRCX",
    "FISV",
    "FIS",
    "ADP",
    "INTU",
    "COST",
    "TJX",
    "LOW",
    "HD",
    "DXCM",
    "VRTX",
    "BIIB",
    "GILD",
    "AMGN",
    "BMRN",
    "INCY",
    "NBIX",
    "SGEN",
    "TREX",
    "IDXX",
    "MTD",
    "WST",
    "ZBRA",
    "ANSS",
    "BKNG",
]


def _stocks(listings: pd.DataFrame) -> pd.DataFrame:
    stocks = listings[
        listings["asset_type"].astype(str).eq("Stock") & listings["exchange"].isin(EXCHANGES)
    ].copy()
    stocks["start"] = pd.to_datetime(stocks["start_date"])
    stocks["end"] = pd.to_datetime(stocks["end_date"])
    return stocks.sort_values(["ticker", "start"], kind="stable")


def _pick(row: Any, stratum: str, recycled: set[str]) -> Pick:
    end = None if pd.isna(row.end) else row.end.date()
    return Pick(str(row.ticker), row.start.date(), end, stratum, str(row.ticker) in recycled)


def pick_sample(
    listings: pd.DataFrame,
    seed: int = DEFAULT_SEED,
    per_year: int = PER_YEAR,
    live: int = LIVE_N,
    winners: int = WINNERS_N,
    years: Sequence[int] = DELISTED_YEARS,
) -> list[Pick]:
    """The sample from a frame of ``ticker`` / ``exchange`` / ``asset_type`` / ``start_date`` /
    ``end_date`` rows. One listing per ticker, strata in order winners, delisted, live."""
    if per_year * len(years) + live + winners > MAX_SYMBOLS:
        raise ValueError(f"the sample would ask for more than {MAX_SYMBOLS} symbols")
    stocks = _stocks(listings)
    count = Counter(str(t) for t in listings["ticker"])
    recycled = {t for t, n in count.items() if n > 1}
    rng = random.Random(seed)
    taken: set[str] = set()
    picks: list[Pick] = []

    def take(frame: pd.DataFrame, n: int, stratum: str, ordered: bool = False) -> None:
        rows = [r for r in frame.itertuples() if str(r.ticker) not in taken]
        chosen = rows[:n] if ordered else rng.sample(rows, min(n, len(rows)))
        for r in chosen:
            taken.add(str(r.ticker))
            picks.append(_pick(r, stratum, recycled))

    long_lived = (stocks["end"] - stocks["start"]).dt.days >= MIN_LISTED_DAYS
    open_early = stocks[stocks["end"].isna() & (stocks["start"] <= pd.Timestamp("2010-12-31"))]
    order = {t: i for i, t in enumerate(BIG_WINNERS)}
    listed = open_early[open_early["ticker"].isin(order)]
    take(listed.sort_values("ticker", key=lambda s: s.map(order)), winners, WINNER, ordered=True)
    for year in years:
        ended = stocks[long_lived & (stocks["end"].dt.year == year)]
        take(ended, per_year, DELISTED)
    take(open_early, live, LIVE)
    return picks


NO_BARS = pd.DataFrame(columns=["ts", "close"])
NO_ACTIONS = pd.DataFrame(columns=["ts", "split_factor"])


def _status(row: dict[str, Any]) -> str:
    return f"OK: {json.dumps(row, separators=(',', ':'))}"


def _fetch_name(
    run: IngestRun, source: Source, pick: Pick, sessions: list[date], until: date
) -> str:
    key = f"{pick.ticker}:{SINCE.isoformat()}:"  # the whole history from 2010, clipped here
    request = FetchRequest(key)
    raw_key = f"{pick.ticker}__{pick.start_date.isoformat()}"
    try:
        normalized = run.fetch(source, request, raw_key=raw_key)
    except NoResponseError:  # 404: Tiingo does not list the ticker
        empty = pd.DataFrame(columns=["ts", "close"])
        noted = coverage_row(
            pick, empty, pd.DataFrame(columns=["ts", "split_factor"]), sessions, SINCE, until
        )
        return "NO_DATA: " + json.dumps(noted, separators=(",", ":"))
    bars = normalized.tables["bars/1d"] if normalized else pd.DataFrame(columns=["ts", "close"])
    actions = (
        normalized.parsed["actions"] if normalized else pd.DataFrame(columns=["ts", "split_factor"])
    )
    return _status(coverage_row(pick, bars, actions, sessions, SINCE, until))


def _item(pick: Pick) -> str:
    return f"win:{pick.ticker}:{pick.start_date.isoformat()}"


def _earlier(run: IngestRun, sample: dict[str, Any]) -> dict[str, str]:
    """The finished items (a coverage row each) of earlier runs (any status) that sampled the same
    way (``sample``: seed, listing snapshot, strata sizes): item key -> status, later wins."""
    done: dict[str, str] = {}
    for record in run.writer.runs_for(TASK):  # any status: a crashed run's items count
        if record.run_id == run.run_id:
            continue
        if all(record.stats.get(k) == v for k, v in sample.items()):
            done.update({k: s for k, s in record.items.items() if status_label(s) in DONE})
    return done


def _rows(items: dict[str, str], picks: Sequence[Pick]) -> list[dict[str, Any]]:
    """The coverage rows the items hold, in sample order."""
    rows = []
    for pick in picks:
        status = items.get(_item(pick), "")
        if status_label(status) in DONE:
            rows.append(json.loads(status.partition(": ")[2]))
    return rows


def ingest_winners_sample(
    ctx: TaskContext,
    source: Source,
    session: date,
    report: Path | None = None,
    seed: int = DEFAULT_SEED,
    limit: int | None = None,
    per_year: int = PER_YEAR,
    live: int = LIVE_N,
    winners: int = WINNERS_N,
) -> RunRecord:
    """Fetch and grade the sample (``limit``: ask for at most that many names this run)."""
    with IngestRun(ctx, TASK, session) as run:
        try:
            listings, snapshot = read_listings(run.reader)
        except MissingDataError as error:  # no listing-history snapshot yet
            run.failed(f"{error}: run `algotrade-ingest run listing-history` first")
            return run.record
        picks = pick_sample(listings, seed, per_year, live, winners)
        symbols = {p.ticker for p in picks}
        assert len(symbols) <= MAX_SYMBOLS
        sessions = sessions_between(SINCE, session)
        sample = {
            "seed": seed,
            "listing_snapshot": snapshot.isoformat(),
            "strata": [per_year, live, winners],
        }
        earlier = _earlier(run, sample)
        todo = [p for p in picks if _item(p) not in run.items and _item(p) not in earlier]
        todo = todo[: len(todo) if limit is None else max(0, limit)]
        failed_in_a_row = 0
        for i, pick in enumerate(todo, 1):
            fetch = partial(_fetch_name, run, source, pick, sessions, session)
            status = run.attempt(_item(pick), fetch)
            failed_in_a_row = failed_in_a_row + 1 if status_label(status) == FETCH_ERROR else 0
            if i % CHECKPOINT_EVERY == 0:
                run.checkpoint()
            if failed_in_a_row >= STOP_AFTER_FAILED:
                run.partial(f"stopped: Tiingo failed {failed_in_a_row} names in a row ({status})")
                break
        rows = _rows({**earlier, **run.items}, picks)
        summary = summarize(rows)
        left = len(picks) - len(rows)
        if left and not run.failures():
            run.partial(f"{left} sampled names not fetched yet")
        run.stats.update(
            **sample,
            symbols=len(symbols),
            fetched=len(todo),
            pending=left,
            licence=ctx.settings.tiingo_licence,
            summary=summary,
        )
        if rows:
            path = report or Path(DEFAULT_REPORT.format(session=session.isoformat()))
            path.parent.mkdir(parents=True, exist_ok=True)
            document = {
                "session": session.isoformat(),
                "listing_snapshot": snapshot.isoformat(),
                "seed": seed,
                "summary": summary,
                "names": rows,
            }
            path.write_text(json.dumps(document, indent=1, sort_keys=False))
            run.stats["report"] = str(path)
        run.stats["items"] = run.counts()
    return run.record
