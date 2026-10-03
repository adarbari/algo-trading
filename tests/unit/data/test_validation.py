import pandas as pd
import pytest

from algotrade.core.errors import DataValidationError
from algotrade.data.frames import frame_to_series, series_to_frame
from algotrade.data.validation import validate_ohlcv
from tests.factories import series_from_closes


@pytest.fixture
def good() -> pd.DataFrame:
    return series_to_frame(series_from_closes([10, 11, 12, 11]))


def test_valid_frame_passes(good: pd.DataFrame) -> None:
    validate_ohlcv(good, "good")


def test_roundtrip(good: pd.DataFrame) -> None:
    s = frame_to_series("T", good)
    assert list(s.close) == [10, 11, 12, 11]


def _problems(frame: pd.DataFrame) -> list[str]:
    with pytest.raises(DataValidationError) as exc:
        validate_ohlcv(frame, "bad")
    return exc.value.problems


def test_missing_columns(good: pd.DataFrame) -> None:
    assert "missing columns" in _problems(good.drop(columns=["volume"]))[0]


def test_empty() -> None:
    frame = pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])
    assert _problems(frame) == ["no rows"]


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (lambda f: f.assign(close=[10, None, 12, 11]), "NaN"),
        (lambda f: f.iloc[::-1].reset_index(drop=True), "not sorted"),
        (lambda f: f.assign(timestamp=[f.timestamp[0]] * 4), "duplicate"),
        (lambda f: f.assign(low=[-1.0] * 4), "non-positive"),
        (lambda f: f.assign(volume=[-1.0] * 4), "negative volume"),
        (lambda f: f.assign(high=f.close * 0.5), "high below"),
        (lambda f: f.assign(low=f.close * 2), "low above"),
    ],
)
def test_detects_problem(good: pd.DataFrame, mutate, expected: str) -> None:  # type: ignore[no-untyped-def]
    assert any(expected in p for p in _problems(mutate(good)))
