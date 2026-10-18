"""``futures-curves``: the nightly futures curve snapshot (``rates/futures_curve``).

For each root of ``[ibkr] futures_roots`` (commodity and bond futures: crude, gas, metals,
grains, sugar, the Treasury note and bond futures, VIX) one request to the read-only IB
Gateway facade (``ctx.sources["ibkr"]``, opened and closed around the work): the ``[ibkr]
futures_front`` nearest unexpired listed contracts with their quotes streamed after the close
(last, IB's close = the prior settle, bid, ask, day volume, open interest). Per contract one
row: ``instrument_id`` ``FUT:<root>:<YYYY-MM>`` with ``parent_id`` ``FUT:<root>`` (ADR 0009),
expiry, ``price`` (one ``price_kind`` per root and session: ``last`` or ``settle``) and the raw
fields, so the curve (basis, roll yield) is rebuilt from our own history, which accrues from
the first night: IB serves expired contracts only a couple of years back and nothing is
backfilled here. Personal licence (IBKR market data, ADR 0028).

The prices are an EVENING SNAPSHOT whose kind follows each contract's OWN next session open (IB's
``tradingHours``, kept as ``next_open``; IB rolls its ``close`` tick then, which differs by
exchange: CME 18:00 New York, CBOT grains 20:00, ICE sugar the next morning, a holiday Monday
from the Sunday evening). Before ``next_open`` ``price`` is ``last`` (``price_kind`` ``last``:
the session's own last trade; ``close`` is still the day before's settle); from it until
``SETTLE_BOUND`` (12:00 New York on the next weekday, before every root's next settlement)
``price`` is IB's ``close``, exactly the session's exchange settle (``settle``), and ``last`` is
ignored (the next trade date's trading); later nothing is stored (every root ``NO_DATA``, the run
PARTIAL). A root whose ``tradingHours`` are missing or unparsable, or whose contracts disagree,
is ``NO_DATA`` too (fail closed). One ``price_kind`` per root and session.

A root the gateway does not list, or whose contracts came back with no price at all (no market
data permission for the exchange), is recorded ``NO_DATA: <reason>`` and writes nothing; the
others are stored. A gateway that cannot be opened is a skip: the run records ``skipped`` and
is PARTIAL, never COMPLETE (the nightly step is SKIPPED with a WARN, never FAILED). Items are
resumable per root: a root already ``OK`` or ``NO_DATA`` in a resumed run is not asked again.
"""

from collections.abc import Sequence
from contextlib import nullcontext
from datetime import date, datetime, time, timedelta
from functools import partial

import pandas as pd

from algotrade.config.site.ibkr import FuturesRoot
from algotrade.core.time.calendar import EXCHANGE_TZ, is_weekend
from algotrade.data.futures.curves import FUTURES_CURVE, contract_id, month_label, root_id
from algotrade.storage.runs import RunRecord
from algotrade_ingestion.tasks.framework.run import IngestRun, TaskContext, status_label
from algotrade_sources.framework.base import (
    FetchRequest,
    SessionSource,
    SessionUnavailableError,
    opened,
)

TASK = "futures_curves"
TABLE = FUTURES_CURVE
SOURCE = "ibkr"
DONE = ("OK", "NO_DATA")  # root statuses that need no refetch
# The window in which IB's ``close`` is still a session S's settle ends before the EARLIEST
# settlement of the next trade date S+1 among the roots: sugar about 12:55 New York, gold 13:30,
# crude 14:30, the Treasury futures about 15:00. 12:00 New York on the next WEEKDAY (a holiday
# Monday still trades and settles, so the calendar's next session would be too late).
SETTLE_BOUND = time(12, 0)
LAST, SETTLE = "last", "settle"  # price_kind of a read before / after the contract's next open


def settle_cutoff(session: date) -> datetime:
    """``SETTLE_BOUND`` New York on the first weekday after ``session``."""
    day = session + timedelta(days=1)
    while is_weekend(day):
        day += timedelta(days=1)
    return datetime.combine(day, SETTLE_BOUND, EXCHANGE_TZ)


def contract_kind(next_open: datetime, now: datetime) -> str:
    """What a read at ``now`` may store for a contract whose next trading session starts at
    ``next_open`` (IB's ``tradingHours``; the caller has checked ``settle_cutoff``): before it
    ``LAST``, the session's own last trade (``close`` is still the day before's settle); from it
    ``SETTLE``, IB's ``close``, which is exactly the session's settle, ``last`` being the next
    trade date's trading and ignored."""
    return LAST if now < next_open else SETTLE


def curve_frame(
    root: str, rows: pd.DataFrame, ts: pd.Timestamp, session: date, kind: str
) -> pd.DataFrame:
    """The table rows of one root's answer (``IbkrSource`` ``futures`` frame): ids and
    ``price`` from the one column ``kind`` names (``LAST``: ``last``; ``SETTLE``: ``close``), so
    a root and session never mix kinds; a contract without it has no price."""
    out = rows.copy()
    out["contract_month"] = [month_label(str(m)) for m in out["contract_month"]]
    out["root"], out["parent_id"] = root, root_id(root)
    out["instrument_id"] = [contract_id(root, m) for m in out["contract_month"]]
    column = "last" if kind == LAST else "close"
    has = out[column].notna()
    out["price"] = out[column].astype(float)
    out["price_kind"] = pd.Series([kind if h else None for h in has], index=out.index, dtype=object)
    out["expiry"] = pd.to_datetime(out["expiry"]).dt.date
    out["next_open"] = pd.to_datetime(out["next_open"], utc=True)
    out["ts"], out["session_date"] = ts, session
    return out.drop_duplicates("instrument_id", keep="last").reset_index(drop=True)


def root_kind(rows: pd.DataFrame, now: datetime) -> str:
    """The one ``price_kind`` of a root's contracts at ``now``, from each one's ``next_open``;
    ``LookupError`` (-> ``NO_DATA``, fail closed) when a contract has none (``tradingHours``
    missing or unparsable) or the contracts disagree."""
    opens = pd.to_datetime(rows["next_open"], utc=True)
    if opens.isna().any():
        raise LookupError(
            f"tradingHours missing or unparsable for {int(opens.isna().sum())} contracts"
        )
    kinds = {contract_kind(o.to_pydatetime(), now) for o in opens}
    if len(kinds) != 1:
        raise LookupError("the contracts' next session opens straddle the read time")
    return kinds.pop()


def _root_curve(
    run: IngestRun, source: SessionSource, root: FuturesRoot, front: int, session: date
) -> str:
    key = (
        f"futures__{root.symbol}__{root.exchange}__{root.trading_class}__{front}"  # IbkrSource keys
    )
    try:
        normalized = run.fetch(source, FetchRequest(key, None, session))
    except LookupError as exc:  # IB lists nothing for the root, or refuses it: not an error
        return f"NO_DATA: {exc}"
    if normalized is None or "futures" not in normalized.parsed:
        return "NO_DATA: nothing parsed"
    rows = normalized.parsed["futures"]
    try:
        kind = root_kind(rows, run.clock())
    except LookupError as exc:
        return f"NO_DATA: {exc}"
    frame = curve_frame(root.symbol, rows, pd.Timestamp(run.clock()), session, kind)
    priced = int(frame["price"].notna().sum())
    if priced == 0:
        return (
            f"NO_DATA: {len(frame)} contracts listed, none with a price (market data permission?)"
        )
    run.stage_sessions(TABLE, f"root_{root.symbol}", frame, SOURCE)
    return f"OK: {priced}/{len(frame)} {kind}"


def nightly_curves(
    ctx: TaskContext, source: SessionSource, session: date, roots: Sequence[str] = ()
) -> RunRecord:
    """The session's curve of every configured root (``roots``: only those)."""
    settings = ctx.settings.ibkr
    wanted = [r for r in settings.futures_roots if not roots or r.symbol in roots]
    with IngestRun(ctx, TASK, session, resume=True) as run:
        run.stats["roots"] = len(wanted)
        late = run.clock() >= settle_cutoff(session)
        if late:  # point in time: IB's close may be the next settle by now
            why = f"read after {settle_cutoff(session):%Y-%m-%d %H:%M} New York"
            for root in wanted:
                if status_label(run.items.get(f"root:{root.symbol}", "")) not in DONE:
                    run.record_item(f"root:{root.symbol}", f"NO_DATA: {why}")
            run.partial(f"nothing stored for {session}: {why}")
        try:
            with nullcontext() if late else opened(source):
                for root in () if late else wanted:
                    item = f"root:{root.symbol}"
                    if status_label(run.items.get(item, "")) in DONE:
                        continue
                    run.attempt(
                        item,
                        partial(_root_curve, run, source, root, settings.futures_front, session),
                    )
        except SessionUnavailableError as exc:
            # Not COMPLETE (nothing new was fetched); what a resumed run staged is published.
            run.stats["skipped"] = f"WARN: {exc}"
            run.partial(f"skipped: {exc}")
        written = run.publish_sessions(TABLE, sort_by="instrument_id")
        served = [k.removeprefix("root:") for k, v in run.items.items() if v.startswith("OK")]
        run.stats.update(
            served=len(served), served_roots=sorted(served), rows=sum(written.values())
        )
    return run.record
