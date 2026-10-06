"""Feature values by catalogue name (ADR 0038): ``FeatureValue`` for (instrument, name,
session), each with its ``FeatureInfo`` and, when the value is not known for the session, an
``Unknown`` saying why (ADR 0036).

Values come from ``services.features.field_view``, the same read a selection evaluates (so a
page and a screener agree): rollups and the inputs of expression features for exactly
``ctx.session.date``, ``instrument.*`` facts from the snapshot the session sees. Never an older
partition: a table with no partition for the session makes its values ``NO_PARTITION``.

UNKNOWN codes: ``NO_PARTITION`` (a table the value reads has no partition for the session;
for company facts: no company snapshot on or before it),
``NO_ROW`` (the instrument has no row: not in the reference snapshot, or no row in the rollup
or in any input of the expression), ``NULL`` (stored or computed null; ``FeatureInfo.null_meaning``
says what null means), ``NOT_APPLICABLE`` (the feature is not defined for this kind of
instrument: option features of a non-optionable one, earnings of an ETF; from the session's
reference snapshot) and ``ILLIQUID`` (an option feature null because the chain is too thin: its
status column says so). A present value wins over both; they win over NO_ROW and NULL, so a
non-optionable instrument with no option rows is n/a, not a gap (ADR 0042). ``LICENCE``
waits for a second user (ADR 0028: personal-licence values are hidden from users other than
the owner once there are any). A name outside the caller's catalogue is an error
(``UnknownFeatureError``), not a value."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any, cast

from algotrade.core.model.fields import (
    COMPANY_TABLE,
    FEATURE_FIELD_PREFIX,
    REFERENCE_TABLE,
    ROLLUP_TABLE_PREFIX,
    field_source,
    is_feature_field,
)
from algotrade.core.views.feature_view import FeatureValue as Scalar
from algotrade.features.expressions.feature_set import FeatureSet
from algotrade.services.features import field_view
from algotrade.services.read.context import ReadContext
from algotrade.services.read.instruments.catalogue import FeatureInfo, feature_infos
from algotrade.services.read.instruments.identity import ETF
from algotrade.services.read.session import Grain, grain_of
from algotrade.services.read.values import Unknown, UnknownCode, to_scalar

# A rollup partition's own ``instrument_id`` read as a field: non-null exactly when the
# instrument has a row in that table for the session (tells NO_ROW from a stored NULL).
_ROW = "instrument_id"
_OPTIONABLE = "instrument.optionable"
_SECURITY_TYPE = "instrument.security_type"
type Reasons = tuple[frozenset[str], tuple[tuple[str, frozenset[str]], ...]]  # applicability


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
    """The extra fields a value's NOT_APPLICABLE / ILLIQUID decision reads."""
    applies, statuses = reasons
    return [
        *([_OPTIONABLE] if "optionable" in applies else []),
        *([_SECURITY_TYPE] if "not_etf" in applies else []),
        *(field for field, _ in statuses),
    ]


def _marker(table: str) -> str:
    """The field reading ``table``'s ``instrument_id`` (rollup tables only)."""
    return f"rollup.{table.removeprefix(ROLLUP_TABLE_PREFIX)}.{_ROW}"


def _absent(tables: Sequence[str], day: date) -> str:
    def why(table: str) -> str:
        if grain_of(table) is Grain.SESSION:
            return f"{table} has no partition for {day.isoformat()}"
        return f"{table} has no snapshot on or before {day.isoformat()}"

    return "; ".join(why(t) for t in tables)


def _not_applicable(
    applies: frozenset[str], row: Mapping[str, Any], ctx: ReadContext, iid: str
) -> str:
    """Why the feature does not apply to the instrument (the reference snapshot's facts; a
    null ``optionable`` is not "no"), or ``""``."""
    snapshot = f"(reference snapshot {ctx.session.reference_snapshot})"
    if "optionable" in applies and to_scalar(row.get(_OPTIONABLE)) is False:
        return f"{iid} is not optionable {snapshot}"
    if "not_etf" in applies and to_scalar(row.get(_SECURITY_TYPE)) == ETF:
        return f"{iid} is an ETF {snapshot}: no earnings"
    return ""


def _illiquid(
    statuses: Sequence[tuple[str, frozenset[str]]], row: Mapping[str, Any], iid: str, day: date
) -> str:
    """Why an option feature is null for want of a tradeable chain (the status column), or
    ``""``."""
    for field, thin in statuses:
        status = to_scalar(row.get(field))
        if status in thin:
            return (
                f"{field.rpartition('.')[2]} is {status} for {iid} on {day.isoformat()}: "
                "no near-the-money quote within the spread limit"
            )
    return ""


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
        return FeatureValue(info.name, None, Unknown(UnknownCode.NO_ROW, detail), info)
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
    """Why a null value is null (ADR 0042 precedence): not applicable, illiquid, no row in a
    table it reads, else a stored null."""
    day = ctx.session.date
    why = _not_applicable(reasons[0], row, ctx, iid)
    if why:
        return Unknown(UnknownCode.NOT_APPLICABLE, why)
    why = _illiquid(reasons[1], row, iid, day)
    if why:
        return Unknown(UnknownCode.ILLIQUID, why)
    rowless = [
        t
        for t in tables
        if t.startswith(ROLLUP_TABLE_PREFIX) and to_scalar(row.get(_marker(t))) is None
    ]
    if rowless:
        detail = f"{' / '.join(rowless)} has no row for {iid} on {day.isoformat()}"
        return Unknown(UnknownCode.NO_ROW, detail)
    return Unknown(UnknownCode.NULL, f"{info.name} is null for {iid} on {day.isoformat()}")


def load_feature_values(
    ctx: ReadContext, instrument_ids: Sequence[str] | None, names: Sequence[str]
) -> dict[str, tuple[FeatureValue, ...]]:
    """``names`` (catalogue fields, in the order asked; repeats dropped) for each instrument
    of ``instrument_ids`` (None: every instrument of the session's reference snapshot, the
    population a distribution is over), for ``ctx.session``: one read for them all.
    ``UnknownFeatureError`` when a name is not in the caller's catalogue."""
    wanted = list(dict.fromkeys(names))
    infos = feature_infos(ctx.features, wanted)
    tables = {n: _tables(ctx.features, n) for n in wanted}
    reasons = {
        n: ctx.features.applicability(n) if not n.startswith("instrument.") else (frozenset(), ())
        for n in wanted
    }
    if ctx.session.reference_snapshot is None:  # nothing stored to say who anything is
        rows: dict[str, Mapping[str, Any]] = {}
        missing: tuple[str, ...] = (REFERENCE_TABLE,)
        tables = dict.fromkeys(wanted, (REFERENCE_TABLE,))
    else:
        rollups = sorted(
            {t for ts in tables.values() for t in ts if t.startswith(ROLLUP_TABLE_PREFIX)}
        )
        fields = [
            *wanted,
            *(_marker(t) for t in rollups),
            *dict.fromkeys(f for r in reasons.values() for f in _reason_fields(r)),
        ]
        view = field_view(
            ctx.reader, ctx.session.date, fields, instrument_ids, features=ctx.features
        )
        rows = {
            str(r["instrument_id"]): cast(dict[str, Any], r) for r in view.frame.to_dict("records")
        }
        # A company snapshot taken after the session is not known on it (no lookahead).
        missing = (*view.missing, COMPANY_TABLE) if view.company_pre_snapshot else view.missing
    if instrument_ids is None:
        instrument_ids = list(rows)
    return {
        iid: tuple(
            _value(infos[n], tables[n], rows.get(iid), missing, ctx, iid, reasons[n])
            for n in wanted
        )
        for iid in instrument_ids
    }
