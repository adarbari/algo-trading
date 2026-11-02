"""What one edge evaluation evaluates (ADR 0053, ADR 0074, ADR 0088 G19): the variants (screeners,
baselines, position baselines, an ensemble), the scopes (the edge itself and each of its
``[[variants]]``, with the borrow rate made explicit and the implied-vol field each reads), the
universe of a scope, the event names by decision session of the scopes with an event schedule,
and the licence of an implied-vol field."""

from collections.abc import Sequence
from dataclasses import replace
from datetime import date
from functools import partial

from algotrade.config.edges.document import MAIN, PAIR_KIND, Edge, Outcome
from algotrade.config.edges.identity import LONG
from algotrade.config.edges.named import TIME_SERIES
from algotrade.config.edges.portfolio import ENSEMBLE
from algotrade.config.edges.positions.templates import POSITION_PREFIX, load_templates
from algotrade.config.strategy.schema import Selection, parse_selection
from algotrade.config.user import UserContext
from algotrade.core.model.errors import ConfigurationError
from algotrade.data import StoreReader
from algotrade.services.configs import resolve_config
from algotrade.services.evaluation.cross_section.baselines.variant import Variant, _Scope
from algotrade.services.evaluation.cross_section.events import EventSchedule, read_events_for
from algotrade.services.evaluation.cross_section.hit import IMPLIED_VOL_FIELD
from algotrade.services.evaluation.cross_section.measures import BASELINE, MEMBER, SCREENER
from algotrade.services.evaluation.cross_section.reads.session import SessionReads
from algotrade.services.features import catalogue
from algotrade.storage.configs.store import ConfigStore

# The one fixed implied-vol field of a run is never a field mixing sources by name or by rule.
MIXED_SOURCE_IV = ("feature.vrp_iv30",)
SELECTIONS = "selections"


def edge_variants(configs: ConfigStore, user: UserContext, edge: Edge) -> list[Variant]:
    """The screeners, the baselines and, for an ``[ensemble]``, the combined variant (ADR 0074):
    its grid's screeners are ``member``s (reported, never a trial nor a basis) and the ensemble
    itself the one trial, counted once whatever the grid's size."""
    found = [
        *(
            Variant(s, MEMBER if s in edge.ensemble else SCREENER, resolve_config(configs, s, user))
            for s in edge.screeners
        ),
        *(Variant(s, BASELINE, resolve_config(configs, s, user)) for s in edge.baselines),
    ]
    if edge.position_baselines:  # the setup's own picks, valued as another position (G19)
        own = next((v for v in found if v.role == SCREENER), found[0] if found else None)
        if own is None:
            raise ConfigurationError(f"edge {edge.id}: a position baseline needs a screener")
        found += [
            Variant(f"{POSITION_PREFIX}{t}", BASELINE, own.config, position=t)
            for t in edge.position_baselines
        ]
    if edge.ensemble:
        members = tuple(v for v in found if v.role == MEMBER)
        found.append(Variant(ENSEMBLE, SCREENER, members[0].config, members))
    if not found:
        raise ConfigurationError(f"edge {edge.id}: no screeners or baselines to evaluate")
    return found


def screen_uses(configs: ConfigStore, edges: Sequence[Edge]) -> list[tuple[str, str]]:
    """The (owner, config hash) of every screener and baseline the ``edges`` score, one pair
    per use: what ``shared_screens`` counts to choose the screens worth caching for a run."""
    uses: list[tuple[str, str]] = []
    for edge in edges:
        if edge.base in TIME_SERIES:
            continue  # measured by time_series/, no screener runs
        try:
            found = edge_variants(configs, UserContext(edge.owner), edge)
        except ConfigurationError:
            continue  # the run of that edge reports it
        uses.extend((edge.owner, v.config.hash) for v in found if not v.members)
    return uses


def edge_universe(configs: ConfigStore, user: UserContext, edge: Edge) -> Selection:
    if isinstance(edge.universe, Selection):
        return edge.universe
    for scope in (user.user_id, "site"):
        doc = configs.load(scope, SELECTIONS, edge.universe)
        if doc is not None:
            return parse_selection(doc, f"{scope}/{SELECTIONS}/{edge.universe}")
    raise ConfigurationError(f"edge {edge.id}: unknown selection {edge.universe!r}")


def iv_field_of(edge: Edge, run_field: str = IMPLIED_VOL_FIELD) -> str:
    """The implied-vol field an edge's outcome reads: its own ``iv_field``, else the run's."""
    return edge.outcome.iv_field or run_field


def edge_scopes(
    configs: ConfigStore, user: UserContext, edge: Edge, iv_field: str, borrow: float
) -> list[_Scope]:
    """The edge itself (``main``), then each of its ``[[variants]]`` with its overrides. Each
    reads one implied-vol field: its outcome's ``iv_field``, else the run's; ``borrow``: the
    site's default borrow rate (``verdict.toml``), for a short leg without its own."""
    edge = replace(edge, outcome=_borrowing(edge.outcome, borrow))
    templates = load_templates(configs) if edge.position_baselines else {}
    scopes = [
        _Scope(
            MAIN,
            edge,
            edge_universe(configs, user, edge),
            iv_field_of(edge, iv_field),
            (),
            templates,
        )
    ]
    for v in edge.variants:
        base, picks = v.base or edge.base, v.picks or edge.picks
        applied = replace(
            edge,
            outcome=_borrowing(v.outcome, borrow),
            universe=v.universe,
            base=base,
            picks=picks,
            variants=(),
        )
        field_name = v.outcome.iv_field or iv_field
        marks = (f"base={base}", f"picks={picks}") if v.base or v.picks else ()
        scopes.append(
            _Scope(
                v.id, applied, edge_universe(configs, user, applied), field_name, marks, templates
            )
        )
    return scopes


def _borrowing(outcome: Outcome, site_default: float) -> Outcome:
    """``outcome`` with the borrow rate its short leg pays made explicit (its own, else the site's
    ``verdict.toml`` default), so the trial hash and the values see one number; a long outcome has
    no short leg and is returned as it is (a pair spread's short leg is the sibling)."""
    if outcome.borrow_bps_annual is not None or (
        outcome.side == LONG and outcome.kind != PAIR_KIND
    ):
        return outcome
    return replace(outcome, borrow_bps_annual=site_default)


def event_schedules(
    reader: StoreReader, session: SessionReads, scopes: Sequence[_Scope], days: Sequence[date]
) -> dict[str, EventSchedule]:
    """The event names by decision session of each scope with an event schedule (by scope key;
    the others are absent). Scopes with the same event class, subtype and offset share one read of
    the event fields."""
    groups: dict[tuple[str, str | None, int], list[_Scope]] = {}
    for scope in scopes:
        if scope.edge.event_class is not None:
            key = (
                scope.edge.event_class,
                scope.edge.event_subtype,
                scope.edge.outcome.start_offset_sessions,
            )
            groups.setdefault(key, []).append(scope)
    found: dict[str, EventSchedule] = {}
    for (cls, subtype, offset), members in groups.items():
        found.update(
            read_events_for(
                reader,
                cls,
                offset,
                days,
                {m.key: partial(session.eligible, m.universe) for m in members},
                subtype,
            )
        )
    return found


def iv_licence(configs: ConfigStore, user: UserContext, iv_field: str) -> str:
    """The catalogue licence of ``iv_field`` (a stored rollup column or an expression feature)."""
    found = catalogue(configs, user.user_id).feature(iv_field)
    if found is None:
        raise ConfigurationError(f"iv_field {iv_field!r} is not a catalogue feature")
    return str(found.licence)
