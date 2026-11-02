"""``training_frame``: the purge (no window closing within a horizon of the frozen period), the
lookahead (features read at D only) and the refusals."""

from datetime import date

import pytest

from algotrade.config.edges.verdict import OptionCosts
from algotrade.config.user import UserContext
from algotrade.core.model.errors import ConfigurationError
from algotrade.services.evaluation.cross_section.harness import edge_universe
from algotrade.services.evaluation.discovery.frame import feature_reads
from algotrade.services.evaluation.training import frame as module
from algotrade.services.evaluation.training import no_ml
from algotrade.services.evaluation.training.frame import LABEL, purge_cutoff, training_frame
from algotrade.services.features import site_features
from tests.unit.services.evaluation.cross_section.conftest import (
    DAYS,
    IDS,
    PRICE,
    World,
    build_world,
    edge,
    outcome_row,
)

USER = UserContext("site")
FROZEN = "2026-09-10"  # h = 2: windows must close before Sept 8 (Sept 7 is Labor Day)


def frame(w: World, option_costs=None, **changes):  # type: ignore[no-untyped-def]
    e = edge(scorer={"features": [PRICE]}, frozen_from=FROZEN, **changes)
    return training_frame(
        w.reader, e, edge_universe(w.configs, USER, e), DAYS[0], DAYS[-1], option_costs=option_costs
    )


def test_the_cutoff_is_one_horizon_before_the_frozen_period() -> None:
    assert purge_cutoff(date(2026, 9, 10), 2) == date(2026, 9, 8)
    assert purge_cutoff(date(2026, 9, 8), 1) == date(2026, 9, 4)  # over the holiday weekend


def test_no_training_row_has_a_window_closing_in_the_purge_zone() -> None:
    t = frame(build_world())
    # D = Sept 1, 3, 8, 10 (every 2nd session), S = D + 1; the windows close two days after S:
    # S = Sept 2 and 4 close before Sept 8; S = Sept 9 and 11 do not.
    assert sorted(t.frame["session"].unique()) == [date(2026, 9, 1), date(2026, 9, 3)]
    assert (t.cutoff, t.fitted_through, t.sessions) == (date(2026, 9, 8), date(2026, 9, 6), 2)
    assert len(t.frame) == 2 * len(IDS) and set(t.frame[LABEL]) == {0.0, 1.0}


def test_a_later_window_never_reaches_the_frame() -> None:
    changed = build_world(
        rows_of=lambda d: (
            [outcome_row(i, 0, d, fwd_excess_return=0.5) for i in IDS]
            if d >= date(2026, 9, 8)
            else [outcome_row(i, k, d) for k, i in enumerate(IDS)]
        )
    )
    assert frame(changed).frame.equals(frame(build_world()).frame)


def test_features_are_read_at_the_decision_session_only() -> None:
    def later(d: date, i: int) -> float:  # the sessions after each entry session change
        return 100.0 + 10 * i if d in (DAYS[0], DAYS[2]) else 999.0 - i

    a, b = frame(build_world()), frame(build_world(price_of=later))
    assert a.frame.equals(b.frame)  # the entry sessions (Sept 2, 4) differ in b: never read


def test_the_label_is_the_edges_hit() -> None:
    t = frame(build_world()).frame
    row = t[(t["session"] == DAYS[0])].set_index("instrument_id")
    assert row.loc[IDS[10], LABEL] == 1.0 and row.loc[IDS[9], LABEL] == 0.0  # (i - 9.5)% > 0
    assert row.loc[IDS[10], PRICE] == 200.0  # name i costs 100 + 10 i at D


@pytest.mark.parametrize(
    ("changes", "why"),
    [
        ({"scorer": None}, "no \\[scorer\\] features"),
        ({"frozen_from": None}, "needs frozen_from"),
        ({"schedule": "on_event:earnings_reaction"}, "event schedule"),
    ],
)
def test_an_edge_that_cannot_be_fitted_is_refused(changes, why: str) -> None:  # type: ignore[no-untyped-def]
    doc = {"scorer": {"features": [PRICE]}, "frozen_from": FROZEN, **changes}
    e, w = edge(**doc), build_world()
    with pytest.raises(ConfigurationError, match=why):
        training_frame(w.reader, e, edge_universe(w.configs, USER, e), DAYS[0], DAYS[-1])


def test_a_scorer_feature_on_a_no_ml_table_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """The test that would have caught a learned scorer reading FINRA's rows: the catalogue's
    price feature reads a table, and with that table no_ml the fit is refused before any read."""
    features = site_features()
    feature = features.feature(PRICE)
    assert feature is not None
    table = sorted(feature_reads(features, feature).tables)[0]
    monkeypatch.setattr(no_ml, "NO_ML_TABLES", frozenset({table}))
    w = build_world()
    e = edge(scorer={"features": [PRICE]}, frozen_from=FROZEN)
    with pytest.raises(ConfigurationError, match="machine learning"):
        training_frame(w.reader, e, edge_universe(w.configs, USER, e), DAYS[0], DAYS[-1])


def test_an_unresolvable_scorer_field_is_refused() -> None:
    w = build_world()
    e = edge(scorer={"features": ["rollup.nope@v1.x"]}, frozen_from=FROZEN)
    with pytest.raises(ConfigurationError, match="unknown inputs"):
        training_frame(w.reader, e, edge_universe(w.configs, USER, e), DAYS[0], DAYS[-1])


def test_the_frame_scores_labels_with_the_given_option_costs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """E6b-2 review: the fit's labels were scored without the commission the backtest pays."""
    seen: list[object] = []
    real = module.apply_outcome

    def spy(edge, outcomes, *args, option_costs=None, **kw):  # type: ignore[no-untyped-def]
        seen.append(option_costs)
        return real(edge, outcomes, *args, option_costs=option_costs, **kw)

    monkeypatch.setattr(module, "apply_outcome", spy)
    costs = OptionCosts(commission_usd=1.5)
    frame(build_world(), option_costs=costs)
    assert seen and all(c == costs for c in seen)
