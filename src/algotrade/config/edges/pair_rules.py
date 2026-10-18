"""The ``pair_field`` of a ``pair_spread`` outcome (ADR 0053 amendment, EB H9): required there and
refused on any other kind, with the keys a two-leg spread cannot take."""

from algotrade.config.site.fields import Table
from algotrade.core.model.errors import ConfigurationError


def pair_field_of(
    o: Table, is_pair: bool, benchmark: str, side: str, drawdown: float | None
) -> str | None:
    """The ``pair_field`` of an outcome table: the picks of a pair spread are the cheap legs (side
    ``long``), both legs are raw returns and a spread's dip is not stored."""
    named = " ".join(o.text("pair_field", "").split()) if o.raw("pair_field") is not None else ""
    if not is_pair:
        if named:
            raise ConfigurationError(f"{o.where} pair_field: only a pair_spread outcome has one")
        return None
    if not named:
        raise ConfigurationError(f"{o.where} pair_field: required")
    if benchmark != "none" or side != "long" or drawdown is not None:
        raise ConfigurationError(
            f"{o.where}: a pair_spread needs benchmark = 'none', side long (the picks are the "
            f"cheap legs; the sibling is the short leg) and no max_drawdown"
        )
    return named
