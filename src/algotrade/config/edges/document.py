"""The edge document (ADR 0053 decision 1; the quality bar is docs/edges-plan.md): one
``config/site/edges/<id>.toml`` typed into a frozen ``Edge``, fail closed: an unknown key, a
wrong type, an unknown status, schedule or event class, or a missing answer fails with the file
and the key.

    id, name          the file's stem (an id), the name on screen
    thesis            one sentence: what is mispriced, and which way
    mechanism         quality bar 1: who is forced, constrained or systematically wrong
    persistence       quality bar 2: why it survives being known
    [outcome]         kind (``excess_return`` | ``hit_target``), horizon_sessions (one or more),
                      benchmark (``SPY`` | ``none``), start_offset_sessions (the entry session S:
                      D + this for every_session / month_end, D the decision session, so at
                      least 1; for an event schedule the event's anchor session + this, D = S - 1;
                      <= 0 only for an event announced ahead), optional target, max_drawdown (a
                      fraction), cost_bps; a hit_target also names its measure (MEASURES) and
                      direction (``below`` | ``above``); an ``expires_otm`` outcome (the short
                      option is not assigned at the horizon's close: put | call | strangle) names
                      its ``structure``, exactly one of ``strike_delta`` (a delta in (0, 1)) and
                      ``otm_pct`` (a fraction in (0, 1)) and the ``iv_field`` it reads at D;
                      ``iv_field`` is allowed on a ratio measure too (default: the run's)
    schedule          ``every_session`` | ``month_end`` | ``on_event:<class>`` (EVENT_CLASSES)
    base              what the picks are compared with: ``event`` (the names with the event at
                      D; default for an event schedule) | ``universe`` (every eligible name)
    [[variants]]      id, optional [variants.outcome] and universe overriding the edge's: each
                      is another evaluation of the same edge, one trial in the deflated Sharpe
                      ratio (ADR 0053 amendment 2026-10-08; the id ``main`` is the edge itself)
    universe          a selection preset name, or an inline selection (``[universe] where``)
    top_k             an integer >= 1, or ``"all"`` (every qualified name)
    screeners         the screener presets that implement it (empty while a candidate waits)
    baselines         screener presets run on the same sessions (quality bar 9)
    status            candidate | evidenced | live | retired | rejected | blocked
    frozen_from       optional date: the harness reports sessions from it on their own as the
                      frozen period (fixed once chosen, never rolling; none: no frozen slice)
    [evidence]        run_id and split_from of the run an evidenced or live edge rests on; its
                      split_from must equal frozen_from (ADR 0053 amendment, ED5a)
    rejection_reason  required when rejected or blocked, allowed when retired, else an error
    [[sources]]       title, optional https url (a paper without one: author, title, year)
    [quality_bar]     the other seven answers (QUALITY_BAR); required unless rejected / blocked
    notes             optional: a proxy, an open decision
    [implementation]  optional: ``promoted``, the one of ``screeners`` that implements the edge
                      for use (ED7c). A learned (``impl = "model"``) screener is promoted only
                      with evidence that it beat the edge's rule screeners in the frozen
                      period: ``tests/architecture/data/test_edge_promotion.py``
    [scorer]          optional: ``features``, the selection fields (``rollup.<group>@v<n>.<column>``
                      or ``feature.<name>``) a learned scorer is fitted on (ED7)

Whether the named presets exist is checked by ``loading.py``, which sees the store.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any, NoReturn

from algotrade.config.site.fields import Table, reject_secrets
from algotrade.config.strategy.schema import Selection, parse_selection
from algotrade.core.model.errors import ConfigurationError
from algotrade.core.model.ids import validate_id

STATUSES = ("candidate", "evidenced", "live", "retired", "rejected", "blocked")
CLOSED = ("rejected", "blocked")  # kept on file with the reason; the bar is not required
OUTCOME_KINDS = ("excess_return", "hit_target", "expires_otm")
STRUCTURES = ("put", "call", "strangle")  # an expires_otm outcome's short option(s)
BENCHMARKS = ("SPY", "none")
SCHEDULES = ("every_session", "month_end")
BASES = ("event", "universe")
MAIN = "main"  # the edge itself, as the key of a results row (a variant has its own id)
ON_EVENT = "on_event:"
# The event classes a schedule may trigger on, and its ANCHOR session. The entry session is
# S = anchor + start_offset_sessions, the decision session D = S - 1, the outcome's horizons
# count from S's close, and the event must be known by D (``known_from <= D``, ADR 0050): the
# harness skips an event that is not, never reads it early (``cross_section/events.py`` names
# the stored field each class is read from).
EVENT_CLASSES: Mapping[str, str] = {
    "earnings_reaction": "a reported result's two-session reaction (earnings_reaction@v1); "
    "anchor: the reaction's last session, E+1 (E: the report date)",
    "earnings_expected": "a next report expected, scheduled or from the year-ago report "
    "(earnings_expected@v1); anchor: the expected report date's session",
    "ex_dividend": "an ex-dividend date (events/dividend); anchor: the ex-date",
    "index_change": "an S&P 500 membership change (events/index_change); anchor: the session "
    "it is first stored",
    "macro_release": "a scheduled macro release (events/macro_release); anchor: the release "
    "session",
}
ANNOUNCED_AHEAD = ("earnings_expected", "macro_release")  # an entry may precede these
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
    "notes", "frozen_from", "base", "variants", "evidence", "scorer", "implementation",
)  # fmt: skip
OUTCOME_KEYS = (
    "kind", "horizon_sessions", "benchmark", "start_offset_sessions", "target", "max_drawdown",
    "cost_bps", "measure", "direction", "structure", "strike_delta", "otm_pct", "iv_field",
)  # fmt: skip
SHARED_KEYS = ("horizon_sessions", "benchmark", "start_offset_sessions", "iv_field")
VARIANT_KEYS = ("id", "outcome", "universe")
EVIDENCE_KEYS = ("run_id", "split_from")
EVIDENCE_STATUSES = ("evidenced", "live", "retired")
_SENTENCE_BREAK = re.compile(r"[.!?]\s+[A-Z]")


@dataclass(frozen=True)
class Outcome:
    """What counts as the edge working for one (instrument, entry session S): returns from S's
    close to the close ``h`` sessions later, for each horizon ``h``; a hit_target holds when
    ``measure`` is ``direction`` the ``target`` (and the path stays within ``max_drawdown``).
    ``start_offset_sessions``: S = D + it (D: the decision session), or for an event schedule
    the event's anchor + it."""

    kind: str
    horizon_sessions: tuple[int, ...]
    benchmark: str
    start_offset_sessions: int = 0
    target: float | None = None
    max_drawdown: float | None = None
    cost_bps: float | None = None
    measure: str | None = None
    direction: str | None = None
    structure: str | None = None
    strike_delta: float | None = None
    otm_pct: float | None = None
    iv_field: str | None = None


@dataclass(frozen=True)
class EdgeVariant:
    """One more evaluation of an edge (ADR 0053 amendment 2026-10-08): the edge's outcome and
    universe with this variant's overrides applied. Each is a trial of the deflated Sharpe ratio."""

    id: str
    outcome: Outcome
    universe: str | Selection


@dataclass(frozen=True)
class Evidence:
    """The harness run an evidenced or live edge cites (ADR 0053 amendment, ED5a): its record id
    and the split it was measured at, which must be the document's ``frozen_from``."""

    run_id: str
    split_from: date


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
    frozen_from: date | None = None
    base: str = "universe"  # what the picks are compared with: the event's names | the universe
    variants: tuple[EdgeVariant, ...] = ()
    scorer_features: tuple[str, ...] = ()  # the fields a learned scorer reads (ADR 0053, ED7)
    evidence: Evidence | None = None
    promoted: str | None = None  # the screener that implements the edge for use (ED7c)

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


def job_name(edge_id: str, user_id: str) -> str:
    """The run-record ``job`` whose records hold one user's trial log of an edge (ADR 0015):
    written by the harness, read by the read model."""
    return f"edge-eval:{edge_id}:{user_id}"


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
    outcome = _outcome(t, schedule)
    universe = _universe(t, edge_id)
    edge = Edge(
        id=edge_id,
        name=_required(t, "name"),
        thesis=_thesis(t),
        mechanism=_answer(t, "mechanism", closed),
        persistence=_answer(t, "persistence", closed),
        outcome=outcome,
        schedule=schedule,
        universe=universe,
        top_k=_top_k(t),
        screeners=_ids(t, "screeners"),
        baselines=_ids(t, "baselines"),
        status=status,
        sources=_sources(t),
        quality_bar=_quality_bar(t, closed),
        rejection_reason=_prose(t, "rejection_reason"),
        notes=_prose(t, "notes"),
        frozen_from=_frozen_from(t),
        base=_base(t, schedule),
        variants=_variants(t, schedule, edge_id, universe),
        scorer_features=_scorer_features(t),
        evidence=_evidence(t),
        promoted=_promoted(t),
    )
    if edge.promoted is not None and edge.promoted not in edge.screeners:
        raise ConfigurationError(
            f"{where} implementation.promoted: {edge.promoted!r} is not one of the screeners "
            f"{list(edge.screeners)}"
        )
    if edge.evidence is not None and status not in EVIDENCE_STATUSES:
        raise ConfigurationError(
            f"{where} evidence: only an evidenced, live or retired edge cites a run"
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


def _evidence(t: Table) -> Evidence | None:
    if t.raw("evidence") is None:
        return None
    sub = t.table("evidence", EVIDENCE_KEYS)
    run_id, split = sub.text("run_id", ""), sub.raw("split_from")
    if not run_id or split is None:
        raise ConfigurationError(f"{sub.where}: run_id and split_from are both required")
    return Evidence(run_id, _date(sub, "split_from", split))


def _frozen_from(t: Table) -> date | None:
    raw = t.raw("frozen_from")
    return None if raw is None else _date(t, "frozen_from", raw)


def _date(t: Table, key: str, raw: Any) -> date:
    if type(raw) is date:
        return raw
    try:
        if isinstance(raw, str):
            return date.fromisoformat(raw)
    except ValueError:
        pass
    raise ConfigurationError(f"{t.where} {key}: expected a date (2026-04-01), got {raw!r}")


def _schedule(t: Table) -> str:
    schedule = _required(t, "schedule")
    if schedule in SCHEDULES or event_class(schedule) in EVENT_CLASSES:
        return schedule
    options = [*SCHEDULES, *(f"{ON_EVENT}{c}" for c in EVENT_CLASSES)]
    raise ConfigurationError(f"{t.where} schedule: expected one of {options}, got {schedule!r}")


def _base(t: Table, schedule: str) -> str:
    event = event_class(schedule) is not None
    base = (
        t.choice("base", "", BASES) if "base" in t.names() else ("event" if event else "universe")
    )
    if base == "event" and not event:
        raise ConfigurationError(f"{t.where} base: 'event' needs an on_event schedule")
    return base


def _outcome(t: Table, schedule: str) -> Outcome:
    if t.raw("outcome") is None:
        _missing(t, "outcome")
    return _outcome_of(t.table("outcome", OUTCOME_KEYS), schedule)


def _outcome_of(o: Table, schedule: str) -> Outcome:
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
    if event is None and offset < 1:
        raise ConfigurationError(
            f"{o.where} start_offset_sessions: the screen runs after the decision session's "
            f"close, so the entry session is at least 1 session later (>= 1), got {offset}"
        )
    if event is not None and offset < 1 and event not in ANNOUNCED_AHEAD:
        raise ConfigurationError(
            f"{o.where} start_offset_sessions: an entry before the event needs it announced "
            f"ahead ({list(ANNOUNCED_AHEAD)}); {event!r} is known when it happens, so the "
            f"offset from its anchor is >= 1, got {offset}"
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
    structure, strike_delta, otm_pct, iv_field = _expires_otm(o, kind)
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
        structure=structure,
        strike_delta=strike_delta,
        otm_pct=otm_pct,
        iv_field=iv_field,
    )


def _expires_otm(o: Table, kind: str) -> tuple[str | None, float | None, float | None, str | None]:
    """``(structure, strike_delta, otm_pct, iv_field)`` of an outcome: the first three only for
    ``expires_otm`` (exactly one of the two strikes; the implied vol field is required there)."""
    names = o.names()
    structure = o.choice("structure", "", STRUCTURES) if "structure" in names else None
    delta, pct = o.number("strike_delta", None), o.number("otm_pct", None)
    iv_field = _prose(o, "iv_field") or None
    if kind != "expires_otm":
        for key, value in (("structure", structure), ("strike_delta", delta), ("otm_pct", pct)):
            if value is not None:
                raise ConfigurationError(f"{o.where} {key}: only an expires_otm outcome has one")
        return None, None, None, iv_field
    if structure is None:
        _missing(o, "structure")
    if (delta is None) == (pct is None):
        raise ConfigurationError(
            f"{o.where}: an expires_otm outcome names exactly one of strike_delta and otm_pct"
        )
    for key, value in (("strike_delta", delta), ("otm_pct", pct)):
        if value is not None and not 0 < value < 1:
            raise ConfigurationError(f"{o.where} {key}: expected a fraction in (0, 1), got {value}")
    if iv_field is None:
        raise ConfigurationError(f"{o.where} iv_field: required for an expires_otm outcome")
    return structure, delta, pct, iv_field


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


def _variants(
    t: Table, schedule: str, edge_id: str, universe: str | Selection
) -> tuple[EdgeVariant, ...]:
    raw = t.raw("variants")
    if raw is None:
        return ()
    if not isinstance(raw, list) or not all(isinstance(v, Mapping) for v in raw):
        raise ConfigurationError(f"{t.where} variants: expected [[variants]] tables")
    base = t.raw("outcome") or {}
    found: list[EdgeVariant] = []
    for i, item in enumerate(raw):
        v = Table(item, f"{t.where} [[variants]][{i}]")
        v.only(VARIANT_KEYS)
        vid = validate_id("variant", _required(v, "id"))
        if vid == MAIN or vid in {x.id for x in found}:
            raise ConfigurationError(f"{v.where} id: {vid!r} is reserved or listed twice")
        over = v.table("outcome", OUTCOME_KEYS)
        kept = (
            base
            if "kind" not in over.names() or over.raw("kind") == base.get("kind")
            else {k: x for k, x in base.items() if k in SHARED_KEYS}
        )  # a variant of another kind drops the base's kind-specific keys
        merged = Table({**kept, **{k: over.raw(k) for k in over.names()}}, f"{v.where} outcome")
        found.append(
            EdgeVariant(
                id=vid,
                outcome=_outcome_of(merged, schedule),
                universe=_universe(v, f"{edge_id}-{vid}") if "universe" in v.names() else universe,
            )
        )
    return tuple(found)


def _top_k(t: Table) -> int | None:
    raw = t.raw("top_k")
    if raw == "all":
        return None
    if type(raw) is int and raw >= 1:
        return raw
    raise ConfigurationError(f"{t.where} top_k: expected an integer >= 1 or 'all', got {raw!r}")


def _scorer_features(t: Table) -> tuple[str, ...]:
    if t.raw("scorer") is None:
        return ()
    found = t.table("scorer", ("features",)).strings("features", ())
    if not found or len(set(found)) != len(found):
        raise ConfigurationError(f"{t.where} scorer.features: one or more distinct fields")
    return found


def _promoted(t: Table) -> str | None:
    if t.raw("implementation") is None:
        return None
    sub = t.table("implementation", ("promoted",))
    return validate_id("screener", sub.text("promoted", "") or _missing(sub, "promoted"))


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
