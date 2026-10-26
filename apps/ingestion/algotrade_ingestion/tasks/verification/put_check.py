"""The ``option-history-put-check`` task (ADR 0084 decision 6): replicate Cboe's PUT index from the
stored option history and compare it with the published level (``macro/series`` ``IDX:PUT``).

``algotrade-ingest run option-history-put-check [--from D] [--to D] [--price mid|bid]``. The
history is read through ``data/option_history`` (the history store), the 3-month rate of each roll
day from the stored Treasury curve (a roll before the first stored curve FAILS the check: today's
rate is never used for 2019), the published level from ``macro/series``. The result is the run
record: the gap statistics (``put_replication.compare``), the tolerance fixed in the ADR before
any full run and whether the gap is within it. A miss is reported, never tuned away."""

from dataclasses import dataclass
from datetime import date

import pandas as pd

from algotrade.core.model.errors import MissingDataError
from algotrade.core.model.instruments import index_id
from algotrade.core.time.calendar import is_session, previous_session, third_friday
from algotrade.data import StoreReader
from algotrade.data.macro.series import latest_vintages, stored_vintages
from algotrade.data.option_history import reading
from algotrade.data.option_history.store import open_history
from algotrade.data.rates import TABLE as RATES_TABLE
from algotrade.data.rates import curve
from algotrade.storage.runs import RunRecord
from algotrade_ingestion.tasks.framework.run import IngestRun, TaskContext
from algotrade_ingestion.tasks.verification import put_replication

TASK = "option-history-put-check"
SERIES = "PUT"
THREE_MONTHS = 91  # tenor_days of the curve's 3M point
# Fixed before the full run (ADR 0084): the RMS of the daily return difference and the
# cumulative gap, annualised.
MAX_RMS_BP, MAX_ANNUAL_GAP_BP = 5.0, 100.0


@dataclass(frozen=True)
class PutCheckOptions:
    start: date | None = None
    end: date | None = None
    price: str = "mid"


def roll_sessions(sessions: list[date], start: date, end: date) -> list[date]:
    """The monthly expiry session of each month from ``start`` to ``end`` that the history holds:
    the third Friday, or the session before it when that is a holiday (a Saturday expiry before
    2015 traded its last on that Friday too)."""
    held = set(sessions)
    rolls = []
    for year in range(start.year, end.year + 1):
        for month in range(1, 13):
            friday = third_friday(year, month)
            day = friday if is_session(friday) else previous_session(friday)
            if start <= day <= end and day in held:
                rolls.append(day)
    return rolls


def three_month_rate(reader: StoreReader, roll: date) -> float:
    """The simple 3-month par rate (a fraction) on ``roll``; ``MissingDataError`` before the
    first stored curve (the stored fallback is the earliest curve, never a rate for that day)."""
    found = curve(reader, roll)
    if found.pre_snapshot:
        raise MissingDataError(
            RATES_TABLE,
            f"no curve stored on or before {roll} (the first is {found.curve_date})",
            "backfill `algotrade-ingest rates --from <start>`: it must reach back to 2002",
        )
    row = found.frame.loc[found.frame["tenor_days"] == THREE_MONTHS, "rate_par"]
    if row.empty:
        raise MissingDataError(RATES_TABLE, f"no 3M point on {found.curve_date}", "")
    return float(row.iloc[0])


def published_levels(reader: StoreReader) -> pd.Series:
    """The stored PUT index level per observation date (each date's latest vintage)."""
    frame = latest_vintages(stored_vintages(reader, [index_id(SERIES)]), date.max)
    if frame.empty:
        raise MissingDataError(
            "macro", f"no {SERIES} index levels stored", "run `algotrade-ingest run macro`"
        )
    return pd.Series(frame["value"].to_numpy(), index=pd.to_datetime(frame["obs_date"]).dt.date)


def put_check(
    ctx: TaskContext, url: str | None, today: date, options: PutCheckOptions
) -> RunRecord:
    """Run the check on the history store at ``url``; ``ctx.reader`` is the main store (rates,
    the published level)."""
    history = StoreReader(open_history(url))
    sessions = reading.sessions(history)
    with IngestRun(ctx, TASK, today) as run:
        lo = options.start or (sessions[0] if sessions else today)
        hi = options.end or (sessions[-1] if sessions else today)
        rolls = roll_sessions(sessions, lo, hi)
        run.stats.update(price=options.price, rolls=len(rolls))
        if len(rolls) < 2:
            run.failed("fewer than two monthly rolls in the stored history range")
            return run.record
        quotes: dict[date, pd.DataFrame] = {}
        for day in (s for s in sessions if rolls[0] <= s <= rolls[-1]):
            rows = reading.option_quotes(history, day, [put_replication.ROOT])
            if rows is not None:
                quotes[day] = rows
        try:
            rates = {r: three_month_rate(ctx.reader, r) for r in rolls}
            simulated = put_replication.replicate(quotes, rolls, rates, options.price)
            report = put_replication.compare(simulated, published_levels(ctx.reader))
        except (MissingDataError, ValueError) as exc:
            run.failed(f"{type(exc).__name__}: {exc}")
            return run.record
        days = max((report["end"] - report["start"]).days, 1)
        annual_gap = abs(float(report["gap_bp"])) * 365 / days
        run.stats.update({k: str(v) if isinstance(v, date) else v for k, v in report.items()})
        run.stats["annualised_gap_bp"] = annual_gap
        within = bool(report["rms_daily_diff_bp"] <= MAX_RMS_BP and annual_gap <= MAX_ANNUAL_GAP_BP)
        run.stats["within_tolerance"] = within
        if not within:  # reported as a FAILED check, never tuned away (ADR 0084 decision 6)
            run.failed(
                f"outside tolerance: RMS {report['rms_daily_diff_bp']:.1f} bp "
                f"(max {MAX_RMS_BP}), annualised gap {annual_gap:.1f} bp (max {MAX_ANNUAL_GAP_BP})"
            )
    return run.record
