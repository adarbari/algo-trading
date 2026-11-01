"""``Template``: a position as a list of legs (ADR 0088, design 2.4), from
``config/site/positions/templates.toml``, typed fail closed. A leg is shares (a signed quantity)
or one option chosen at entry from a session's chain by a strike rule (``delta``, ``atm`` or
``otm_pct``; never a target yield). A template adds the collateral its return is measured on.
``position_of`` names the templates of an outcome, so the read model and the trade contract share
one vocabulary for share and option setups."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from algotrade.config.edges.identity import LONG, LONG_SHORT, SHORT
from algotrade.config.site.fields import Table
from algotrade.core.model.errors import ConfigurationError
from algotrade.core.model.ids import validate_id

KIND = "positions"
NAME = "templates"
WHERE = "config/site/positions/templates.toml"
SHARES, OPTION = "shares", "option"
LEG_KINDS = (SHARES, OPTION)
RIGHTS = ("P", "C")
STRIKE_RULES = ("delta", "atm", "otm_pct")  # a target yield is refused (design 2.4)
COLLATERALS = ("notional", "cash_secured", "max_loss", "regt")
LEG_KEYS = ("kind", "qty", "right", "strike", "delta", "otm_pct", "tenor_days")
RETURN_KINDS = ("excess_return", "hit_target")  # outcomes whose position is shares, by side
MAX_QTY = 1000
POSITION_PREFIX = "position:"  # in ``baselines``: the setup's own picks valued with a template
SIDE_TEMPLATES = {LONG: ("long_shares",), SHORT: ("short_shares",),
                   LONG_SHORT: ("long_shares", "short_shares")}  # fmt: skip


class Documents(Protocol):
    """What the loader needs from a config store (``ConfigStore``)."""

    def load(self, scope: str, kind: str, name: str) -> Mapping[str, Any] | None: ...


@dataclass(frozen=True)
class Leg:
    kind: str
    qty: int
    right: str | None = None
    strike: str | None = None
    delta: float | None = None
    otm_pct: float | None = None
    tenor_days: int | None = None  # an option leg's own tenor (None: the outcome's)


@dataclass(frozen=True)
class Template:
    id: str
    legs: tuple[Leg, ...]
    collateral: str

    @property
    def has_option(self) -> bool:
        return any(leg.kind == OPTION for leg in self.legs)

    @property
    def share_only(self) -> bool:
        return not self.has_option


Templates = Mapping[str, Template]


def _leg(t: Table) -> Leg:
    kind = t.choice("kind", "", LEG_KINDS) if "kind" in t.names() else _missing(t, "kind")
    qty = t.integer("qty", 0)
    if qty == 0 or abs(qty) > MAX_QTY:
        raise ConfigurationError(f"{t.where} qty: a signed integer, not 0, up to {MAX_QTY}")
    if kind == SHARES:
        extra = [k for k in LEG_KEYS[2:] if k in t.names()]
        if extra:
            raise ConfigurationError(f"{t.where}: a shares leg has no {extra}")
        return Leg(kind, qty)
    if "strike" in t.names() and t.raw("strike") == "yield":
        raise ConfigurationError(
            f"{t.where} strike: there is no target-yield strike rule, use one of {STRIKE_RULES}"
        )
    strike = (
        t.choice("strike", "", STRIKE_RULES) if "strike" in t.names() else _missing(t, "strike")
    )
    right = t.choice("right", "", RIGHTS) if "right" in t.names() else _missing(t, "right")
    delta, pct = t.number("delta", None), t.number("otm_pct", None)
    if (strike == "delta") != (delta is not None) or (strike == "otm_pct") != (pct is not None):
        raise ConfigurationError(
            f"{t.where}: strike {strike!r} takes exactly its own value (delta, otm_pct; atm none)"
        )
    for key, value in (("delta", delta), ("otm_pct", pct)):
        if value is not None and not 0 < value < 1:
            raise ConfigurationError(f"{t.where} {key}: expected a fraction in (0, 1), got {value}")
    tenor = t.integer("tenor_days", 0, 0) or None
    return Leg(kind, qty, right, strike, delta, pct, tenor)


def _missing(t: Table, key: str) -> Any:
    raise ConfigurationError(f"{t.where} {key}: required")


def _template(t: Table) -> Template:
    t.only(("id", "legs", "collateral"))
    tid = validate_id("position", t.text("id", ""))
    raw = t.raw("legs")
    if not isinstance(raw, list) or not raw or not all(isinstance(x, Mapping) for x in raw):
        raise ConfigurationError(f"{t.where} legs: expected one or more leg tables")
    legs = tuple(_leg(_sub(t, f"legs[{i}]", leg)) for i, leg in enumerate(raw))
    collateral = t.choice("collateral", "", COLLATERALS)
    template = Template(tid, legs, collateral)
    shares = any(leg.kind == SHARES for leg in legs)
    if shares != (collateral == "notional") or (collateral == "max_loss" and len(legs) < 2):
        raise ConfigurationError(
            f"{t.where} collateral: {collateral!r} does not fit these legs (a position with a "
            f"share leg is 'notional'; an option-only one is 'cash_secured', 'max_loss' (two "
            f"legs or more) or 'regt')"
        )
    return template


def _sub(t: Table, label: str, raw: Mapping[str, Any]) -> Table:
    leg = Table(raw, f"{t.where}.{label}")
    leg.only(LEG_KEYS)
    return leg


def parse_templates(doc: Mapping[str, Any] | None, where: str = WHERE) -> Templates:
    """The ``[[template]]`` tables, typed; ids are distinct (a missing document: no templates)."""
    t = Table(doc, where)
    t.only(("template",))
    found: dict[str, Template] = {}
    for item in t.tables("template"):
        template = _template(item)
        if template.id in found:
            raise ConfigurationError(f"{where}: template {template.id!r} is listed twice")
        found[template.id] = template
    return found


def load_templates(configs: Documents) -> Templates:
    return parse_templates(configs.load("site", KIND, NAME))


def check_known(where: str, key: str, ids: tuple[str, ...], templates: Templates) -> None:
    """Every id in ``ids`` names a template of the site."""
    unknown = [i for i in ids if i not in templates]
    if unknown:
        raise ConfigurationError(
            f"{where} {key}: no position template named {unknown} (known: {sorted(templates)})"
        )


def position_of(outcome: Any) -> tuple[str, ...] | None:
    """The template ids an outcome holds: its ``position`` when set (one), else for a return
    outcome the template of its ``side`` (``long_shares``, ``short_shares``, or one of each for
    a ``long_short`` book). None for a shape that is not one position (``pair_spread``,
    ``portfolio_return``, and the older option kinds with a ``structure``)."""
    named = getattr(outcome, "position", None)
    if named is not None:
        return (named.template,)
    if outcome.kind in RETURN_KINDS and outcome.structure is None:
        return SIDE_TEMPLATES[outcome.side]
    return None


def baseline_template(entry: str) -> str:
    """The template id of a ``position:<id>`` baselines entry."""
    return validate_id("position", entry.removeprefix(POSITION_PREFIX))
