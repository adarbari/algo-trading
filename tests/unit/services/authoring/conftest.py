"""A memory config writer with a site selection and a pinned rule-screen preset."""

import tomllib

import pytest

from algotrade.storage.configs.writer import MemoryConfigWriter

SELECTION = """name = "all_active"
[where]
all = [{field = "instrument.status", op = "eq", value = "ACTIVE"}]
"""
PRESET = """id = "vrp"
kind = "screener"
impl = "rules"
version = 3
selection = "all_active"
schedule = "nightly"

[criteria.price]
field = "rollup.price_stats@v2.close"
op = "gt"
value = 5
mode = "hard"

[criteria.hv]
field = "rollup.price_stats@v2.hv20"
op = "gte"
value = 0.2
mode = "soft"
tolerance = 0.05
"""


@pytest.fixture
def writer() -> MemoryConfigWriter:
    return MemoryConfigWriter(
        {
            ("site", "selections", "all_active"): tomllib.loads(SELECTION),
            ("site", "screeners", "vrp@3"): tomllib.loads(PRESET),
        }
    )
