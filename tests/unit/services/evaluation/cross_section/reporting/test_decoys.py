"""The decoy report: the Jaccard overlap of pick sets at D, averaged over the sessions both
held picks at, and the edge's decile spread less the decoy's (whole history, out of sample)."""

from dataclasses import dataclass
from datetime import date
from typing import Any, cast

import pytest

from algotrade.services.evaluation.cross_section.measures import (
    BASELINE,
    SCREENER,
    Pick,
    SessionStat,
)
from algotrade.services.evaluation.cross_section.reporting.decoys import (
    decoy_overlaps,
    jaccard,
    mean_overlap,
)

D1, D2, D3 = date(2026, 9, 1), date(2026, 9, 2), date(2026, 9, 3)


def stat(day: date, *names: str) -> SessionStat:
    return SessionStat(
        session=day, regime="UNKNOWN", picks=tuple(Pick(n, i) for i, n in enumerate(names, 1))
    )


@dataclass
class Measure:
    slice_kind: str
    decile_spread: float | None


@dataclass
class Result:
    variant: str
    role: str
    stats: tuple[SessionStat, ...]
    measures: tuple[Any, ...]
    edge_variant: str = "main"
    horizon: int = 20


def result(variant: str, role: str, stats: tuple[SessionStat, ...], *spreads: Any) -> Result:
    kinds = ("all", "frozen")
    return Result(
        variant, role, stats, tuple(Measure(k, s) for k, s in zip(kinds, spreads, strict=False))
    )


def test_jaccard_is_shared_over_either_and_none_when_both_are_empty() -> None:
    assert jaccard(["a", "b", "c"], ["b", "c", "d"]) == pytest.approx(0.5)
    assert jaccard(["a"], ["a"]) == 1.0 and jaccard(["a"], ["b"]) == 0.0
    assert jaccard([], ["a"]) == 0.0 and jaccard([], []) is None
    assert jaccard(["a", "a", "b"], ["b"]) == pytest.approx(0.5)  # sets, not lists


def test_the_overlap_is_the_mean_over_sessions_both_held_picks() -> None:
    edge = (stat(D1, "a", "b"), stat(D2, "a", "b"), stat(D3))  # D3: unmeasured, no picks
    decoy = (stat(D1, "a", "b"), stat(D2, "c", "d"), stat(D3, "a"))
    assert mean_overlap(edge, decoy) == (2, 0.5)  # (1.0 + 0.0) / 2; D3 has no edge picks
    assert mean_overlap(edge, ()) == (0, None)
    assert mean_overlap((), decoy) == (0, None)


def test_a_session_one_side_lacks_is_not_counted() -> None:
    assert mean_overlap((stat(D1, "a"), stat(D2, "a")), (stat(D2, "a"),)) == (1, 1.0)


def test_each_screener_is_reported_against_each_decoy_of_its_own_variant_and_horizon() -> None:
    mine = result("momo", SCREENER, (stat(D1, "a", "b"),), 0.05, 0.04)
    near = result("size_small", BASELINE, (stat(D1, "a", "c"),), 0.02, 0.05)
    far = result("beta_low", BASELINE, (stat(D1, "x", "y"),), None, 0.0)
    other = Result("momo", BASELINE, (stat(D1, "a", "b"),), (), edge_variant="cheap")
    other_h = Result("momo", BASELINE, (stat(D1, "a", "b"),), (), horizon=5)
    found = decoy_overlaps(cast(Any, [mine, near, far, other, other_h]))
    assert [(d.screener, d.decoy) for d in found] == [("momo", "size_small"), ("momo", "beta_low")]
    first, second = found
    assert (first.sessions, first.overlap) == (1, pytest.approx(1 / 3))
    assert first.spread_gap == pytest.approx(0.03)
    assert first.spread_gap_oos == pytest.approx(-0.01)  # the decoy did better out of sample
    assert (second.overlap, second.spread_gap, second.spread_gap_oos) == (0.0, None, 0.04)


def test_no_baselines_no_report() -> None:
    assert decoy_overlaps(cast(Any, [result("momo", SCREENER, (stat(D1, "a"),), 0.1, 0.1)])) == ()
