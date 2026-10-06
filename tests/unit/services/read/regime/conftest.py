"""A small regime store: the ``regime@v3`` and ``regime_indicators@v1`` market groups (declared
here, as the RG3 groups will), written for 28 and 29 Sep (CALM), none for 30 Sep and STRESS on
1 Oct (D1), and four cards: ``curve`` and ``hy`` (slow; ``hy``'s column is in no group),
``trend`` and ``vix`` (fast; ``vix`` has a value column but no verdict column)."""

from dataclasses import replace
from datetime import date
from typing import Any

import pandas as pd

from algotrade.config.user import UserContext
from algotrade.core.model.instruments import market_id
from algotrade.features.expressions.feature_set import FeatureSet
from algotrade.features.framework.declaration import FeatureGroup, Input
from algotrade.services.read.context import ReadContext
from algotrade.storage.configs.files import MemoryConfigStore
from tests.helpers.rollup_store import features, write_rows
from tests.unit.services.read.instruments.conftest import D1, context, store_with

SEP28, SEP29, SEP30 = date(2026, 9, 28), date(2026, 9, 29), date(2026, 9, 30)
PREFIX = "market.regime_indicators@v1."


def _never(*_: Any) -> pd.DataFrame:  # pragma: no cover - the rows are written, not computed
    raise AssertionError("not computed in these tests")


REGIME = FeatureGroup(
    "regime",
    3,
    "test regime group",
    (Input("bars/1d"),),
    features(
        {"label": "str", "macro_risk": "float", "market_stress": "float", "fragility": "float"}
    ),
    _never,
    entity="market",
)
INDICATORS = FeatureGroup(
    "regime_indicators",
    1,
    "test regime indicators group",
    (Input("bars/1d"),),
    features(
        {
            "curve": "float",
            "curve_on": "bool",
            "curve_changed": "bool",
            "trend": "float",
            "trend_on": "bool",
            "trend_changed": "bool",
            "vix": "float",
        }
    ),
    _never,
    entity="market",
)


def card(key: str, pace: str, **extra: Any) -> dict[str, Any]:
    return {
        "key": key,
        "technical_name": f"{key} (technical)",
        "pace": pace,
        "feature": PREFIX + key,
        "plain_name": f"Plain {key}?",
        "one_liner": f"What {key} measures.",
        "why_it_matters": f"Why {key} matters.",
        "what_on_means": f"{key} is on when high.",
        "lead_time": "Months.",
        "false_alarms": "Some.",
        "links": [{"title": f"{key} page", "url": f"https://example.org/{key}"}],
        "before": {"2008": f"{key} rose.", "2020": f"{key} jumped."},
        "range": {"min": 0, "max": 1},
        "how": f"How {key} is computed.",
        "terms": [{"text": key, "url": f"https://example.org/{key}/how"}],
        **extra,
    }


CARDS = [card("curve", "slow"), card("hy", "slow"), card("trend", "fast"), card("vix", "fast")]


def with_regime(
    ctx: ReadContext,
    cards: list[dict[str, Any]] | None = None,
    defaults: dict[str, Any] | None = None,
    docs: dict[tuple[str, str, str], dict[str, Any]] | None = None,
    user: str | None = None,
) -> ReadContext:
    """``ctx`` whose catalogue has the two market groups and whose configs have ``cards``,
    when given a ``defaults.toml`` document, and ``docs`` (``(scope, kind, name)``: document,
    the screeners the caller sees); ``user``: whose context it is."""
    site = ctx.features
    code = {**site.code, REGIME.key: REGIME, INDICATORS.key: INDICATORS}
    documents = {("site", "regime", "cards"): {"card": CARDS if cards is None else cards}}
    if defaults is not None:
        documents[("site", "defaults", "defaults")] = defaults
    documents.update(docs or {})
    return replace(
        ctx,
        user=ctx.user if user is None else UserContext(user),
        features=FeatureSet(code, site.expressions, site.superseded),
        configs=MemoryConfigStore(documents),
    )


def write_regime(writer: Any, day: date, label: str | None, **scores: float | None) -> None:
    row = {"instrument_id": market_id("US"), "label": label, "macro_risk": None,
           "market_stress": None, "fragility": None, **scores}  # fmt: skip
    write_rows(writer, REGIME.table, day, [row])


def write_indicators(writer: Any, day: date, **values: Any) -> None:
    write_rows(writer, INDICATORS.table, day, [{"instrument_id": market_id("US"), **values}])


def stored(writer: Any) -> None:
    for day in (SEP28, SEP29):
        write_regime(writer, day, "CALM", macro_risk=10.0, market_stress=12.0)
    write_regime(writer, D1, "STRESS", macro_risk=62.5, market_stress=71.0, fragility=None)
    write_indicators(
        writer, D1, curve=-0.2, curve_on=True, curve_changed=True,
        trend=0.9, trend_on=False, trend_changed=False, vix=1.1,
    )  # fmt: skip


def regime_ctx(day: date | None = None) -> ReadContext:
    return with_regime(context(store_with(stored), day))
