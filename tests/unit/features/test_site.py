"""The site's expression features (``config/site/features/*.toml``) as ``site_features``
builds them: the liquidity class reproduces ``liquidity_class@v1`` on its scenarios (each
threshold decides, the worse option tier counts, unknown inputs give UNKNOWN only when they
could change the class), the price, volatility and fundamentals formulas, and the moved
features reproduce their v1 values on golden data."""

import dataclasses

import numpy as np
import pandas as pd
import pytest

from algotrade.data import StoreReader
from algotrade.features.expressions.feature_set import FeatureSet
from algotrade.features.framework.declaration import FeatureGroup
from algotrade.features.framework.runner import SessionResult, compute_in_memory
from algotrade.features.site import site_features
from algotrade.storage.configs.files import FileConfigStore
from tests.conftest import REPO_ROOT
from tests.helpers.features_v1 import liquidity_class_v1, moved_numbers_v1
from tests.helpers.rollup_store import END

PRICE_STATS = "rollups/instrument/price_stats@v2"
OPTIONS = "rollups/instrument/option_liquidity@v1"
STATS = {  # id: (adv_usd_20d, close)
    "EQ:BIG": (500e6, 150.0),
    "EQ:PUTONLY": (500e6, 150.0),
    "EQ:MID": (20e6, 30.0),
    "EQ:PENNY": (500e6, 2.0),
    "EQ:NOOPT": (500e6, 150.0),
    "EQ:FAILED": (500e6, 150.0),
    "EQ:FAILEDSMALL": (1e6, 150.0),
    "EQ:NOADV": (np.nan, 150.0),
}
OPTION_ROWS = {  # id: (liq_status, put_tier, call_tier, chain_oi, chain_volume)
    "EQ:BIG": ("OK", "A", "A", 900_000, 90_000),
    "EQ:PUTONLY": ("OK", "A", "C", 900_000, 90_000),
    "EQ:MID": ("OK", "B", "A", 20_000, 100),
    "EQ:PENNY": ("OK", "A", "A", 900_000, 90_000),
    "EQ:FAILED": ("FETCH_ERROR", "D", "D", None, None),
    "EQ:FAILEDSMALL": ("FETCH_ERROR", "D", "D", None, None),
    "EQ:NOADV": ("OK", "A", "A", 900_000, 90_000),
}
OPTION_COLUMNS = ("liq_status", "put_tier", "call_tier", "chain_oi", "chain_volume")
OPTION_COLUMNS = ("liq_status", "put_tier", "call_tier", "chain_oi", "chain_volume")
LIQUIDITY = ["liquidity_class", "option_tier", "option_chain_oi"]


@pytest.fixture(scope="module")
def fs() -> FeatureSet:
    return site_features(FileConfigStore(REPO_ROOT / "config"))


def _frames(with_options: bool = True) -> dict[str, pd.DataFrame | None]:
    stats = pd.DataFrame(
        {
            "instrument_id": list(STATS),
            "session_date": END,
            "adv_usd_20d": [v[0] for v in STATS.values()],
            "close": [v[1] for v in STATS.values()],
        }
    )
    options = pd.DataFrame(
        [
            {"instrument_id": k, "session_date": END, **dict(zip(OPTION_COLUMNS, v, strict=True))}
            for k, v in OPTION_ROWS.items()
        ]
    )
    return {PRICE_STATS: stats, OPTIONS: options if with_options else None}


def test_liquidity_class_reproduces_v1(fs: FeatureSet) -> None:
    out = fs.evaluate(_frames(), LIQUIDITY).set_index("instrument_id")
    assert out["liquidity_class"].to_dict() == {
        "EQ:BIG": "HIGH",
        "EQ:PUTONLY": "LOW",  # worse tier C: below MEDIUM's A,B
        "EQ:MID": "MEDIUM",
        "EQ:PENNY": "LOW",
        "EQ:NOOPT": "LOW",  # not in the chain run: no options
        "EQ:FAILED": "UNKNOWN",  # options unknown and could make it HIGH
        "EQ:FAILEDSMALL": "LOW",  # too small for MEDIUM whatever the options
        "EQ:NOADV": "UNKNOWN",
    }
    assert out.loc["EQ:PUTONLY", "option_tier"] == "C" and out.loc["EQ:NOOPT", "option_tier"] == "D"
    assert out.loc["EQ:NOOPT", "option_chain_oi"] == 0
    assert pd.isna(out.loc["EQ:FAILED", "option_tier"])
    assert pd.isna(out.loc["EQ:FAILED", "option_chain_oi"])
    assert str(out["option_chain_oi"].dtype) == "int64[pyarrow]"


def test_no_chain_run_is_unknown_not_no_options(fs: FeatureSet) -> None:
    out = fs.evaluate(_frames(with_options=False), LIQUIDITY).set_index("instrument_id")
    assert out.loc["EQ:NOOPT", "liquidity_class"] == "UNKNOWN"  # could be HIGH
    assert out.loc["EQ:FAILEDSMALL", "liquidity_class"] == "LOW"  # too small anyway
    assert out["option_tier"].isna().all()


def test_an_instrument_with_options_but_no_bar_has_no_class(fs: FeatureSet) -> None:
    frames = _frames()
    stats = frames[PRICE_STATS]
    assert stats is not None
    frames[PRICE_STATS] = stats[stats["instrument_id"] != "EQ:BIG"]
    out = fs.evaluate(frames, ["liquidity_class"]).set_index("instrument_id")
    assert pd.isna(out.loc["EQ:BIG", "liquidity_class"])


def test_price_and_volatility_expressions(fs: FeatureSet) -> None:
    stats = pd.DataFrame(
        {
            "instrument_id": ["EQ:A", "EQ:B", "EQ:C", "EQ:D"],
            "session_date": END,
            "close": [95.0, 50.0, 20.0, 10.0],
            "high_52w": [100.0, 100.0, 21.0, np.nan],
            "low_52w": [50.0, 48.0, 19.0, np.nan],
            "hv30": [0.2, 0.0, 0.3, np.nan],
        }
    ).astype({"close": "float32", "high_52w": "float32", "low_52w": "float32"})
    ivs = pd.DataFrame({"instrument_id": ["EQ:A", "EQ:B"], "session_date": END, "iv30": [0.3, 0.4]})
    frames = {PRICE_STATS: stats, "rollups/instrument/iv_history@v2": ivs}
    out = fs.evaluate(
        frames, ["pct_from_high_52w", "near_52w", "iv_hv_spread", "iv_hv_ratio"]
    ).set_index("instrument_id")
    assert out.loc["EQ:A", "pct_from_high_52w"] == pytest.approx(-0.05)
    assert out["near_52w"].to_dict() == {
        "EQ:A": "HIGH",
        "EQ:B": "LOW",
        "EQ:C": "BOTH",
        "EQ:D": None,
    }
    assert out.loc["EQ:A", "iv_hv_spread"] == pytest.approx(0.1)
    assert out.loc["EQ:A", "iv_hv_ratio"] == pytest.approx(1.5)
    assert pd.isna(out.loc["EQ:B", "iv_hv_ratio"])  # hv30 is 0
    assert pd.isna(out.loc["EQ:C", "iv_hv_spread"])  # no IV


def test_market_cap_and_the_materialised_dividend_yield(fs: FeatureSet) -> None:
    stats = pd.DataFrame({"instrument_id": ["EQ:A", "EQ:B"], "session_date": END,
                          "close": [100.0, 0.0]})  # fmt: skip
    fundamentals = pd.DataFrame(
        {
            "instrument_id": ["EQ:A", "EQ:B"],
            "session_date": END,
            "shares_outstanding": [1e9, 5e8],
            "market_cap_status": ["OK", "NO_PRICE"],
        }
    )
    dividends = pd.DataFrame({"instrument_id": ["EQ:A", "EQ:B"], "session_date": END,
                              "div_ttm": [2.0, 1.0]})  # fmt: skip
    frames = {
        PRICE_STATS: stats,
        "rollups/instrument/fundamentals@v2": fundamentals,
        "rollups/instrument/dividends@v2": dividends,
    }
    out = fs.evaluate(frames, ["market_cap", "div_yield"], compute=["div_yield"])
    out = out.set_index("instrument_id")
    assert out.loc["EQ:A", "market_cap"] == pytest.approx(1e11)
    assert pd.isna(out.loc["EQ:B", "market_cap"])
    assert out.loc["EQ:A", "div_yield"] == pytest.approx(0.02)
    assert pd.isna(out.loc["EQ:B", "div_yield"])  # close not positive
    assert str(out["div_yield"].dtype) == "float32"
    assert fs.expressions["div_yield"].materialise
    assert fs.table("div_yield") == "rollups/instrument/div_yield@v1"
    assert "div_yield@v1" in fs.groups and fs.stored_columns(["div_yield"]) == {
        "rollups/instrument/div_yield@v1": {"div_yield"}
    }


def _float64(group: FeatureGroup) -> FeatureGroup:
    """The v1 precision of a v2 group: its float32 columns as float64."""
    wide = tuple(dataclasses.replace(f, dtype="float") if f.dtype == "float32" else f
                 for f in group.features)  # fmt: skip
    return dataclasses.replace(group, features=wide)


def _computed(
    results: dict[str, list[SessionResult]], groups: list[FeatureGroup]
) -> dict[str, pd.DataFrame | None]:
    out: dict[str, pd.DataFrame | None] = {}
    for g in groups:
        parts = [
            r.frame.assign(session_date=r.session) for r in results[g.key] if r.frame is not None
        ]
        out[g.table] = pd.concat(parts, ignore_index=True) if parts else None
    return out


def test_moved_features_reproduce_v1_on_golden_data(
    fs: FeatureSet, golden_reader: StoreReader
) -> None:
    """Labels exactly, numbers within float32 tolerance, nulls in the same places."""
    sessions = golden_reader.dates("bars/1d")[-25:]
    v2 = [
        fs.groups[k] for k in ("price_stats@v2", "dividends@v2", "fundamentals@v2", "div_yield@v1")
    ]
    stored = _computed(compute_in_memory(golden_reader, v2, sessions), v2)
    v1 = [_float64(g) for g in v2[:3]]
    exact = _computed(compute_in_memory(golden_reader, v1, sessions), v1)
    keys = ["session_date", "instrument_id"]
    ps, dv, fu = (exact[g.table] for g in v1)
    assert ps is not None and dv is not None and fu is not None
    reference = (
        ps.merge(dv[[*keys, "div_ttm"]], on=keys)
        .merge(fu[[*keys, "shares_outstanding", "market_cap_status"]], on=keys, how="left")
        .assign(iv30=np.nan)
    )
    want = moved_numbers_v1(reference.set_index(keys))
    names = ["pct_from_high_52w", "pct_from_low_52w", "div_yield", "market_cap", "liquidity_class"]
    got = fs.evaluate(stored, names).set_index(keys).reindex(want.index)
    for name in ("pct_from_high_52w", "pct_from_low_52w", "div_yield", "market_cap"):
        a, b = got[name].to_numpy(dtype=float), want[name].to_numpy(dtype=float)
        assert (np.isnan(a) == np.isnan(b)).all(), name
        assert np.allclose(a[~np.isnan(a)], b[~np.isnan(b)], rtol=1e-6, atol=1e-7), name
    assert got["pct_from_high_52w"].notna().sum() > 0 and got["div_yield"].notna().sum() > 0
    classes = pd.concat([liquidity_class_v1(ps, None, day) for day in sessions])
    assert (got["liquidity_class"].droplevel(0).to_numpy() == classes.to_numpy()).all()
    assert set(classes) <= {"LOW", "UNKNOWN"}  # golden data has no option chains


def test_vrp_iv30_is_the_lower_source_and_its_ratios(fs: FeatureSet) -> None:
    ids = ["EQ:BOTH", "EQ:IBLOW", "EQ:CBOE", "EQ:IBKR", "EQ:NONE", "EQ:FLAT"]
    stats = pd.DataFrame(
        {
            "instrument_id": ids,
            "session_date": END,
            "hv30": [0.4, 0.4, 0.4, np.nan, 0.4, 0.0],
        }
    ).astype({"hv30": "float32"})
    cboe = pd.DataFrame(
        {
            "instrument_id": ["EQ:BOTH", "EQ:IBLOW", "EQ:CBOE", "EQ:NONE", "EQ:FLAT"],
            "session_date": END,
            "iv30_cboe": [0.55, 0.70, 0.60, np.nan, 0.5],
        }
    )
    ibkr = pd.DataFrame(
        {"instrument_id": ["EQ:BOTH", "EQ:IBLOW", "EQ:IBKR"], "session_date": END}
    ).assign(iv30_ibkr=np.array([0.65, 0.50, 0.80], dtype="float32"))
    frames = {
        PRICE_STATS: stats,
        "rollups/instrument/iv30@v1": cboe,
        "rollups/instrument/ibkr_iv@v1": ibkr,
    }
    names = ["vrp_iv30", "vrp_iv30_source", "vrp_iv_hv_spread", "vrp_iv_hv_ratio"]
    out = fs.evaluate(frames, names).set_index("instrument_id")
    iv = out["vrp_iv30"]
    assert iv["EQ:BOTH"] == pytest.approx(0.55)  # the lower of the two
    assert iv["EQ:IBLOW"] == pytest.approx(0.50)
    assert iv["EQ:CBOE"] == pytest.approx(0.60)  # whichever exists
    assert iv["EQ:IBKR"] == pytest.approx(0.80)
    assert pd.isna(iv["EQ:NONE"])  # neither: UNKNOWN
    assert out["vrp_iv30_source"].to_dict() == {
        "EQ:BOTH": "cboe",
        "EQ:IBLOW": "ibkr",
        "EQ:CBOE": "cboe",
        "EQ:IBKR": "ibkr",
        "EQ:NONE": None,
        "EQ:FLAT": "cboe",
    }
    assert out.loc["EQ:BOTH", "vrp_iv_hv_spread"] == pytest.approx(0.15)
    assert out.loc["EQ:BOTH", "vrp_iv_hv_ratio"] == pytest.approx(0.55 / 0.4)
    assert pd.isna(out.loc["EQ:IBKR", "vrp_iv_hv_spread"])  # no HV30
    assert pd.isna(out.loc["EQ:FLAT", "vrp_iv_hv_ratio"])  # HV30 0: missing, no floor
    assert out.loc["EQ:FLAT", "vrp_iv_hv_spread"] == pytest.approx(0.5)
    assert {fs.expressions[n].feature.licence for n in names} == {"personal"}  # IBKR input


def test_distance_to_52w_extreme_and_moving_averages(fs: FeatureSet) -> None:
    stats = pd.DataFrame(
        {
            "instrument_id": ["EQ:A", "EQ:B", "EQ:C"],
            "session_date": END,
            "close": [95.0, 52.0, 30.0],
            "high_52w": [100.0, 100.0, np.nan],
            "low_52w": [50.0, 50.0, 20.0],
            "sma_20": [100.0, 40.0, 30.0],
            "sma_50": [95.0, np.nan, 25.0],
            "sma_200": [50.0, 52.0, 60.0],
        }
    ).astype("float32", errors="ignore")
    names = ["dist_52w", "pct_vs_sma_20", "pct_vs_sma_50", "pct_vs_sma_200"]
    out = fs.evaluate({PRICE_STATS: stats}, names).set_index("instrument_id")
    assert out.loc["EQ:A", "dist_52w"] == pytest.approx(0.05)  # 5% under the high
    assert out.loc["EQ:B", "dist_52w"] == pytest.approx(0.04)  # 4% over the low
    assert pd.isna(out.loc["EQ:C", "dist_52w"])  # no 52-week high
    assert out.loc["EQ:A", "pct_vs_sma_20"] == pytest.approx(-0.05)
    assert out.loc["EQ:B", "pct_vs_sma_20"] == pytest.approx(0.3)
    assert pd.isna(out.loc["EQ:B", "pct_vs_sma_50"])
    assert out.loc["EQ:C", "pct_vs_sma_200"] == pytest.approx(-0.5)
