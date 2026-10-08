"""The edge document (ADR 0053 decision 1; the quality bar is docs/edges-plan.md): one
``config/site/edges/<id>.toml`` typed into a frozen ``Edge``, fail closed: an unknown key, a
wrong type, an unknown status, schedule or event class, or a missing answer fails with the file
and the key.

    id, name          the file's stem (an id), the name on screen
    thesis            one sentence: what is mispriced, and which way
    mechanism         quality bar 1: who is forced, constrained or systematically wrong
    persistence       quality bar 2: why it survives being known
    [outcome]         kind (``excess_return`` | ``hit_target``), horizon_sessions (one or more),
                      benchmark (``SPY`` | ``none``), start_offset_sessions (S = the event's
                      anchor session + this; negative only before an event announced ahead),
                      optional target, max_drawdown (a fraction), cost_bps; a hit_target also
                      names its measure (MEASURES) and direction (``below`` | ``above``)
    schedule          ``every_session`` | ``month_end`` | ``on_event:<class>`` (EVENT_CLASSES)
    universe          a selection preset name, or an inline selection (``[universe] where``)
    top_k             an integer >= 1, or ``"all"`` (every qualified name)
    screeners         the screener presets that implement it (empty while a candidate waits)
    baselines         screener presets run on the same sessions (quality bar 9)
    status            candidate | evidenced | live | retired | rejected | blocked
    rejection_reason  required when rejected or blocked, allowed when retired, else an error
    [[sources]]       title, optional https url (a paper without one: author, title, year)
    [quality_bar]     the other seven answers (QUALITY_BAR); required unless rejected / blocked
    notes             optional: a proxy, an open decision

Whether the named presets exist is checked by ``loading.py``, which sees the store.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, NoReturn

from algotrade.config.site.fields import Table, reject_secrets
from algotrade.config.strategy.schema import Selection, parse_selection
from algotrade.core.model.errors import ConfigurationError
from algotrade.core.model.ids import validate_id

STATUSES = ("candidate", "evidenced", "live", "retired", "rejected", "blocked")
CLOSED = ("rejected", "blocked")  # kept on file with the reason; the bar is not required
OUTCOME_KINDS = ("excess_return", "hit_target")
BENCHMARKS = ("SPY", "none")
SCHEDULES = ("every_session", "month_end")
ON_EVENT = "on_event:"
# The event classes a schedule may trigger on: the stored rows that date each, and its ANCHOR
# session. The start session is S = anchor + start_offset_sessions, the outcome's horizons count
# from S's close, and the event must be known by S (``known_from <= S``, ADR 0050): the harness
# skips an event that is not, never reads it early.
EVENT_CLASSES: Mapping[str, str] = {
    "earnings": "a reported result (events/earnings); anchor: the reaction session, the first "
    "to trade after the report time (an after-close report: the next session)",
    "earnings_scheduled": "a next report date known (earnings_schedule@v1 reads SCHEDULED); "
    "anchor: the scheduled report date's session",
    "ex_dividend": "an ex-dividend date (events/dividend); anchor: the ex-date",
    "index_change": "an S&P 500 membership change (events/index_change); anchor: the session "
    "it is first stored",
    "macro_release": "a scheduled macro release (events/macro_release); anchor: the release "
    "session",
}
ANNOUNCED_AHEAD = ("earnings_scheduled", "macro_release")  # a window may start before these
# Quality bar answers 3 to 9 (1 and 2 are the document's mechanism and persistence).
# What a hit_target compares with its target over the window (ED2 stores each as a field).
MEASURES = ("excess_return", "realised_to_implied_vol")
DIRECTIONS = ("below", "above")
QUALITY_BAR = (
    "outcome",
    "trigger_timing",
    "replication",
    "expected_size",
    "capacity_costs",
    "failure_modes",
    "decoys",
)
KEYS = (
    "id", "name", "thesis", "mechanism", "persistence", "outcome", "schedule", "universe",
    "top_k", "screeners", "baselines", "status", "rejection_reason", "sources", "quality_bar",
    "notes",
)  # fmt: skip
OUTCOME_KEYS = (
    "kind", "horizon_sessions", "benchmark", "start_offset_sessions", "target", "max_drawdown",
    "cost_bps", "measure", "direction",
)  # fmt: skip
_SENTENCE_BREAK = re.compile(r"[.!?]\s+[A-Z]")


@dataclass(frozen=True)
class Outcome:
    """What counts as the edge working for one (instrument, start session S): returns from S's
    close to the close ``h`` sessions later, for each horizon ``h``; a hit_target holds when
    ``measure`` is ``direction`` the ``target`` (and the path stays within ``max_drawdown``)."""

    kind: str
    horizon_sessions: tuple[int, ...]
    benchmark: str
    start_offset_sessions: int = 0
    target: float | None = None
    max_drawdown: float | None = None
    cost_bps: float | None = None
    measure: str | None = None
    direction: str | None = None


@dataclass(frozen=True)
class Source:
    title: str
    url: str = ""


@dataclass(frozen=True)
class Edge:
    id: str
    name: str
    thesis: str
    mechanism: str
    persistence: str
    outcome: Outcome
    schedule: str
    universe: str | Selection
    top_k: int | None  # None: every qualified name
    screeners: tuple[str, ...]
    baselines: tuple[str, ...]
    status: str
    sources: tuple[Source, ...]
    quality_bar: Mapping[str, str]  # QUALITY_BAR -> answer ("" only when CLOSED)
    rejection_reason: str = ""
    notes: str = ""

    @property
    def event_class(self) -> str | None:
        """The class an ``on_event:`` schedule triggers on, else None."""
        return event_class(self.schedule)

    @property
    def answers(self) -> tuple[tuple[str, str], ...]:
        """The nine quality-bar answers in the plan's order."""
        return (
            ("mechanism", self.mechanism),
            ("persistence", self.persistence),
            *((key, self.quality_bar[key]) for key in QUALITY_BAR),
        )


def event_class(schedule: str) -> str | None:
    """The event class of an ``on_event:<class>`` schedule, else None."""
    return schedule.removeprefix(ON_EVENT) if schedule.startswith(ON_EVENT) else None


def parse_edge(doc: Mapping[str, Any], name: str, where: str) -> Edge:
    """``doc`` (the layered document of ``<name>.toml``) as an ``Edge``; ``where`` names it."""
    reject_secrets(doc, where)
    t = Table(doc, where)
    t.only(KEYS)
    edge_id = validate_id("edge", _required(t, "id"))
    if edge_id != name:
        raise ConfigurationError(f"{where} id: {edge_id!r} must equal the file name {name!r}")
    status = t.choice("status", "", STATUSES) if "status" in doc else _missing(t, "status")
    closed = status in CLOSED
    schedule = _schedule(t)
    edge = Edge(
        id=edge_id,
        name=_required(t, "name"),
        thesis=_thesis(t),
        mechanism=_answer(t, "mechanism", closed),
        persistence=_answer(t, "persistence", closed),
        outcome=_outcome(t, schedule),
        schedule=schedule,
        universe=_universe(t, edge_id),
        top_k=_top_k(t),
        screeners=_ids(t, "screeners"),
        baselines=_ids(t, "baselines"),
        status=status,
        sources=_sources(t),
        quality_bar=_quality_bar(t, closed),
        rejection_reason=_prose(t, "rejection_reason"),
        notes=_prose(t, "notes"),
    )
    if closed and not edge.rejection_reason:
        raise ConfigurationError(f"{where} rejection_reason: required when status is {status!r}")
    if edge.rejection_reason and status not in (*CLOSED, "retired"):
        raise ConfigurationError(
            f"{where} rejection_reason: only a rejected, blocked or retired edge has one"
        )
    return edge


def _missing(t: Table, key: str) -> NoReturn:
    raise ConfigurationError(f"{t.where} {key}: required")


def _prose(t: Table, key: str) -> str:
    """Optional text with its whitespace collapsed (TOML multi-line strings read as one line)."""
    return " ".join(t.text(key, "").split()) if t.raw(key) is not None else ""


def _required(t: Table, key: str) -> str:
    return _prose(t, key) or _missing(t, key)


def _answer(t: Table, key: str, closed: bool) -> str:
    return _prose(t, key) if closed else _required(t, key)


def _thesis(t: Table) -> str:
    thesis = _required(t, "thesis")
    if _SENTENCE_BREAK.search(thesis) or thesis[-1] not in ".!?":
        raise ConfigurationError(f"{t.where} thesis: expected one sentence, got {thesis!r}")
    return thesis


def _schedule(t: Table) -> str:
    schedule = _required(t, "schedule")
    if schedule in SCHEDULES or event_class(schedule) in EVENT_CLASSES:
        return schedule
    options = [*SCHEDULES, *(f"{ON_EVENT}{c}" for c in EVENT_CLASSES)]
    raise ConfigurationError(f"{t.where} schedule: expected one of {options}, got {schedule!r}")


def _outcome(t: Table, schedule: str) -> Outcome:
    if t.raw("outcome") is None:
        _missing(t, "outcome")
    o = t.table("outcome", OUTCOME_KEYS)
    kind = o.choice("kind", "", OUTCOME_KINDS) if "kind" in o.names() else _missing(o, "kind")
    benchmark = (
        o.choice("benchmark", "", BENCHMARKS)
        if "benchmark" in o.names()
        else _missing(o, "benchmark")
    )
    if kind == "excess_return" and benchmark == "none":
        raise ConfigurationError(f"{o.where} benchmark: an excess return needs SPY, not 'none'")
    horizons = _horizons(o)
    offset = o.integer("start_offset_sessions", 0)
    event = event_class(schedule)
    if offset and event is None:
        raise ConfigurationError(
            f"{o.where} start_offset_sessions: only an on_event schedule has an offset"
        )
    if offset < 0 and event not in ANNOUNCED_AHEAD:
        raise ConfigurationError(
            f"{o.where} start_offset_sessions: a window may start before the event only when "
            f"it is announced ahead ({list(ANNOUNCED_AHEAD)}); {event!r} is known when it happens"
        )
    target = o.number("target", None)
    measure = o.choice("measure", "", MEASURES) if "measure" in o.names() else None
    direction = o.choice("direction", "", DIRECTIONS) if "direction" in o.names() else None
    hit = {"target": target, "measure": measure, "direction": direction}
    for key, value in hit.items():
        if kind == "hit_target" and value is None:
            raise ConfigurationError(f"{o.where} {key}: required for a hit_target outcome")
        if kind != "hit_target" and value is not None:
            raise ConfigurationError(f"{o.where} {key}: only a hit_target outcome has one")
    drawdown = o.number("max_drawdown", None, 0)
    if drawdown is not None and not 0 < drawdown <= 1:
        raise ConfigurationError(f"{o.where} max_drawdown: expected a fraction in (0, 1]")
    return Outcome(
        kind=kind,
        horizon_sessions=horizons,
        benchmark=benchmark,
        start_offset_sessions=offset,
        target=target,
        max_drawdown=drawdown,
        cost_bps=o.number("cost_bps", None, 0),
        measure=measure,
        direction=direction,
    )


def _horizons(o: Table) -> tuple[int, ...]:
    raw = o.raw("horizon_sessions")
    numbers = isinstance(raw, list) and all(type(h) is int and h >= 1 for h in raw)
    if not numbers or not raw or raw != sorted(set(raw)):
        raise ConfigurationError(
            f"{o.where} horizon_sessions: expected one or more ascending, distinct integers "
            f">= 1, got {raw!r}"
        )
    return tuple(raw)


def _universe(t: Table, edge_id: str) -> str | Selection:
    raw = t.raw("universe")
    if isinstance(raw, str):
        return validate_id("selection", raw)
    if isinstance(raw, Mapping):
        return parse_selection({"name": edge_id, **raw}, f"{t.where} universe")
    raise ConfigurationError(
        f"{t.where} universe: expected a selection preset name or an inline selection "
        f"([universe] where = ...), got {raw!r}"
    )


def _top_k(t: Table) -> int | None:
    raw = t.raw("top_k")
    if raw == "all":
        return None
    if type(raw) is int and raw >= 1:
        return raw
    raise ConfigurationError(f"{t.where} top_k: expected an integer >= 1 or 'all', got {raw!r}")


def _ids(t: Table, key: str) -> tuple[str, ...]:
    found = tuple(validate_id("screener", s) for s in t.strings(key, ()))
    if len(set(found)) != len(found):
        raise ConfigurationError(f"{t.where} {key}: a screener is listed twice: {list(found)}")
    return found


def _sources(t: Table) -> tuple[Source, ...]:
    raw = t.raw("sources")
    if not isinstance(raw, list) or not raw or not all(isinstance(s, Mapping) for s in raw):
        raise ConfigurationError(f"{t.where} sources: expected one or more [[sources]] tables")
    found = []
    for i, item in enumerate(raw):
        s = Table(item, f"{t.where} [[sources]][{i}]")
        s.only(("title", "url"))
        url = _prose(s, "url")
        if url and not url.startswith("https://"):
            raise ConfigurationError(f"{s.where} url: expected an https:// address, got {url!r}")
        found.append(Source(title=_required(s, "title"), url=url))
    return tuple(found)


def _quality_bar(t: Table, closed: bool) -> dict[str, str]:
    if t.raw("quality_bar") is None and not closed:
        _missing(t, "quality_bar")
    bar = t.table("quality_bar", QUALITY_BAR)
    return {key: _answer(bar, key, closed) for key in QUALITY_BAR}
