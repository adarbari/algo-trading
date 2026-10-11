"""The evaluation runs of an edge (``EdgeRun``) and their rows (``EdgeRow``).

``results/edge_eval`` is partitioned by the range end, so it is read by run, as ``Backtest``
is: the run records ``edge-eval:<edge>:<user>`` (committed: COMPLETE) and each run's own rows
in its partition (``context.run_partition``: only that run's rows, never another run of the
same range end). Every run discloses its ``run_id``, range, ``split_from``, ``knowledge_ts`` and
``as_of``; a run whose split is not the edge's ``frozen_from`` is ``exploratory``. The
canonical run of an edge is the latest committed run of the site user whose split is its
``frozen_from``: none is ``NOT_RUN`` with the reason, never an older or exploratory run.

A run's trade ledger (``results/edge_trades``, ADR 0064) is read here too (``load_run_trades``),
the one reader: a hidden run's rows before its split only, per-name values under a licence the
viewer does not hold as ``LICENCE``, and a ledger the retention purge removed (``PRUNED``) told
apart from one the run never wrote (``NOT_STORED``). ``ledger_keep`` says which partitions the
purge spares: those of each edge's canonical run, latest run per user and cited run."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Final

import pandas as pd

from algotrade.config.edges.document import LEGACY_SITE_CUTOFF, LEGACY_SITE_OWNERS, job_name
from algotrade.config.edges.loading import UserDocuments, load_all_edges
from algotrade.config.site.settings import load_users
from algotrade.config.user import SITE_USER
from algotrade.data import StoreReader
from algotrade.services.read.availability.cause import run_cause, table_cause
from algotrade.services.read.context import ReadContext, Stores, run_partition
from algotrade.services.read.evaluation.edges import Edge, load_edges
from algotrade.services.read.values import Unknown, UnknownCode, to_scalar
from algotrade.storage.runs import RunRecord, RunStatus
from algotrade.storage.tables.schemas import result_table

EDGE_EVAL = "edge_eval"
EDGE_SERIES = "edge_series"  # the per-session series of a run (ADR 0064)
MAIN = "main"
RANDOM = "random"  # the role of a random-pick draw (ED8), never a screener or a baseline
DECILES = 10
IN_SAMPLE = "in_sample"  # the slice before the split


@dataclass(frozen=True)
class EdgeRun:
    """One committed evaluation run. ``owner``: whose run (the user's id, or ``site``);
    ``range_from`` / ``range_to``: the sessions it covered; ``split_from``: the split the
    frozen slice was measured at (None: a run from before splits were recorded);
    ``exploratory``: its split is not the edge's ``frozen_from``; ``knowledge_ts``: when it
    committed; ``as_of``: the data version it read (ISO); ``after_session``: it committed
    after the request's session (a session-bound read only; always False without one): its
    numbers were not knowable on that session; ``lost_inputs``: what the run could not read, as
    "<variant>: <table> (<n> sessions)" (a screener missing a table on those decision sessions);
    ``oos_hidden``: the run is a copy's whose out-of-sample result is withheld until the user shows
    it (ADR 0053 amendment 2026-10-09): its rows are served in-sample only (``load_run_rows``);
    ``legacy_owner``: a site run recorded under an older owner (``LEGACY_SITE_OWNERS``, the
    ``local`` fallback), read as the site's and never rewritten; ``trigger``: what started it
    (``nightly`` | ``ui`` | ``cli``; None for a run from before it was recorded)."""

    run_id: str
    edge_id: str
    owner: str
    status: str
    range_from: date | None
    range_to: date
    split_from: date | None
    exploratory: bool
    knowledge_ts: datetime
    as_of: str | None
    trials_counted: int | None
    after_session: bool = False
    lost_inputs: tuple[str, ...] = ()
    oos_hidden: bool = False
    legacy_owner: str | None = None
    trigger: str | None = None


@dataclass(frozen=True)
class EdgeRow:
    """One stored row of a run: a screener or baseline (``variant``, its ``role``) of an edge
    variant (``main`` for the edge itself) over a horizon, for one slice (``all``, ``year``,
    ``regime``, ``frozen`` or ``split``). A number not stored is None."""

    edge_variant: str
    variant: str
    role: str
    horizon_sessions: int
    slice_kind: str
    slice_value: str
    sessions: int | None
    picks: int | None
    hits: int | None
    trials: int | None
    pre_snapshot_sessions: int | None
    hit_rate: float | None
    base_rate: float | None
    lift: float | None
    mean_excess_picks: float | None
    decile_spread: float | None
    decile_t: float | None
    effect_size: float | None
    sharpe: float | None
    deflated_sharpe: float | None
    pbo: float | None
    exploratory: bool = False
    decile_sessions: int | None = None
    in_sample: bool = False  # a model screener's score was fitted on sessions of this slice
    decile_means: tuple[float | None, ...] = ()  # each tenth's mean outcome, best-ranked first;
    # empty when the slice had none or the run is older than the columns (never zeros)


@dataclass(frozen=True)
class SeriesRow:
    """One block of decision sessions of a run's main edge variant, one screener or baseline at
    one horizon (``results/edge_series``, ADR 0064): the window it measured (``entry_session`` to
    ``exit_session``, from the calendar), ``before_split`` (the decision session is before the
    run's split, decided by the harness), why it holds no number (``status``: measured |
    excluded_coverage | lost_input | no_picks; ``lost_table`` is the admin cause of lost_input),
    the counts and the oriented means of the picks and of every eligible name, in ``unit``, and
    each tenth's mean. A number not stored is None."""

    variant: str
    role: str
    horizon_sessions: int
    decision_session: date
    entry_session: date | None
    exit_session: date | None
    block_days: int | None
    before_split: bool
    regime: str | None
    status: str
    lost_table: str | None
    unit: str | None
    licence: str | None
    picks: int | None
    pick_hits: int | None
    eligible: int | None
    base_hits: int | None
    pick_mean: float | None
    base_mean: float | None
    decile_means: tuple[float | None, ...] = ()


def lift_points(hit_rate: float | None, base_rate: float | None) -> float | None:
    """Win rate minus base rate, in points (None when either is not stored): the one place the
    served lift in points is computed."""
    return None if hit_rate is None or base_rate is None else (hit_rate - base_rate) * 100


@dataclass(frozen=True)
class CanonicalRun:
    """The canonical run of an edge, or why it has none (``not_run``: ``NOT_RUN``)."""

    run: EdgeRun | None
    not_run: Unknown | None


def _day(value: Any) -> date | None:
    return date.fromisoformat(value) if value else None


def _run(
    ctx: Stores, record: RunRecord, edge: Edge, owner: str, legacy_owner: str | None = None
) -> EdgeRun:
    stats = record.stats
    frozen_from = edge.frozen_from
    committed = record.finished_at or record.started_at
    session = ctx.session.date if isinstance(ctx, ReadContext) else None
    split = _day(stats.get("split_from"))
    start = (stats.get("range") or [None])[0]
    exploratory = _exploratory(stats, frozen_from)
    return EdgeRun(
        run_id=record.run_id,
        edge_id=edge.id,
        owner=owner,
        status=record.status.value,
        range_from=_day(start),
        range_to=record.session_date,
        split_from=split,
        exploratory=exploratory,
        knowledge_ts=committed,
        as_of=stats.get("as_of"),
        trials_counted=stats.get("trials_counted"),
        after_session=session is not None and committed.date() > session,
        lost_inputs=_lost(stats),
        oos_hidden=edge.oos_hidden and owner != SITE_USER,
        legacy_owner=legacy_owner,
        trigger=stats.get("trigger"),
    )


def _exploratory(stats: Mapping[str, Any], frozen_from: date | None) -> bool:
    """A run whose split is not the edge's ``frozen_from``, or that says it is exploratory."""
    return _day(stats.get("split_from")) != frozen_from or bool(stats.get("exploratory"))


def _lost(stats: Mapping[str, Any]) -> tuple[str, ...]:
    lost = [t for t in stats.get("lost_sessions") or [] if isinstance(t, dict)]
    return tuple(
        f"{t.get('variant', '?')}: {t.get('table', '?')} ({t.get('sessions', '?')} sessions)"
        for t in lost
    )


def _committed(ctx: Stores, edge: Edge, owner: str) -> list[EdgeRun]:
    """The committed runs of ``owner``, newest first; the site's include the records of
    ``LEGACY_SITE_OWNERS`` (built as the site's, the old owner disclosed)."""
    sources: list[tuple[str, str | None]] = [(owner, None)]
    if owner == SITE_USER and not edge.mine:  # a user's own edge has no legacy runs
        sources += [(legacy, legacy) for legacy in LEGACY_SITE_OWNERS]
    found = [
        (r, legacy)
        for who, legacy in sources
        for r in ctx.reader.runs(job_name(edge.id, who))
        if r.status is RunStatus.COMPLETE
        and (legacy is None or (r.finished_at or r.started_at) < LEGACY_SITE_CUTOFF)
    ]
    ordered = sorted(found, key=lambda f: f[0].finished_at or f[0].started_at, reverse=True)
    return [_run(ctx, r, edge, owner, legacy) for r, legacy in ordered]


def load_edge_runs(ctx: Stores, edge: Edge) -> tuple[EdgeRun, ...]:
    """Every committed run of ``edge`` the user sees (theirs, then the site's), newest first."""
    owners = dict.fromkeys([ctx.user.user_id, SITE_USER])
    runs: dict[str, EdgeRun] = {}
    for o in owners:  # a legacy ``local`` run is the viewer's own record too: the site's copy wins
        for r in _committed(ctx, edge, o):
            if r.run_id not in runs or r.legacy_owner is not None:
                runs[r.run_id] = r
    return tuple(sorted(runs.values(), key=lambda r: r.knowledge_ts, reverse=True))


def load_runs_of(ctx: Stores, edge_id: str) -> tuple[EdgeRun, ...]:
    """``load_edge_runs`` by edge id; none for an edge the user does not have."""
    edge = next((e for e in load_edges(ctx) if e.id == edge_id), None)
    return load_edge_runs(ctx, edge) if edge is not None else ()


def load_canonical_run(ctx: Stores, edge: Edge) -> CanonicalRun:
    """The latest committed run of the site user whose split is ``edge.frozen_from``; else
    ``NOT_RUN`` (no frozen period, or no run at it): never an exploratory or older split."""
    job = job_name(edge.id, SITE_USER)
    if edge.frozen_from is None:
        why = f"{edge.id} has no frozen period, so no run is canonical"
    else:
        found = [r for r in _committed(ctx, edge, SITE_USER) if not r.exploratory]
        if found:
            return CanonicalRun(found[0], None)
        why = f"{edge.id} has no committed run at its frozen period from {edge.frozen_from}"
    return CanonicalRun(None, Unknown(UnknownCode.NOT_RUN, run_cause(job, why)))


def _int(value: Any) -> int | None:
    stored = to_scalar(value)
    return int(stored) if stored is not None else None


def _float(value: Any) -> float | None:
    stored = to_scalar(value)
    return float(stored) if stored is not None else None


def _deciles(row: Mapping[str, Any]) -> tuple[float | None, ...]:
    found = tuple(_float(row.get(f"decile_mean_{i:02d}")) for i in range(1, DECILES + 1))
    return found if any(x is not None for x in found) else ()


def _row(row: Mapping[str, Any]) -> EdgeRow:
    return EdgeRow(
        edge_variant=str(to_scalar(row.get("edge_variant")) or MAIN),  # a null is NaN in a frame
        variant=str(row["variant"]),
        role=str(row["role"]),
        horizon_sessions=int(row["horizon_sessions"]),
        slice_kind=str(row["slice_kind"]),
        slice_value=str(row["slice_value"]),
        sessions=_int(row.get("sessions")),
        picks=_int(row.get("picks")),
        hits=_int(row.get("hits")),
        trials=_int(row.get("trials")),
        pre_snapshot_sessions=_int(row.get("pre_snapshot_sessions")),
        hit_rate=_float(row.get("hit_rate")),
        base_rate=_float(row.get("base_rate")),
        lift=_float(row.get("lift")),
        mean_excess_picks=_float(row.get("mean_excess_picks")),
        decile_spread=_float(row.get("decile_spread")),
        decile_t=_float(row.get("decile_t")),
        effect_size=_float(row.get("effect_size")),
        sharpe=_float(row.get("sharpe")),
        deflated_sharpe=_float(row.get("deflated_sharpe")),
        pbo=_float(row.get("pbo")),
        exploratory=to_scalar(row.get("exploratory")) is True,
        decile_sessions=_int(row.get("decile_sessions")),
        in_sample=to_scalar(row.get("in_sample")) is True,
        decile_means=_deciles(row),
    )


def _day_of(value: Any) -> date | None:
    """A stored date (ISO text, a date or a Timestamp; null is None or NaT)."""
    return None if pd.isna(value) else pd.Timestamp(value).date()


def _text(value: Any) -> str | None:
    stored = to_scalar(value)
    return None if stored is None else str(stored)


def _series_row(row: Mapping[str, Any]) -> SeriesRow:
    decision = _day_of(row["decision_session"])
    assert decision is not None  # a key column
    return SeriesRow(
        variant=str(row["variant"]),
        role=str(row["role"]),
        horizon_sessions=int(row["horizon_sessions"]),
        decision_session=decision,
        entry_session=_day_of(row.get("entry_session")),
        exit_session=_day_of(row.get("exit_session")),
        block_days=_int(row.get("block_days")),
        before_split=to_scalar(row.get("before_split")) is True,
        regime=_text(row.get("regime")),
        status=str(row["status"]),
        lost_table=_text(row.get("lost_table")),
        unit=_text(row.get("unit")),
        licence=_text(row.get("licence")),
        picks=_int(row.get("picks")),
        pick_hits=_int(row.get("pick_hits")),
        eligible=_int(row.get("eligible")),
        base_hits=_int(row.get("base_hits")),
        pick_mean=_float(row.get("pick_mean")),
        base_mean=_float(row.get("base_mean")),
        decile_means=_deciles(row),
    )


def _stored(ctx: Stores, record: RunRecord) -> tuple[EdgeRow, ...]:
    frame = run_partition(ctx, result_table(EDGE_EVAL), record)
    if frame is None:
        return ()
    return tuple(_row({str(k): v for k, v in r.items()}) for r in frame.to_dict("records"))


def rows_of_record(ctx: Stores, record: RunRecord) -> tuple[EdgeRow, ...]:
    """The screener and baseline rows the run ``record`` wrote, as it left them; none when its
    partition holds none of its own. The random-pick draws are not among them (the one filter
    every verdict, record and promotion consumer reads through): ``draws_of_record``."""
    return tuple(r for r in _stored(ctx, record) if r.role != RANDOM)


def draws_of_record(ctx: Stores, record: RunRecord) -> tuple[EdgeRow, ...]:
    """The random-pick draws the run ``record`` wrote (slice kind ``draw``, out-of-sample only),
    each a ``lift`` and ``hit_rate`` of one draw of names chosen with no information."""
    return tuple(r for r in _stored(ctx, record) if r.role == RANDOM)


def load_run_rows(ctx: Stores, run: EdgeRun) -> tuple[EdgeRow, ...]:
    """The rows ``run`` wrote, as it left them; none when its partition holds none of its own.
    A run whose out-of-sample result is hidden serves its ``in_sample`` rows only: the whole
    history, the years and the regimes all contain out-of-sample sessions, so they are withheld
    here, in the one reader, not in the browser."""
    record = ctx.reader.run(run.run_id)
    found = rows_of_record(ctx, record) if record is not None else ()
    return tuple(r for r in found if r.slice_kind == IN_SAMPLE) if run.oos_hidden else found


def load_run_draws(ctx: Stores, run: EdgeRun) -> tuple[EdgeRow, ...]:
    """The random-pick draws ``run`` wrote; none for a run from before they were drawn, and
    none while its out-of-sample result is hidden (a draw is measured out of sample)."""
    record = ctx.reader.run(run.run_id)
    if record is None or run.oos_hidden:
        return ()
    return draws_of_record(ctx, record)


def load_run_series(ctx: Stores, run: EdgeRun) -> tuple[SeriesRow, ...]:
    """The per-session series ``run`` wrote (``results/edge_series``, ADR 0064), oldest decision
    session first; none for a run from before the table (read as not stored) or a run that
    wrote none. A run whose out-of-sample result is hidden serves only the rows whose decision
    session is before its split (``before_split``): a later session is out of sample, and its
    window, counts and means would show the figure that is withheld; filtered here, in the one
    reader, never in the browser."""
    record = ctx.reader.run(run.run_id)
    frame = None if record is None else run_partition(ctx, result_table(EDGE_SERIES), record)
    if frame is None or frame.empty:
        return ()
    found = [_series_row({str(k): v for k, v in r.items()}) for r in frame.to_dict("records")]
    kept = [r for r in found if r.before_split] if run.oos_hidden else found
    return tuple(sorted(kept, key=lambda r: (r.variant, r.horizon_sessions, r.decision_session)))


# ---------------------------------------------------------------------------- the trade ledger
LEDGER = "edge_trades"
STORED, PRUNED, NOT_STORED = "STORED", "PRUNED", "NOT_STORED"
LEDGER_STATES: Final = (STORED, PRUNED, NOT_STORED)
PERSONAL = "personal"
# The per-name columns each recorded column licence covers (ADR 0064 decision 10).
LICENSED: Final = {
    "value_licence": ("value", "gross_value", "reference", "touch"),
    "score_licence": ("score",),
    "adv_licence": ("adv_usd_20d",),
}
LEDGER_ORDER = ["variant", "horizon_sessions", "decision_session", "rank"]

Cell = float | bool | Unknown | None


@dataclass(frozen=True)
class TradeRow:
    """One pick of a run's ledger. ``status``: ``won`` | ``lost`` | ``excluded`` (with its
    public ``excluded_reason``); a per-name value under a licence the viewer does not hold is
    ``Unknown(LICENCE)``, one not stored is None (never 0)."""

    variant: str
    horizon_sessions: int
    decision_session: date
    entry_session: date | None
    exit_session: date | None
    instrument_id: str
    rank: int | None
    status: str
    excluded_reason: str | None
    hit: bool | None
    delisted: bool
    before_split: bool
    score: Cell
    value: Cell
    gross_value: Cell
    max_drawdown: float | None
    adv_usd_20d: Cell
    reference: Cell
    touch: Cell


@dataclass(frozen=True)
class RunTrades:
    """One page of a run's ledger (``offset`` .. ``offset + limit`` of ``total`` rows matching
    the filters, by variant, horizon, decision session and rank). ``state``: ``STORED``,
    ``PRUNED`` (the run wrote rows the retention purge has removed: re-run the backtest) or
    ``NOT_STORED`` (a run from before the ledger); ``licence``: the trial licence of its rows."""

    state: str
    rows: tuple[TradeRow, ...] = ()
    total: int = 0
    licence: str | None = None


def _date(value: Any) -> date | None:
    stored = to_scalar(value)
    return date.fromisoformat(str(stored)[:10]) if stored is not None else None


def _flag(value: Any) -> bool | None:
    stored = to_scalar(value)
    return None if stored is None else bool(stored)


def _trade(row: Mapping[str, Any], hidden: dict[str, Unknown]) -> TradeRow:
    def cell(column: str, read: Any = _float) -> Cell:
        return hidden[column] if column in hidden else read(row.get(column))

    reason = to_scalar(row.get("excluded_reason"))
    return TradeRow(
        variant=str(row["variant"]),
        horizon_sessions=int(row["horizon_sessions"]),
        decision_session=_date(row["decision_session"]) or date.min,
        entry_session=_date(row.get("entry_session")),
        exit_session=_date(row.get("exit_session")),
        instrument_id=str(row["instrument_id"]),
        rank=_int(row.get("rank")),
        status=str(row["status"]),
        excluded_reason=None if reason is None else str(reason),
        hit=_flag(row.get("hit")),
        delisted=_flag(row.get("delisted")) is True,
        before_split=_flag(row.get("before_split")) is True,
        score=cell("score"),
        value=cell("value"),
        gross_value=cell("gross_value"),
        max_drawdown=_float(row.get("max_drawdown")),
        adv_usd_20d=cell("adv_usd_20d"),
        reference=cell("reference"),
        touch=cell("touch", _flag),
    )


def _redacted(row: Mapping[str, Any], holder: bool, table: str) -> dict[str, Unknown]:
    """The per-name columns of ``row`` the viewer may not see: those whose recorded licence is
    personal, unless the viewer holds it (decided by the recorded licence, never by name)."""
    if holder:
        return {}
    out: dict[str, Unknown] = {}
    for licence_column, columns in LICENSED.items():
        if to_scalar(row.get(licence_column)) == PERSONAL:
            why = table_cause(table, f"{licence_column} is personal", "LICENCE")
            out.update(dict.fromkeys(columns, Unknown(UnknownCode.LICENCE, why)))
    return out


def load_run_trades(
    ctx: Stores,
    run: EdgeRun,
    *,
    variant: str | None = None,
    horizon: int | None = None,
    before_split: bool | None = None,
    offset: int = 0,
    limit: int | None = None,
) -> RunTrades:
    """The ledger ``run`` wrote, filtered (``before_split``: the in-sample side, False the
    out-of-sample one) and paged. A run whose out-of-sample result is hidden serves its rows
    before the split only, whatever is asked."""
    record = ctx.reader.run(run.run_id)
    count = None if record is None else record.stats.get("ledger_rows")
    if record is None or count is None:
        return RunTrades(NOT_STORED)
    table = result_table(LEDGER)
    frame = run_partition(ctx, table, record)
    if frame is None or frame.empty:
        return RunTrades(PRUNED if count else STORED)
    keep = pd.Series(True, index=frame.index)
    if run.oos_hidden or before_split is True:
        keep &= frame["before_split"].fillna(False).astype(bool)
    elif before_split is False:
        keep &= ~frame["before_split"].fillna(False).astype(bool)
    if variant is not None:
        keep &= frame["variant"] == variant
    if horizon is not None:
        keep &= frame["horizon_sessions"] == horizon
    found = frame[keep].sort_values(LEDGER_ORDER, kind="stable")
    page = found.iloc[offset : None if limit is None else offset + limit]
    holder = load_users(ctx.configs).holds(ctx.user.user_id, PERSONAL)
    rows = tuple(
        _trade(r, _redacted(r, holder, table))
        for r in ({str(k): v for k, v in row.items()} for row in page.to_dict("records"))
    )
    licences = {str(v) for v in found["licence"].dropna()} if "licence" in found else set()
    licence = PERSONAL if PERSONAL in licences else (licences.pop() if licences else None)
    return RunTrades(STORED, rows, len(found), licence)


def ledger_keep(reader: StoreReader, configs: UserDocuments) -> frozenset[date]:
    """The ``results/edge_trades`` partitions the retention purge spares (ADR 0064 decision 2):
    those of every edge's canonical run (the latest committed site run at its frozen split), of
    the latest committed run of each edge and user, and of every run an edge's ``[evidence]``
    cites. Every edge of every user is looked at, the site's and each user's own."""
    users = list(dict.fromkeys([SITE_USER, *configs.users()]))
    keep: set[date] = set()
    for edge in load_all_edges(configs):
        for user in users:
            done = sorted(
                (r for r in reader.runs(job_name(edge.id, user)) if r.status is RunStatus.COMPLETE),
                key=lambda r: r.finished_at or r.started_at,
                reverse=True,
            )
            if done:
                keep.add(done[0].session_date)
            if user == SITE_USER and edge.frozen_from is not None:
                canon = next((r for r in done if not _exploratory(r.stats, edge.frozen_from)), None)
                if canon is not None:
                    keep.add(canon.session_date)
        if edge.evidence is not None:
            cited = reader.run(edge.evidence.run_id)
            if cited is not None:
                keep.add(cited.session_date)
    return frozenset(keep)
