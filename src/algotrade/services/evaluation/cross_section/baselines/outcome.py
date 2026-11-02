"""The outcome a ``position:<template>`` baseline values the setup's own picks with (ADR 0088,
G19; design 2.7). A shares template is a return outcome of its side on the stock grain: the
setup's own measure (excess return) when the setup has a benchmark, else the raw return
(``benchmark = "none"``: an option setup's value is a return on the spot, so the stock alone is
the raw return over the same window). The picks are the setup's own, so the shares are of its own
side (a long setup's picks are held as ``long_shares``). An option template is the setup's
``option_pnl`` outcome with that template's legs on the chain grain; it keeps the entry, tenor and
cycle of the setup but none of its exits or cases, which are the setup's own."""

from dataclasses import replace

from algotrade.config.edges.document import Outcome
from algotrade.config.edges.positions.key import with_template
from algotrade.config.edges.positions.templates import SIDE_TEMPLATES, Templates
from algotrade.core.model.errors import ConfigurationError
from algotrade.services.evaluation.cross_section.hit import RAW_RETURN

CHAIN_KIND = "option_pnl"
RETURN_KIND = "excess_return"
SHARE_SIDES = {ids[0]: side for side, ids in SIDE_TEMPLATES.items() if len(ids) == 1}


def position_outcome(outcome: Outcome, template_id: str, templates: Templates) -> Outcome:
    """``outcome`` with the position of ``template_id``: what a baseline of that template is
    valued by, over the same horizons, entry offset and costs."""
    template = templates.get(template_id)
    if template is None:
        raise ConfigurationError(f"position:{template_id}: no such position template")
    if not template.has_option:
        side = SHARE_SIDES.get(template_id)
        if side != outcome.side:  # the picks are the setup's own, so its own side
            raise ConfigurationError(
                f"position:{template_id}: the picks are the setup's own ({outcome.side}), so "
                f"they are held as that side's shares only"
            )
        return replace(
            outcome,
            kind=RETURN_KIND,
            side=side,
            position=None,
            structure=None,
            strike_delta=None,
            otm_pct=None,
            iv_field=None,
            tenor_days=None,
            measure=RAW_RETURN if outcome.benchmark == "none" else outcome.measure,
            direction=None,
            target=None,
            max_drawdown=None,
        )
    spec = outcome.position
    if outcome.kind != CHAIN_KIND or spec is None:
        raise ConfigurationError(
            f"position:{template_id}: an option position is a baseline of an option_pnl setup "
            f"only (it takes that setup's entry, tenor and expiry cycle)"
        )
    moved = replace(
        spec, exit=None, cases=(), book=False, skip_report_in_life=False
    )  # the exits and cases are the setup's own
    return with_template(replace(outcome, position=moved), template_id, templates)
