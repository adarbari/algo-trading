"""Which evaluation an edge's verdict rests on and whether it is current (ADR 0053): the
provenance line under the verdict, decided on the server (the browser derives nothing).

``Provenance`` describes the run the verdict is judged on, as the run left it (the verdict's
basis stays fixed; this only says how old it is): the session it evaluated, how many exchange
sessions that is behind the request's session, whether a screener implementing the edge changed
since (its config hash against the one the run recorded in ``stats["screener_hashes"]``; a run
from before that record is not claimed changed), whether a newer evaluation is running, and the
sentence. ``state`` is ``RE_EVALUATING`` while a newer evaluation of the same owner is running,
else ``STALE`` when the run is more than ``STALE_AFTER_SESSIONS`` sessions behind or a screener
changed, else ``CURRENT``. A running record counts only while its evaluation session is the
request's (a crashed run leaves its record RUNNING, never a reason to say re-evaluating next
week), so the read holds no clock. Public: the short run id and the figures; the full run id
is served to admins only (``AdminCause`` on the field), with no step or table name here."""

from dataclasses import dataclass
from datetime import date, datetime

from algotrade.config.user import UserContext
from algotrade.core.model.errors import ConfigurationError
from algotrade.core.time.calendar import sessions_to
from algotrade.services.configs import latest_screen_version, resolve_config
from algotrade.services.read.context import ReadContext
from algotrade.services.read.evaluation import runs, versions
from algotrade.services.read.evaluation.edges import Edge
from algotrade.storage.runs import RunStatus

CURRENT = "CURRENT"
STALE = "STALE"
RE_EVALUATING = "RE_EVALUATING"
STATES = (CURRENT, STALE, RE_EVALUATING)

# A verdict this many exchange sessions behind the served one is stale: a week of sessions.
# The nightly evaluates site edges, so a run older than this missed several nights. A constant,
# not a verdict.toml key: that file's settings are part of the stored headline's fingerprint, and
# a new key would re-judge every stored verdict for a wording threshold.
STALE_AFTER_SESSIONS = 5
# The run record of an ``edge-eval`` job (services/jobs writes it: ``job:<kind>``, the owner in
# ``stats["user"]``, the edge in ``stats["params"]["edge"]``, ``started_at`` its submission). The
# read model never imports the jobs package (ADR 0037), so the shape is read here.
EDGE_EVAL_JOB = "job:edge-eval"


@dataclass(frozen=True)
class Provenance:
    """The evaluation a verdict rests on. ``evaluated_session``: the run's last session;
    ``sessions_behind``: exchange sessions from it to the request's session (0: today's data);
    ``screener_changed`` / ``screener_version``: a screener of the edge changed since the run
    and its current version (None: unversioned); ``short_id``: the run's distinguishing stamp;
    ``run_id``: the full id (admins only on the wire); ``variants_tried``: the run's trial count
    (None: not recorded); ``re_evaluating`` / ``re_evaluation_started``: a newer evaluation is
    running and when it started; ``line``: the sentence."""

    state: str
    evaluated_session: date
    sessions_behind: int
    screener_changed: bool
    screener_version: int | None
    short_id: str
    run_id: str
    variants_tried: int | None
    re_evaluating: bool
    re_evaluation_started: datetime | None
    line: str


def short_id(run_id: str) -> str:
    """The run's stamp: the UTC write instant its id ends with (``20261022T235000Z``)."""
    stamp = run_id.rsplit("-", 1)[-1]
    return stamp if stamp != run_id else run_id[-16:]


def _day(value: date) -> str:
    return f"{value.day} {value:%b}"


def _count(n: int, noun: str) -> str:
    return f"{n} {noun}" if n == 1 else f"{n} {noun}s"


def _changed(ctx: ReadContext, edge: Edge, run: runs.EdgeRun) -> tuple[bool, int | None]:
    """Whether a screener of the edge now has another config than the run recorded, and the
    version of the first that does. Each is resolved as the run resolved it (as the run's owner,
    never as the viewer: a trader's own same-id config must not make a site edge look stale); a
    screener the run did not record, or that no longer resolves, is not claimed changed."""
    hashes = dict(run.screener_hashes)
    owner = UserContext(run.owner)
    for screener in edge.screeners:
        before = hashes.get(screener)
        if not before:
            continue
        try:
            now = resolve_config(ctx.configs, screener, owner)
        except ConfigurationError:
            continue
        if now.hash != before:
            return True, latest_screen_version(ctx.configs, run.owner, screener)
    return False, None


def _running_since(ctx: ReadContext, edge: Edge, run: runs.EdgeRun) -> datetime | None:
    """When a newer evaluation of this edge by the run's owner started: an ``edge-eval`` job
    queued or running (the jobs record the pool fails when its process stops, so a crash does not
    stay running) submitted after the run committed, on the request's session or later. The run
    record itself is written once, already COMPLETE, so it never shows an evaluation in flight."""
    started = [
        job.started_at
        for job in ctx.reader.runs(EDGE_EVAL_JOB)
        if job.stats.get("user") == run.owner
        and (job.stats.get("params") or {}).get("edge") == edge.id
        and job.status in (RunStatus.QUEUED, RunStatus.RUNNING)
        and job.started_at > run.knowledge_ts
        and job.started_at.date() >= ctx.session.date
    ]
    return max(started, default=None)


def _line(
    state: str,
    run: runs.EdgeRun,
    behind: int,
    changed: bool,
    started: datetime | None,
) -> str:
    when = _day(run.range_to)
    if state == RE_EVALUATING and started is not None:
        return (
            f"A new evaluation started {_day(started.date())} {started:%H:%M}. "
            f"Showing the {when} verdict until it finishes."
        )
    tried = run.trials_counted
    if state == CURRENT:
        data = "today's data" if behind == 0 else f"{_count(behind, 'session')} ago"
        text = f"Evaluated on the {when} session, {data}."
        text += f" Run {short_id(run.run_id)}"
        return text + (f", {_count(tried, 'variant')} tried." if tried else ".")
    ago = "today" if behind == 0 else f"{_count(behind, 'session')} ago"
    text = f"Evaluated {when}, {ago}."
    if changed:
        text += " The screener changed since: this verdict is for the earlier version."
    return text


def load_verdict_provenance(ctx: ReadContext | None, edge: Edge) -> Provenance | None:
    """The provenance of ``edge``'s verdict: of the run it is judged on (the canonical run of a
    site edge, the user's latest of their own); None when there is no served session (an empty
    store), no run, or when the run is newer than the request's session (a pinned older session:
    nothing honest to say about it)."""
    if ctx is None:
        return None
    run = versions.own_run(ctx, edge) if edge.mine else runs.load_canonical_run(ctx, edge).run
    if run is None:
        return None
    if run.range_to > ctx.session.date:
        return None
    behind = sessions_to(run.range_to, ctx.session.date)
    changed, version = _changed(ctx, edge, run)
    started = _running_since(ctx, edge, run)
    if started is not None:
        state = RE_EVALUATING
    elif changed or behind > STALE_AFTER_SESSIONS:
        state = STALE
    else:
        state = CURRENT
    return Provenance(
        state=state,
        evaluated_session=run.range_to,
        sessions_behind=behind,
        screener_changed=changed,
        screener_version=version,
        short_id=short_id(run.run_id),
        run_id=run.run_id,
        variants_tried=run.trials_counted,
        re_evaluating=started is not None,
        re_evaluation_started=started,
        line=_line(state, run, behind, changed, started),
    )
