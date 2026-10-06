"""``FeatureTable``: instruments x catalogue features for the session, columnar and server-paged
(ADR 0038 "tables are one widget"): the Explore ticker table (the universe, filtered and
sorted) and compare (the instruments asked for, in the order asked).

The population is the universe snapshot the session sees (snapshot grain, ADR 0007's one rule:
disclosed as ``universe_snapshot`` / ``pre_snapshot``) or, with ``keys``, the instruments they
name; either way only instruments in the session's reference snapshot (who they are:
``Instrument``). Filters (``UniverseFilter``) and the sort read catalogue fields for the whole
population (``services.features.field_view``, the read a selection evaluates); the requested
columns are read only for the page's rows (``features.load_feature_values``), so a cell is a
``FeatureValue``: a value, or the UNKNOWN code saying why not (``unknown``, a matrix parallel to
``rows``). The filtered, sorted order of a query is cached per published state, so paging
through it reads only each page's values.

Sort keys are the column ids of the web's factories: ``symbol`` (the ticker) or a catalogue
name; a ``-`` prefix sorts descending; missing values sort last, ties by symbol. Without a
sort the universe is in symbol order and ``keys`` in the order asked."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

import pandas as pd

from algotrade.core.model.errors import MissingDataError
from algotrade.core.model.fields import COMPANY_TABLE, field_source, is_feature_field
from algotrade.core.views.feature_view import FeatureValue as Scalar
from algotrade.data.reference import load_universe
from algotrade.features.framework.feature import NullReason
from algotrade.services.features import field_view
from algotrade.services.read.context import NotFoundError, ReadContext, catalogue_key
from algotrade.services.read.instruments.catalogue import FeatureInfo, feature_infos
from algotrade.services.read.instruments.features import cell_codes, load_feature_values
from algotrade.services.read.instruments.identity import Instrument, load_instruments, resolve_id
from algotrade.services.read.session import Session
from algotrade.services.read.values import UnknownCode

SYMBOL = "symbol"  # the ticker column's sort key
_SYMBOL = "instrument.symbol"
_NAME = "instrument.name"
DEFAULT_SIZE = 100


@dataclass(frozen=True)
class UniverseFilter:
    """Which rows a table keeps (catalogue fields, case-insensitive): ``security_type``
    (``instrument.security_type``), ``sector`` (``instrument.sector``), ``liquidity_class``
    (``feature.liquidity_class``), ``leveraged`` (``instrument.is_leveraged``), ``optionable``
    (``instrument.optionable``), ``q`` (the symbol or name contains it)."""

    security_type: str | None = None
    leveraged: bool | None = None
    sector: str | None = None
    liquidity_class: str | None = None
    q: str | None = None
    optionable: bool | None = None


# The filter's text and flag fields, by attribute: the catalogue field each one matches.
_TEXT_FILTERS = {
    "security_type": "instrument.security_type",
    "sector": "instrument.sector",
    "liquidity_class": "feature.liquidity_class",
}
_FLAG_FILTERS = {"leveraged": "instrument.is_leveraged", "optionable": "instrument.optionable"}


@dataclass(frozen=True)
class FeatureTable:
    """One page of instruments x ``columns`` for ``session``. ``rows[i][j]`` is the value of
    ``columns[j]`` for ``instruments[i]`` (a JSON scalar), ``None`` exactly when
    ``unknown[i][j]`` says why. ``total``: rows matching the filters (every page); ``sort``:
    the order applied (None: the keys' order). ``universe_snapshot``: the universe snapshot the
    rows come from (None with ``keys`` or when none is stored; ``pre_snapshot``: one taken after
    the session). ``missing``: the tables the filters and the sort read that have nothing
    for the session (their fields are unknown, so no row passes a filter on them and the sort
    puts every row last); the nightly tables missing for it: ``session.missing``."""

    session: Session
    universe_snapshot: date | None
    pre_snapshot: bool
    columns: tuple[FeatureInfo, ...]
    instruments: tuple[Instrument, ...]
    rows: tuple[tuple[Scalar, ...], ...]
    unknown: tuple[tuple[UnknownCode | None, ...], ...]
    reasons: tuple[tuple[NullReason | None, ...], ...]  # the NullReason of each EXPLAINED cell
    sort: str | None
    total: int
    page: int
    size: int
    missing: tuple[str, ...]


@dataclass(frozen=True)
class _Population:
    ids: tuple[str, ...]
    snapshot: date | None
    pre_snapshot: bool


@dataclass(frozen=True)
class _Order:
    ids: tuple[str, ...]
    missing: tuple[str, ...]


def _universe(ctx: ReadContext, seq: int) -> _Population:
    """The universe snapshot the session sees (cached per published state ``seq``)."""
    key = ("universe", ctx.session.date, seq)
    found = ctx.cache.get(key)
    if found is None:
        try:
            universe = load_universe(ctx.reader, ctx.session.date)
        except MissingDataError:
            found = _Population((), None, False)
        else:
            ids = tuple(str(i) for i in universe.frame["instrument_id"])
            found = _Population(ids, universe.snapshot_date, universe.pre_snapshot)
        ctx.cache.put(key, found)
    return found


def _keyed(ctx: ReadContext, keys: Sequence[str]) -> _Population:
    """The instruments ``keys`` (ids or tickers) name, in order, repeats dropped;
    ``NotFoundError`` naming a key the reference snapshot does not know."""
    ids = []
    for key in dict.fromkeys(keys):
        iid = resolve_id(ctx, key)
        if iid is None:
            raise NotFoundError(
                f"no instrument {key!r} in the reference snapshot {ctx.session.reference_snapshot}"
            )
        ids.append(iid)
    return _Population(tuple(dict.fromkeys(ids)), None, False)


def _same(values: "pd.Series[Any]", wanted: str) -> "pd.Series[bool]":
    return values.astype("string").str.casefold().eq(wanted.casefold()).fillna(False)


def _kept(frame: pd.DataFrame, f: UniverseFilter) -> "pd.Series[bool]":
    keep = pd.Series(True, index=frame.index)
    for attribute, field in _TEXT_FILTERS.items():
        wanted = getattr(f, attribute)
        if wanted:
            keep &= _same(frame[field], wanted)
    for attribute, field in _FLAG_FILTERS.items():
        wanted = getattr(f, attribute)
        if wanted is not None:
            keep &= frame[field].astype("boolean").eq(wanted).fillna(False)
    if f.q:
        text = (
            frame[_SYMBOL].astype("string").fillna("")
            + " "
            + frame[_NAME].astype("string").fillna("")
        )
        keep &= text.str.contains(f.q.strip(), case=False, regex=False).fillna(False)
    return keep


def _fields(f: UniverseFilter, column: str | None) -> list[str]:
    """The catalogue fields the filters and the sort column read (symbol and name always)."""
    used = [field for a, field in _TEXT_FILTERS.items() if getattr(f, a)]
    used += [field for a, field in _FLAG_FILTERS.items() if getattr(f, a) is not None]
    return list(dict.fromkeys([_SYMBOL, _NAME, *used, *([column] if column else [])]))


def _company(name: str) -> bool:
    return not is_feature_field(name) and field_source(name)[0] == COMPANY_TABLE


def catalogue_values(
    ctx: ReadContext, fields: Sequence[str], instrument_ids: Sequence[str] | None
) -> tuple[pd.DataFrame, tuple[str, ...]]:
    """``fields`` (catalogue names) for ``instrument_ids`` (None: the reference snapshot) for
    the session, one row per instrument indexed by id, and the tables with nothing for it (a
    field its table does not store, or a table with no partition, reads as null; a company
    snapshot taken after the session is not known on it). What a table's filters and sort
    read over its whole population (the screen results' too)."""
    view = field_view(
        ctx.reader, ctx.session.date, list(fields), instrument_ids, features=ctx.features
    )
    frame = view.frame.drop_duplicates("instrument_id").set_index("instrument_id")
    frame = frame.reindex(columns=list(fields))
    missing = list(view.missing)
    if view.company_pre_snapshot:  # taken after the session: not known on it (no lookahead)
        frame[[n for n in fields if _company(n)]] = None
        missing.append(COMPANY_TABLE)
    return frame, tuple(sorted(set(missing)))


def _ordered(
    ctx: ReadContext,
    population: _Population,
    f: UniverseFilter,
    sort: str | None,
    keyed: bool,
    seq: int,
) -> _Order:
    """The population's ids that pass ``f``, in ``sort`` order, and the tables those read
    with nothing for the session (cached per query and published state ``seq``)."""
    key = (
        "table",
        ctx.session.date,
        population.ids if keyed else None,
        f,
        sort,
        ctx.user.user_id,
        catalogue_key(ctx),
        seq,
    )
    found = ctx.cache.get(key)
    if found is not None:
        return found  # type: ignore[no-any-return]
    column = None if sort is None else sort.removeprefix("-")
    field = _SYMBOL if column == SYMBOL else column
    fields = _fields(f, field)
    frame, missing = catalogue_values(ctx, fields, population.ids if keyed else None)
    # Population order, only instruments the reference snapshot has (who they are).
    frame = frame.reindex([i for i in population.ids if i in frame.index])
    frame = frame[_kept(frame, f)]
    if field is not None:
        descending = sort is not None and sort.startswith("-")
        frame = frame.assign(_key=frame[field], _tie=frame[_SYMBOL].astype("string"))
        frame = frame.sort_values(
            ["_key", "_tie"],
            ascending=[not descending, True],
            na_position="last",
            kind="stable",
        )
    found = _Order(tuple(str(i) for i in frame.index), missing)
    ctx.cache.put(key, found)
    return found


def load_table(
    ctx: ReadContext,
    columns: Sequence[str],
    filters: UniverseFilter | None = None,
    sort: str | None = None,
    page: int = 1,
    size: int = DEFAULT_SIZE,
    keys: Sequence[str] | None = None,
) -> FeatureTable:
    """Page ``page`` (1-based, ``size`` rows) of the universe for ``ctx.session`` (or of the
    instruments ``keys`` name) x ``columns`` (catalogue names, in order, repeats dropped),
    filtered by ``filters`` and sorted by ``sort`` (``symbol`` or a catalogue name, ``-``:
    descending; default: symbol, or the keys' order). ``UnknownFeatureError`` for a column or
    sort field outside the caller's catalogue; ``NotFoundError`` for a key naming nothing."""
    wanted = list(dict.fromkeys(columns))
    infos = feature_infos(ctx.features, wanted)
    keyed = keys is not None
    order = sort or (None if keyed else SYMBOL)
    if order is not None and order.removeprefix("-") != SYMBOL:
        feature_infos(ctx.features, [order.removeprefix("-")])
    page, size = max(page, 1), max(size, 1)
    seq = ctx.reader.visible_seq()  # read once, before computing (ADR 0022)
    if ctx.session.reference_snapshot is None:  # nothing stored says who anything is
        population = _Population((), None, False)
    else:
        population = _keyed(ctx, keys) if keys is not None else _universe(ctx, seq)
    order_ = _ordered(ctx, population, filters or UniverseFilter(), order, keyed, seq)
    ordered = order_.ids
    shown = list(ordered[(page - 1) * size : page * size])
    identity = load_instruments(ctx, shown)
    shown = [i for i in shown if i in identity]  # the snapshot just read has each of them
    cells = load_feature_values(ctx, shown, wanted) if wanted and shown else {}
    codes = cell_codes(cells, shown)
    return FeatureTable(
        session=ctx.session,
        universe_snapshot=population.snapshot,
        pre_snapshot=population.pre_snapshot,
        columns=tuple(infos[n] for n in wanted),
        instruments=tuple(identity[i] for i in shown),
        rows=tuple(tuple(v.value for v in cells.get(i, ())) for i in shown),
        unknown=codes[0],
        reasons=codes[1],
        sort=order,
        total=len(ordered),
        page=page,
        size=size,
        missing=order_.missing,
    )
