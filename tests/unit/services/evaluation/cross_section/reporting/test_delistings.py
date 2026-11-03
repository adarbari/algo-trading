"""``delistings``: the window's delisted names and the picks' figures with and without the
delisting return (ADR 0087 decision 5), and the DELISTINGS lines of the report."""

from datetime import date
from types import SimpleNamespace
from typing import Any

import pytest

from algotrade.data.listings.basis import BasisCounts
from algotrade.services.evaluation.cross_section.measures import SCREENER, Pick
from algotrade.services.evaluation.cross_section.reporting.delistings import delistings
from algotrade.services.evaluation.cross_section.reporting.report import render_edge_report
from algotrade.services.evaluation.cross_section.run.universe_basis import (
    SURVIVORS,
    UniverseBasis,
)

COUNTS = BasisCounts(
    listing_snapshot=date(2026, 10, 5), delisting_snapshot=date(2026, 10, 30), merged=True,
    listings=10, no_id=0, stocks=9, null_type=0, delisted=4, with_bars=4, unknown=1,
    by_reason={"ACQUIRED": 3, "BANKRUPTCY": 1}, by_basis={"REPLACEMENT": 1, "ZERO_ACQUIRED": 3},
)  # fmt: skip


def _evaluation(picks: list[Pick], stamp: UniverseBasis | None) -> Any:
    leg = SimpleNamespace(stat=SimpleNamespace(picks=tuple(picks)))
    mine = SimpleNamespace(role=SCREENER, variant="momo", horizon=2, legs=(leg,))
    baseline = SimpleNamespace(role="baseline", variant="b", horizon=2, legs=(leg,))
    return SimpleNamespace(results=(mine, baseline), universe_basis=stamp)


PICKS = [
    Pick("EQ:A", 1, "", -0.5, False, delisted=True, delisting_basis="REPLACEMENT",
         zero_value=0.10, zero_hit=True),
    Pick("EQ:B", 2, "", 0.02, True),  # not delisted: its own figures are its zero figures
    Pick("EQ:C", 3, "no_entry_bar"),  # not counted
]  # fmt: skip


def test_the_picks_figures_are_the_headline_beside_the_zero_convention() -> None:
    found = delistings(_evaluation(PICKS, UniverseBasis(SURVIVORS, ("outcomes_not_v3",), COUNTS)))
    assert found["window"] == {
        "delisted": 4, "with_bars": 4, "unknown": 1, "snapshot": "2026-10-30",
        "by_reason": {"ACQUIRED": 3, "BANKRUPTCY": 1},
        "by_basis": {"REPLACEMENT": 1, "ZERO_ACQUIRED": 3},
    }  # fmt: skip
    (momo,) = found["picks"]  # the baseline is not a trial
    assert (momo["picks"], momo["hits"], momo["zero_picks"], momo["zero_hits"]) == (2, 1, 2, 2)
    assert momo["mean_value"] == pytest.approx(-0.24)
    assert momo["mean_zero_value"] == pytest.approx(0.06)
    assert momo["delisted_by_basis"] == {"REPLACEMENT": 1}


def test_a_run_that_read_no_counts_has_no_window_and_a_v2_pick_reads_none() -> None:
    v2 = [Pick("EQ:A", 1, "", 0.01, True, delisted=True)]
    found = delistings(_evaluation(v2, None))
    assert found["window"] is None and found["picks"][0]["delisted_by_basis"] == {"none": 1}


def test_the_report_prints_the_window_and_the_picks_beside_the_zero_figure() -> None:
    found = delistings(_evaluation(PICKS, UniverseBasis(SURVIVORS, ("outcomes_not_v3",), COUNTS)))
    text = render_edge_report(
        {
            "edge": "e", "run_id": "r", "trials": 1, "survivorship": {}, "unclosed_sessions": {},
            "universe_basis": "survivors", "universe_basis_gaps": ["outcomes_not_v3"],
            "delistings": found, "rows": [],
        }
    )  # fmt: skip
    lines = text.splitlines()
    assert "UNIVERSE BASIS: survivors (gaps: outcomes_not_v3)" in lines
    assert any(
        x.startswith("DELISTINGS: 4 names delisted in the window (4 with bars")
        and "by reason: ACQUIRED 3, BANKRUPTCY 1" in x
        for x in lines
    )
    assert any(
        "momo h=2 picked delisted names (REPLACEMENT 1): hit rate 50.0%, with the delisting "
        "return taken out 100.0%" in x
        for x in lines
    )
