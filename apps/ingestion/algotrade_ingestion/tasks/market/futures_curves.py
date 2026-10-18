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

The prices are an EVENING SNAPSHOT of three windows by the read clock (``price_window``; the
nightly starts from 16:30 New York, before Globex halts 17:00-18:00 and reopens): before
``GLOBEX_REOPEN`` ``price`` is ``last`` (``price_kind`` ``last``: the session's own last trade;
IB's ``close`` is still the day before's settle); from the reopen until ``SETTLE_BOUND`` on the
next session ``price`` is IB's ``close``, which is exactly the session's exchange settle
(``price_kind`` ``settle``), and ``last`` is ignored (next trade date's trading); later nothing
is stored (every root ``NO_DATA`` with the reason, the run PARTIAL). One ``price_kind`` per root
and session.

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
from algotrade.core.time.calendar import EXCHANGE_TZ, next_session
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
GLOBEX_REOPEN = time(18, 0)  # New York: the evening session of the next trade date opens
# S+1's own settlement is published from about 13:30 Chicago (14:30 New York, crude and metals;
# the rate futures settle earlier); 14:00 New York is the conservative bound used for the
# window in which IB's ``close`` is still S's settle: after it, ``close`` may be S+1's.
SETTLE_BOUND = time(14, 0)
LAST, SETTLE = "last", "settle"  # price_kind of a read before / after the reopen


def reopen_cutoff(session: date) -> datetime:
    """When Globex reopens for the trade date after ``session`` (``GLOBEX_REOPEN`` New York the
    evening before it: Sunday for a Friday session)."""
    return datetime.combine(next_session(session) - timedelta(days=1), GLOBEX_REOPEN, EXCHANGE_TZ)


def settle_cutoff(session: date) -> datetime:
    """``SETTLE_BOUND`` New York on the session after ``session``: the end of the window in
    which IB's ``close`` is still ``session``'s settle."""
    return datetime.combine(next_session(session), SETTLE_BOUND, EXCHANGE_TZ)


def price_window(session: date, now: datetime) -> str | None:
    """What a read of ``session`` at ``now`` may store, from the clock alone:

    - before ``reopen_cutoff``: ``LAST``, the session's own last trade (``close`` is still the
      day before's settle);
    - from it until ``settle_cutoff``: ``SETTLE``, IB's ``close``, which is exactly the
      session's settle; ``last`` is contaminated by the next trade date's trading and ignored;
    - later: ``None``, nothing (``close`` may have moved on to the next settle)."""
    if now < reopen_cutoff(session):
        return LAST
    return SETTLE if now < settle_cutoff(session) else None


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
    has = out["last" if kind == LAST else "close"].notna()
    out["price"] = out["last" if kind == LAST else "close"].astype(float)
    out["price_kind"] = pd.Series([kind if h else None for h in has], index=out.index, dtype=object)
    out["expiry"] = pd.to_datetime(out["expiry"]).dt.date
    out["ts"], out["session_date"] = ts, session
    return out.drop_duplicates("instrument_id", keep="last").reset_index(drop=True)


def _root_curve(
    run: IngestRun, source: SessionSource, root: FuturesRoot, front: int, session: date, kind: str
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
    frame = curve_frame(
        root.symbol, normalized.parsed["futures"], pd.Timestamp(run.clock()), session, kind
    )
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
        kind = price_window(session, run.clock())
        if kind is None:  # point in time: IB's close may be the next settle by now
            why = f"read after {settle_cutoff(session):%Y-%m-%d %H:%M} New York"
            for root in wanted:
                run.record_item(f"root:{root.symbol}", f"NO_DATA: {why}")
            run.partial(f"nothing stored for {session}: {why}")
        try:
            with opened(source) if kind else nullcontext():
                for root in wanted if kind is not None else ():
                    item, done = f"root:{root.symbol}", run.items.get(f"root:{root.symbol}", "")
                    # a resumed run's root done in the other window is read again: one kind
                    if status_label(done) in DONE and (
                        status_label(done) != "OK" or str(kind) in done
                    ):
                        continue
                    run.attempt(
                        item,
                        partial(
                            _root_curve,
                            run,
                            source,
                            root,
                            settings.futures_front,
                            session,
                            str(kind),
                        ),
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
