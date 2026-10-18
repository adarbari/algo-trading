"""``futures-curves``: the nightly futures curve snapshot (``rates/futures_curve``).

For each root of ``[ibkr] futures_roots`` (commodity and bond futures: crude, gas, metals,
grains, sugar, the Treasury note and bond futures, VIX) one request to the read-only IB
Gateway facade (``ctx.sources["ibkr"]``, opened and closed around the work): the ``[ibkr]
futures_front`` nearest unexpired listed contracts with their quotes streamed after the close
(last, IB's close = the prior settle, bid, ask, day volume, open interest). Per contract one
row: ``instrument_id`` ``FUT:<root>:<YYYY-MM>`` with ``parent_id`` ``FUT:<root>`` (ADR 0009),
expiry, ``price`` (one ``price_kind`` per root and session: ``last`` or ``close``) and the raw
fields, so the curve (basis, roll yield) is rebuilt from our own history, which accrues from
the first night: IB serves expired contracts only a couple of years back and nothing is
backfilled here. Personal licence (IBKR market data, ADR 0028).

The prices are an EVENING SNAPSHOT, not the exchange settle: ``close`` is the settle before the
read time, ``last`` the last trade at it. Point in time: Globex reopens 18:00 New York, after
which ``last`` can be a trade of the next trade date and ``close`` changes meaning, so a run (or
a catch-up) at or past ``reopen_cutoff`` stores nothing for the session (every root ``NO_DATA``
with the reason, the run PARTIAL); the nightly must read before then.

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
PRICES = ("last", "close")  # price columns, in preference order on a tie
GLOBEX_REOPEN = time(18, 0)  # New York: the evening session of the next trade date opens


def reopen_cutoff(session: date) -> datetime:
    """When Globex reopens for the trade date after ``session`` (18:00 New York the evening
    before it: Sunday for a Friday session). From then ``last`` may be a trade of that next
    session and IB's ``close`` changes meaning, so nothing is read or stored for ``session``."""
    return datetime.combine(next_session(session) - timedelta(days=1), GLOBEX_REOPEN, EXCHANGE_TZ)


def curve_frame(root: str, rows: pd.DataFrame, ts: pd.Timestamp, session: date) -> pd.DataFrame:
    """The table rows of one root's answer (``IbkrSource`` ``futures`` frame): ids and
    ``price``, ONE ``price_kind`` for the whole root and session: the ``PRICES`` column with a
    value on most contracts (a tie: the first), so a curve never mixes last trades and
    settles; a contract without that column has no price."""
    out = rows.copy()
    out["contract_month"] = [month_label(str(m)) for m in out["contract_month"]]
    out["root"], out["parent_id"] = root, root_id(root)
    out["instrument_id"] = [contract_id(root, m) for m in out["contract_month"]]
    counts = {c: int(out[c].notna().sum()) for c in PRICES}
    kind = max(PRICES, key=lambda c: (counts[c], -PRICES.index(c)))
    has = out[kind].notna()
    out["price"] = out[kind].astype(float)
    out["price_kind"] = pd.Series([kind if h else None for h in has], index=out.index, dtype=object)
    out["expiry"] = pd.to_datetime(out["expiry"]).dt.date
    out["ts"], out["session_date"] = ts, session
    return out.drop_duplicates("instrument_id", keep="last").reset_index(drop=True)


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
    frame = curve_frame(
        root.symbol, normalized.parsed["futures"], pd.Timestamp(run.clock()), session
    )
    priced = int(frame["price"].notna().sum())
    if priced == 0:
        return (
            f"NO_DATA: {len(frame)} contracts listed, none with a price (market data permission?)"
        )
    run.stage_sessions(TABLE, f"root_{root.symbol}", frame, SOURCE)
    return f"OK: {priced}/{len(frame)}"


def nightly_curves(
    ctx: TaskContext, source: SessionSource, session: date, roots: Sequence[str] = ()
) -> RunRecord:
    """The session's curve of every configured root (``roots``: only those)."""
    settings = ctx.settings.ibkr
    wanted = [r for r in settings.futures_roots if not roots or r.symbol in roots]
    with IngestRun(ctx, TASK, session, resume=True) as run:
        run.stats["roots"] = len(wanted)
        late = run.clock() >= reopen_cutoff(session)
        if late:  # point in time: the streams now belong to the next trade date
            why = f"read after Globex reopened ({reopen_cutoff(session):%Y-%m-%d %H:%M} New York)"
            for root in wanted:
                run.record_item(f"root:{root.symbol}", f"NO_DATA: {why}")
            run.partial(f"nothing stored for {session}: {why}")
        try:
            with opened(source) if not late else nullcontext():
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
