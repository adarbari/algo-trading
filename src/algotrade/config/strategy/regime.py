"""``[regime]``: the run overlay and the screener gate from the market regime (ADR 0049).

Layered like ``[screening]`` and ``[backtest]`` (ADR 0015: built-in < ``config/site/defaults.toml``
< the site preset < the user's config < run overrides), so the config hash records it. Off by
default. ``label`` is the market feature holding the session's regime (``market.regime@v1.label``:
CALM, CAUTION, STRESS, CRISIS; null is unknown). ``multipliers`` size positions per label;
``unknown_multiplier`` is the size when the label is unknown (fail closed: 0 by default).
``pause_in`` lists the labels in which a screener's QUALIFIED / WATCH rows are PAUSED;
``[regime.screeners.<config id>] pause_in`` replaces it for one screener (the VRP scanner's
short volatility pauses in STRESS and CRISIS).
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from algotrade.config.site.fields import Table
from algotrade.config.site.settings import DocumentLoader, site_defaults
from algotrade.core.model.errors import ConfigurationError
from algotrade.core.model.fields import field_source, group_of_table

REGIME_LABELS = ("CALM", "CAUTION", "STRESS", "CRISIS")  # calmest first
REGIME_LABEL = "market.regime@v1.label"
DEFAULT_MULTIPLIERS: Mapping[str, float] = MappingProxyType(
    {"CALM": 1.0, "CAUTION": 0.75, "STRESS": 0.5, "CRISIS": 0.25}
)


def _labels(t: Table, key: str) -> frozenset[str]:
    found = t.strings(key, ())
    unknown = sorted(set(found) - set(REGIME_LABELS))
    if unknown:
        raise ConfigurationError(f"{t.where} {key}: unknown labels {unknown}; use {REGIME_LABELS}")
    return frozenset(found)


def _market_field(t: Table, key: str, default: str) -> str:
    name = t.text(key, default)
    try:
        group = group_of_table(field_source(name)[0])
    except ConfigurationError:
        group = None
    if group is None or group[0] != "market":
        raise ConfigurationError(
            f"{t.where} {key}: expected a market feature field "
            f"('market.<group>@v<N>.<column>'), got {name!r}"
        )
    return name


def _screeners(t: Table) -> Mapping[str, frozenset[str]]:
    """``[regime.screeners.<config id>] pause_in`` per screener."""
    raw = t.raw("screeners")
    ids = sorted(raw) if isinstance(raw, Mapping) else []
    outer = t.table("screeners", ids)
    return MappingProxyType(
        {sid: _labels(outer.table(sid, ["pause_in"]), "pause_in") for sid in ids}
    )


@dataclass(frozen=True)
class RegimeSettings:
    enabled: bool = False
    label: str = REGIME_LABEL
    multipliers: Mapping[str, float] = field(default_factory=lambda: DEFAULT_MULTIPLIERS)
    unknown_multiplier: float = 0.0
    pause_in: frozenset[str] = frozenset()
    screeners: Mapping[str, frozenset[str]] = field(default_factory=dict)  # id -> pause_in

    def pauses_for(self, screener: str) -> frozenset[str]:
        """The labels in which ``screener`` (a config id) pauses its picks."""
        return self.screeners.get(screener, self.pause_in)

    @classmethod
    def parse(cls, doc: Mapping[str, Any] | None, where: str) -> "RegimeSettings":
        d = cls()
        t = Table(doc, where)
        t.only([*d.__dataclass_fields__])
        multipliers = t.table("multipliers", REGIME_LABELS)
        return cls(
            enabled=t.boolean("enabled", d.enabled),
            label=_market_field(t, "label", d.label),
            multipliers=MappingProxyType(
                {k: multipliers.fraction(k, d.multipliers[k]) for k in REGIME_LABELS}
            ),
            unknown_multiplier=t.fraction("unknown_multiplier", d.unknown_multiplier),
            pause_in=_labels(t, "pause_in"),
            screeners=_screeners(t),
        )


def site_regime(load: DocumentLoader) -> RegimeSettings:
    """The site's ``[regime]`` (``config/site/defaults.toml``), for runs outside a config (the
    with-versus-without evaluation)."""
    return RegimeSettings.parse(site_defaults(load).get("regime"), "defaults.toml [regime]")
