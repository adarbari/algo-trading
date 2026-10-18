"""The site's forward expression features (``config/site/features/company/forward.toml``):
forward P/E on FY1 and FY2, expected EPS and revenue growth and the upside to the analysts'
price target: each formula's value on hand-built group rows, each null guard (a forecast loss,
an ADR, a status that is not OK or a name the vendor does not cover, a stale reported EPS, no or
zero revenue, no close), that nothing divides into an infinity, that every one inherits the
personal licence of its source (ADR 0069) and that a hard criterion on one reads UNKNOWN for a
viewer without the licence."""

import math

import numpy as np
import pandas as pd
import pytest

from algotrade.config.user import SITE_USER, UserContext
from algotrade.engines.screening.runner import RunCoverage
from algotrade.features.expressions.feature_set import FeatureSet
from algotrade.features.site import site_features
from algotrade.services.configs import resolve_config
from algotrade.services.features import site_features as catalogue_features
from algotrade.services.licences import ALL_LICENCES, hidden_fields, licence_of
from algotrade.services.screening.run import screen_session
from algotrade.storage.configs.files import FileConfigStore, MemoryConfigStore
from tests.conftest import REPO_ROOT
from tests.helpers.rollup_store import END
from tests.helpers.stored_frames import T0, stamped
from tests.unit.services.screening.test_rule_screens import ACTIVE, DAY, seeded

PRICE = "rollups/instrument/price_stats@v2"
FINANCIALS = "rollups/instrument/financials@v3"
ESTIMATES = "rollups/instrument/analyst_estimates@v1"
TARGETS = "rollups/instrument/analyst_targets@v1"
TABLES = {
    PRICE: ("close",),
    FINANCIALS: ("revenue_ttm", "eps_diluted_ttm", "financials_status", "eps_stale", "is_adr"),
    ESTIMATES: ("eps_fy1", "eps_fy2", "revenue_fy1", "estimates_status"),
    TARGETS: ("target_consensus", "targets_status"),
}
BASE = {  # covered, profitable, growing: forward P/E 100 / 5 = 20
    "close": 100.0, "revenue_ttm": 1000.0, "eps_diluted_ttm": 4.0, "financials_status": "OK",
    "eps_stale": False, "is_adr": False, "eps_fy1": 5.0, "eps_fy2": 8.0, "revenue_fy1": 1100.0,
    "estimates_status": "OK", "target_consensus": 120.0, "targets_status": "OK",
}  # fmt: skip
NAMES = [
    "forward_pe", "forward_pe_fy2", "forward_eps_growth", "forward_revenue_growth",
    "target_upside",
]  # fmt: skip
STATUS_COLUMNS = ("financials_status", "estimates_status", "targets_status")
FLAG_COLUMNS = ("eps_stale", "is_adr")


@pytest.fixture(scope="module")
def fs() -> FeatureSet:
    return site_features(FileConfigStore(REPO_ROOT / "config"))


def evaluate(fs: FeatureSet, rows: dict[str, dict]) -> pd.DataFrame:
    """Every forward feature over one row per id: ``BASE`` with the row's overrides."""
    full = {i: {**BASE, **over} for i, over in rows.items()}
    ids = list(full)
    frames = {}
    for table, columns in TABLES.items():
        frame = pd.DataFrame(
            {"instrument_id": ids, "session_date": END}
            | {c: pd.Series([full[i][c] for i in ids], dtype=object) for c in columns}
        )
        for c in columns:
            if c in FLAG_COLUMNS:
                frame[c] = frame[c].astype(bool)
            elif c not in STATUS_COLUMNS:
                frame[c] = frame[c].astype(float)  # None is NaN
        frames[table] = frame
    return fs.evaluate(frames, NAMES).set_index("instrument_id").drop(columns="session_date")


def test_each_formula_on_a_covered_company(fs: FeatureSet) -> None:
    out = evaluate(fs, {"EQ:A": {}}).loc["EQ:A"]
    assert out["forward_pe"] == pytest.approx(20.0)  # 100 / 5
    assert out["forward_pe_fy2"] == pytest.approx(12.5)  # 100 / 8
    assert out["forward_eps_growth"] == pytest.approx(0.25)  # 5 / 4 - 1
    assert out["forward_revenue_growth"] == pytest.approx(0.1)  # 1100 / 1000 - 1
    assert out["target_upside"] == pytest.approx(0.2)  # 120 / 100 - 1


def test_a_target_below_the_close_is_a_negative_upside_above_minus_one(fs: FeatureSet) -> None:
    out = evaluate(fs, {"EQ:T": {"target_consensus": 80.0}}).loc["EQ:T"]
    assert out["target_upside"] == pytest.approx(-0.2)
    assert -1 < out["target_upside"] < 0


@pytest.mark.parametrize("eps", [0.0, -2.0])
def test_a_forecast_loss_has_no_forward_pe_but_keeps_the_growth_and_the_target(
    fs: FeatureSet, eps: float
) -> None:
    """A non-positive EPS gives no P/E (a negative multiple is not shown); the growth stays and
    reads below -1 for a forecast loss."""
    out = evaluate(fs, {"EQ:L": {"eps_fy1": eps, "eps_fy2": eps}}).loc["EQ:L"]
    assert out[["forward_pe", "forward_pe_fy2"]].isna().all()
    assert out["forward_eps_growth"] == pytest.approx(eps / 4.0 - 1)
    assert out["target_upside"] == pytest.approx(0.2)


def test_a_loss_last_year_has_no_expected_eps_growth_but_keeps_the_multiple(
    fs: FeatureSet,
) -> None:
    rows = {"EQ:Z": {"eps_diluted_ttm": 0.0}, "EQ:N": {"eps_diluted_ttm": -3.0}}
    out = evaluate(fs, rows)
    assert out["forward_eps_growth"].isna().all()
    assert (out["forward_pe"] == 20.0).all()


def test_an_adr_has_no_forward_ratio_over_a_price_or_a_reported_figure(fs: FeatureSet) -> None:
    """Its per-share figures are per ordinary share and its revenue is in another currency: the
    same rule as ``pe_ratio``. The target is not divided into a reported figure, so it stays."""
    out = evaluate(fs, {"EQ:ADR": {"is_adr": True}}).loc["EQ:ADR"]
    assert out[["forward_pe", "forward_pe_fy2", "forward_eps_growth"]].isna().all()
    assert math.isnan(out["forward_revenue_growth"])
    assert out["target_upside"] == pytest.approx(0.2)


@pytest.mark.parametrize("status", ["STALE", "NOT_COVERED", "NOT_FETCHED"])
def test_estimates_that_are_not_ok_give_no_estimate_formula(fs: FeatureSet, status: str) -> None:
    """Even when a value is present (the group nulls it, but the formula must not rely on it)."""
    out = evaluate(fs, {"EQ:S": {"estimates_status": status}}).loc["EQ:S"]
    assert out[["forward_pe", "forward_pe_fy2", "forward_eps_growth"]].isna().all()
    assert math.isnan(out["forward_revenue_growth"])
    assert out["target_upside"] == pytest.approx(0.2)  # the targets have their own status


@pytest.mark.parametrize("status", ["STALE", "NOT_COVERED", "NOT_FETCHED"])
def test_targets_that_are_not_ok_give_no_upside(fs: FeatureSet, status: str) -> None:
    out = evaluate(fs, {"EQ:S": {"targets_status": status}}).loc["EQ:S"]
    assert math.isnan(out["target_upside"])
    assert out["forward_pe"] == pytest.approx(20.0)


def test_a_name_the_vendor_does_not_cover_is_null_everywhere(fs: FeatureSet) -> None:
    """The free key covers few names: no estimate, no target, status NOT_COVERED."""
    gap = {
        "eps_fy1": None, "eps_fy2": None, "revenue_fy1": None, "target_consensus": None,
        "estimates_status": "NOT_COVERED", "targets_status": "NOT_COVERED",
    }  # fmt: skip
    out = evaluate(fs, {"EQ:U": gap})
    assert out.loc["EQ:U"].isna().all()


def test_a_stale_reported_eps_gives_no_expected_growth(fs: FeatureSet) -> None:
    out = evaluate(fs, {"EQ:E": {"eps_stale": True}}).loc["EQ:E"]
    assert math.isnan(out["forward_eps_growth"])
    assert out["forward_pe"] == pytest.approx(20.0)  # the estimate does not use the reported EPS


def test_a_missing_estimate_is_null_never_zero(fs: FeatureSet) -> None:
    out = evaluate(fs, {"EQ:M": {"eps_fy1": None, "revenue_fy1": None}}).loc["EQ:M"]
    assert out[["forward_pe", "forward_eps_growth", "forward_revenue_growth"]].isna().all()
    assert out["forward_pe_fy2"] == pytest.approx(12.5)  # FY2 is its own estimate


@pytest.mark.parametrize("revenue", [0.0, -5.0, None])
def test_no_reported_revenue_gives_no_expected_revenue_growth(
    fs: FeatureSet, revenue: float | None
) -> None:
    out = evaluate(fs, {"EQ:R": {"revenue_ttm": revenue}}).loc["EQ:R"]
    assert math.isnan(out["forward_revenue_growth"])
    assert out["forward_pe"] == pytest.approx(20.0)


def test_stale_reported_financials_give_no_expected_revenue_growth(fs: FeatureSet) -> None:
    out = evaluate(fs, {"EQ:F": {"financials_status": "STALE"}}).loc["EQ:F"]
    assert math.isnan(out["forward_revenue_growth"])
    assert out["forward_eps_growth"] == pytest.approx(0.25)  # the EPS has its own eps_stale


@pytest.mark.parametrize("close", [0.0, -1.0, None])
def test_no_close_gives_no_price_ratio(fs: FeatureSet, close: float | None) -> None:
    out = evaluate(fs, {"EQ:C": {"close": close}}).loc["EQ:C"]
    assert out[["forward_pe", "forward_pe_fy2", "target_upside"]].isna().all()
    assert out["forward_eps_growth"] == pytest.approx(0.25)  # no price involved


def test_a_zero_target_is_no_upside_not_minus_one(fs: FeatureSet) -> None:
    assert math.isnan(
        evaluate(fs, {"EQ:Q": {"target_consensus": 0.0}}).loc["EQ:Q", "target_upside"]
    )


def test_nothing_divides_into_an_infinity(fs: FeatureSet) -> None:
    rows = {
        "EQ:1": {"close": 0.0, "eps_fy1": 0.0, "revenue_ttm": 0.0, "target_consensus": 0.0},
        "EQ:2": {"eps_fy1": 1e-300, "eps_diluted_ttm": 1e-300},
    }
    out = evaluate(fs, rows)
    assert not np.isinf(out.to_numpy(dtype=float)).any()


# The data-licence gate (ADR 0028, ADR 0069): every feature here reads a personal-use source.
FEATURES = [f"feature.{n}" for n in NAMES]


def test_each_forward_feature_inherits_the_personal_licence() -> None:
    features = catalogue_features()
    assert {n: licence_of(features, n) for n in FEATURES} == dict.fromkeys(FEATURES, "personal")


def test_the_forward_features_are_hidden_from_a_viewer_without_the_licence() -> None:
    features = catalogue_features()
    assert hidden_fields(features, FEATURES, {"open"}) == set(FEATURES)
    assert hidden_fields(features, FEATURES, ALL_LICENCES) == frozenset()


FORWARD_SCREEN = {
    "id": "cheap_forward",
    "kind": "screener",
    "impl": "rules",
    "version": 1,
    "selection": "active",
    "screening": {"min_coverage": 0.5},
    "criteria": {"pe": {"field": "feature.forward_pe", "op": "lt", "value": 25}},
}


def _forward_session():  # type: ignore[no-untyped-def]
    """Three stocks, two with estimates (forward P/E 20 and 40), one with none."""
    reader, writer = seeded()
    ids = ["EQ:AAA", "EQ:BBB", "EQ:CCC"]
    price = [{"instrument_id": i, "close": 100.0} for i in ids]
    financials = [{"instrument_id": i, "is_adr": False} for i in ids]
    estimates = [
        {"instrument_id": "EQ:AAA", "eps_fy1": 5.0, "estimates_status": "OK"},
        {"instrument_id": "EQ:BBB", "eps_fy1": 2.5, "estimates_status": "OK"},
        {"instrument_id": "EQ:CCC", "eps_fy1": None, "estimates_status": "NOT_COVERED"},
    ]
    for table, rows in ((PRICE, price), (FINANCIALS, financials), (ESTIMATES, estimates)):
        writer.write_table(table, DAY, "f9", stamped(rows, DAY, "f9"))
    store = MemoryConfigStore(
        {
            ("site", "selections", "active"): ACTIVE,
            ("site", "strategies", "cheap_forward"): FORWARD_SCREEN,
        }
    )
    return reader, resolve_config(store, "cheap_forward", UserContext(SITE_USER))


def test_a_hard_criterion_on_forward_pe_is_unknown_for_a_viewer_without_the_licence() -> None:
    """Fix for the risk the licence gate exists for: a trader without the personal licence
    must not get picks decided on FMP's estimates. The holder passes AAA (20 < 25) and rejects
    BBB (40); without the licence every row is UNKNOWN or rejected, nothing passes, and no
    value is read."""
    reader, config = _forward_session()
    both = frozenset({"open", "personal"})
    holder = screen_session(reader, config, DAY, now=T0, held=both)
    assert holder.run.coverage is RunCoverage.COMPLETE
    assert holder.rules is not None and holder.rules.summary.passed == 1
    hidden = screen_session(reader, config, DAY, now=T0, held=frozenset({"open"}))
    assert hidden.rules is not None and hidden.rules.summary.passed == 0
    for row in hidden.rules.rows:
        for result in row.results:
            assert result.outcome.value == "MISSING" and result.value is None
