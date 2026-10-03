from datetime import date, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from algotrade.core.model.options import OptionRight, third_friday
from algotrade.features.registry import GROUPS
from algotrade.features.rollups import option_liquidity as liq
from tests.unit.features import legacy_reference

SESSION = date(2026, 10, 2)
P = liq.LiquidityParams()


def c(
    expiry: date,
    right: str,
    strike: float,
    bid: float,
    ask: float,
    oi: float = 1000,
    delta: float | None = -0.3,
    volume: float = 10,
) -> liq.Contract:
    return liq.Contract(expiry, OptionRight(right), strike, bid, ask, oi, volume, delta)


def test_target_expiry_prefers_standard_monthly_in_window() -> None:
    nov_monthly, nov_weekly = date(2026, 11, 20), date(2026, 11, 6)  # 49 and 35 DTE
    assert liq.choose_target_expiry([nov_weekly, nov_monthly], SESSION, P) == nov_monthly


def test_target_expiry_fallbacks() -> None:
    weekly = date(2026, 11, 6)
    assert liq.choose_target_expiry([weekly, date(2026, 10, 9)], SESSION, P) == weekly
    far = date(2027, 1, 15)
    assert liq.choose_target_expiry([far, date(2026, 10, 9)], SESSION, P) == far
    assert liq.choose_target_expiry([date(2026, 10, 9)], SESSION, P) is None


def test_pick_tightest_spread_in_band_then_higher_oi() -> None:
    e = date(2026, 11, 20)
    side = liq.assess_side(
        [
            c(e, "P", 90, 1.00, 1.10, oi=50, delta=-0.25),
            c(e, "P", 95, 2.00, 2.20, oi=900, delta=-0.33),  # same relative spread, more OI
            c(e, "P", 85, 0.50, 0.70, oi=5000, delta=-0.18),  # outside pick band, inside zone
            c(e, "P", 80, 0.20, 0.30, delta=None),
        ],
        P,
    )
    assert side["strike"] == 95
    assert side["zone_oi"] == 5950
    assert side["missing_delta"] == 1


def test_pick_falls_back_to_closest_delta_and_handles_no_quotes() -> None:
    e = date(2026, 11, 20)
    fallback = liq.assess_side(
        [c(e, "P", 80, 0.2, 0.3, delta=-0.10), c(e, "P", 70, 0.1, 0.2, delta=-0.05)], P
    )
    assert fallback["strike"] == 80
    unquoted = liq.assess_side([c(e, "P", 80, 0.0, 0.3)], P)
    assert "bid" not in unquoted
    assert liq.tier_for(unquoted, 10**6, P) == "D"


@pytest.mark.parametrize(
    ("spread_pct", "spread_abs", "zone_oi", "chain_oi", "bid", "expected"),
    [
        (0.04, 0.5, 2000, 20000, 0.25, "A"),
        (0.5, 0.03, 2000, 20000, 0.25, "A"),
        (0.08, 0.5, 2000, 20000, 0.25, "B"),
        (0.04, 0.5, 400, 20000, 0.25, "C"),
        (0.04, 0.5, 2000, 900, 0.25, "D"),
        (0.30, 0.5, 2000, 20000, 0.25, "D"),
    ],
)
def test_tiers(
    spread_pct: float, spread_abs: float, zone_oi: int, chain_oi: int, bid: float, expected: str
) -> None:
    side = {"spread_pct": spread_pct, "spread_abs": spread_abs, "zone_oi": zone_oi, "bid": bid}
    assert liq.tier_for(side, chain_oi, P) == expected


def test_assess_statuses_and_dte_from_session() -> None:
    assert liq.assess([], SESSION, P)["liq_status"] == "NO_STANDARD_SERIES"
    near = liq.assess([c(date(2026, 10, 9), "P", 90, 1, 1.1)], SESSION, P)
    assert near["liq_status"] == "NO_TARGET_EXPIRY"
    e = date(2026, 11, 20)
    row = liq.assess(
        [
            c(e, "P", 95, 2.0, 2.05, oi=30000, delta=-0.3),
            c(e, "C", 105, 2.0, 2.05, oi=30000, delta=0.3),
        ],
        SESSION,
        P,
    )
    assert row["target_dte"] == 49  # measured from the session, not today's date
    assert (row["put_tier"], row["call_tier"]) == ("A", "A")
    assert row["short_put_ok"] and row["short_call_ok"]


def test_contracts_from_rows_normalises_types() -> None:
    from datetime import datetime  # noqa: PLC0415

    rows = [
        {
            "expiry": datetime(2026, 11, 20),  # noqa: DTZ001 - as parquet may return it
            "right": "P",
            "strike": 95,
            "bid": None,
            "ask": 1.0,
            "open_interest": float("nan"),
            "volume": 3,
            "delta": float("nan"),
        },
        {
            "expiry": "2026-11-20",
            "right": "C",
            "strike": 95,
            "bid": 1,
            "ask": 1.1,
            "open_interest": 1,
            "volume": 1,
            "delta": 0.3,
        },
    ]
    a, b = liq.contracts_from_rows(rows)
    assert a.expiry == b.expiry == date(2026, 11, 20)
    assert (a.bid, a.open_interest, a.delta) == (0.0, 0.0, None)
    assert b.delta == 0.3


def test_registered() -> None:
    assert GROUPS["option_liquidity@v1"].table == "rollups/instrument/option_liquidity@v1"


# ----------------------------------------------------------------- equivalence with the original
monthlies = [third_friday(2026, m) for m in (10, 11, 12)] + [third_friday(2027, 1)]
weeklies = [m + timedelta(days=7) for m in monthlies]
quote = st.tuples(
    st.sampled_from(monthlies + weeklies),
    st.sampled_from(["C", "P"]),
    st.integers(50, 150),
    st.floats(0.0, 5.0),
    st.floats(0.0, 1.0),
    st.integers(0, 5000),
    st.floats(0.01, 0.99),
)


@given(st.lists(quote, min_size=1, max_size=60, unique_by=lambda q: (q[0], q[1], q[2])))
def test_port_matches_original_selection(quotes: list[tuple]) -> None:  # type: ignore[type-arg]
    """On standard monthly/weekly expiries the port picks the same expiry, strikes and tiers.

    The original broke exact ties by feed order; the port breaks them by lower strike so the
    result does not depend on how the vendor orders its response. Feeding the original rows
    sorted by strike makes the two comparable.
    """
    legacy_rows, contracts = [], []
    for exp, cp, k, bid, width, oi, d in sorted(quotes, key=lambda q: (q[0], q[2], q[1])):
        delta = d if cp == "C" else -d
        legacy_rows.append(
            {
                "exp": exp,
                "cp": cp,
                "k": float(k),
                "bid": round(bid, 2),
                "ask": round(bid + width, 2),
                "oi": oi,
                "vol": 0,
                "delta": delta,
            }
        )
        contracts.append(c(exp, cp, float(k), round(bid, 2), round(bid + width, 2), oi, delta))
    old = legacy_reference.analyse(legacy_rows, SESSION)
    new = liq.assess(contracts, SESSION, P)
    assert new.get("target_expiry") == old["target_expiry"]
    for side in ("put", "call"):
        assert new[f"{side}_tier"] == old[f"{side}_tier"]
        assert new.get(f"{side}_strike") == old[f"{side}_strike"]
