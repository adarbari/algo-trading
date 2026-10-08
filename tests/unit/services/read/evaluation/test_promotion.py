"""``promotion_problems`` and ``load_promotion``: a model screener beats the rule screeners only
when, at every horizon, its frozen-slice lift AND decile spread are strictly higher and every
compared row has the quality bar's sessions; anything not stored fails. The reader honours
``promoted`` only then."""

from typing import Any

from algotrade.config.edges.document import MIN_INDEPENDENT_SESSIONS, QUALITY_BAR, parse_edge
from algotrade.services.read.evaluation.promotion import load_promotion, promotion_problems
from algotrade.services.read.evaluation.runs import EdgeRow
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.runs import RunRecord
from algotrade.storage.tables.result_writer import ResultWriter
from tests.helpers.stored_frames import stamped
from tests.unit.services.read.evaluation.conftest import (
    DOCS,
    EDGE,
    END,
    FROZEN,
    START,
    T,
    row,
    stores,
)

N = MIN_INDEPENDENT_SESSIONS


def stored(variant: str, lift: float | None, spread: float | None, **kw: Any) -> EdgeRow:
    base: dict[str, Any] = {
        "edge_variant": "main", "variant": variant, "role": "screener", "horizon_sessions": 20,
        "slice_kind": "frozen", "slice_value": "frozen", "sessions": N, "picks": 100, "hits": 50,
        "trials": 3, "pre_snapshot_sessions": 0, "hit_rate": 0.5, "base_rate": 0.4,
        "lift": lift, "mean_excess_picks": 0.01, "decile_spread": spread, "decile_t": 1.0,
        "effect_size": 0.1, "sharpe": 0.5, "deflated_sharpe": None, "pbo": None,
        "decile_sessions": N,
    }  # fmt: skip
    return EdgeRow(**{**base, **kw})


DOC = {
    **EDGE,
    "screeners": ["momo", "mod"],
    "status": "evidenced",
    "evidence": {"run_id": "r1", "split_from": FROZEN},
    "implementation": {"promoted": "mod"},
}
EDGE_DOC = parse_edge(DOC, "drift", "drift.toml")
RULE = stored("momo", 1.2, 0.010)
assert QUALITY_BAR


def problems(rows: list[EdgeRow], rules: tuple[str, ...] = ("momo",)) -> list[str]:
    return promotion_problems(EDGE_DOC, rows, rules)


def test_a_model_above_the_rule_on_both_numbers_wins() -> None:
    assert problems([RULE, stored("mod", 1.3, 0.020)]) == []


def test_one_number_not_above_is_a_loss() -> None:
    for lift, spread in ((1.3, 0.010), (1.2, 0.020), (1.1, 0.030), (1.4, 0.005)):
        (out,) = problems([RULE, stored("mod", lift, spread)])
        assert "do not both exceed" in out


def test_only_the_frozen_not_in_sample_slice_counts() -> None:
    for changes in ({"slice_kind": "all"}, {"in_sample": True}, {"exploratory": True}):
        assert problems([RULE, stored("mod", 9.0, 9.0, **changes)])  # no row to judge by
    assert problems([RULE, stored("mod", 9.0, 9.0, slice_kind="year")])


def test_too_few_sessions_is_a_failure_for_either_side() -> None:
    assert problems([RULE, stored("mod", 1.3, 0.02, sessions=N - 1)])
    assert problems([RULE, stored("mod", 1.3, 0.02, decile_sessions=N - 1)])
    assert problems([stored("momo", 1.0, 0.0, sessions=N - 1), stored("mod", 1.3, 0.02)])
    assert problems([RULE, stored("mod", 1.3, 0.02, sessions=None)])


def test_a_missing_number_row_horizon_or_rule_is_a_failure() -> None:
    assert problems([RULE, stored("mod", None, 0.02)])
    assert problems([stored("mod", 1.3, 0.02)])  # no rule row
    assert problems([RULE, stored("mod", 1.3, 0.02)], rules=())  # nothing to beat
    two = parse_edge(
        {**DOC, "outcome": {**EDGE["outcome"], "horizon_sessions": [5, 20]}}, "drift", "d.toml"
    )
    assert promotion_problems(two, [RULE, stored("mod", 1.3, 0.02)], ["momo"])  # h=5 missing


def test_it_must_beat_every_rule_screener() -> None:
    rows = [RULE, stored("rule2", 1.5, 0.05), stored("mod", 1.3, 0.02)]
    (problem,) = problems(rows, ("momo", "rule2"))
    assert "rule2" in problem


# --- the reader --------------------------------------------------------------------------------

SCREENERS = {
    **DOCS,
    ("site", "edges", "drift"): DOC,
    ("site", "screeners", "mod@1"): {
        "id": "mod", "kind": "screener", "impl": "model", "version": 1, "selection": "active",
        "score": "feature.edge_score_drift",
    },
}  # fmt: skip


def write(backend: MemoryBackend, model: dict[str, Any]) -> None:
    rows = [
        row("momo", "frozen", 0.5, FROZEN, user_id="site", sessions=N, decile_sessions=N,
            decile_spread=0.010, lift=1.2),
        row("mod", "frozen", 0.5, FROZEN, user_id="site", sessions=N, decile_sessions=N,
            **{"decile_spread": 0.02, "lift": 1.3, **model}),
    ]  # fmt: skip
    frame = stamped(rows, END, "r1", T, "edge-eval")
    writer = ResultWriter(backend)
    stats = {"edge": "drift", "split_from": FROZEN.isoformat(), "exploratory": False,
             "range": [START.isoformat(), END.isoformat()], "trials_counted": 1}  # fmt: skip
    record = RunRecord("r1", "edge-eval:drift:site", END, T)
    done = T
    with writer.publishing("r1", done):
        writer.write_result("edge_eval", END, "r1", frame, pending=True)
        writer.save_run(record.finish(done, complete=True, stats=stats))


def reader(backend: MemoryBackend):  # type: ignore[no-untyped-def]
    ctx = stores(backend)
    object.__setattr__(ctx, "configs", type(ctx.configs)(SCREENERS))
    return ctx


def test_the_reader_honours_promoted_only_when_the_cited_run_shows_it(backend) -> None:  # type: ignore[no-untyped-def]
    write(backend, {})
    p = load_promotion(reader(backend), "drift")
    assert (p.promoted, p.reasons) == ("mod", ())


def test_the_reader_reports_not_promoted_with_the_reasons(backend) -> None:  # type: ignore[no-untyped-def]
    write(backend, {"lift": 1.1})
    p = load_promotion(reader(backend), "drift")
    assert p.promoted is None and "do not both exceed" in p.reasons[0]


def test_an_edge_with_no_stored_run_is_not_promoted(backend) -> None:  # type: ignore[no-untyped-def]
    p = load_promotion(reader(backend), "drift")
    assert p.promoted is None and "not a committed run" in p.reasons[0]


def test_an_edge_that_promotes_nothing_has_no_promotion(backend) -> None:  # type: ignore[no-untyped-def]
    assert load_promotion(stores(backend), "drift").promoted is None
