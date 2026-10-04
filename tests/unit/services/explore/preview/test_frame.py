"""The cached field frame's memos are bounded, and its selection is the nightly one."""

from datetime import date

import pandas as pd

from algotrade.config.strategy.schema import parse_selection
from algotrade.core.views.feature_view import FeatureView
from algotrade.data.reference import Universe
from algotrade.services.explore.preview.frame import MAX_MEMO, FieldFrame, features_key

DAY = date(2026, 10, 2)


def frame() -> FieldFrame:
    view = FeatureView(DAY, {"EQ:A": {"instrument.status": "ACTIVE"}, "EQ:B": {}})
    universe = Universe(DAY, pd.DataFrame({"instrument_id": ["EQ:A"]}), 1, "v1", None)
    return FieldFrame(view, universe, ("t",), False)


def selection(value: str) -> object:
    raw = {"name": "s", "where": {"all": [{"field": "instrument.status", "op": "eq",
                                          "value": value}]}}  # fmt: skip
    return parse_selection(raw, "s")


def test_selection_is_memoised_and_bounded() -> None:
    f = frame()
    chosen = f.selected(selection("ACTIVE"))  # type: ignore[arg-type]
    assert chosen.instruments == ("EQ:A",) and chosen.unknown_excluded == 1
    assert chosen.missing_tables == ("t",)
    assert f.selected(selection("ACTIVE")) is chosen  # type: ignore[arg-type]
    for n in range(MAX_MEMO):
        f.selected(selection(f"S{n}"))  # type: ignore[arg-type]
    assert len(f.selections) <= MAX_MEMO


def test_the_criterion_memo_is_emptied_when_full() -> None:
    f = frame()
    f.memo.update({n: {} for n in range(MAX_MEMO)})  # type: ignore[misc]
    assert f.memo_for() == {}


def test_features_key_is_stable() -> None:
    assert features_key(()) == features_key([])
