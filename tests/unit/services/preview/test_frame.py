"""The cached field frame's memos are bounded, and its selection is the nightly one."""

import threading
from datetime import date
from types import SimpleNamespace
from typing import Any

import pandas as pd
import pytest

from algotrade.config.strategy.schema import parse_selection
from algotrade.core.views.feature_view import FeatureView
from algotrade.data.reference import Universe
from algotrade.services.preview import frame as frames
from algotrade.services.preview.frame import MAX_MEMO, FieldFrame, features_key, field_frame
from algotrade.services.read.context import ResultCache

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


def test_a_frame_weighs_what_its_view_holds_and_the_cache_is_bounded_by_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A frame is dicts per instrument, which ``weigh`` cannot walk: it says its own size, so
    the preview cache (a frame per screen) cannot grow past its byte bound."""
    view = FeatureView(DAY, {f"EQ:{n}": {"a": 1.0, "b": 2.0} for n in range(100)})
    universe = Universe(DAY, pd.DataFrame({"instrument_id": ["EQ:A"]}), 1, "v1", None)
    read = (view, SimpleNamespace(missing=(), pre_snapshot=False))
    monkeypatch.setattr(frames, "fields_view", lambda *a, **k: read)
    monkeypatch.setattr(frames, "load_universe", lambda *a, **k: universe)
    reader = SimpleNamespace(visible_seq=lambda: 1)
    built, _ = field_frame(reader, ResultCache(4), DAY, ["a", "b"], None, ())  # type: ignore[arg-type]
    assert built.weight_bytes() == 100 * (frames.ROW_BYTES + 2 * frames.FIELD_BYTES)
    cache = ResultCache(size=24, max_bytes=2 * built.weight_bytes() + 1)
    for name in "xyz":
        cache.put(name, built)
    assert [cache.get(k) is not None for k in "xyz"] == [False, True, True]  # the oldest left


def test_a_frame_being_read_is_waited_for_not_read_twice(monkeypatch: pytest.MonkeyPatch) -> None:
    """The warmer and a first preview ask for one frame together: one reads it, the other
    takes it (and reports it cached)."""
    reads: list[int] = []
    inside, release = threading.Event(), threading.Event()
    view = FeatureView(DAY, {"EQ:A": {"a": 1.0}})
    universe = Universe(DAY, pd.DataFrame({"instrument_id": ["EQ:A"]}), 1, "v1", None)

    def slow(*_a: Any, **_k: Any) -> Any:
        reads.append(1)
        inside.set()
        release.wait(5)
        return view, SimpleNamespace(missing=(), pre_snapshot=False)

    monkeypatch.setattr(frames, "fields_view", slow)
    monkeypatch.setattr(frames, "load_universe", lambda *a, **k: universe)
    cache, reader = ResultCache(4), SimpleNamespace(visible_seq=lambda: 1)
    got: list[bool] = []

    def ask() -> None:
        got.append(field_frame(reader, cache, DAY, ["a"], None, ())[1])  # type: ignore[arg-type]

    first = threading.Thread(target=ask)
    first.start()
    inside.wait(5)
    second = threading.Thread(target=ask)
    second.start()
    release.set()
    first.join(5)
    second.join(5)
    assert reads == [1] and sorted(got) == [False, True]
