"""``share_classes@v1``: the other listed class of an issuer, from the reference snapshot the
session sees, and the z-score of the pair's price ratio (ADR 0053 amendment, EB H9)."""

from datetime import date

import numpy as np
import pandas as pd

from algotrade.core.time.calendar import sessions_ending
from algotrade.features.rollups.reference import share_classes
from algotrade.features.rollups.reference.share_classes import (
    AMBIGUOUS,
    LOOKBACK,
    PAIRED,
    compute,
    pairs,
)

SESSION = date(2026, 10, 5)


def ref(rows: list[tuple[str, str, str, str]]) -> pd.DataFrame:
    """``(instrument_id, cik, share_class_figi, security_type)`` as a reference snapshot."""
    return pd.DataFrame(rows, columns=["instrument_id", "cik", "share_class_figi", "security_type"])


def bars(closes: dict[str, np.ndarray]) -> pd.DataFrame:
    days = sessions_ending(SESSION, LOOKBACK + 1)
    return pd.DataFrame(
        [
            {"instrument_id": i, "session_date": d, "open": c, "high": c, "low": c, "close": c,
             "volume": 1.0}
            for i, series in closes.items()
            for d, c in zip(days, series, strict=True)
        ]
    )  # fmt: skip


def test_two_classes_of_one_issuer_are_each_others_sibling() -> None:
    found = pairs(
        ref(
            [
                ("EQ:GOOGL", "1652044", "BBG-A", "COMMON_STOCK"),
                ("EQ:GOOG", "1652044", "BBG-C", "COMMON_STOCK"),
                ("EQ:AAPL", "320193", "BBG-AAPL", "COMMON_STOCK"),  # one class: no row
            ]
        )
    ).set_index("instrument_id")
    assert list(found.index) == ["EQ:GOOGL", "EQ:GOOG"]
    assert found.at["EQ:GOOGL", "sibling_id"] == "EQ:GOOG"
    assert found.at["EQ:GOOG", "sibling_id"] == "EQ:GOOGL"
    assert set(found["sibling_status"]) == {PAIRED} and set(found["class_count"]) == {2}


def test_three_classes_or_a_class_under_two_ids_name_no_sibling() -> None:
    found = pairs(
        ref(
            [
                ("EQ:X1", "1", "F1", "COMMON_STOCK"),
                ("EQ:X2", "1", "F2", "COMMON_STOCK"),
                ("EQ:X3", "1", "F3", "COMMON_STOCK"),  # three classes
                ("EQ:Y1", "2", "G1", "COMMON_STOCK"),
                ("EQ:Y2", "2", "G2", "COMMON_STOCK"),
                ("EQ:Y3", "2", "G2", "COMMON_STOCK"),  # G2 is listed under two ids
            ]
        )
    )
    assert set(found["sibling_status"]) == {AMBIGUOUS}
    assert found["sibling_id"].isna().all()  # never a guess
    assert dict(zip(found["instrument_id"], found["class_count"], strict=True))["EQ:X1"] == 3


def test_a_fund_a_preferred_or_a_row_missing_the_issuer_or_class_is_not_a_class() -> None:
    found = pairs(
        ref(
            [
                ("EQ:A", "9", "F1", "COMMON_STOCK"),
                ("EQ:B", "9", "F2", "ETF"),  # an ETF is no share class
                ("EQ:C", "9", "F3", "PREFERRED"),
                ("EQ:D", "", "F4", "COMMON_STOCK"),  # no issuer id
                ("EQ:E", "9", None, "COMMON_STOCK"),  # no class id
            ]
        )
    )
    assert found.empty


def test_a_reference_without_the_columns_has_no_pairs() -> None:
    assert pairs(pd.DataFrame({"instrument_id": ["EQ:A"]})).empty


def test_the_sibling_is_the_one_of_the_snapshot_the_session_sees() -> None:
    """A reclassification: the reference at the earlier session pairs A with B, the later one A
    with C. Each session's rows are computed from its own snapshot, so a leg at the earlier D
    reads B, never today's C."""
    before = ref([("EQ:A", "1", "F1", "COMMON_STOCK"), ("EQ:B", "1", "F2", "COMMON_STOCK"),
                  ("EQ:C", "2", "F3", "COMMON_STOCK")])  # fmt: skip
    after = ref([("EQ:A", "2", "F1", "COMMON_STOCK"), ("EQ:B", "1", "F2", "COMMON_STOCK"),
                 ("EQ:C", "2", "F3", "COMMON_STOCK")])  # fmt: skip
    one = compute({share_classes.REFERENCE: before, share_classes.BARS: None}, SESSION, None)
    two = compute({share_classes.REFERENCE: after, share_classes.BARS: None}, SESSION, None)
    assert dict(zip(one["instrument_id"], one["sibling_id"], strict=True))["EQ:A"] == "EQ:B"
    assert dict(zip(two["instrument_id"], two["sibling_id"], strict=True))["EQ:A"] == "EQ:C"


def test_the_spread_z_score_is_negative_for_the_cheap_class_and_mirrored_for_the_sibling() -> None:
    n = LOOKBACK + 1
    rng = np.random.default_rng(1)
    base = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    gap = np.exp(rng.normal(0, 0.01, n))
    rich = base * gap
    rich[-1] = base[-1] * 1.05  # today the first class is 5% above its usual gap
    inputs = {
        share_classes.REFERENCE: ref(
            [("EQ:A", "1", "F1", "COMMON_STOCK"), ("EQ:B", "1", "F2", "COMMON_STOCK")]
        ),
        share_classes.BARS: bars({"EQ:A": rich, "EQ:B": base}),
    }
    out = compute(inputs, SESSION, None).set_index("instrument_id")
    z = out["spread_z_252d"].astype(float)
    assert z["EQ:A"] > 2 and np.isclose(z["EQ:A"], -z["EQ:B"])  # B is the cheap one
    assert list(out["sibling_status"]) == [PAIRED, PAIRED]


def test_a_thin_history_or_a_flat_ratio_has_no_z_score_never_a_zero() -> None:
    n = LOOKBACK + 1
    flat = np.full(n, 10.0)
    full = pd.DataFrame(
        compute(
            {
                share_classes.REFERENCE: ref(
                    [("EQ:A", "1", "F1", "COMMON_STOCK"), ("EQ:B", "1", "F2", "COMMON_STOCK")]
                ),
                share_classes.BARS: bars({"EQ:A": flat, "EQ:B": flat}),
            },
            SESSION,
            None,
        )
    )
    assert full["spread_z_252d"].isna().all()  # no spread
    thin_a = np.full(n, np.nan)
    thin_a[-50:] = 10.0 + np.arange(50) * 0.01
    thin = compute(
        {
            share_classes.REFERENCE: ref(
                [("EQ:A", "1", "F1", "COMMON_STOCK"), ("EQ:B", "1", "F2", "COMMON_STOCK")]
            ),
            share_classes.BARS: bars({"EQ:A": thin_a, "EQ:B": np.linspace(9, 11, n)}),
        },
        SESSION,
        None,
    )
    assert thin["spread_z_252d"].isna().all()
