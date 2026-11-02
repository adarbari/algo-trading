"""``PORTFOLIO_FIELDS``: the facts of a setup's own book of open trades at a decision session
(ADR 0088, design 2.15, G15), named ``portfolio.<name>`` and readable by a rule at the ``gate``,
``entry`` and ``case`` sites (the ``portfolio`` row of ``LEVELS``). Declared once here (name, type,
unit, which positions each applies to, the Guide term that explains it); the provider that computes
them is ``services/evaluation/portfolio_level``. Every position counts equally: no size and no
account profile exists (ADR 0083), and no field reads real holdings."""

from collections.abc import Mapping
from dataclasses import dataclass

from algotrade.config.edges.positions.fields import BOTH, OPTION, PositionField, applies_to
from algotrade.config.edges.positions.templates import Template
from algotrade.core.model.fields import portfolio_field


@dataclass(frozen=True)
class PortfolioField:
    name: str
    type: str
    unit: str
    applies: str  # BOTH (any position) | OPTION (an option setup's book only)
    guide: str  # the glossary term that explains it


PORTFOLIO_FIELDS: tuple[PortfolioField, ...] = (
    PortfolioField("open_positions", "int", "trades", BOTH, "portfolio_open_positions"),
    PortfolioField("effective_bets", "float", "bets", BOTH, "portfolio_effective_bets"),
    PortfolioField("max_sector_share", "float", "fraction", BOTH, "portfolio_max_sector_share"),
    PortfolioField("max_name_share", "float", "fraction", BOTH, "portfolio_max_name_share"),
    PortfolioField("open_collateral", "float", "dollars", OPTION, "portfolio_open_collateral"),
)  # fmt: skip
BY_NAME: Mapping[str, PortfolioField] = {f.name: f for f in PORTFOLIO_FIELDS}


def fields_for(template: Template) -> dict[str, str]:
    """``portfolio.<name>`` -> type of the fields that apply to a book of ``template`` trades."""
    return {
        portfolio_field(f.name): f.type
        for f in PORTFOLIO_FIELDS
        if applies_to(PositionField(f.name, f.type, f.unit, f.applies, f.guide), template)
    }
