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

from collections.abc import Hashable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date
from typing import Any

import pandas as pd

from algotrade.core.model.errors import ConfigurationError
from algotrade.core.views.feature_view import FeatureValue as Scalar
from algotrade.features.framework.feature import NullReason
from algotrade.services.features import catalogue
from algotrade.services.licences import ALL_LICENCES, hidden_stored
from algotrade.services.read.availability.cause import Unavailable, UnavailableKind
from algotrade.services.read.availability.unavailable import unavailable_tables
from algotrade.services.read.context import (
    Held,
    ReadContext,
    at_session,
    catalogue_key,
    run_rows_of,
)
from algotrade.services.read.evaluation.pick_edges import PickEdge, load_pick_edges
from algotrade.services.read.instruments.catalogue import FeatureInfo, feature_infos
from algotrade.services.read.instruments.features import cell_codes, load_feature_values
from algotrade.services.read.instruments.identity import Instrument, load_instruments
from algotrade.services.read.instruments.table import DEFAULT_SIZE, catalogue_values
from algotrade.services.read.screens.runs import (
    RULE_SCREEN,
    ScreenerRun,
    load_previous_run,
    run_picks,
    run_row_details,
    run_rows,
)
from algotrade.services.read.screens.screeners import ScreenGroup
from algotrade.services.read.values import UnknownCode, to_scalar
from algotrade.services.screening.rule_results import change_of
from algotrade.storage.tables.schemas import (
    is_criterion_row,
    is_display_column,
    is_group_row,
    result_table,
)

RULE_SCREEN_VALUES = result_table("rule_screen_values")
FIELD_COLUMNS = ("user_id", "config_id", "mode", "field")  # what ``_run_fields`` reads of the file
VALUE_COLUMNS = (
    "user_id", "config_id", "criterion_id", "mode", "field", "outcome", "value_num", "value_str",
    "distance", "group_id",
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
    group: str | None = None  # the group it sits in (ADR 0071); None: a gate


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
    ``previous_decision``: the previous run's (None: not in it, or not compared).
    ``regime`` / ``size_multiplier``: the session's regime label and the size the gate applied,
    as the run stamped them (None: gate off, regime unknown, or a run before the stamp);
    a ``PAUSED`` row says why first in ``reasons`` (ADR 0049)."""

    run_id: str
    config_id: str
    instrument_id: str
    instrument: Instrument | None
    rank: int | None  # None: withheld (the order follows values the viewer may not see)
    decision: str
    score: float | None
    tie_break: float | None
    reasons: str
    flags: tuple[str, ...]
    criteria: tuple[CriterionResult, ...]
    columns: tuple[ResultColumn, ...]
    change: str | None = None
    previous_decision: str | None = None
    regime: str | None = None
    size_multiplier: float | None = None
    groups: tuple[ScreenGroup, ...] = ()  # the screen's groups, each with its outcome (ADR 0071)
    # What each edge that lists the screener does with the row (``pick_edges``); only a review
    # table page fills it (empty: no edge lists the screener, or a read that does not ask)
    counts_toward: tuple[PickEdge, ...] = ()


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


def _decisions(ctx: ReadContext, run: ScreenerRun, wanted: set[str]) -> dict[str, str]:
    """``run``'s decision for each of ``wanted`` it has a row for: a pick or a ``PAUSED`` row from
    the run's cached picks (``run_picks``), any other (a name it did not pick) from its own
    ``rule_screen`` file for those names only, never the run's every row."""
    picks = run_picks(ctx, run)
    found = picks[picks["instrument_id"].isin(wanted)]
    out = {str(i): str(d) for i, d in zip(found["instrument_id"], found["decision"], strict=True)}
    rest = sorted(wanted - out.keys())
    if rest:
        stored = run_rows_of(
            ctx, RULE_SCREEN, run.run_id, ("user_id", "config_id", "decision"), rest
        )
        mine = stored[(stored["user_id"] == run.owner) & (stored["config_id"] == run.config_id)]
        out.update(
            (str(i), str(d)) for i, d in zip(mine["instrument_id"], mine["decision"], strict=True)
        )
    return out


def load_instrument_changes(ctx: ReadContext, run: ScreenerRun, ids: Sequence[str]) -> RunChanges:
    """``run`` against the screener's run in the previous stored session for ``ids`` only (the
    same ``Change`` as ``load_run_changes``; no counts): what one instrument's hits need, without
    comparing every row of the run. Reads the two runs' cached picks (``run_picks``) and, for a
    name neither picked, its own row."""
    previous = load_previous_run(ctx, run)
    if previous is None:
        return RunChanges(None, (), {})
    wanted = set(ids)
    now = _decisions(ctx, run, wanted)
    before = _decisions(at_session(ctx, previous.session), previous, wanted)
    moved = {i: (change_of(d, before.get(i)), before.get(i)) for i, d in now.items()}
    return RunChanges(previous.session, (), moved)


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
    the sort read with nothing for the session; ``unavailable``: what they leave out, in
    public words (ADR 0056)."""

    run_id: str
    sort: str
    total: int
    page: int
    size: int
    columns: tuple[FeatureInfo, ...]
    results: tuple[ScreenResult, ...]
    rows: tuple[tuple[Scalar, ...], ...]
    unknown: tuple[tuple[UnknownCode | None, ...], ...]
    reasons: tuple[tuple[NullReason | None, ...], ...]  # the NullReason of each EXPLAINED cell
    kinds: tuple[tuple[UnavailableKind | None, ...], ...]  # the public kind of each UNKNOWN cell
    missing: tuple[str, ...]
    unavailable: tuple[Unavailable, ...] = ()


def _records(frame: pd.DataFrame) -> list[Mapping[str, Any]]:
    return [{str(k): v for k, v in r.items()} for r in frame.to_dict("records")]


def _float(value: object) -> float | None:
    found = to_scalar(value)
    return None if found is None else float(found)


def _value(row: Mapping[str, Any]) -> Scalar:
    number = to_scalar(row.get("value_num"))
    return number if number is not None else to_scalar(row.get("value_str"))


def _values(
    ctx: ReadContext,
    runs: Sequence[ScreenerRun],
    ids: Sequence[str] | None,
    wanted: Mapping[str, Sequence[str]] | None = None,
    keep: bool = True,
) -> dict[ResultKey, list[Mapping[str, Any]]]:
    """The stored value rows of ``ids`` (None: every instrument) in each run, by (run id,
    instrument id). ``wanted`` (``{run id: instrument ids}``): a run's rows only for the
    instruments it is asked for (the rest are never read back, and turning them into records
    was most of an Ideas read). A run's stored values are the same for every caller until the
    next publish: the answer is kept in ``ctx.cache`` under the runs and instruments asked for
    and the published state (read first, ADR 0022), so a page asked again (the Ideas page's
    read of the session's 4.9 million value rows took 0.75 s) reads nothing. The rows are only
    read by callers. ``keep=False``: read, not cached (a caller that keeps its own result, the
    hits of one instrument, must not push the pages' entries out of the 32)."""
    if not keep:
        return _read_values(ctx, runs, ids, wanted)
    asked = tuple(
        (r.run_id, None if wanted is None else tuple(sorted(set(wanted.get(r.run_id) or ()))))
        for r in runs
    )
    key = (
        "screen-values",
        ctx.session.date,
        ctx.reader.own_run,
        ctx.reader.version(),
        None if ids is None else tuple(sorted(ids)),
        asked,
    )
    cached: dict[ResultKey, list[Mapping[str, Any]]] = ctx.cache.get_or_compute(
        key, lambda: _read_values(ctx, runs, ids, wanted)
    )
    return cached


def _read_values(
    ctx: ReadContext,
    runs: Sequence[ScreenerRun],
    ids: Sequence[str] | None,
    wanted: Mapping[str, Sequence[str]] | None,
) -> dict[ResultKey, list[Mapping[str, Any]]]:
    """Each run's own values file, read for the instruments the run is asked for (``wanted``, else
    ``ids``, else every one): never the session's every run filtered by the union of their picks."""
    out: dict[ResultKey, list[Mapping[str, Any]]] = {}
    for run in runs:
        if wanted is not None:
            asked: Sequence[str] | None = sorted(set(wanted.get(run.run_id) or ()))
            if not asked:
                continue
        else:
            asked = ids
        stored = run_rows_of(ctx, RULE_SCREEN_VALUES, run.run_id, VALUE_COLUMNS, asked)
        mine = stored[(stored["user_id"] == run.owner) & (stored["config_id"] == run.config_id)]
        for row in _records(mine):
            out.setdefault((run.run_id, str(row["instrument_id"])), []).append(row)
    return out


MISSING = "MISSING"  # a criterion outcome: no value (here: one the viewer may not see)


def _criterion(v: Mapping[str, Any], hidden: frozenset[str]) -> CriterionResult:
    """What a criterion judged; a field under a licence the viewer does not hold has no value,
    no distance and is MISSING to them (the stored value is never served)."""
    group = _parent(v)
    if str(v["field"]) in hidden:
        return CriterionResult(
            str(v["criterion_id"]), str(v["field"]), str(v["mode"]), MISSING, None, None, group
        )
    return CriterionResult(
        str(v["criterion_id"]),
        str(v["field"]),
        str(v["mode"]),
        str(v["outcome"]),
        _value(v),
        _float(v.get("distance")),
        group,
    )


def _parent(v: Mapping[str, Any]) -> str | None:
    """The group a stored row sits in (None: a gate, or a partition from before groups)."""
    found = to_scalar(v.get("group_id"))
    return None if found is None else str(found)


def _groups(values: Sequence[Mapping[str, Any]], hidden: frozenset[str]) -> tuple[ScreenGroup, ...]:
    """The groups of one instrument's stored rows, in stored order, each with its members (the
    rows naming it as parent). A group over a field the viewer may not see is MISSING to them
    and names no deciding member: its outcome would show what the hidden value did."""
    children: dict[str, list[str]] = {}
    for v in values:
        parent = _parent(v)
        if parent is not None and not is_display_column(v["mode"]):
            children.setdefault(parent, []).append(str(v["criterion_id"]))
    fields = {
        str(v["criterion_id"]): str(v["field"]) for v in values if is_criterion_row(v["mode"])
    }

    first = {cid: n for n, cid in enumerate(fields)}  # criteria are stored in spec order

    def position(node: str) -> int:
        """Funnel position: a criterion's, a group's its first descendant's (as plan does)."""
        if node not in first:
            first[node] = min((position(m) for m in children.get(node, ())), default=0)
        return first[node]

    for kids in children.values():
        kids.sort(key=position)  # stored order of the group rows is not the funnel's

    def shows_hidden(gid: str) -> bool:
        return any(
            (fields[m] in hidden) if m in fields else shows_hidden(m) for m in children.get(gid, ())
        )

    out = []
    for v in values:
        if not is_group_row(v["mode"]):
            continue
        gid = str(v["criterion_id"])
        withheld = shows_hidden(gid)
        decided = to_scalar(v.get("value_str"))
        out.append(
            ScreenGroup(
                gid,
                str(v["field"]),
                tuple(children.get(gid, ())),
                _parent(v),
                MISSING if withheld else str(v["outcome"]),
                None if withheld or decided is None else str(decided),
            )
        )
    return tuple(out)


def _run_fields(ctx: ReadContext, run: ScreenerRun) -> frozenset[str]:
    """The catalogue fields ``run``'s stored criteria and columns read; empty when its values are
    not readable. Read from the run's own values file once per publish and kept with every other
    run's in one container (``Held``), not an entry per run in ``ctx.cache``."""
    key = ("screen_run_fields", ctx.session.date, ctx.reader.own_run, ctx.reader.version())
    held: Held[tuple[str, ...]] = ctx.cache.get_or_compute(key, Held)

    def read() -> tuple[str, ...]:
        stored = run_rows_of(ctx, RULE_SCREEN_VALUES, run.run_id, FIELD_COLUMNS)
        if stored.empty:
            return ()
        mine = stored[(stored["user_id"] == run.owner) & (stored["config_id"] == run.config_id)]
        read = mine[~mine["mode"].map(is_group_row).astype(bool)]  # a group's field is its kind
        return tuple(sorted(str(f) for f in read["field"].dropna().unique()))

    fields, added = held.get_or_read(run.run_id, read)
    if added:
        ctx.cache.put(key, held)  # its weight changed
    return frozenset(fields)


UNREADABLE = "*"  # in ``run_withheld``: the run has rows but no stored values to tell its fields


def run_withheld(ctx: ReadContext, run: ScreenerRun) -> frozenset[str]:
    """The fields ``run`` read that the viewer's data licences do not cover (none for a viewer
    who holds them all: nothing is read). A run with any is a screen the viewer sees by names
    and decisions only: its ``score``, ``tie_break`` and ``reasons`` embed the hidden values
    (``reasons`` says "0.83, needs >= 0.9") and its rank order follows them, so they and
    the ``rank`` are withheld, and a sort by them is by symbol (ADR 0064 decision 10, ADR 0069).
    A run evaluated under licences the viewer also holds read nothing else (``fields_view`` hid
    the rest at run time): its fields count as open unless recorded otherwise. Each field (the
    stored ones and every one the run recorded, ``audit["field_licences"]``: the tie-break and
    flag fields too) is gated by ``hidden_stored``: the run's record and the site catalogue's
    current licence, never the viewer's own names. A run with rows but no readable values and no
    record is withheld whole.

    A run that recorded its fields is read from that record alone: the run path records every
    field it stores a value for (a contract test over ``run_screener``), so its values file is
    not read (it was the whole of this function's cost). A run with no record (before ADR 0069's
    ``field_licences``) still reads the file and fails closed as above."""
    if set(ctx.licences) >= ALL_LICENCES:
        return frozenset()
    at_run = run.audit.get("licences")
    within = isinstance(at_run, list | tuple) and set(at_run) <= set(ctx.licences)
    recorded = run.audit.get("field_licences")
    known: Mapping[str, str] = recorded if isinstance(recorded, Mapping) else {}
    stored = frozenset(known) if known else _run_fields(ctx, run)
    fields = stored | frozenset(known)
    if within:
        # evaluated under licences the viewer holds: what it read is open to them as recorded
        # (``fields_view`` hid the rest), but a field the site has since made personal is not
        known = {**dict.fromkeys(fields, "open"), **known}
    site = ctx.cache.get_or_compute(("site_catalogue",), lambda: catalogue(ctx.configs))
    hidden = hidden_stored(site, known, fields, ctx.licences)
    if within:
        return hidden
    if not stored and not known and run.decisions:
        return hidden | {UNREADABLE}
    return hidden


def run_audit(ctx: ReadContext, run: ScreenerRun) -> dict[str, Any]:
    """The run record's audit as the viewer may see it: a narrow miss of a withheld field
    quotes its value and threshold, so it is dropped (a role grants no licence)."""
    audit = dict(run.audit)
    summary = audit.get("summary")
    if not isinstance(summary, Mapping) or not (hidden := run_withheld(ctx, run)):
        return audit
    misses = summary.get("narrow_misses") or []
    kept = [
        m for m in misses
        if UNREADABLE not in hidden and str(m.get("field")) not in hidden
    ]  # fmt: skip
    audit["summary"] = {**summary, "narrow_misses": kept}
    return audit


def _result(
    run: ScreenerRun,
    row: Mapping[str, Any],
    values: Sequence[Mapping[str, Any]],
    instrument: Instrument | None,
    change: Change,
    hidden: frozenset[str] = frozenset(),
) -> ScreenResult:
    withheld = bool(hidden)
    criteria = tuple(_criterion(v, hidden) for v in values if is_criterion_row(v["mode"]))
    columns = tuple(
        ResultColumn(str(v["criterion_id"]), None if str(v["field"]) in hidden else _value(v))
        for v in values
        if is_display_column(v["mode"])
    )
    flags = str(to_scalar(row.get("flags")) or "")
    return ScreenResult(
        run_id=run.run_id,
        config_id=run.config_id,
        instrument_id=str(row["instrument_id"]),
        instrument=instrument,
        rank=None if withheld else int(row["rank"]),
        decision=str(row["decision"]),
        score=None if withheld else _float(row.get("score")),
        tie_break=None if withheld else _float(row.get("tie_break")),
        reasons="" if withheld else str(to_scalar(row.get("reasons")) or ""),
        flags=tuple(f for f in flags.split(",") if f),
        criteria=criteria,
        columns=columns,
        change=change[0],
        previous_decision=change[1],
        regime=None if (label := to_scalar(row.get("regime"))) is None else str(label),
        size_multiplier=_float(row.get("size_multiplier")),
        groups=_groups(values, hidden),
    )


def load_results(
    ctx: ReadContext,
    wanted: Mapping[str, Sequence[str]],
    runs: Sequence[ScreenerRun],
    changes: Mapping[str, RunChanges] | None = None,
    keep: bool = True,
) -> dict[ResultKey, ScreenResult]:
    """The results of ``wanted`` (``{run id: instrument ids}``) among ``runs``, by (run id,
    instrument id); an instrument the run has no row for is left out. ``changes``: each run's
    comparison with its previous run, by run id (absent: not compared). ``keep=False``: the
    stored values are read, not cached (``_values``)."""
    ids = sorted({i for found in wanted.values() for i in found})
    if not ids:
        return {}
    values = _values(ctx, runs, ids, wanted, keep)
    # The licence gate on stored values: a run recorded under a licence the viewer does not
    # hold (the scheduled site run holds every one, or a user lost one since) never serves
    # those fields' values, score, tie-break or reasons (the stored rows are shared in the
    # cache, so it is applied here, per viewer).
    instruments = load_instruments(ctx, ids)
    out: dict[ResultKey, ScreenResult] = {}
    for run in runs:
        asked = set(wanted.get(run.run_id, ()))
        if not asked:
            continue
        hidden = run_withheld(ctx, run)
        moved = changes[run.run_id].by_instrument if changes and run.run_id in changes else {}
        for row in _records(run_row_details(ctx, run, asked)):
            iid = str(row["instrument_id"])
            found = values.get((run.run_id, iid), [])
            change = moved.get(iid, (None, None))
            out[(run.run_id, iid)] = _result(run, row, found, instruments.get(iid), change, hidden)
    return out


def _compare(now: pd.DataFrame, before: Mapping[str, str]) -> dict[str, Change]:
    out: dict[str, Change] = {}
    for iid, decision in zip(now["instrument_id"], now["decision"], strict=True):
        was = before.get(str(iid))
        out[str(iid)] = (change_of(str(decision), was), was)
    return out


def load_change_summary(ctx: ReadContext, run: ScreenerRun) -> RunChanges:
    """``run``'s previous session and ``new`` / ``dropped`` counts, without the per-name tags
    (``by_instrument`` is empty): a frozen run (a ``screen_runs`` row) reads them as stored, no
    row of either run; a run before the table is recounted (``load_run_changes``)."""
    frozen = run.frozen
    if frozen is None:
        return load_run_changes(ctx, run)
    if frozen.previous_run_id is None or frozen.new_picks is None or frozen.dropped is None:
        return RunChanges(None, (), {})
    counted = {"new": frozen.new_picks, "dropped": frozen.dropped}
    counts = tuple(ChangeCount(c, counted[c]) for c in CHANGES)
    return RunChanges(frozen.previous_session, counts, {})


def load_run_changes(ctx: ReadContext, run: ScreenerRun) -> RunChanges:
    """``run`` against the screener's run in the previous stored session (cached per run and
    published state): every name's ``Change`` from the two runs' rows, the counts as frozen when
    the run has a ``screen_runs`` row, else counted from those rows."""
    key = ("run_changes", run.run_id, ctx.session.date, ctx.reader.version())
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
        frozen = load_change_summary(ctx, run) if run.frozen is not None else None
        if frozen is not None and frozen.counts:
            counts = frozen.counts
        else:
            counted = pd.Series([c for c, _ in moved.values() if c], dtype="string").value_counts()
            counts = tuple(ChangeCount(c, int(counted.get(c, 0))) for c in CHANGES)
        found = RunChanges(previous.session, counts, moved)
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
    (a read of the run's own values file, cached per run, key and published state)."""
    cache_key = (
        "screen_sort_key",
        run.run_id,
        ctx.session.date,
        key,
        ctx.user.user_id,  # what a viewer may see differs by licence
        ctx.reader.version(),
    )
    found: Mapping[str, Scalar] | None = ctx.cache.get(cache_key)
    if found is not None:
        return found
    kind, _, name = key.partition(":")
    stored = run_rows_of(ctx, RULE_SCREEN_VALUES, run.run_id, VALUE_COLUMNS)
    out: dict[str, Scalar] = {}
    if not stored.empty:
        column = stored["mode"].map(is_display_column).astype(bool)
        group = stored["mode"].map(is_group_row).astype(bool)
        mine = stored[
            (stored["user_id"] == run.owner)
            & (stored["config_id"] == run.config_id)
            & (stored["criterion_id"] == name)
            & (column == (kind == "column"))
            & ~group  # a group is no criterion (ADR 0071)
        ]
        seen = _records(mine)
        hidden = run_withheld(ctx, run)
        out = {str(r["instrument_id"]): _value(r) for r in seen if str(r["field"]) not in hidden}
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


def _ordered(ctx: ReadContext, run: ScreenerRun, query: ResultQuery, seq: Hashable) -> _Order:
    user = (ctx.user.user_id, catalogue_key(ctx))  # a sort on an edited feature: a new order
    key = ("screen_results", run.run_id, ctx.session.date, query, user, seq)
    found: _Order | None = ctx.cache.get(key)
    if found is not None:
        return found
    sort = query.sort or "rank"
    if sort.removeprefix("-") in ("rank", "score") and run_withheld(ctx, run):
        sort = ("-" if sort.startswith("-") else "") + "symbol"  # no order by hidden values
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
    seq = ctx.reader.version()  # read once, before computing (ADR 0022)
    query = ResultQuery(
        tuple(sorted({d.casefold() for d in query.decisions})), query.change, query.q, query.sort
    )
    order = _ordered(ctx, run, query, seq)
    shown = list(order.ids[(page - 1) * size : page * size])
    changes = {run.run_id: load_run_changes(ctx, run)}
    found = load_results(ctx, {run.run_id: shown}, [run], changes)
    results = [found[(run.run_id, i)] for i in shown if (run.run_id, i) in found]
    toward = load_pick_edges(ctx, run, [(r.instrument_id, r.decision, r.rank) for r in results])
    results = [replace(r, counts_toward=toward.get(r.instrument_id, ())) for r in results]
    cells = load_feature_values(ctx, shown, wanted) if wanted and shown else {}
    codes = cell_codes(cells, [r.instrument_id for r in results])
    return ResultPage(
        run_id=run.run_id,
        sort=query.sort or "rank",
        total=len(order.ids),
        page=page,
        size=size,
        columns=tuple(infos[n] for n in wanted),
        results=tuple(results),
        rows=tuple(tuple(v.value for v in cells.get(r.instrument_id, ())) for r in results),
        unknown=codes[0],
        reasons=codes[1],
        kinds=codes[2],
        missing=order.missing,
        unavailable=unavailable_tables(order.missing, ctx.session.date),
    )
