"""User expression features (ADR 0023 step 4): typed by the same loader as the site's, never
materialised, built on top of the site's (which they may read but not shadow), cycles named."""

from dataclasses import replace

import pytest

from algotrade.config.site.settings import FeatureDefinition, feature_definitions
from algotrade.core.model.errors import ConfigurationError
from algotrade.features.expressions.feature_set import FeatureSet
from algotrade.features.expressions.nodes import ExpressionError
from algotrade.features.registry import GROUPS, SUPERSEDED
from algotrade.features.site import site_features
from algotrade.storage.configs.files import FileConfigStore
from tests.conftest import REPO_ROOT


def section(expr: str, **extra: object) -> dict[str, object]:
    return {"expr": expr, "dtype": "float", "unit": "decimal", "description": "d",
            "null_meaning": "n", **extra}  # fmt: skip


def user(docs: dict[str, dict[str, object]], owner: str = "alice") -> list[FeatureDefinition]:
    return list(feature_definitions({"mine": docs}, owner))


@pytest.fixture(scope="module")
def site() -> FeatureSet:
    return site_features(FileConfigStore(REPO_ROOT / "config"))


def test_user_features_read_site_features_groups_and_each_other(site: FeatureSet) -> None:
    defs = user({
        "deep": section("half * 2"),
        "half": section("pct_from_high_52w / k", params={"k": 2}),
        "hv_gap": section("price_stats.hv20 - price_stats.hv30"),
    })  # fmt: skip
    assert defs[0].where == "config/users/alice/features/mine.toml [deep]"
    fs = site.with_user(defs)
    assert list(fs.expressions)[-3:] == ["half", "deep", "hv_gap"]  # after the site's
    assert fs.expressions["half"].scope == "user" and fs.expressions["half"].uses == (
        "pct_from_high_52w",
    )
    assert fs.expressions["pct_from_high_52w"].scope == "site"
    assert fs.expressions["deep"].feature.inputs == ("half@v1",)
    assert site.with_user([]) is site and "half" not in site.expressions  # site set unchanged


@pytest.mark.parametrize(
    ("docs", "message"),
    [
        (
            {"pct_from_high_52w": section("1")},
            "config/users/alice/features/mine.toml [pct_from_high_52w]: 'pct_from_high_52w' "
            "shadows the site feature config/site/features/price.toml [pct_from_high_52w]",
        ),
        ({"price_stats": section("1")}, "'price_stats' is already a feature or group name"),
        (
            {"a": section("b + 1"), "b": section("a + pct_from_high_52w")},
            "[a]: dependency cycle: a -> b -> a",
        ),
        (
            {"a": section("pct_from_high_52w +\n nope")},
            "config/users/alice/features/mine.toml [a] expr, line 2 col 2: unknown name 'nope'",
        ),
        ({"a": section("price_stats.clsoe")}, "price_stats@v2 has no feature 'clsoe'"),
    ],
)
def test_user_definition_errors_name_file_feature_and_position(
    site: FeatureSet, docs: dict[str, dict[str, object]], message: str
) -> None:
    with pytest.raises(ExpressionError) as err:
        site.with_user(user(docs))
    assert message in str(err.value)


def test_a_site_feature_never_sees_user_features(site: FeatureSet) -> None:
    """The site is built without users, so a site formula naming a user feature is unknown
    (and a cycle can only run through user features)."""
    defs = [e.definition for e in site.expressions.values()]
    reads_user = replace(defs[0], name="site_reads", expr="half * 2")
    with pytest.raises(ExpressionError, match="unknown name 'half'"):
        FeatureSet.build(GROUPS, [*defs, reads_user], SUPERSEDED)


@pytest.mark.parametrize(
    ("doc", "message"),
    [
        (section("1", materialise=False), "[a] materialise: a user feature is always virtual"),
        (section("1", api_key="x"), "mine.toml.a.api_key: looks like a secret"),
        (section("1", colour="red"), "[a]: unknown keys ['colour']"),
        ({"expr": "1", "dtype": "float"}, "[a]: missing ['unit', 'description', 'null_meaning']"),
    ],
)
def test_the_loader_types_user_files_like_site_files(doc: dict[str, object], message: str) -> None:
    with pytest.raises(ConfigurationError) as err:
        user({"a": doc})
    assert message in str(err.value)
    assert str(err.value).startswith("config/users/alice/features/mine.toml")


def test_with_user_takes_only_virtual_user_definitions(site: FeatureSet) -> None:
    with pytest.raises(ConfigurationError, match=r"not a \(virtual\) user feature"):
        site.with_user([replace(site.expressions["pct_from_high_52w"].definition, name="x")])
