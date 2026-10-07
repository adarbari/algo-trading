"""What a leveraged or inverse fund tracks (``FundReference``, ADR 0050 decision 2), read by
catalogue name (ADR 0038: ``rollup.fund_reference@v1.*`` through ``load_feature_values``, never
a typed read of the table), for exactly the session (ADR 0036).

A fund's reference is the instrument whose events it inherits: its earnings are the fund's
"reference earnings" ahead. ``reference_instrument_id`` is set only for a single-stock fund
(``LINKED``); a basket fund (index, sector, commodity) has a kind and no instrument. Every other
instrument reads NOT_APPLICABLE (the group's ``applies_to = leveraged_fund``): no reference and
no gap. A fund whose value is not known for the session (no partition, no row) has no reference
and that UNKNOWN as its gap."""

from collections.abc import Sequence
from dataclasses import dataclass

from algotrade.services.read.context import ReadContext
from algotrade.services.read.instruments.features import load_feature_values
from algotrade.services.read.instruments.identity import load_instruments
from algotrade.services.read.values import Unknown, UnknownCode

REFERENCE_ID = "rollup.fund_reference@v1.reference_instrument_id"
REFERENCE_KIND = "rollup.fund_reference@v1.reference_kind"
REFERENCE_SOURCE = "rollup.fund_reference@v1.reference_source"
REFERENCE_STATUS = "rollup.fund_reference@v1.reference_status"
NAMES = (REFERENCE_ID, REFERENCE_KIND, REFERENCE_SOURCE, REFERENCE_STATUS)


@dataclass(frozen=True)
class FundReference:
    """What the fund tracks for the session. ``instrument_id`` / ``symbol``: the one stock
    (None for a basket, or a stock the reference snapshot does not list); ``kind``:
    single_stock | index | sector | commodity | none; ``source``: holdings | name_rule (None
    when nothing settled it); ``status``: LINKED | BASKET | UNLISTED | NO_REFERENCE."""

    instrument_id: str | None
    symbol: str | None
    kind: str
    source: str | None
    status: str


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def load_fund_references(
    ctx: ReadContext, instrument_ids: Sequence[str]
) -> tuple[dict[str, FundReference], dict[str, Unknown]]:
    """Each fund's reference among ``instrument_ids`` (absent: not a leveraged or inverse
    fund, or not known), and the UNKNOWN of each fund whose reference is not known for the
    session: one feature read, one identity read for them all."""
    found = load_feature_values(ctx, list(instrument_ids), NAMES)
    references: dict[str, tuple[str | None, str, str | None, str]] = {}
    gaps: dict[str, Unknown] = {}
    for iid, values in found.items():
        rid, kind, source, status = values
        if status.unknown is not None or kind.unknown is not None:
            unknown = status.unknown or kind.unknown
            if unknown is not None and unknown.code is not UnknownCode.NOT_APPLICABLE:
                gaps[iid] = unknown
            continue
        references[iid] = (
            _text(rid.value),
            str(kind.value),
            _text(source.value),
            str(status.value),
        )
    linked = [r[0] for r in references.values() if r[0] is not None]
    symbols = {i: d.symbol for i, d in load_instruments(ctx, linked).items()}
    return {
        iid: FundReference(rid, symbols.get(rid) if rid else None, kind, source, status)
        for iid, (rid, kind, source, status) in references.items()
    }, gaps
