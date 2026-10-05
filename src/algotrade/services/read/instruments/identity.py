"""Who an instrument is (ADR 0038 "typed field"): ``Instrument``, its identity for the session,
from the snapshot tables (``instruments/reference``, ``instruments/company``) and the latest
stored description (``instruments/description``, incremental grain).

Snapshot grain (ADR 0036 decision 4): identity is read from the reference snapshot the session
sees (``data.reference``: latest on or before the session, else the earliest, flagged
``Session.pre_snapshot``) and discloses it as ``reference_snapshot``. A key is an
``instrument_id`` or a ticker, resolved through that snapshot's ``SymbolResolver`` (ADR 0018);
neither known is no such instrument (``None``), never an error."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

import pandas as pd

from algotrade.data.reference import companies, descriptions, instruments, resolver
from algotrade.services.read.context import ReadContext
from algotrade.services.read.values import to_scalar

ETF = "ETF"


@dataclass(frozen=True)
class Instrument:
    """One instrument as the session's reference snapshot has it. ``name``: the company's
    name (SEC), else the listing's; ``description``: what it is about (None: none stored);
    ``reference_snapshot``: the ``instruments/reference`` partition read."""

    instrument_id: str
    symbol: str
    name: str
    security_type: str | None
    asset_class: str
    exchange: str | None
    is_etf: bool
    description: str | None
    reference_snapshot: date


def _text(value: Any) -> str | None:
    found = to_scalar(value)
    return (found.strip() or None) if isinstance(found, str) else None


def _descriptions(ctx: ReadContext) -> pd.DataFrame:
    """Every stored description with text: the table is read once per publish (a year of
    nightly increments is hundreds of small files, ~1 s), not once per page."""
    key = ("descriptions", ctx.reader.visible_seq())  # read before computing (ADR 0022)
    found = ctx.cache.get(key)
    if found is None:
        found = descriptions(ctx.reader)
        ctx.cache.put(key, found)
    return found


def resolve_id(ctx: ReadContext, key: str) -> str | None:
    """The ``instrument_id`` ``key`` (an id or a ticker) names in the session's reference
    snapshot; ``None`` when it names none (or no reference is stored)."""
    if ctx.session.reference_snapshot is None:
        return None
    if not instruments(ctx.reader, ctx.session.date, [key]).empty:
        return key
    names = resolver(ctx.reader, ctx.session.date)
    return names.id_for(key) if names.knows(key) else None


def load_instrument(ctx: ReadContext, key: str) -> Instrument | None:
    """The instrument ``key`` names for ``ctx.session`` (see ``resolve_id``), else ``None``."""
    iid = resolve_id(ctx, key)
    return None if iid is None else load_instruments(ctx, [iid]).get(iid)


def load_instruments(ctx: ReadContext, instrument_ids: Sequence[str]) -> dict[str, Instrument]:
    """The instruments of ``instrument_ids`` the session's reference snapshot has, by id, in
    one read (an id it does not have is left out): a table's rows name theirs this way."""
    snapshot = ctx.session.reference_snapshot
    wanted = list(dict.fromkeys(instrument_ids))
    if snapshot is None or not wanted:
        return {}
    reference = _by_id(instruments(ctx.reader, ctx.session.date, wanted))
    company = _by_id(companies(ctx.reader, ctx.session.date, wanted))
    stored = _descriptions(ctx)
    texts = _by_id(stored[stored["instrument_id"].isin(set(reference))])
    return {
        iid: _instrument(iid, row, company.get(iid, {}), texts.get(iid, {}), snapshot)
        for iid, row in reference.items()
    }


def _by_id(frame: pd.DataFrame | None) -> dict[str, Mapping[str, Any]]:
    """The first row of each instrument in ``frame``, by id."""
    if frame is None or frame.empty:
        return {}
    first = frame.drop_duplicates("instrument_id", keep="first")
    return {
        str(r["instrument_id"]): {str(k): v for k, v in r.items()} for r in first.to_dict("records")
    }


def _instrument(
    iid: str,
    reference: Mapping[str, Any],
    company: Mapping[str, Any],
    text: Mapping[str, Any],
    snapshot: date,
) -> Instrument:
    security_type = _text(reference.get("security_type"))
    return Instrument(
        instrument_id=iid,
        symbol=str(reference["symbol"]),
        name=_text(company.get("name")) or _text(reference.get("name")) or "",
        security_type=security_type,
        asset_class=str(reference["asset_class"]),
        exchange=_text(reference.get("exchange")),
        is_etf=to_scalar(reference.get("is_etf")) is True or security_type == ETF,
        description=_text(text.get("description")),
        reference_snapshot=snapshot,
    )
