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
sort the universe is in symbol order and ``keys`` in the order asked.

Filtered (ADR 0082, surface ``universe``): the ``filters`` the viewer set, and the older
``UniverseFilter`` attributes mapped onto the ``security_type`` / ``sector`` / ``liquidity_class``
/ ``leveraged`` / ``optionable`` filters (a text one matches case-insensitively, as before),
narrow the WHOLE population before it is sorted and paged, from one masked pass over a frame of
every offered filter's field (read under the viewer's licences: a field the viewer may not use has
no filter and no value, so a count never leaks it). ``total`` counts the rows passing the filters
and ``q``; ``FeatureTable.facets`` the counts of the population before ``q`` (``facets.total``:
every row; None for ``keys``, a list the caller chose, unless a filter is set). The pass is cached
per population, filters, viewer and published state; the sort and ``q`` come after it."""

from collections.abc import Hashable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date

import pandas as pd

from algotrade.core.model.errors import MissingDataError
from algotrade.core.model.fields import COMPANY_TABLE, field_source, is_feature_field
from algotrade.core.views.feature_view import FeatureValue as Scalar
from algotrade.data.reference import load_universe
from algotrade.features.framework.feature import NullReason
from algotrade.services.features import field_view
from algotrade.services.licences import hidden_fields
from algotrade.services.read.availability.cause import Unavailable, UnavailableKind
from algotrade.services.read.availability.unavailable import unavailable_tables
from algotrade.services.read.context import NotFoundError, ReadContext, catalogue_key
from algotrade.services.read.filtering.definitions import ResolvedFilters
from algotrade.services.read.filtering.facets import Facets, compute_facets
from algotrade.services.read.filtering.masks import Cell, FilterInput, rule_for
from algotrade.services.read.filtering.served import load_list_filters
from algotrade.services.read.instruments.catalogue import FeatureInfo, feature_infos
from algotrade.services.read.instruments.features import cell_codes, load_feature_values
from algotrade.services.read.instruments.identity import Instrument, load_instruments, resolve_id
from algotrade.services.read.session import Session
from algotrade.services.read.values import UnknownCode, to_scalar

SURFACE = "universe"  # config/site/filters/universe.toml
SYMBOL = "symbol"  # the ticker column's sort key
_SYMBOL = "instrument.symbol"
_NAME = "instrument.name"
DEFAULT_SIZE = 100


@dataclass(frozen=True)
class UniverseFilter:
    """Which rows a table keeps; every attribute but ``q`` is deprecated for the ``universe``
    filters (ADR 0082). Catalogue fields, case-insensitive: ``security_type``
    (``instrument.security_type``), ``sector`` (``instrument.sector``), ``liquidity_class``
    (``feature.liquidity_class``), ``leveraged`` (``instrument.is_leveraged``), ``optionable``
    (``instrument.optionable``), ``q`` (the symbol or name contains it)."""

    security_type: str | None = None
    leveraged: bool | None = None
    sector: str | None = None
    liquidity_class: str | None = None
    q: str | None = None
    optionable: bool | None = None


@dataclass(frozen=True)
class FeatureTable:
    """One page of instruments x ``columns`` for ``session``. ``rows[i][j]`` is the value of
    ``columns[j]`` for ``instruments[i]`` (a JSON scalar), ``None`` exactly when
    ``unknown[i][j]`` says why. ``total``: rows matching the filters (every page); ``sort``:
    the order applied (None: the keys' order). ``universe_snapshot``: the universe snapshot the
    rows come from (None with ``keys`` or when none is stored; ``pre_snapshot``: one taken after
    the session). ``missing``: the tables the filters and the sort read that have nothing
    for the session (their fields are unknown, so no row passes a filter on them and the sort
    puts every row last), and ``unavailable`` what they leave out in public words (ADR 0056); the
    nightly tables missing for the session: ``session.unavailable``."""

    session: Session
    universe_snapshot: date | None
    pre_snapshot: bool
    columns: tuple[FeatureInfo, ...]
    instruments: tuple[Instrument, ...]
    rows: tuple[tuple[Scalar, ...], ...]
    unknown: tuple[tuple[UnknownCode | None, ...], ...]
    reasons: tuple[tuple[NullReason | None, ...], ...]  # the NullReason of each EXPLAINED cell
    kinds: tuple[tuple[UnavailableKind | None, ...], ...]  # the public kind of each UNKNOWN cell
    sort: str | None
    total: int
    page: int
    size: int
    missing: tuple[str, ...]
    unavailable: tuple[Unavailable, ...] = ()
    facets: Facets | None = None


@dataclass(frozen=True)
class _Population:
    ids: tuple[str, ...]
    snapshot: date | None
    pre_snapshot: bool


@dataclass(frozen=True)
class _Passing:
    ids: tuple[str, ...]  # the population's order
    missing: tuple[str, ...]
    facets: Facets | None


@dataclass(frozen=True)
class _Order:
    ids: tuple[str, ...]
    missing: tuple[str, ...]
    facets: Facets | None


def _universe(ctx: ReadContext, seq: Hashable) -> _Population:
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


# The deprecated ``UniverseFilter`` attributes as the filters they are: attribute -> filter id
_TEXT_IDS = {
    "security_type": "security_type",
    "sector": "sector",
    "liquidity_class": "liquidity_class",
}
_FLAG_IDS = {"leveraged": "leveraged", "optionable": "optionable"}


def _mapped(
    f: UniverseFilter, columns: Mapping[str, Sequence[Cell]], resolved: ResolvedFilters
) -> list[FilterInput]:
    """``f``'s attributes as inputs. A text value is matched case-insensitively against the
    values stored (one that matches none is passed as given: it keeps nothing)."""
    out: list[FilterInput] = []
    for attribute, filter_id in _TEXT_IDS.items():
        wanted = getattr(f, attribute)
        definition = resolved.get(filter_id)
        if wanted and definition is not None:
            stored = {str(v) for v in columns[definition.field] if v is not None}
            hits = sorted(v for v in stored if v.casefold() == wanted.casefold())
            out.append(FilterInput(filter_id, hits or [wanted]))
        elif wanted:
            resolved.check([filter_id])  # not offered: refused
    for attribute, filter_id in _FLAG_IDS.items():
        wanted = getattr(f, attribute)
        if wanted is not None:
            resolved.check([filter_id])
            out.append(FilterInput(filter_id, ["yes" if wanted else "no"]))
    return out


def _signature(inputs: Sequence[FilterInput]) -> tuple[object, ...]:
    """What the inputs are, hashable, in id order (a cache key)."""
    return tuple(
        (i.id, tuple(i.values), i.min, i.max, i.within, i.active)
        for i in sorted(inputs, key=lambda i: i.id)
    )


def _symbol_or_name(frame: pd.DataFrame, q: str) -> "pd.Series[bool]":
    text = (
        frame[_SYMBOL].astype("string").fillna("") + " " + frame[_NAME].astype("string").fillna("")
    )
    return text.str.contains(q.strip(), case=False, regex=False).fillna(False)


def _company(name: str) -> bool:
    return not is_feature_field(name) and field_source(name)[0] == COMPANY_TABLE


def catalogue_values(
    ctx: ReadContext, fields: Sequence[str], instrument_ids: Sequence[str] | None
) -> tuple[pd.DataFrame, tuple[str, ...]]:
    """``fields`` (catalogue names) for ``instrument_ids`` (None: the reference snapshot) for
    the session, one row per instrument indexed by id, and the tables with nothing for it (a
    field its table does not store, or a table with no partition, reads as null; a company
    snapshot taken after the session is not known on it). What a table's filters and sort
    read over its whole population (the screen results' too). A field under a data licence the
    caller does not hold is not read: its column is null (``services.licences``), so a sort or
    a filter on it orders and keeps nothing by a hidden value."""
    hidden = hidden_fields(ctx.features, fields, ctx.licences)
    view = field_view(
        ctx.reader,
        ctx.session.date,
        [f for f in fields if f not in hidden],
        instrument_ids,
        features=ctx.features,
    )
    frame = view.frame.drop_duplicates("instrument_id").set_index("instrument_id")
    frame = frame.reindex(columns=list(fields))
    missing = list(view.missing)
    if view.company_pre_snapshot:  # taken after the session: not known on it (no lookahead)
        frame[[n for n in fields if _company(n)]] = None
        missing.append(COMPANY_TABLE)
    return frame, tuple(sorted(set(missing)))


def _passing(
    ctx: ReadContext,
    population: _Population,
    f: UniverseFilter,
    inputs: Sequence[FilterInput],
    keyed: bool,
    seq: Hashable,
) -> _Passing:
    """The population's ids that pass the filters (``f``'s attributes and ``inputs``), their
    facets, and the tables the SET filters read with nothing for the session (cached per
    population, filters, viewer and published state ``seq``: a new sort or ``q`` re-reads
    nothing). ``FilterRefusedError`` for a filter the viewer is not offered."""
    key = (
        "table_passing",
        ctx.session.date,
        population.ids if keyed else None,
        (f.security_type, f.sector, f.liquidity_class, f.leveraged, f.optionable),
        _signature(inputs),
        ctx.user.user_id,
        catalogue_key(ctx),
        seq,
    )
    found = ctx.cache.get(key)
    if found is not None:
        return found  # type: ignore[no-any-return]
    resolved = load_list_filters(ctx, SURFACE, [i.id for i in inputs]).resolved
    resolved.check(i.id for i in inputs)
    ids = population.ids if keyed else None
    offered = list(dict.fromkeys(d.field for d in resolved.offered))
    frame, _ = catalogue_values(ctx, offered, ids)
    frame = frame.reindex([i for i in population.ids if i in frame.index])
    columns: dict[str, list[Cell]] = {n: [to_scalar(v) for v in frame[n]] for n in offered}
    every = [*_mapped(f, columns, resolved), *inputs]
    facets = compute_facets(columns, len(frame), resolved, every)
    missing: tuple[str, ...] = ()
    set_fields = [  # the facets alone are no reason to disclose a gap: only a set filter's
        d.field
        for i in every
        if i.active and (d := resolved.get(i.id)) is not None and rule_for(d, i) is not None
    ]  # fmt: skip
    if set_fields:
        missing = catalogue_values(ctx, list(dict.fromkeys(set_fields)), ids)[1]
    shown = None if keyed and not set_fields else facets
    found = _Passing(tuple(str(frame.index[i]) for i in facets.matched_rows), missing, shown)
    ctx.cache.put(key, found)
    return found


def _ordered(
    ctx: ReadContext,
    population: _Population,
    f: UniverseFilter,
    inputs: Sequence[FilterInput],
    sort: str | None,
    keyed: bool,
    seq: Hashable,
) -> _Order:
    """The ids that pass the filters and ``q``, in ``sort`` order, and the tables the filters,
    the search and the sort read with nothing for the session (cached per query and published
    state ``seq``)."""
    key = (
        "table",
        ctx.session.date,
        population.ids if keyed else None,
        f,
        _signature(inputs),
        sort,
        ctx.user.user_id,
        catalogue_key(ctx),
        seq,
    )
    found = ctx.cache.get(key)
    if found is not None:
        return found  # type: ignore[no-any-return]
    passing = _passing(ctx, population, f, inputs, keyed, seq)
    column = None if sort is None else sort.removeprefix("-")
    field = _SYMBOL if column == SYMBOL else column
    fields = list(dict.fromkeys([_SYMBOL, _NAME, *([field] if field else [])]))
    frame, missing = catalogue_values(ctx, fields, passing.ids if keyed else None)
    # Population order, only the instruments that passed (who they are: the reference snapshot).
    frame = frame.reindex([i for i in passing.ids if i in frame.index])
    if f.q:
        frame = frame[_symbol_or_name(frame, f.q)]
    if field is not None:
        descending = sort is not None and sort.startswith("-")
        frame = frame.assign(_key=frame[field], _tie=frame[_SYMBOL].astype("string"))
        frame = frame.sort_values(
            ["_key", "_tie"],
            ascending=[not descending, True],
            na_position="last",
            kind="stable",
        )
    both = tuple(sorted({*passing.missing, *missing}))
    found = _Order(tuple(str(i) for i in frame.index), both, passing.facets)
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
    inputs: Sequence[FilterInput] = (),
) -> FeatureTable:
    """Page ``page`` (1-based, ``size`` rows) of the universe for ``ctx.session`` (or of the
    instruments ``keys`` name) x ``columns`` (catalogue names, in order, repeats dropped),
    filtered by ``filters`` and sorted by ``sort`` (``symbol`` or a catalogue name, ``-``:
    descending; default: symbol, or the keys' order); ``inputs``: the ``universe`` filters
    (ADR 0082). ``UnknownFeatureError`` for a column or sort field outside the caller's
    catalogue; ``NotFoundError`` for a key naming nothing; ``FilterRefusedError`` for a filter
    the viewer is not offered."""
    wanted = list(dict.fromkeys(columns))
    infos = feature_infos(ctx.features, wanted)
    keyed = keys is not None
    order = sort or (None if keyed else SYMBOL)
    if order is not None and order.removeprefix("-") != SYMBOL:
        feature_infos(ctx.features, [order.removeprefix("-")])
    page, size = max(page, 1), max(size, 1)
    seq = ctx.reader.version()  # read once, before computing (ADR 0022)
    if ctx.session.reference_snapshot is None:  # nothing stored says who anything is
        population = _Population((), None, False)
    else:
        population = _keyed(ctx, keys) if keys is not None else _universe(ctx, seq)
    order_ = _ordered(
        ctx, population, filters or UniverseFilter(), tuple(inputs), order, keyed, seq
    )
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
        kinds=codes[2],
        sort=order,
        total=len(ordered),
        page=page,
        size=size,
        missing=order_.missing,
        unavailable=unavailable_tables(order_.missing, ctx.session.date),
        facets=order_.facets,
    )
