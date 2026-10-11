"""Drawdown and volatility of the evidence curve: hand-computed episodes, each side of the split
on its own, volatility by independent windows, and no drawdown for an outcome with no return."""

import math

import numpy as np
import pytest

from algotrade.services.read.edge_evidence.drawdown import load_drawdown
from algotrade.services.read.values import Unknown, UnknownCode
from algotrade.storage.backends.memory import MemoryBackend
from tests.unit.services.read.edge_evidence.stored_result import (
    DAYS,
    EXIT,
    read,
    series_of,
    stored_run,
)
from tests.unit.services.read.evaluation.conftest import FROZEN, series_row

VALUES = [0.02, -0.03, 0.01, -0.01, -0.02, 0.04, -0.01, 0.03]  # four before the split, four after


def stored(backend: MemoryBackend, values: list[float], **kw: object) -> None:
    stored_run(
        backend,
        [series_row(d, FROZEN, pick_mean=v, **kw) for d, v in zip(DAYS, values, strict=False)],
    )


def test_the_underwater_series_and_the_deepest_episode_with_dates(backend: MemoryBackend) -> None:
    stored(backend, VALUES)
    d = load_drawdown(series_of(read(backend)))
    assert [round(p.depth, 4) for p in d.points] == [
        0.0,
        -0.03,
        -0.02,
        -0.03,
        -0.05,
        -0.01,
        -0.02,
        0.0,
    ]
    assert [p.exit for p in d.points] == [x + EXIT for x in DAYS]
    (episode,) = d.episodes  # one drop from the first high; the curve is back above it at the end
    assert (episode.peak, episode.trough, episode.recovered) == (
        DAYS[0] + EXIT, DAYS[4] + EXIT, DAYS[7] + EXIT,
    )  # fmt: skip
    assert episode.depth == pytest.approx(0.05)


def test_each_side_of_the_split_is_its_own_curve(backend: MemoryBackend) -> None:
    stored(backend, VALUES)
    d = load_drawdown(series_of(read(backend)))
    assert d.max_in_sample == pytest.approx(0.03)
    assert d.max_out_of_sample == pytest.approx(
        0.02
    )  # from the first out-of-sample window: 0 -> -0.02


def test_an_open_drop_from_the_start_has_no_recovery(backend: MemoryBackend) -> None:
    stored(backend, [-0.01, -0.02])
    (episode,) = load_drawdown(series_of(read(backend))).episodes
    assert episode.peak == DAYS[0]  # from the start of the curve: the first decision
    assert (episode.recovered, round(episode.depth, 4)) == (None, 0.03)


def test_volatility_counts_independent_windows_not_overlapping_ones(backend: MemoryBackend) -> None:
    stored(backend, VALUES)
    d = load_drawdown(series_of(read(backend)))
    # weekly 20-session windows overlap: 4 windows in 21 days would be ~70 a year, but only
    # 252 / 20 = 12.6 independent windows fit a year
    sd = float(np.std(VALUES[:4], ddof=1))
    assert d.vol_in_sample == pytest.approx(sd * math.sqrt(252 / 20))
    assert d.vol_out_of_sample == pytest.approx(
        float(np.std(VALUES[4:], ddof=1)) * math.sqrt(252 / 20)
    )


def test_one_window_has_no_volatility_and_no_window_no_drawdown(backend: MemoryBackend) -> None:
    stored(backend, [0.01])
    d = load_drawdown(series_of(read(backend)))
    assert (d.vol_in_sample, d.max_out_of_sample) == (None, None) and d.max_in_sample == 0.0


def test_an_outcome_with_no_return_has_no_drawdown(backend: MemoryBackend) -> None:
    kw = {"unit": "ratio", "picks": 4, "eligible": 20, "base_hits": 10, "pick_hits": 2}
    stored_run(backend, [series_row(d, FROZEN, **kw) for d in DAYS])
    d = load_drawdown(series_of(read(backend)))
    assert d.points == () and d.unit == "ratio"
    assert d.unknown is not None and d.unknown.code is UnknownCode.NOT_APPLICABLE
    assert (d.vol_in_sample, d.max_in_sample) == (None, None)


def test_no_series_is_unknown(backend: MemoryBackend) -> None:
    stored_run(backend, [])
    found = series_of(read(backend))
    assert isinstance(found, Unknown) and load_drawdown(found).unknown is found
