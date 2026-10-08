"""Small Guide configs: a field guide of two entries and two situations, the sections file
(one family listing ``alpha`` and a preset that does not exist), ``alpha``'s playbook prose
(a related id that is no playbook, one criterion without ``asks``), and three site presets:
``alpha`` (two versions: v2 is read), ``zeta`` (in no family) and ``broken`` (not a rule
screen); apart (``regime``), one regime card over three episodes. The catalogue is the
site's (a store without feature files sees the site's)."""

from collections.abc import Mapping
from datetime import date
from typing import Any

import pytest

from algotrade.config.user import SITE_USER, UserContext
from algotrade.data import StoreReader
from algotrade.services.read.context import StoreContext, open_stores
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import FileConfigStore, MemoryConfigStore
from tests.conftest import REPO_ROOT

ADV = "rollup.price_stats@v2.adv_usd_20d"
CLOSE = "rollup.price_stats@v2.close"
REL_VOLUME = "rollup.momentum@v1.rel_volume"
PULLBACK = "feature.pullback_atr_20d"

GUIDE = {
    "field": [
        {
            "name": ADV,
            "theme": "liquidity",
            "reads": f"Dollars a day. Compare {REL_VOLUME} and feature.atr_pct; not {ADV} "
            "itself, and not rollup.nope@v1.x (not in the catalogue).",
            "caveats": ["Check feature.atr_pct again (twice), then instrument.symbol."],
            "use": [
                {"for": "liquid", "op": "gte", "value": 50_000_000, "note": f"with {CLOSE}"},
                {"for": "very liquid", "op": "gte", "value": 500_000_000},
            ],
        },
        {
            "name": PULLBACK,
            "theme": "momentum and trend",
            "reads": f"How far below the 20-day high, in ATRs; {CLOSE} is the price.",
            "use": [{"for": "liquid", "op": "lte", "value": 1.5}],
        },
    ],
    "situation": [
        {"name": "thin name", "signs": "Few trades.", "affects": [ADV, CLOSE], "do": "Gate."},
        {"name": "takeover", "signs": "Dead tape.", "affects": [REL_VOLUME], "do": "Skip."},
    ],
}
SECTIONS = {
    "section": [
        {"id": "fields", "title": "Fields", "purpose": "Every field."},
        {"id": "playbooks", "title": "Playbooks", "purpose": "Every screen."},
        {"id": "glossary", "title": "Glossary", "purpose": "Words."},
    ],
    "theme_group": [
        {"id": "tradeable", "title": "Who is tradeable", "themes": ["liquidity", "volume"]},
        {"id": "chart", "title": "The chart", "themes": ["momentum and trend"]},
    ],
    "family": [{"id": "trend", "title": "Trend", "presets": ["alpha", "missing"]}],
}


def preset(config_id: str, name: str, criteria: Mapping[str, Any], **rest: Any) -> dict[str, Any]:
    return {
        "id": config_id, "kind": "screener", "impl": "rules", "name": name,
        "criteria": criteria, **rest,
    }  # fmt: skip


ALPHA_V2 = preset(
    "alpha",
    "Alpha",
    {
        "adv": {"field": ADV, "op": "gte", "value": 50_000_000, "mode": "soft",
                "tolerance": {"relative": 0.2}, "on_miss": "LIQUIDITY_RISK"},
        "band": {"field": PULLBACK, "op": "between", "value": [-0.5, 0.5], "mode": "soft",
                 "tolerance": 0.25},
        "listed": {"field": "instrument.status", "op": "eq", "value": "ACTIVE"},
    },
    columns={"close": CLOSE, "adv": ADV},
    rank={"tie_break": PULLBACK},
    version=2,
)  # fmt: skip
ALPHA_PROSE = {
    "id": "alpha",
    "version": 2,
    "summary": f"Finds dips; read {PULLBACK} first.",
    "hit": "Near the average.",
    "not_checked": "News.",
    "before_acting": [f"Thin names: {ADV} under $40M."],
    "related": [{"id": "zeta", "reason": "the other one"}, {"id": "missing", "reason": "gone"}],
    "sources": ["A book"],
    "asks": {"adv": "Trades $50M a day", "band": "Near its average"},  # no "listed"
}
DOCUMENTS: dict[tuple[str, str, str], Mapping[str, Any]] = {
    ("site", "field_guide", "liquidity"): GUIDE,
    ("site", "guide", "sections"): SECTIONS,
    ("site", "guide_playbooks", "alpha"): ALPHA_PROSE,
    ("site", "screeners", "alpha@1"): preset(
        "alpha", "Alpha v1", {"c": {"field": CLOSE, "op": "gt", "value": 1}}
    ),
    ("site", "screeners", "alpha@2"): ALPHA_V2,
    ("site", "screeners", "zeta@1"): preset(
        "zeta",
        "Zeta",
        {"close": {"field": CLOSE, "op": "gt", "value": 5}},
        columns={"adv": ADV},
        flags={"thin": {"any": [{"field": REL_VOLUME, "op": "lt", "value": 0.5}]}},
    ),
    ("site", "screeners", "broken@1"): {
        "id": "broken",
        "kind": "screener",
        "impl": "python",
        "name": "Broken",
    },
}


def stores(documents: Mapping[tuple[str, str, str], Mapping[str, Any]]) -> StoreContext:
    return open_stores(
        StoreReader(MemoryBackend()), MemoryConfigStore(documents), UserContext("local")
    )


@pytest.fixture
def ctx() -> StoreContext:
    return stores(DOCUMENTS)


# The regime: one card (``before`` labels for one episode, two episodes and none) over three
# episodes, two of them in 2011.
EPISODE = {
    "key": "gfc", "name": "Financial crisis", "peak": date(2007, 10, 9),
    "trough": date(2009, 3, 9), "recovered": date(2013, 3, 28), "spx_drawdown": -0.57,
    "nasdaq_drawdown": -0.56, "recession": True, "nber_start": date(2007, 12, 1),
    "nber_end": date(2009, 6, 1), "kind": "recession",
    "cause": f"Housing; {ADV} dried up.", "known_from": date(2009, 3, 9), "notes": "Curve.",
}  # fmt: skip
SHOCK = {
    "key": "eu", "name": "Euro", "peak": date(2011, 4, 29), "trough": date(2011, 10, 3),
    "spx_drawdown": -0.19, "nasdaq_drawdown": -0.18, "recession": False, "kind": "shock",
    "cause": "Debt.", "known_from": date(2011, 10, 3), "notes": "Spreads.",
}  # fmt: skip
CARD = {
    "key": "curve", "technical_name": "10y minus 3m (T10Y3M)", "pace": "slow",
    "feature": "market.regime_indicators@v1.curve_10y3m",
    "plain_name": "Are long rates below short ones?", "one_liner": "The 10y minus the 3m.",
    "why_it_matters": f"Banks earn less; see {CLOSE}.", "what_on_means": "On below zero.",
    "lead_time": "6 to 18 months.", "false_alarms": "1998.",
    "links": [{"title": "FRED T10Y3M", "url": "https://fred.stlouisfed.org/series/T10Y3M"}],
    "before": {"2008": "Inverted in 2006.", "2011": "Flat.", "1999": "Before any episode."},
    "range": {"min": -0.02, "max": 0.04}, "how": "The 10-year yield minus the 3-month bill.",
    "terms": [{"text": "3-month bill", "url": "https://fred.stlouisfed.org/series/DGS3MO"}],
}  # fmt: skip
REGIME: dict[tuple[str, str, str], Mapping[str, Any]] = {
    ("site", "regime", "cards"): {"card": [CARD]},
    ("site", "regime", "episodes"): {
        "episode": [EPISODE, SHOCK, {**SHOCK, "key": "eu2", "name": "Euro again"}]
    },
}


@pytest.fixture
def regime() -> StoreContext:
    return stores(REGIME)


SHIPPED = FileConfigStore(REPO_ROOT / "config")


@pytest.fixture(scope="module")
def site() -> StoreContext:
    """The repo's site configs (for the fitness tests over the shipped files)."""
    return open_stores(StoreReader(MemoryBackend()), SHIPPED, UserContext(SITE_USER))
