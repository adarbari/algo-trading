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

from algotrade.config.edges.document import job_name
from algotrade.core.time.calendar import sessions_to
from algotrade.services.read.context import ReadContext, Stores
from algotrade.services.read.evaluation import runs, versions
from algotrade.services.read.evaluation.edges import Edge
from algotrade.services.read.screens.screeners import load_screener
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


def _changed(ctx: Stores, edge: Edge, hashes: dict[str, str]) -> tuple[bool, int | None]:
    """Whether a screener of the edge now has another config than the run recorded, and the
    version of the first that does. A screener the run did not record is not claimed changed."""
    if not isinstance(ctx, ReadContext) or edge.mine:
        return False, None
    for screener in edge.screeners:
        before = hashes.get(screener)
        found = load_screener(ctx, screener) if before else None
        if found is not None and found.hash != before:
            return True, found.version
    return False, None


def _running_since(ctx: Stores, edge: Edge, run: runs.EdgeRun) -> datetime | None:
    """When a newer evaluation of the run's owner started, if one is running for the session."""
    job = job_name(edge.id, run.owner)
    session = ctx.session.date if isinstance(ctx, ReadContext) else run.range_to
    started = [
        r.started_at
        for r in ctx.reader.runs(job)
        if r.status is RunStatus.RUNNING
        and r.started_at > run.knowledge_ts
        and r.session_date >= session
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


def load_verdict_provenance(ctx: Stores, edge: Edge) -> Provenance | None:
    """The provenance of ``edge``'s verdict: of the run it is judged on (the canonical run of a
    site edge, the user's latest of their own); None when there is no run."""
    run = versions.own_run(ctx, edge) if edge.mine else runs.load_canonical_run(ctx, edge).run
    if run is None:
        return None
    served = ctx.session.date if isinstance(ctx, ReadContext) else run.range_to
    behind = max(sessions_to(run.range_to, served), 0)
    changed, version = _changed(ctx, edge, dict(run.screener_hashes))
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
