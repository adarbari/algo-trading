"""ETF category settings: the committed rules and overrides load, and bad ones fail closed."""

import csv
import re
import tomllib

import pytest

from algotrade.config.site.universe.etf_category import (
    CATEGORIES,
    EtfCategoryRules,
    etf_overrides,
)
from algotrade.core.model.errors import ConfigurationError
from tests.conftest import REPO_ROOT

SITE = REPO_ROOT / "config" / "site"


def test_committed_rules_load_and_every_phrase_compiles() -> None:
    doc = tomllib.loads((SITE / "universe.toml").read_text())
    rules = EtfCategoryRules.from_document(doc["etf_category"], "universe.toml")
    assert rules.broad and rules.exclusions and rules.themes and rules.sectors
    for group in (rules.exclusions, rules.themes, rules.sectors):
        names = [name for name, _ in group]
        assert len(names) == len(set(names))
        for _, patterns in group:
            assert patterns
            for pattern in patterns:
                re.compile(pattern)


def test_committed_overrides_are_valid_and_unique() -> None:
    with (SITE / "overrides" / "thematic_etfs.csv").open(newline="") as fh:
        rows = [r for r in csv.DictReader(fh) if not r["symbol"].startswith("#")]
    found = etf_overrides(rows)
    assert len(found) == len(rows) > 0
    assert {category for category, _ in found.values()} <= set(CATEGORIES)


@pytest.mark.parametrize(
    ("doc", "message"),
    [
        ({"surprise": []}, "unknown keys"),
        ({"broad": ["(unclosed"]}, "broad[0]"),
        ({"themes": {"ai": []}}, "expected a list"),
        ({"themes": [{"name": "ai", "phrases": ["fine", "(bad"]}]}, "phrases[1]"),
        ({"themes": [{"name": "ai"}, {"name": "ai"}]}, "listed twice"),
        ({"themes": [{"name": "ai", "color": "red"}]}, "unknown keys"),
    ],
)
def test_bad_rules_fail_closed(doc: dict[str, object], message: str) -> None:
    with pytest.raises(ConfigurationError, match=re.escape(message)):
        EtfCategoryRules.from_document(doc, "universe.toml")


@pytest.mark.parametrize(
    ("rows", "message"),
    [
        ([{"symbol": "XLK", "category": "specialised"}], "is not one of"),
        ([{"symbol": "", "category": "sector"}], "symbol is required"),
        ([{"symbol": "XLK", "category": "sector"}] * 2, "listed twice"),
        ([{"symbol": "XLK", "category": "sector", "color": "red"}], "unknown column"),
    ],
)
def test_bad_overrides_fail_closed(rows: list[dict[str, str]], message: str) -> None:
    with pytest.raises(ConfigurationError, match=message):
        etf_overrides(rows)


def test_override_normalises_case_and_blank_theme() -> None:
    got = etf_overrides([{"symbol": "xlk", "category": "Sector", "theme": " ", "notes": "x"}])
    assert got == {"XLK": ("sector", None)}
