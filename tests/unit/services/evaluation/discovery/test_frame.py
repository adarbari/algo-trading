"""``frame``: which features the discovery reads at a session (a learned score, the matching
variable and a feature over a table not yet stored are left out with the reason) and that a
value is read from the partition of S only."""

from dataclasses import replace
from datetime import date

import numpy as np
import pandas as pd

from algotrade.config.site.features.definitions import FeatureDefinition
from algotrade.features.expressions.feature_set import FeatureSet
from algotrade.features.framework.declaration import FeatureGroup, Input
from algotrade.features.framework.feature import Feature
from algotrade.features.site import site_features
from algotrade.services.evaluation.discovery.frame import (
    EDGE_SCORE,
    MATCHING_VARIABLE,
    assemble,
    read_values,
    usable_fields,
)
from algotrade.storage.configs.files import FileConfigStore
from tests.conftest import REPO_ROOT
from tests.helpers.rollup_store import store, write_rows

SITE = site_features(FileConfigStore(REPO_ROOT / "config"))
LONG_AGO = date(2000, 1, 1)
S = date(2012, 3, 1)
CLOSE = "rollup.price_stats@v2.close"


def define(name: str, expr: str) -> FeatureDefinition:
    base = FeatureDefinition(name, "t", expr, "float", "decimal", f"test {name}", "never")
    return replace(base, owner="u")


def everywhere(fs: FeatureSet, first: date | None = LONG_AGO) -> dict[str, date | None]:
    """Every table any group reads, first stored on ``first``."""
    return {i.table: first for g in fs.code.values() for i in g.inputs}


def test_edge_score_excluded() -> None:
    """A fit scorer's score was trained on windows overlapping the label; a tell made of it (or of
    a formula over it) would be the fit, not a finding. Catches: ``edge_score_*`` entering the
    discovery."""
    fs = SITE.with_user(
        [
            define("edge_score_x", "price_stats.close * 2"),
            define("over_score", "edge_score_x + 1"),
        ]
    )
    got = usable_fields(fs, S, everywhere(fs))
    assert "feature.edge_score_x" not in got.fields and "feature.over_score" not in got.fields
    assert ("feature.edge_score_x", EDGE_SCORE) in got.excluded
    assert ("feature.over_score", EDGE_SCORE) in got.excluded
    assert CLOSE in got.fields


def test_the_matching_variable_and_features_derived_from_it_are_excluded() -> None:
    """The controls are matched on ``adv_usd_20d``; a winner-control difference in it (or in a
    formula of it) is the matching leaking. Catches: the liquidity variable among the tells."""
    fs = SITE.with_user([define("adv_twice", "price_stats.adv_usd_20d * 2")])
    got = usable_fields(fs, S, everywhere(fs))
    assert "rollup.price_stats@v2.adv_usd_20d" not in got.fields
    assert "feature.adv_twice" not in got.fields
    assert ("feature.adv_twice", MATCHING_VARIABLE) in got.excluded


def test_late_input_feature_excluded() -> None:
    """A table that starts in 2026 (company, shares, chains, IV) describes today on a 2012
    session; its features are left out for that session, with the table and its first date.
    Catches: today's knowledge entering an old grid session."""
    first = everywhere(SITE)
    first["instruments/company"] = date(2026, 1, 5)
    got = usable_fields(SITE, S, first)
    late = [f for f, why in got.excluded if "instruments/company" in why]
    assert late, "some catalogue feature reads the company snapshot"
    assert not set(late) & set(got.fields)
    assert any("first stored 2026-01-05" in why for _, why in got.excluded)
    assert usable_fields(SITE, date(2026, 2, 2), first).fields.count(CLOSE) == 1  # after: usable


def test_a_table_never_stored_excludes_its_features() -> None:
    """No partition at all is not a date to compare: the feature has no value anywhere. Catches:
    a ``None`` first partition treated as early enough."""
    first = everywhere(SITE)
    first["bars/1d"] = None
    got = usable_fields(SITE, S, first)
    assert CLOSE not in got.fields
    assert (CLOSE, "input bars/1d never stored") in got.excluded


TOY = FeatureGroup(
    "toy",
    1,
    "toy group",
    (Input("bars/1d"),),
    (Feature("x", "float", "ratio", "test x", "never"),),
    lambda frames, session, params: pd.DataFrame(),
)


def test_value_at_s_plus_1_ignored() -> None:
    """The rollup of the next session holds different numbers; the frame reads S's partition
    only, and a name with no row at S is UNKNOWN even when the next session has one. Catches: a
    read that falls through to a later (or earlier) partition."""
    writer, reader = store()
    nxt = date(2012, 3, 2)
    write_rows(writer, "rollups/instrument/toy@v1", S, [{"instrument_id": "EQ:A", "x": 1.0}])
    write_rows(
        writer,
        "rollups/instrument/toy@v1",
        nxt,
        [{"instrument_id": "EQ:A", "x": 99.0}, {"instrument_id": "EQ:B", "x": 98.0}],
    )
    fs = FeatureSet.build({TOY.key: TOY})
    view = read_values(reader, S, ("rollup.toy@v1.x",), ["EQ:A", "EQ:B"], fs)
    frame = assemble(view, ("rollup.toy@v1.x",), {"EQ:A"}, {"EQ:B"}, pd.Series({"EQ:A": "c"}))
    assert frame.loc[frame["instrument_id"] == "EQ:A", "rollup.toy@v1.x"].item() == 1.0
    assert np.isnan(frame.loc[frame["instrument_id"] == "EQ:B", "rollup.toy@v1.x"].item())


def test_an_unknown_value_stays_nan_in_the_frame() -> None:
    """UNKNOWN is dropped and counted, never filled: an absent column and a null are NaN. Catches:
    a fillna(0) or a mean imputation in the assembled frame."""
    values = pd.DataFrame({"instrument_id": ["A", "B"], "f": [1.5, None]})
    frame = assemble(values, ("f", "absent"), {"A"}, {"B"}, pd.Series({"A": "c", "B": "c"}))
    assert frame["f"].tolist()[0] == 1.5 and np.isnan(frame["f"].tolist()[1])
    assert frame["absent"].isna().all()
