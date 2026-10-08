"""Feature values by catalogue name (ADR 0038): ``FeatureValue`` for (instrument, name,
session), each with its ``FeatureInfo`` and, when the value is not known for the session, an
``Unknown`` saying why (ADR 0036). The same read serves other entities: ``entity="market"``
reads a market's ``MKT:US`` row of the market-entity groups (ADR 0047;
``services.read.market.features``), from exactly the session's partitions too, with the same
UNKNOWN / EXPLAINED rules.

Values come from ``services.features.field_view``, the same read a selection evaluates (so a
page and a screener agree): rollups and the inputs of expression features for exactly
``ctx.session.date``, ``instrument.*`` facts from the snapshot the session sees. Never an older
partition: a table with no partition for the session makes its values ``NO_PARTITION``.

UNKNOWN codes: ``NO_PARTITION`` (a table the value reads has no partition for the session;
for company facts: no company snapshot on or before it),
``NO_ROW`` (the instrument has no row: not in the reference snapshot, or no row in the rollup
or in any input of the expression), ``NULL`` (stored or computed null; ``FeatureInfo.null_meaning``
says what null means), ``NOT_APPLICABLE`` (the feature is not defined for this kind of
instrument: option features of a non-optionable one, earnings of an ETF, preferred or
blank-check company; from the session's reference snapshot and its company snapshot's SIC) and
``ILLIQUID`` (an option feature null because the chain is too thin: its status column says so)
and ``EXPLAINED`` (the null is itself the fact, a ``NullReason`` its status column holds: no
trade on the session, next earnings not announced, a new listing; ADR 0046).
A present value wins over all three; they win over NO_ROW and NULL, in that order, so a
non-optionable instrument with no option rows is n/a, not a gap (ADR 0042), and a stock with
no bar on the session but a ``NO_TRADE`` status is "no trade", not a gap. ``LICENCE``
waits for a second user (ADR 0028: personal-licence values are hidden from users other than
the owner once there are any). A name outside the caller's catalogue is an error
(``UnknownFeatureError``), not a value."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any, cast

import pandas as pd

from algotrade.core.model.fields import (
    COMPANY_TABLE,
    FEATURE_FIELD_PREFIX,
    REFERENCE_TABLE,
    field_source,
    group_of_table,
    is_feature_field,
    table_field,
)
from algotrade.core.views.feature_view import FeatureValue as Scalar
from algotrade.features.expressions.feature_set import FeatureSet
from algotrade.features.framework.feature import (
    BLANK_CHECK_SIC,
    OPERATING_TYPES,
    NullReason,
    StatusRule,
    not_applicable,
)
from algotrade.services.features import entity_field_view, field_view
from algotrade.services.read.availability.cause import (
    Cause,
    CauseLink,
    UnavailableKind,
    feature_cause,
    table_cause,
)
from algotrade.services.read.context import ReadContext
from algotrade.services.read.instruments.catalogue import FeatureInfo, feature_infos
from algotrade.services.read.session import Grain, grain_of
from algotrade.services.read.values import Unknown, UnknownCode, to_scalar

# A rollup partition's own ``instrument_id`` read as a field: non-null exactly when the
# instrument has a row in that table for the session (tells NO_ROW from a stored NULL).
_ROW = "instrument_id"
_OPTIONABLE = "instrument.optionable"
_SECURITY_TYPE = "instrument.security_type"
_SIC = "instrument.sic"  # company snapshot on or before the session (ADR 0045)
_LEVERAGED, _INVERSE = "instrument.is_leveraged", "instrument.is_inverse"
type Reasons = tuple[frozenset[str], tuple[StatusRule, ...]]  # FeatureSet.applicability
# What an EXPLAINED value's detail adds after "<status> is <reason> for <id> on <day>".
_EXPLAINED = {
    NullReason.NO_TRADE: "no bar on the session",
    NullReason.NOT_ANNOUNCED: "the next report date is not announced",
    NullReason.NEW_LISTING: "too few sessions since listing",
    NullReason.FEW_BARS: "too few bars in the window",
}


@dataclass(frozen=True)
class FeatureValue:
    """One catalogue field of one instrument for the session. ``value`` is a JSON scalar
    (``values.to_scalar``); it is ``None`` exactly when ``unknown`` says why."""

    name: str
    value: Scalar
    unknown: Unknown | None
    info: FeatureInfo


def _tables(fs: FeatureSet, name: str) -> tuple[str, ...]:
    """The stored tables ``name``'s value is read from (an expression: its inputs')."""
    if is_feature_field(name):
        return tuple(sorted(fs.stored_columns([name.removeprefix(FEATURE_FIELD_PREFIX)])))
    return (field_source(name)[0],)


def _reason_fields(reasons: Reasons) -> list[str]:
    """The extra fields a value's NOT_APPLICABLE / ILLIQUID / EXPLAINED decision reads."""
    applies, statuses = reasons
    return [
        *([_OPTIONABLE] if "optionable" in applies else []),
        *([_SECURITY_TYPE, _SIC] if "operating_company" in applies else []),
        *([_LEVERAGED, _INVERSE] if "leveraged_fund" in applies else []),
        *(field for field, _, _, _ in statuses),
    ]


def _marker(table: str) -> str:
    """The field reading ``table``'s ``instrument_id`` (feature group tables only)."""
    return table_field(table, _ROW)


def _absent(tables: Sequence[str], day: date) -> Cause:
    """One TABLE link per table with nothing for the session (no partition, or no snapshot)."""

    def why(table: str) -> CauseLink:
        if grain_of(table) is Grain.SESSION:
            message = f"{table} has no partition for {day.isoformat()}"
        else:
            message = f"{table} has no snapshot on or before {day.isoformat()}"
        return table_cause(table, message, session=day).leaf

    return Cause(tuple(why(t) for t in tables))


def _flag(value: Any) -> bool | None:
    """A reference flag as a bool (``None``: null)."""
    scalar = to_scalar(value)
    return None if scalar is None else bool(scalar)


def _text(value: Any) -> str | None:
    """A reference / company string fact (``None``: null)."""
    scalar = to_scalar(value)
    return None if scalar is None else str(scalar)


def _not_applicable(
    applies: frozenset[str], row: Mapping[str, Any], ctx: ReadContext, iid: str
) -> str:
    """Why the feature does not apply to the instrument (the reference snapshot's facts and
    the company snapshot's SIC; a null fact is not "no"), or ``""``."""
    snapshot = f"(reference snapshot {ctx.session.reference_snapshot})"
    ruled_out = not_applicable(
        applies,
        _flag(row.get(_OPTIONABLE)) if "optionable" in applies else None,
        _text(row.get(_SECURITY_TYPE)) if "operating_company" in applies else None,
        _text(row.get(_SIC)) if "operating_company" in applies else None,
        _flag(row.get(_LEVERAGED)) if "leveraged_fund" in applies else None,
        _flag(row.get(_INVERSE)) if "leveraged_fund" in applies else None,
    )
    if ruled_out == "optionable":
        return f"{iid} is not optionable {snapshot}"
    if ruled_out == "operating_company":
        kind = _text(row.get(_SECURITY_TYPE)) or ""
        if kind in OPERATING_TYPES:
            return f"{iid} is a blank-check company (SIC {BLANK_CHECK_SIC}): no earnings"
        return f"{iid} is not an operating company: {kind} {snapshot}: no earnings"
    if ruled_out == "leveraged_fund":
        return f"{iid} is not a leveraged or inverse fund {snapshot}: no fund reference"
    return ""


def _illiquid(statuses: Sequence[StatusRule], row: Mapping[str, Any], iid: str, day: date) -> str:
    """Why an option feature is null for want of a tradeable chain (the status column), or
    ``""``."""
    for field, thin, _, _ in statuses:
        status = to_scalar(row.get(field))
        if status in thin:
            return (
                f"{field.rpartition('.')[2]} is {status} for {iid} on {day.isoformat()}: "
                "no near-the-money quote within the spread limit"
            )
    return ""


def _explained(
    statuses: Sequence[StatusRule],
    row: Mapping[str, Any],
    rowless: Sequence[str],
    iid: str,
    day: date,
) -> Unknown | None:
    """The ``NullReason`` a status column gives for the null (the first that does), or
    ``None``. Only when the explaining statuses cover every table with no row for the
    instrument: an expression's explained input never hides a real gap in another input
    (``close / days_to_earnings`` with no ``price_stats`` row stays NO_ROW whatever the
    earnings status says)."""
    found = [
        (field, str(status), table)
        for field, _, explained, table in statuses
        if (status := to_scalar(row.get(field))) in explained
    ]
    if not found or not set(rowless) <= {table for _, _, table in found}:
        return None
    field, status, _ = found[0]
    reason = NullReason(status)
    detail = (
        f"{field.rpartition('.')[2]} is {status} for {iid} on {day.isoformat()}: "
        f"{_EXPLAINED[reason]}"
    )
    cause = feature_cause(field.rpartition(".")[2], detail, status, day)
    return Unknown(UnknownCode.EXPLAINED, cause, reason)


def _value(
    info: FeatureInfo,
    tables: Sequence[str],
    row: Mapping[str, Any] | None,
    missing: Sequence[str],
    ctx: ReadContext,
    iid: str,
    reasons: Reasons = (frozenset(), ()),
) -> FeatureValue:
    day = ctx.session.date
    absent = [t for t in tables if t in missing]
    if absent:
        return FeatureValue(
            info.name, None, Unknown(UnknownCode.NO_PARTITION, _absent(absent, day)), info
        )
    if row is None:
        detail = f"{iid} is not in {REFERENCE_TABLE} (snapshot {ctx.session.reference_snapshot})"
        cause = table_cause(REFERENCE_TABLE, detail, "NO_ROW", day)
        kind = ctx.kind_of(UnknownCode.NO_ROW, REFERENCE_TABLE)
        return FeatureValue(info.name, None, Unknown(UnknownCode.NO_ROW, cause, None, kind), info)
    value = to_scalar(row.get(info.name))
    if value is not None:  # a formula may give a value without every input row (exists())
        return FeatureValue(info.name, value, None, info)
    return FeatureValue(info.name, None, _absence(info, tables, row, ctx, iid, reasons), info)


def _absence(
    info: FeatureInfo,
    tables: Sequence[str],
    row: Mapping[str, Any],
    ctx: ReadContext,
    iid: str,
    reasons: Reasons,
) -> Unknown:
    """Why a null value is null (ADR 0042 and 0046 precedence): not applicable, illiquid,
    explained, no row in a table it reads, else a stored null."""
    day = ctx.session.date
    why = _not_applicable(reasons[0], row, ctx, iid)
    if why:
        return Unknown(
            UnknownCode.NOT_APPLICABLE, feature_cause(info.name, why, "NOT_APPLICABLE", day)
        )
    why = _illiquid(reasons[1], row, iid, day)
    if why:
        return Unknown(UnknownCode.ILLIQUID, feature_cause(info.name, why, "ILLIQUID", day))
    rowless = [
        t
        for t in tables
        if group_of_table(t) is not None and to_scalar(row.get(_marker(t))) is None
    ]
    explained = _explained(reasons[1], row, rowless, iid, day)
    if explained is not None:
        return explained
    if rowless:
        detail = f"{' / '.join(rowless)} has no row for {iid} on {day.isoformat()}"
        links = tuple(table_cause(t, detail, "NO_ROW", day).leaf for t in rowless)
        return Unknown(
            UnknownCode.NO_ROW, Cause(links), None, ctx.kind_of(UnknownCode.NO_ROW, *rowless)
        )
    detail = f"{info.name} is null for {iid} on {day.isoformat()}"
    kind = ctx.kind_of(UnknownCode.NULL, *tables)
    return Unknown(UnknownCode.NULL, feature_cause(info.name, detail, "NULL", day), None, kind)


def cell_codes(
    cells: Mapping[str, Sequence[FeatureValue]], ids: Sequence[str]
) -> tuple[
    tuple[tuple[UnknownCode | None, ...], ...],
    tuple[tuple[NullReason | None, ...], ...],
    tuple[tuple[UnavailableKind | None, ...], ...],
]:
    """A table's ``unknown``, ``reasons`` and ``kinds`` matrices for ``ids`` (rows) from their
    ``load_feature_values`` cells: the code of each UNKNOWN cell, its ``NullReason`` when the
    code is EXPLAINED (else None) and its public kind (SYSTEM when a failure stands behind the
    column's table, ADR 0056: a cell is drawn by kind, never by code)."""

    def row(iid: str) -> tuple[Unknown | None, ...]:
        return tuple(v.unknown for v in cells.get(iid, ()))

    return (
        tuple(tuple(u.code if u else None for u in row(i)) for i in ids),
        tuple(tuple(u.reason if u else None for u in row(i)) for i in ids),
        tuple(tuple(u.kind if u else None for u in row(i)) for i in ids),
    )


def _rows(
    ctx: ReadContext,
    entity: str,
    ids: Sequence[str] | None,
    wanted: Sequence[str],
    tables: Mapping[str, tuple[str, ...]],
    reasons: Mapping[str, Reasons],
) -> tuple[dict[str, Mapping[str, Any]], tuple[str, ...]]:
    """-> (each entity's row of ``wanted`` plus the row markers and the fields the reasons
    read, by id; the tables with no partition for the session)."""
    groups = sorted({t for ts in tables.values() for t in ts if group_of_table(t) is not None})
    fields = [
        *wanted,
        *(_marker(t) for t in groups),
        *dict.fromkeys(f for r in reasons.values() for f in _reason_fields(r)),
    ]
    day = ctx.session.date
    if entity != "instrument":
        if ids is None:
            raise ValueError(f"a {entity} read names its ids")
        frame, missing = entity_field_view(ctx.reader, day, fields, ids, features=ctx.features)
        return _by_id(frame), missing
    view = field_view(ctx.reader, day, fields, ids, features=ctx.features)
    rows, missing = _by_id(view.frame), view.missing
    # A company snapshot taken after the session is not known on it (no lookahead).
    if view.company_pre_snapshot:
        missing = (*missing, COMPANY_TABLE)
        # its sic is not known either: never a false n/a
        rows = {i: {**row, _SIC: None} for i, row in rows.items()}
    return rows, missing


def _by_id(frame: pd.DataFrame) -> dict[str, Mapping[str, Any]]:
    return {str(r["instrument_id"]): cast(dict[str, Any], r) for r in frame.to_dict("records")}


def load_feature_values(
    ctx: ReadContext,
    instrument_ids: Sequence[str] | None,
    names: Sequence[str],
    entity: str = "instrument",
) -> dict[str, tuple[FeatureValue, ...]]:
    """``names`` (catalogue fields, in the order asked; repeats dropped) for each instrument
    of ``instrument_ids`` (None: every instrument of the session's reference snapshot, the
    population a distribution is over), for ``ctx.session``: one read for them all.
    ``entity``: whose catalogue and rows (``market``: ``instrument_ids`` are market ids,
    ``market_id("US")``; ADR 0047). ``UnknownFeatureError`` when a name is not in the
    caller's catalogue of that entity."""
    wanted = list(dict.fromkeys(names))
    infos = feature_infos(ctx.features, wanted, entity)
    tables = {n: _tables(ctx.features, n) for n in wanted}
    reasons = {
        n: ctx.features.applicability(n) if not n.startswith("instrument.") else (frozenset(), ())
        for n in wanted
    }
    rows: Mapping[str, Mapping[str, Any]]
    missing: tuple[str, ...]
    if entity == "instrument" and ctx.session.reference_snapshot is None:
        rows, missing = {}, (REFERENCE_TABLE,)  # nothing stored to say who anything is
        tables = dict.fromkeys(wanted, (REFERENCE_TABLE,))
    else:
        rows, missing = _rows(ctx, entity, instrument_ids, wanted, tables, reasons)
    if instrument_ids is None:
        instrument_ids = list(rows)
    return {
        iid: tuple(
            _value(infos[n], tables[n], rows.get(iid), missing, ctx, iid, reasons[n])
            for n in wanted
        )
        for iid in instrument_ids
    }
