"""``render_edge_report``: the survivorship line comes first, then one row per variant, horizon
and slice with the independent sessions beside the numbers; a missing number reads ``-``."""

from algotrade.config.user import UserContext
from algotrade.services.evaluation.cross_section.harness import evaluate_edge
from algotrade.services.evaluation.cross_section.report import render_edge_report
from algotrade.services.evaluation.cross_section.results import (
    edge_eval_frame,
    records,
    survivorship,
)
from tests.unit.services.evaluation.cross_section.conftest import AS_OF, DAYS, build_world, edge


def test_the_report_names_survivorship_unclosed_sessions_and_each_slice() -> None:
    w = build_world(snapshot=DAYS[3], closed=DAYS[:6])
    ev = evaluate_edge(
        w.reader, w.results, w.configs, UserContext("site"), edge(), DAYS[0], DAYS[-1], AS_OF
    )
    result = {
        "edge": ev.edge_id, "run_id": "r1", "trials": ev.trials,
        "universe_snapshot": ev.snapshot.isoformat() if ev.snapshot else None,
        "survivorship": {str(h): list(v) for h, v in survivorship(ev).items()},
        "unclosed_sessions": {str(h): n for h, n in ev.unclosed_sessions.items()},
        "rows": records(edge_eval_frame(ev, "r1", AS_OF)),
    }  # fmt: skip
    text = render_edge_report(result)
    lines = text.splitlines()
    assert lines[0] == "# Edge drift (run r1, 1 trials)"
    assert (
        "SURVIVORSHIP: 2 of 3 sessions (h=2) before the first universe snapshot 2026-09-04" in lines
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
