"""``InstrumentEvents`` (ADR 0050): what is coming for an instrument as of the session, before
any event statistic exists: the dated events ahead (``AheadEvent``), its 8-K filings
(``Filing``), the expiry ladder (``LadderRung``), a leveraged fund's reference
(``FundReference``) and the parts not known for the session (``EventGap``). Every label and
the ladder's spans and clear state come from the server (ADR 0038)."""

import datetime as dt
from typing import Self

import strawberry

from algotrade.services.read.events import ahead, filings, instrument_events, ladder, reference
from algotrade_api.graphql.types.instruments.feature import Unknown


@strawberry.type(
    description="A dated event ahead: `kind` own_earnings | reference_earnings | "
    "macro_release | market_structure; `time` pre_market | intraday | after_hours | unknown "
    "for a report, the release time for a macro release (08:30 ET), close for a market-"
    "structure day; `label` short, `name` in words; `subjectId` whose event (the "
    "instrument, the fund's reference, the MACRO: release; null for a market-structure day); "
    "`knownFrom` the first session the stored row was known on (null: a catalogue value or "
    "a calendar rule); `expiry` a monthly or quarterly option expiry day"
)
class AheadEvent:
    date: dt.date
    time: str
    kind: str
    label: str
    name: str
    subject_id: str | None
    source: str
    known_from: dt.date | None
    expiry: bool

    @classmethod
    def of(cls, d: ahead.AheadEvent) -> Self:
        return cls(
            date=d.date,
            time=d.time,
            kind=d.kind,
            label=d.label,
            name=d.name,
            subject_id=d.subject_id,
            source=d.source,
            known_from=d.known_from,
            expiry=d.expiry,
        )


@strawberry.type(
    description="A part of the events read not known for the session: `part` own_earnings, "
    "reference_earnings, macro_release, reference, filings or ladder; `instrumentId` null "
    "for a market-wide part (the macro calendar)"
)
class EventGap:
    instrument_id: str | None
    part: str
    unknown: Unknown

    @classmethod
    def of(cls, d: ahead.EventGap) -> Self:
        return cls(instrument_id=d.instrument_id, part=d.part, unknown=Unknown.of(d.unknown))


@strawberry.type(
    description="An 8-K or 8-K/A: `accepted` the SEC acceptance instant (UTC), `items` as "
    "SEC lists them, `label` the first item in words, `knownFrom` the session it was public on"
)
class Filing:
    accepted: dt.datetime
    filing_date: dt.date
    form: str
    items: list[str]
    label: str
    known_from: dt.date

    @classmethod
    def of(cls, d: filings.Filing) -> Self:
        return cls(
            accepted=d.accepted,
            filing_date=d.filing_date,
            form=d.form,
            items=list(d.items),
            label=d.label,
            known_from=d.known_from,
        )


@strawberry.type(
    description="A listed expiry 7 to 90 days out: the events it spans (dated on or before "
    "it: an after-close report on the expiry date is inside it) and whether it is `clear` "
    "(it spans none but market-structure days); `marked` the last clear rung (the longest "
    "expiry still clear of earnings and macro events; none when no rung is clear)"
)
class LadderRung:
    expiry: dt.date
    days: int
    spans: list[AheadEvent]
    clear: bool
    marked: bool

    @classmethod
    def of(cls, d: ladder.LadderRung) -> Self:
        return cls(
            expiry=d.expiry,
            days=d.days,
            spans=[AheadEvent.of(e) for e in d.spans],
            clear=d.clear,
            marked=d.marked,
        )


@strawberry.type(
    description="What a leveraged or inverse fund tracks for the session (fund_reference@v1): "
    "`instrumentId` / `symbol` the one stock (null: a basket, or not listed), `kind` "
    "single_stock | index | sector | commodity | none, `source` holdings | name_rule, "
    "`status` LINKED | BASKET | UNLISTED | NO_REFERENCE"
)
class FundReference:
    instrument_id: str | None
    symbol: str | None
    kind: str
    source: str | None
    status: str

    @classmethod
    def of(cls, d: reference.FundReference) -> Self:
        return cls(
            instrument_id=d.instrument_id,
            symbol=d.symbol,
            kind=d.kind,
            source=d.source,
            status=d.status,
        )


@strawberry.type(
    description="What is coming for the instrument as of the session: the events of the next "
    "`days` days (oldest first), the 8-Ks of the last `months` (newest first), the expiry "
    "ladder, a leveraged fund's reference (null: not one, or not known: see `gaps`) and the "
    "parts not known for the session. Event rows are those known on or before the session "
    "(ADR 0050); catalogue values and the chain exactly the session's (ADR 0036)"
)
class InstrumentEvents:
    instrument_id: str
    session: dt.date
    days: int
    months: int
    ahead: list[AheadEvent]
    filings: list[Filing]
    ladder: list[LadderRung]
    reference: FundReference | None
    gaps: list[EventGap]

    @classmethod
    def of(cls, d: instrument_events.InstrumentEvents) -> Self:
        return cls(
            instrument_id=d.instrument_id,
            session=d.session,
            days=d.days,
            months=d.months,
            ahead=[AheadEvent.of(e) for e in d.ahead],
            filings=[Filing.of(f) for f in d.filings],
            ladder=[LadderRung.of(r) for r in d.ladder],
            reference=FundReference.of(d.reference) if d.reference is not None else None,
            gaps=[EventGap.of(g) for g in d.gaps],
        )
