"""The ``verify`` task: compare a session's stored values with IBKR's, read-only (ADR 0026).

For each sampled instrument (``sample.py``) it pulls from IB Gateway, through the session
source ``ctx.sources["ibkr"]`` (opened and closed around the work, ``base.opened``): daily
TRADES bars, the underlying's implied-volatility history and IB dividends; for the
``option_symbols`` also the chain parameters and a few option snapshots. Every response is
saved raw (``IngestRun.fetch``). It compares them with what we stored (``checks.py``) and
writes one row per instrument and check to ``verification/ibkr``. Market data only: the
source cannot place, modify or cancel orders or read accounts (ADR 0026).

Item statuses are per instrument: ``OK`` once its checks are graded, ``FETCH_ERROR`` when
IBKR could not answer (the run is PARTIAL). Check outcomes are in the rows and the run
stats (``checks``: counts by status, ``failing``: examples); the ``quality`` task grades
them. When the gateway cannot be opened the run records ``skipped`` (the nightly step is
SKIPPED, never FAILED: verification never fails ingestion).
"""

from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from functools import partial

import numpy as np
import pandas as pd

from algotrade.config.site.settings import VerificationSettings, load_verification
from algotrade.core.time.calendar import sessions_ending
from algotrade.data import StoreReader
from algotrade.data.chains import option_quotes, underlying_quotes
from algotrade.data.prices import adjusted_bars, frame_to_series
from algotrade.data.rollups import rollup_on
from algotrade.storage.runs import RunRecord
from algotrade_ingestion.tasks.framework.run import IngestRun, TaskContext
from algotrade_ingestion.tasks.verification import checks, sample
from algotrade_sources.framework.base import (
    FetchRequest,
    SessionSource,
    SessionUnavailableError,
    opened,
)

TASK = "verify_ibkr"
TABLE = "verification/ibkr"
SOURCE = "ibkr"
PRICE_STATS = "rollups/instrument/price_stats@v2"
IV30 = "rollups/instrument/iv30@v1"
DIVIDENDS = "rollups/instrument/div_yield@v1"  # the materialised expression feature
TARGET_DAYS, MIN_DAYS = 30, 7  # option expiry nearest 30 calendar days, at least a week out
MAX_EXAMPLES = 10


@dataclass(frozen=True)
class Ours:
    """What we stored for the sample on the session."""

    bars: dict[str, pd.DataFrame]  # id -> date, high, low, close (split-adjusted as of session)
    stats: pd.DataFrame | None  # price_stats@v2, indexed by instrument_id
    iv30: pd.DataFrame | None
    dividends: pd.DataFrame | None

    def row(self, frame: pd.DataFrame | None, iid: str) -> pd.Series | None:
        if frame is None or iid not in frame.index:
            return None
        row = frame.loc[iid]
        return row if isinstance(row, pd.Series) else None


def _indexed(frame: pd.DataFrame | None) -> pd.DataFrame | None:
    if frame is None:
        return None
    return frame.drop_duplicates("instrument_id").set_index("instrument_id")


def load_ours(reader: StoreReader, session: date, ids: Sequence[str], sessions: int) -> Ours:
    start = sessions_ending(session, sessions)[0]
    bars: dict[str, pd.DataFrame] = {}
    try:
        frame, _ = adjusted_bars(reader, "1d", start, session, ids, None, "splits")
        series_of = frame_to_series(frame)  # flagged bars are dropped, never an error (ADR 0061)
    except LookupError:  # MissingDataError: no bars stored in the window at all
        series_of = {}
    for iid, series in series_of.items():
        days = pd.to_datetime(series.timestamps).date
        bars[iid] = pd.DataFrame(
            {"date": days, "high": series.high, "low": series.low, "close": series.close}
        )
    return Ours(
        bars,
        _indexed(rollup_on(reader, PRICE_STATS, session, ids)),
        _indexed(rollup_on(reader, IV30, session, ids)),
        _indexed(rollup_on(reader, DIVIDENDS, session, ids)),
    )


def _parsed(run: IngestRun, source: SessionSource, key: str, iid: str, kind: str) -> pd.DataFrame:
    normalized = run.fetch(source, FetchRequest(key, iid, run.session))
    if normalized is None or kind not in normalized.parsed:
        raise ValueError(f"IBKR {key}: nothing parsed")
    return normalized.parsed[kind]


def verify_one(
    run: IngestRun, source: SessionSource, pick: sample.Pick, ours: Ours, s: VerificationSettings
) -> list[checks.Row]:
    sym, iid, session = pick.symbol, pick.instrument_id, run.session
    g = checks.Grader(iid, sym, s)
    bars = _parsed(run, source, f"bars__{sym}", iid, "bars")
    empty = pd.DataFrame(columns=["date", "high", "low", "close"])
    checks.compare_bars(g, ours.bars.get(iid, empty), bars, session)
    divs = ours.row(ours.dividends, iid)
    div_ttm = divs.get("div_ttm") if divs is not None else None
    checks.compare_stats(g, ours.row(ours.stats, iid), bars, session, div_ttm)
    dividends = _parsed(run, source, f"div__{sym}", iid, "div")
    checks.compare_yield(g, divs.get("div_yield") if divs is not None else None, dividends)
    iv = _parsed(run, source, f"iv__{sym}", iid, "iv")
    checks.compare_iv(g, ours.row(ours.iv30, iid), iv, session)
    return g.rows


def contracts(reader: StoreReader, session: date, iid: str, n: int) -> pd.DataFrame:
    """Our stored ATM call and put (strike nearest the spot) of the expiry nearest 30 days."""
    chain = option_quotes(reader, session, [iid])
    spot = underlying_quotes(reader, session, [iid])
    if chain is None or chain.empty or spot is None or spot.empty or n == 0:
        return pd.DataFrame()
    days = (pd.to_datetime(chain["expiry"]) - pd.Timestamp(session)).dt.days
    chain = chain[days >= MIN_DAYS].assign(dte=days).reset_index(drop=True)
    if chain.empty:
        return chain
    expiry = chain["expiry"].iloc[int(np.argmin(np.abs(chain["dte"].to_numpy() - TARGET_DAYS)))]
    near = chain[chain["expiry"] == expiry].reset_index(drop=True)
    price = float(spot["price"].iloc[0])
    strike = near["strike"].iloc[int(np.argmin(np.abs(near["strike"].to_numpy() - price)))]
    atm: pd.DataFrame = near[near["strike"] == strike].sort_values("right")  # C before P
    return atm.head(n).reset_index(drop=True)


def verify_options(
    run: IngestRun, source: SessionSource, pick: sample.Pick, s: VerificationSettings
) -> list[checks.Row]:
    sym, iid = pick.symbol, pick.instrument_id
    ours = contracts(run.reader, run.session, iid, s.options_per_symbol)
    if ours.empty:
        g = checks.Grader(iid, sym, s)
        g.na("option_mid", "no stored option chain for the session")
        return g.rows
    params = run.fetch(source, FetchRequest(f"option_params__{sym}", iid, run.session))
    expirations = set(params.parsed["expirations"]["expiration"]) if params else set()
    strikes = set(params.parsed["strikes"]["strike"]) if params else set()
    rows: list[checks.Row] = []
    for contract in ours.to_dict("records"):
        expiry, strike = pd.Timestamp(contract["expiry"]).date(), float(contract["strike"])
        listed = (expiry in expirations and strike in strikes) if params else None
        key = f"option__{sym}__{expiry.isoformat()}__{contract['right']}__{strike:g}"
        quote = _parsed(run, source, key, str(contract["instrument_id"]), "option")
        g = checks.Grader(str(contract["instrument_id"]), sym, s)
        checks.compare_option(g, pd.Series(contract), listed, quote)
        rows += g.rows
    return rows


def _picks(run: IngestRun, s: VerificationSettings, symbols: Sequence[str]) -> list[sample.Pick]:
    resolver = run.resolver(run.session)
    if symbols:
        return sample.requested(resolver, symbols)
    stats = rollup_on(run.reader, PRICE_STATS, run.session)
    candidates = [] if stats is None else list(stats["instrument_id"].astype(str))
    events = sample.event_ids(run.reader, run.session)
    return sample.choose(resolver, run.session, s.core_symbols, s.rotating, events, candidates)


def _examples(rows: list[checks.Row]) -> list[dict[str, object]]:
    bad = [r for r in rows if r.status in ("FAIL", "WARN")]
    bad.sort(key=lambda r: (r.status != "FAIL", r.symbol, r.check))
    return [
        {"symbol": r.symbol, "check": r.check, "status": r.status, "ours": r.ours,
         "theirs": r.theirs, "note": r.note}
        for r in bad[:MAX_EXAMPLES]
    ]  # fmt: skip


def verify(
    ctx: TaskContext,
    session: date,
    symbols: Sequence[str] = (),
    settings: VerificationSettings | None = None,
) -> RunRecord:
    """Verify ``session`` (``symbols``: only those tickers; ``settings``: default from
    ``verification.toml``)."""
    s = settings or (
        load_verification(ctx.configs) if ctx.configs is not None else VerificationSettings()
    )
    source = ctx.sources[SOURCE]
    if not isinstance(source, SessionSource):
        raise TypeError("ibkr must be a SessionSource (IB Gateway)")
    with IngestRun(ctx, TASK, session) as run:
        picks = _picks(run, s, symbols)
        ours = load_ours(run.reader, session, [p.instrument_id for p in picks], s.bar_sessions)
        rows: list[checks.Row] = []
        try:
            with opened(source):
                for pick in picks:
                    one = partial(verify_one, run, source, pick, ours, s)
                    run.attempt(pick.instrument_id, partial(_graded, rows, one))
                for pick in [p for p in picks if p.symbol in s.option_symbols]:
                    options = partial(verify_options, run, source, pick, s)
                    run.attempt(f"{pick.instrument_id}#options", partial(_graded, rows, options))
        except SessionUnavailableError as exc:
            run.stats["skipped"] = f"WARN: {exc}"
            return run.record
        if rows:
            run.write(TABLE, pd.DataFrame([r.as_dict() for r in rows]), SOURCE)
        run.stats.update(
            instruments=len(picks),
            sample=dict(Counter(p.why for p in picks)),
            checks=checks.counts(rows),
            failing=_examples(rows),
            rows=len(rows),
        )
    return run.record


def _graded(rows: list[checks.Row], grade: Callable[[], list[checks.Row]]) -> str:
    rows.extend(grade())
    return "OK"
