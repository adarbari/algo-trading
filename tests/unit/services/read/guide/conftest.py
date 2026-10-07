"""Small Guide configs: a field guide of two entries and two situations, the sections file
(one family listing ``alpha`` and a preset that does not exist), and three site presets:
``alpha`` (two versions: v2 is read), ``zeta`` (in no family) and ``broken`` (not a rule
screen). The catalogue is the site's (a store without feature files sees the site's)."""

from collections.abc import Mapping
from typing import Any

import pytest

from algotrade.config.user import UserContext
from algotrade.data import StoreReader
from algotrade.services.read.context import StoreContext, open_stores
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import MemoryConfigStore

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
)  # fmt: skip
DOCUMENTS: dict[tuple[str, str, str], Mapping[str, Any]] = {
    ("site", "field_guide", "liquidity"): GUIDE,
    ("site", "guide", "sections"): SECTIONS,
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
