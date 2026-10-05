"""What a screener's run stored for an instrument (``ScreenResult``): rank, decision, score,
reasons, the flags that hold, every criterion's outcome with the value it judged, the screen's
display columns, and what changed since the previous run (``change``: ``new`` / ``dropped``),
from ``results/rule_screen`` and ``results/rule_screen_values`` for exactly the run's session
(``runs.ScreenerRun``). Nothing is recomputed.

``load_results`` reads the values of the asked instruments once for every run asked (one
column-pruned read of the values partition) and names the instruments in one identity read.

``load_result_page`` is a run as a review table (ADR 0032; read-model PR 8 moved it here from
``explore/screens/table.py``): a run holds a row for every instrument of the day's snapshot
(about 11k), so its rows are filtered (decisions, change, the search ``q``), sorted and paged
here, and the page carries the catalogue ``columns`` the reader adds (a ``FeatureTable``'s
columnar cells: a value, or the UNKNOWN code saying why not). The filtered, sorted order is
cached per query and published state. ``change`` compares the run with the screener's run in
the previous stored session (``runs.load_previous_run``): a ticker is *picked* when
``runs.is_picked`` says so (the Ideas rule)."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import pandas as pd

from algotrade.core.model.errors import ConfigurationError
from algotrade.core.views.feature_view import FeatureValue as Scalar
from algotrade.services.read.context import ReadContext, at_session, partition
from algotrade.services.read.instruments.catalogue import FeatureInfo, feature_infos
from algotrade.services.read.instruments.features import load_feature_values
from algotrade.services.read.instruments.identity import Instrument, load_instruments
from algotrade.services.read.instruments.table import DEFAULT_SIZE, catalogue_values
from algotrade.services.read.screens.runs import (
    ScreenerRun,
    is_picked,
    load_previous_run,
    run_rows,
)
from algotrade.services.read.values import Unknown, UnknownCode, to_scalar
from algotrade.storage.tables.schemas import is_display_column, result_table

RULE_SCREEN_VALUES = result_table("rule_screen_values")
VALUE_COLUMNS = (
    "user_id", "config_id", "criterion_id", "mode", "field", "outcome", "value_num", "value_str",
    "distance",
)  # fmt: skip
CHANGES = ("new", "dropped")
# The typed sort keys (the web's column factory ids); also ``criterion:<id>``,
# ``column:<name>`` and a catalogue name.
SORTS = ("rank", "score", "symbol", "decision", "change")
_SYMBOL, _NAME = "instrument.symbol", "instrument.name"

ResultKey = tuple[str, str]  # (run id, instrument id)
Change = tuple[str | None, str | None]  # (new / dropped / None, the previous decision)


@dataclass(frozen=True)
class CriterionResult:
    """What one criterion judged: the value (None: missing), PASS / NEAR / FAIL / MISSING
    and, for a near miss or a fail, how far from passing."""

    id: str
    field: str
    mode: str
    outcome: str
    value: Scalar
    distance: float | None


@dataclass(frozen=True)
class ResultColumn:
    """One of the screen's display columns (``[columns]``) for the instrument."""

    name: str
    value: Scalar


@dataclass(frozen=True)
class ScreenResult:
    """One instrument's row of one run. ``instrument``: who it is in the session's reference
    snapshot (None: not in it); ``criteria`` in the order stored; ``change``: ``new`` (picked
    now, not by the previous run) or ``dropped`` (the reverse), None when the same or not
    compared (no previous run, or a read that does not compare: Ideas);
    ``previous_decision``: the previous run's (None: not in it, or not compared)."""

    run_id: str
    config_id: str
    instrument_id: str
    instrument: Instrument | None
    rank: int
    decision: str
    score: float | None
    tie_break: float | None
    reasons: str
    flags: tuple[str, ...]
    criteria: tuple[CriterionResult, ...]
    columns: tuple[ResultColumn, ...]
    change: str | None = None
    previous_decision: str | None = None


@dataclass(frozen=True)
class ChangeCount:
    change: str
    count: int


@dataclass(frozen=True)
class RunChanges:
    """A run against the screener's run in the previous stored session: that session (None:
    no previous run, so nothing is new or dropped), how many tickers are ``new`` /
    ``dropped`` over the whole run, and each instrument's ``Change``."""

    previous_session: date | None
    counts: tuple[ChangeCount, ...]
    by_instrument: Mapping[str, Change] = field(repr=False)


@dataclass(frozen=True)
class ResultQuery:
    """Which rows of a run a review table shows: ``decisions`` (none: all; any case),
    ``change`` (``new`` / ``dropped``), ``q`` (the symbol or name contains it) and the order
    (``sort``: a ``SORTS`` key, ``criterion:<id>``, ``column:<name>`` or a catalogue name;
    ``-`` prefix: descending; missing values last; None: by rank)."""

    decisions: tuple[str, ...] = ()
    change: str | None = None
    q: str | None = None
    sort: str | None = None


@dataclass(frozen=True)
class ResultPage:
    """One page of a run's rows matching a ``ResultQuery``: ``results`` in order, and the
    catalogue ``columns`` the reader added for them, columnar as a ``FeatureTable``
    (``rows[i][j]`` is ``columns[j]`` for ``results[i]``, None exactly when ``unknown[i][j]``
    says why). ``total``: rows matching (every page); ``missing``: the tables the search and
    the sort read with nothing for the session."""

    run_id: str
    sort: str
    total: int
    page: int
    size: int
    columns: tuple[FeatureInfo, ...]
    results: tuple[ScreenResult, ...]
    rows: tuple[tuple[Scalar, ...], ...]
    unknown: tuple[tuple[UnknownCode | None, ...], ...]
    missing: tuple[str, ...]


def _records(frame: pd.DataFrame) -> list[Mapping[str, Any]]:
    return [{str(k): v for k, v in r.items()} for r in frame.to_dict("records")]


def _float(value: object) -> float | None:
    found = to_scalar(value)
    return None if found is None else float(found)


def _value(row: Mapping[str, Any]) -> Scalar:
    number = to_scalar(row.get("value_num"))
    return number if number is not None else to_scalar(row.get("value_str"))


def _values(
    ctx: ReadContext, runs: Sequence[ScreenerRun], ids: Sequence[str] | None
) -> dict[ResultKey, list[Mapping[str, Any]]]:
    """The stored value rows of ``ids`` (None: every instrument) in each run, by (run id,
    instrument id)."""
    stored = partition(ctx, RULE_SCREEN_VALUES, VALUE_COLUMNS, ids)
    if isinstance(stored, Unknown) or stored.empty:
        return {}
    out: dict[ResultKey, list[Mapping[str, Any]]] = {}
    for run in runs:
        mine = stored[
            (stored["user_id"] == run.owner)
            & (stored["config_id"] == run.config_id)
            & (stored["run_id"] == run.run_id)
        ]
        for row in _records(mine):
            out.setdefault((run.run_id, str(row["instrument_id"])), []).append(row)
    return out


def _result(
    run: ScreenerRun,
    row: Mapping[str, Any],
    values: Sequence[Mapping[str, Any]],
    instrument: Instrument | None,
    change: Change,
) -> ScreenResult:
    criteria = tuple(
        CriterionResult(
            str(v["criterion_id"]),
            str(v["field"]),
            str(v["mode"]),
            str(v["outcome"]),
            _value(v),
            _float(v.get("distance")),
        )
        for v in values
        if not is_display_column(v["mode"])
    )
    columns = tuple(
        ResultColumn(str(v["criterion_id"]), _value(v))
        for v in values
        if is_display_column(v["mode"])
    )
    flags = str(to_scalar(row.get("flags")) or "")
    return ScreenResult(
        run_id=run.run_id,
        config_id=run.config_id,
        instrument_id=str(row["instrument_id"]),
        instrument=instrument,
        rank=int(row["rank"]),
        decision=str(row["decision"]),
        score=_float(row.get("score")),
        tie_break=_float(row.get("tie_break")),
        reasons=str(to_scalar(row.get("reasons")) or ""),
        flags=tuple(f for f in flags.split(",") if f),
        criteria=criteria,
        columns=columns,
        change=change[0],
        previous_decision=change[1],
    )


def load_results(
    ctx: ReadContext,
    wanted: Mapping[str, Sequence[str]],
    runs: Sequence[ScreenerRun],
    changes: Mapping[str, RunChanges] | None = None,
) -> dict[ResultKey, ScreenResult]:
    """The results of ``wanted`` (``{run id: instrument ids}``) among ``runs``, by (run id,
    instrument id); an instrument the run has no row for is left out. ``changes``: each run's
    comparison with its previous run, by run id (absent: not compared)."""
    ids = sorted({i for found in wanted.values() for i in found})
    if not ids:
        return {}
    values = _values(ctx, runs, ids)
    instruments = load_instruments(ctx, ids)
    out: dict[ResultKey, ScreenResult] = {}
    for run in runs:
        asked = set(wanted.get(run.run_id, ()))
        if not asked:
            continue
        moved = changes[run.run_id].by_instrument if changes and run.run_id in changes else {}
        rows: pd.DataFrame = run_rows(ctx, run)
        for row in _records(rows[rows["instrument_id"].isin(asked)]):
            iid = str(row["instrument_id"])
            found = values.get((run.run_id, iid), [])
            change = moved.get(iid, (None, None))
            out[(run.run_id, iid)] = _result(run, row, found, instruments.get(iid), change)
    return out


def _compare(now: pd.DataFrame, before: Mapping[str, str]) -> dict[str, Change]:
    out: dict[str, Change] = {}
    for iid, decision in zip(now["instrument_id"], now["decision"], strict=True):
        was = before.get(str(iid))
        now_picked, was_picked = is_picked(str(decision)), was is not None and is_picked(was)
        change = "new" if now_picked and not was_picked else None
        out[str(iid)] = ("dropped" if was_picked and not now_picked else change, was)
    return out


def load_run_changes(ctx: ReadContext, run: ScreenerRun) -> RunChanges:
    """``run`` against the screener's run in the previous stored session (cached per run and
    published state)."""
    key = ("run_changes", run.run_id, ctx.session.date, ctx.reader.visible_seq())
    found: RunChanges | None = ctx.cache.get(key)
    if found is not None:
        return found
    previous = load_previous_run(ctx, run)
    if previous is None:
        found = RunChanges(None, (), {})
    else:
        # ``previous`` was read in its own session's context; its rows are read there too.
        before_rows = run_rows(at_session(ctx, previous.session), previous)
        before = {
            str(i): str(d)
            for i, d in zip(before_rows["instrument_id"], before_rows["decision"], strict=True)
        }
        moved = _compare(run_rows(ctx, run), before)
        counted = pd.Series([c for c, _ in moved.values() if c], dtype="string").value_counts()
        found = RunChanges(
            previous.session,
            tuple(ChangeCount(c, int(counted.get(c, 0))) for c in CHANGES),
            moved,
        )
    ctx.cache.put(key, found)
    return found


@dataclass(frozen=True)
class _Order:
    ids: tuple[str, ...]
    missing: tuple[str, ...]


def _check_sort(ctx: ReadContext, sort: str) -> str | None:
    """The catalogue field ``sort`` orders by (None: a typed or stored key);
    ``ConfigurationError`` for a key that names no column."""
    key = sort.removeprefix("-")
    kind, _, name = key.partition(":")
    if key in SORTS:
        return _SYMBOL if key == "symbol" else None
    if kind in ("criterion", "column"):
        if not name:
            raise ConfigurationError(f"sort: {key!r} names no {kind}")
        return None
    feature_infos(ctx.features, [key])  # UnknownFeatureError naming it
    return key


def _stored_key(ctx: ReadContext, run: ScreenerRun, key: str) -> Mapping[str, Scalar]:
    """Each instrument's stored value of ``criterion:<id>`` or ``column:<name>`` in ``run``
    (one filtered read of the values partition, cached per run, key and published state)."""
    cache_key = ("screen_sort_key", run.run_id, ctx.session.date, key, ctx.reader.visible_seq())
    found: Mapping[str, Scalar] | None = ctx.cache.get(cache_key)
    if found is not None:
        return found
    kind, _, name = key.partition(":")
    stored = partition(ctx, RULE_SCREEN_VALUES, VALUE_COLUMNS)
    out: dict[str, Scalar] = {}
    if not isinstance(stored, Unknown) and not stored.empty:
        column = stored["mode"].map(is_display_column).astype(bool)
        mine = stored[
            (stored["user_id"] == run.owner)
            & (stored["config_id"] == run.config_id)
            & (stored["run_id"] == run.run_id)
            & (stored["criterion_id"] == name)
            & (column == (kind == "column"))
        ]
        out = {str(r["instrument_id"]): _value(r) for r in _records(mine)}
    ctx.cache.put(cache_key, out)
    return out


def _sorted(ids: list[str], values: Mapping[str, Any], descending: bool) -> list[str]:
    """``ids`` by their value (numbers before text, text without case); missing values
    last; ties keep the rank order."""
    have = [(i, values.get(i)) for i in ids if values.get(i) is not None]
    lacking = [i for i in ids if values.get(i) is None]
    have.sort(
        key=lambda iv: (0, float(iv[1]), "") if isinstance(iv[1], int | float)
        else (1, 0.0, str(iv[1]).casefold()),
        reverse=descending,
    )  # fmt: skip
    return [i for i, _ in have] + lacking


def _ordered(ctx: ReadContext, run: ScreenerRun, query: ResultQuery, seq: int) -> _Order:
    key = ("screen_results", run.run_id, ctx.session.date, query, ctx.user.user_id, seq)
    found: _Order | None = ctx.cache.get(key)
    if found is not None:
        return found
    sort = query.sort or "rank"
    catalogue_field = _check_sort(ctx, sort)
    rows = run_rows(ctx, run)  # rank order
    changes = load_run_changes(ctx, run).by_instrument
    if query.decisions:
        wanted = {d.casefold() for d in query.decisions}
        rows = rows[rows["decision"].astype(str).str.casefold().isin(wanted)]
    if query.change:
        moved = [changes.get(str(i), (None, None))[0] for i in rows["instrument_id"]]
        rows = rows[[c == query.change for c in moved]]
    ids = [str(i) for i in rows["instrument_id"]]
    fields = [_SYMBOL, _NAME, *([catalogue_field] if catalogue_field else [])]
    missing: tuple[str, ...] = ()
    frame = None
    if ids and (query.q or catalogue_field):
        frame, missing = catalogue_values(ctx, list(dict.fromkeys(fields)), ids)
    if query.q and frame is not None:
        text = (
            frame[_SYMBOL].astype("string").fillna("")
            + " "
            + frame[_NAME].astype("string").fillna("")
        )
        hit = text.str.contains(query.q.strip(), case=False, regex=False).fillna(False)
        kept = set(frame.index[hit.to_numpy(dtype=bool)].astype(str))
        ids = [i for i in ids if i in kept]
    name = sort.removeprefix("-")
    if name != "rank":
        if catalogue_field is not None and frame is not None:
            values: Mapping[str, Any] = {
                str(i): to_scalar(v) for i, v in frame[catalogue_field].items()
            }
        elif name in ("score", "decision"):
            values = {
                str(i): to_scalar(v) for i, v in zip(rows["instrument_id"], rows[name], strict=True)
            }
        elif name == "change":
            values = {i: changes.get(i, (None, None))[0] for i in ids}
        else:
            values = _stored_key(ctx, run, name)
        ids = _sorted(ids, values, sort.startswith("-"))
    elif sort.startswith("-"):
        ids = ids[::-1]
    found = _Order(tuple(ids), missing)
    ctx.cache.put(key, found)
    return found


def load_result_page(
    ctx: ReadContext,
    run: ScreenerRun,
    query: ResultQuery | None = None,
    columns: Sequence[str] = (),
    page: int = 1,
    size: int = DEFAULT_SIZE,
) -> ResultPage:
    """Page ``page`` (1-based, ``size`` rows) of ``run``'s rows matching ``query``, with the
    catalogue ``columns`` (in order, repeats dropped) for its rows. ``ConfigurationError`` for
    an unknown ``change`` or sort key; ``UnknownFeatureError`` for a column or sort field
    outside the caller's catalogue."""
    query = query or ResultQuery()
    if query.change is not None and query.change not in CHANGES:
        raise ConfigurationError(f"change: {query.change!r} is not one of {', '.join(CHANGES)}")
    wanted = list(dict.fromkeys(columns))
    infos = feature_infos(ctx.features, wanted)
    page, size = max(page, 1), max(size, 1)
    seq = ctx.reader.visible_seq()  # read once, before computing (ADR 0022)
    query = ResultQuery(
        tuple(sorted({d.casefold() for d in query.decisions})), query.change, query.q, query.sort
    )
    order = _ordered(ctx, run, query, seq)
    shown = list(order.ids[(page - 1) * size : page * size])
    changes = {run.run_id: load_run_changes(ctx, run)}
    found = load_results(ctx, {run.run_id: shown}, [run], changes)
    results = [found[(run.run_id, i)] for i in shown if (run.run_id, i) in found]
    cells = load_feature_values(ctx, shown, wanted) if wanted and shown else {}
    return ResultPage(
        run_id=run.run_id,
        sort=query.sort or "rank",
        total=len(order.ids),
        page=page,
        size=size,
        columns=tuple(infos[n] for n in wanted),
        results=tuple(results),
        rows=tuple(tuple(v.value for v in cells.get(r.instrument_id, ())) for r in results),
        unknown=tuple(
            tuple(v.unknown.code if v.unknown else None for v in cells.get(r.instrument_id, ()))
            for r in results
        ),
        missing=order.missing,
    )
