"""The regime's catalogue fields (the contract the RG3 market groups fill, ADR 0047) and the one
read of them: each name is a ``market.<group>@v<N>.<column>`` field of the market's ``MKT:US``
row for exactly ``ctx.session``, or ``Unknown(NOT_IN_CATALOGUE)`` while its group does not exist
yet (the regime is UNKNOWN until RG3 writes it, never an error and never an older partition).

``market.regime@v1``: ``label`` (CALM, CAUTION, STRESS, CRISIS), and the scores ``macro_risk``,
``market_stress`` and ``fragility`` (0 to 100). ``market.regime_indicators@v1``: per card
(``config/site/regime/cards.toml``) its value column ``<key>``, and the bool columns
``<key>_on`` (the indicator's own on / off verdict) and ``<key>_changed`` (the verdict differs
from 5 sessions earlier), named by the suffixes below from the card's ``feature``."""

from collections.abc import Sequence
from dataclasses import dataclass

from algotrade.core.views.feature_view import FeatureValue as Scalar
from algotrade.services.read.context import ReadContext
from algotrade.services.read.instruments.catalogue import FeatureFormat
from algotrade.services.read.market.features import load_market_feature_values
from algotrade.services.read.values import Unknown, UnknownCode

REGIME = "market.regime@v1"
LABEL = f"{REGIME}.label"
MACRO_RISK = f"{REGIME}.macro_risk"
MARKET_STRESS = f"{REGIME}.market_stress"
FRAGILITY = f"{REGIME}.fragility"
ON = "_on"  # <card feature> + ON: the indicator's verdict (bool)
CHANGED = "_changed"  # <card feature> + CHANGED: the verdict changed within 5 sessions (bool)


@dataclass(frozen=True)
class Reading:
    """A market field for the session: ``value`` is ``None`` exactly when ``unknown`` says why;
    ``format`` is how a client shows it (``None``: not in the catalogue)."""

    value: Scalar
    unknown: Unknown | None
    format: FeatureFormat | None = None


def read_fields(ctx: ReadContext, names: Sequence[str]) -> dict[str, Reading]:
    """``names`` (market catalogue fields) for ``ctx.session``: one read for those the
    catalogue has, ``NOT_IN_CATALOGUE`` for the rest."""
    known = ctx.features.field_types("market")
    present = [n for n in dict.fromkeys(names) if n in known]
    found = {v.name: v for v in load_market_feature_values(ctx, present)} if present else {}
    out: dict[str, Reading] = {}
    for name in dict.fromkeys(names):
        if name in found:
            v = found[name]
            out[name] = Reading(v.value, v.unknown, v.info.format)
        else:
            detail = f"{name} is not in the market catalogue: the regime has not been computed yet"
            out[name] = Reading(None, Unknown(UnknownCode.NOT_IN_CATALOGUE, detail))
    return out
