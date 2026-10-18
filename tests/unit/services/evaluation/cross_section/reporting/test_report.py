"""``render_edge_report``: the survivorship line comes first, then one row per variant, horizon
and slice with the independent sessions beside the numbers; a missing number reads ``-``."""

from algotrade.config.user import UserContext
from algotrade.services.evaluation.cross_section.harness import evaluate_edge
from algotrade.services.evaluation.cross_section.reporting.report import render_edge_report
from algotrade.services.evaluation.cross_section.results import (
    edge_eval_frame,
    historical_identity,
    records,
)
from tests.unit.services.evaluation.cross_section.conftest import (
    AS_OF,
    DAYS,
    build_world,
    edge,
    with_listing_history,
)


def test_the_report_names_survivorship_unclosed_sessions_and_each_slice() -> None:
    w = with_listing_history(build_world(snapshot=DAYS[3], closed=DAYS[:6]), DAYS[3])
    ev = evaluate_edge(
        w.reader, w.results, w.configs, UserContext("site"), edge(), DAYS[0], DAYS[-1], AS_OF
    )
    result = {
        "edge": ev.edge_id, "run_id": "r1", "trials": ev.trials,
        "universe_snapshot": ev.snapshot.isoformat() if ev.snapshot else None,
        "survivorship": {"2": [2, 3]},  # a store with no listing history (not built here)
        "historical_identity": historical_identity(ev),
        "unclosed_sessions": {str(h): n for h, n in ev.unclosed_sessions.items()},
        "rows": records(edge_eval_frame(ev, "r1", AS_OF)),
    }  # fmt: skip
    text = render_edge_report(result)
    lines = text.splitlines()
    assert lines[0] == "# Edge drift (run r1, 1 trials)"
    assert (
        "SURVIVORSHIP: 2 of 3 sessions (h=2) before the first universe snapshot 2026-09-04" in lines
    )
    assert any(
        x.startswith("HISTORICAL IDENTITY: 2 sessions before the first reference") for x in lines
    )
    assert "UNCLOSED: 1 start sessions at h=2 have no closed window" in lines
    row = next(line for line in lines if "momo" in line and "all=all" in line)
    assert "| 3 | 15 | 100.0% | 50.0% | 2.00 |" in row  # sessions, picks, hit, base, lift
    assert row.rstrip().endswith("| - | - |")  # no deflated Sharpe or PBO with three sessions


def test_an_exploratory_run_is_labelled_in_the_header_and_each_slice() -> None:
    row = {"slice_kind": "split", "slice_value": "split", "exploratory": True, "variant": "v"}
    result = {
        "edge": "e", "run_id": "r", "trials": 1, "survivorship": {}, "unclosed_sessions": {},
        "universe_snapshot": None, "rows": [row], "exploratory": True, "split_from": "2026-06-01",
    }  # fmt: skip
    text = render_edge_report(result)
    assert "EXPLORATORY: test split from 2026-06-01" in text
    assert "split=split (EXPLORATORY)" in text


def test_an_iv_field_with_no_value_in_range_is_a_line_beside_the_zeros() -> None:
    gap = {
        "variant": "our_iv30/vrp_rich", "horizon": 15, "field": "rollup.iv30@v1.iv30",
        "sessions": 31, "stored": 0, "picks": 155,
    }  # fmt: skip
    result = {
        "edge": "e", "run_id": "r", "trials": 1, "survivorship": {}, "unclosed_sessions": {},
        "universe_snapshot": None, "rows": [], "iv_coverage": [gap],
    }  # fmt: skip
    assert (
        "IV FIELD: our_iv30/vrp_rich h=15 reads rollup.iv30@v1.iv30, which has a value at 0 of "
        "31 measured sessions; 155 picks excluded for no implied vol (not misses)"
    ) in render_edge_report(result).splitlines()


def test_each_decoy_reads_as_a_line_with_its_overlap_and_spread_gap() -> None:
    result = {
        "edge": "drift", "run_id": "r1", "trials": 1, "universe_snapshot": None,
        "survivorship": {}, "unclosed_sessions": {}, "rows": [],
        "decoys": [
            {"edge_variant": "main", "horizon": 20, "screener": "momo", "decoy": "size_small",
             "sessions": 9, "overlap": 0.25, "spread_gap": 0.0312, "spread_gap_oos": None},
            {"edge_variant": "main", "horizon": 20, "screener": "momo", "decoy": "beta_low",
             "sessions": 0, "overlap": None, "spread_gap": None, "spread_gap_oos": -0.01},
        ],
    }  # fmt: skip
    lines = render_edge_report(result).splitlines()
    assert (
        "DECOY: main/momo vs size_small h=20: pick overlap 0.25 (Jaccard at D, 9 sessions); "
        "spread less the decoy's +0.0312 all, - out of sample"
    ) in lines
    assert any(
        "vs beta_low" in line and "overlap - (" in line and "-0.0100 out of sample" in line
        for line in lines
    )
