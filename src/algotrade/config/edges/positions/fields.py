"""``POSITION_FIELDS``: the facts that exist only while a trade is open (ADR 0088, design 2.4a),
named ``position.<name>`` and readable only by a rule at the ``exit`` site. Declared once here
(name, type, unit, which positions each applies to, the Guide term that explains it); the engine
that computes them at each close is ``engines/structures`` (E3b) and the catalogue takes them from
``fields_for`` per template, so a field that does not apply to the template's legs is refused."""

from collections.abc import Mapping
from dataclasses import dataclass

from algotrade.config.edges.positions.templates import SHARES, Template
from algotrade.core.model.fields import position_field

BOTH, OPTION, CREDIT = "both", "option", "credit"  # the positions a field applies to


@dataclass(frozen=True)
class PositionField:
    name: str
    type: str
    unit: str
    applies: str  # BOTH (any position) | OPTION (an option leg) | CREDIT (a net credit position)
    guide: str  # the glossary term that explains it


POSITION_FIELDS: tuple[PositionField, ...] = (
    PositionField("days_held", "int", "sessions", BOTH, "position_days_held"),
    PositionField("move_since_entry_pct", "float", "fraction", BOTH, "position_move_since_entry"),
    PositionField(
        "profit_share_of_credit", "float", "share of credit", CREDIT, "position_profit_share"
    ),
    PositionField(
        "mark_loss_share_of_collateral", "float", "share of collateral", OPTION,
        "position_mark_loss_share",
    ),
    PositionField("position_delta", "float", "delta", OPTION, "position_delta"),
    PositionField(
        "distance_to_strike_pct", "float", "fraction", OPTION, "position_distance_to_strike"
    ),
    PositionField("dte", "int", "calendar days", OPTION, "position_dte"),
)  # fmt: skip
BY_NAME: Mapping[str, PositionField] = {f.name: f for f in POSITION_FIELDS}


def _closeness(leg_strike: str, delta: float | None, otm_pct: float | None) -> float:
    """How near the money a leg's strike rule puts it (higher: nearer; ``atm`` is 0.5, a delta
    is itself, ``otm_pct`` p is 0.5 - p): an ordering of declared rules, not a price."""
    if leg_strike == "atm":
        return 0.5
    return delta if delta is not None else 0.5 - (otm_pct or 0.0)


def is_credit(template: Template) -> bool:
    """A net-credit position: its leg nearest the money is short (a short put, a put spread, a
    short straddle, an iron fly, a covered call's call). The engine reads the realised credit;
    this decides only whether ``profit_share_of_credit`` may be named."""
    options = [leg for leg in template.legs if leg.kind != SHARES]
    if not options:
        return False
    nearest = max(options, key=lambda leg: _closeness(leg.strike or "", leg.delta, leg.otm_pct))
    return nearest.qty < 0


def applies_to(field: PositionField, template: Template) -> bool:
    return {
        BOTH: True,
        OPTION: template.has_option,
        CREDIT: template.has_option and is_credit(template),
    }[field.applies]


def fields_for(template: Template) -> dict[str, str]:
    """``position.<name>`` -> type of the fields that apply to ``template``'s legs."""
    return {position_field(f.name): f.type for f in POSITION_FIELDS if applies_to(f, template)}
