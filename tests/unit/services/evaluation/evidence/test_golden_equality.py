"""The golden edges' scores are the same with and without the trade contract (ADR 0088, 2.5a,
risk 19): per outcome kind on the small world, a digest of every ``edge_eval`` column and of the
ledger columns that existed before E6a, and the time series' measures. Pinned in the commit that
precedes the contract, on unmodified code. A digest that changes is a defect, never a re-pin."""

import hashlib
from datetime import date
from typing import Any

import pandas as pd
import pytest

from algotrade.config.user import UserContext
from algotrade.services.evaluation.cross_section.detail.trades import trades_frame
from algotrade.services.evaluation.cross_section.harness import EdgeEvaluation, evaluate_edge
from algotrade.services.evaluation.cross_section.legs import key
from algotrade.services.evaluation.cross_section.results import edge_eval_frame
from algotrade.services.evaluation.time_series.evaluate import evaluate_time_series
from tests.helpers.stored_frames import stamped
from tests.unit.services.evaluation.cross_section.conftest import (
    AS_OF,
    DAYS,
    World,
    build_world,
    edge,
)
from tests.unit.services.evaluation.cross_section.portfolio.test_book import _book
from tests.unit.services.evaluation.cross_section.test_harness import OTM_OUTCOME, otm_world
from tests.unit.services.evaluation.cross_section.test_harness_trials import (
    CHAIN_OUTCOME,
    PAIR_OUTCOME,
    _sided,
    _with_chain_outcomes,
    pair_world,
)
from tests.unit.services.evaluation.time_series import conftest as ts
from tests.unit.services.evaluation.time_series.conftest import timed_edge

STAMPS = {"run_id", "knowledge_ts", "ts"}
# the ledger's columns before E6a (the contract adds more; ``value_licence`` is per row now)
LEDGER = [
    "edge_id", "user_id", "edge_variant", "variant", "side", "role", "config_hash",
    "run_config_hash", "benchmark", "horizon_sessions", "range_from", "range_to", "split_from",
    "exploratory", "decision_session", "entry_session", "exit_session", "before_split",
    "instrument_id", "rank", "score", "value", "gross_value", "hit", "status", "excluded_reason",
    "delisted", "max_drawdown", "adv_usd_20d", "reference", "touch", "licence", "score_licence",
    "adv_licence", "session_date", "source",
]  # fmt: skip
VRP = {
    "kind": "hit_target", "horizon_sessions": [2], "benchmark": "none", "target": 1.0,
    "measure": "realised_to_implied_vol", "direction": "below", "start_offset_sessions": 1,
}  # fmt: skip


def _digest(frame: pd.DataFrame, columns: list[str] | None = None) -> str:
    cols = [c for c in (columns or list(frame.columns)) if c not in STAMPS]
    out = frame[cols].copy()
    for c in cols:
        if pd.api.types.is_float_dtype(out[c]):
            out[c] = out[c].round(12)
    text = out.astype(str)
    text = text.sort_values(cols, kind="stable").reset_index(drop=True)
    return hashlib.sha256(text.to_csv().encode()).hexdigest()[:16]


def _run(w: World, e: Any) -> EdgeEvaluation:
    return evaluate_edge(
        w.reader, w.results, w.configs, UserContext("site"), e, DAYS[0], DAYS[-1], AS_OF
    )


def _vrp_world() -> World:
    w = build_world()
    for day in DAYS:
        iv = [{"instrument_id": f"EQ:N{i:02d}", "iv30": 0.4} for i in range(20)]
        w.writer.write_table(
            "rollups/instrument/iv30@v1", day, f"iv-{day}", stamped(iv, day, f"iv-{day}")
        )
    return w


def _evaluations() -> dict[str, EdgeEvaluation]:
    return {
        "long": _run(build_world(), edge(top_k=5)),
        "short": _sided("short"),
        "long_short": _sided("long_short", borrow_bps_annual=252),
        "hit_target": _run(_vrp_world(), edge(outcome=VRP)),
        "expires_otm": _run(otm_world(), edge(outcome=OTM_OUTCOME)),
        "option_pnl": _run(_with_chain_outcomes(build_world()), edge(outcome=CHAIN_OUTCOME)),
        "pair_spread": _run(pair_world(), edge(outcome=PAIR_OUTCOME)),
        "portfolio_return": _book(),
    }


DIGESTS: dict[str, tuple[str, str]] = {  # (edge_eval, ledger), computed on origin/main
    "long": ("30495083693dc0dd", "5ec1257fbe0a795f"),
    "short": ("8a5be54b65cf7448", "60c7f37dd4cdaa30"),
    "long_short": ("2f02dfade59107a7", "5625c55ec76c7220"),
    "hit_target": ("4fa2a61dac328851", "ab73369e4bc0aff1"),
    "expires_otm": ("22d2faaee8d62085", "d92e6cd61083351c"),
    "option_pnl": ("3fbfc5c8a5dc6315", "5bceadef7c7c768b"),
    "pair_spread": ("8d8b92b65a0090dc", "1ace53a0cd9957fb"),
    "portfolio_return": ("320e2349658aa2b8", "empty"),  # a book has no ledger rows
}


def _ledger_columns(name: str) -> list[str]:
    """The ledger columns of origin/main; an option trade's ``exit_session`` is now its own
    (stored, ADR 0088 2.5a), not S + h sessions, so it is left out of that edge's digest."""
    return [c for c in LEDGER if not (name == "option_pnl" and c == "exit_session")]


def _digests(evaluations: dict[str, EdgeEvaluation]) -> dict[str, tuple[str, str]]:
    got: dict[str, tuple[str, str]] = {}
    for name, ev in evaluations.items():
        ledger = trades_frame(ev, "r", AS_OF)
        got[name] = (
            _digest(edge_eval_frame(ev, "r", AS_OF)),
            _digest(ledger, _ledger_columns(name)) if len(ledger) else "empty",
        )
    return got


def _scored(evaluations: dict[str, EdgeEvaluation]) -> dict[str, str]:
    """Every row of ``edge_eval`` but the random draws': the screeners', baselines' and costs'."""
    out = {}
    for name, ev in evaluations.items():
        frame = edge_eval_frame(ev, "r", AS_OF)
        out[name] = _digest(frame[~frame["role"].astype(str).str.startswith("random")])
    return out


def test_each_outcome_kinds_scores_and_ledger_are_pinned(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pinned under the leg version of origin/main (4): the leg key seeds a session's random
    draws, so version 5 (E6a) re-draws them; the next test shows nothing else moved."""
    monkeypatch.setattr(key, "LEG_VERSION", 4)
    assert _digests(_evaluations()) == DIGESTS


def test_version_5_moves_only_the_random_draws(monkeypatch: pytest.MonkeyPatch) -> None:
    """The leg bump (ADR 0088, E6a) reseeds the draws of a session (``random_picks.generator``);
    every value, hit, measure and ledger row is the one of version 4 (the screeners', baselines'
    and costs' ``edge_eval`` rows by digest, the ledger by the pinned digests)."""
    now = _evaluations()
    assert {n: d[1] for n, d in _digests(now).items()} == {n: d[1] for n, d in DIGESTS.items()}
    monkeypatch.setattr(key, "LEG_VERSION", 4)
    assert _scored(now) == _scored(_evaluations())


def test_the_time_series_measures_and_windows_are_pinned() -> None:
    w = ts.build_world()
    ran = evaluate_time_series(
        w.reader, timed_edge(), ts.FIRST, ts.LAST, ts.AS_OF, lambda d: "calm", date(2025, 1, 1),
        False, 50,
    )  # fmt: skip
    (spy,) = ran.results
    text = repr((spy.measures, spy.randoms, spy.in_window, spy.paired, spy.lost))
    assert hashlib.sha256(text.encode()).hexdigest()[:16] == TS_DIGEST


TS_DIGEST = "0cf9a38f445537be"
