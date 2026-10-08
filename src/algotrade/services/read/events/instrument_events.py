"""``InstrumentEvents`` (ADR 0050, docs/api/read-model.md "The domain objects"): what is coming
for one instrument as of the session, before any event statistic exists: the dated events
ahead (``ahead.load_ahead``), its 8-K filings (``filings``), the expiry ladder over the
session's chain (``ladder``) and, for a leveraged or inverse fund, its reference
(``reference``). Each part says why it is missing (``gaps``) instead of passing an empty list
off as "nothing".

Point in time (ADR 0036, ADR 0050 decision 3): catalogue values and the chain are exactly the
session's partitions (never an older one: NO_PARTITION); event tables are read by event date
among the rows known on or before the session (``known_from``); the identity is the reference
snapshot the session sees. Gaps: an own or reference report not known for the session (its
feature's UNKNOWN: NO_PARTITION, NOT_APPLICABLE for a fund, EXPLAINED "not announced", ...),
a fund's reference not known, the macro calendar with nothing known by the session, filings of
a fund (NOT_APPLICABLE) or of a company with none known (NO_ROW), and no chain for the session
(the ladder: NO_PARTITION, or NO_ROW when the partition lacks the underlying)."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta

from algotrade.data.chains import OPTION_QUOTES
from algotrade.services.read.availability.cause import feature_cause, table_cause
from algotrade.services.read.context import ReadContext, partition
from algotrade.services.read.events.ahead import AheadEvent, EventGap, load_ahead, order
from algotrade.services.read.events.filings import Filing, load_filings
from algotrade.services.read.events.ladder import LADDER_DAYS, LadderRung, ladder
from algotrade.services.read.events.reference import FundReference
from algotrade.services.read.instruments.chains import load_chains
from algotrade.services.read.instruments.identity import load_instruments
from algotrade.services.read.values import Unknown, UnknownCode

DEFAULT_DAYS = 90  # the events ahead: calendar days from the session
DEFAULT_MONTHS = 24  # the filings: calendar months back from the session
FILINGS, LADDER = "filings", "ladder"


@dataclass(frozen=True)
class InstrumentEvents:
    """What is coming for ``instrument_id`` as of ``session``: the events of the next ``days``
    calendar days (oldest first), the filings of the last ``months`` (newest first), the expiry
    ladder (7 to 90 days, its spans over every event ahead through its last rung), the fund's
    reference (None: not a leveraged or inverse fund, or not known: see ``gaps``) and the parts
    not known for the session (``gaps``)."""

    instrument_id: str
    session: date
    days: int
    months: int
    ahead: tuple[AheadEvent, ...]
    filings: tuple[Filing, ...]
    ladder: tuple[LadderRung, ...]
    reference: FundReference | None
    gaps: tuple[EventGap, ...]


def _no_chain(ctx: ReadContext, underlying_id: str) -> Unknown:
    """Why the session has no chain of ``underlying_id``."""
    found = partition(ctx, OPTION_QUOTES, columns=["expiry"], instruments=[underlying_id])
    if isinstance(found, Unknown):
        return found
    day = ctx.session.date.isoformat()
    message = f"{OPTION_QUOTES} has no quotes of {underlying_id} for {day}"
    cause = table_cause(OPTION_QUOTES, message, "NO_ROW", ctx.session.date)
    return Unknown(UnknownCode.NO_ROW, cause, None, ctx.kind_of(UnknownCode.NO_ROW, OPTION_QUOTES))


def load_instrument_events(
    ctx: ReadContext,
    instrument_ids: Sequence[str],
    days: int = DEFAULT_DAYS,
    months: int = DEFAULT_MONTHS,
) -> dict[str, InstrumentEvents]:
    """``InstrumentEvents`` of each of ``instrument_ids`` the session's reference snapshot
    has (absent: no such instrument): one read of each source for them all."""
    known = load_instruments(ctx, instrument_ids)
    ids = [iid for iid in dict.fromkeys(instrument_ids) if iid in known]
    if not ids:
        return {}
    day = ctx.session.date
    end = day + timedelta(days=days)
    horizon = day + timedelta(days=max(days, LADDER_DAYS[1]))  # the ladder's last rung
    ahead = load_ahead(ctx, ids, horizon)
    stocks = [iid for iid in ids if not known[iid].is_etf]
    filings, no_filings = load_filings(ctx, stocks, months)
    chains = load_chains(ctx, ids)
    out = {}
    for iid in ids:
        events = tuple(sorted((*ahead.by_name[iid], *ahead.market), key=order))
        gaps = [*ahead.gaps[iid], *ahead.market_gaps]
        if known[iid].is_etf:
            detail = f"{iid} is a fund: funds file no 8-Ks"
            cause = feature_cause(FILINGS, detail, "NOT_APPLICABLE", day)
            gaps.append(EventGap(iid, FILINGS, Unknown(UnknownCode.NOT_APPLICABLE, cause)))
        elif iid in no_filings:
            gaps.append(EventGap(iid, FILINGS, no_filings[iid]))
        chain = chains.get(iid)
        if chain is None:
            gaps.append(EventGap(iid, LADDER, _no_chain(ctx, iid)))
        out[iid] = InstrumentEvents(
            instrument_id=iid,
            session=day,
            days=days,
            months=months,
            ahead=tuple(e for e in events if e.date <= end),
            filings=filings.get(iid, ()),
            ladder=ladder(chain.expiries, events) if chain is not None else (),
            reference=ahead.references.get(iid),
            gaps=tuple(gaps),
        )
    return out
