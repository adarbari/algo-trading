"""The one scalar coercion and the UNKNOWN vocabulary (docs/api/read-model.md "Values and
UNKNOWN")."""

from datetime import UTC, date, datetime
from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from algotrade.services import views
from algotrade.services.read.values import Unknown, UnknownCode, to_scalar


@pytest.mark.parametrize(
    ("stored", "plain"),
    [
        (None, None),
        (float("nan"), None),
        (np.float64("nan"), None),
        (pd.NaT, None),
        (np.int64(3), 3),
        (np.float32(0.5), 0.5),
        (np.bool_(True), True),
        (True, True),
        (7, 7),
        ("text", "text"),
        (date(2026, 10, 2), "2026-10-02"),
        (datetime(2026, 10, 2, 20, tzinfo=UTC), "2026-10-02T20:00:00+00:00"),
        (pd.Timestamp("2026-10-02", tz="UTC"), "2026-10-02T00:00:00+00:00"),
        (Decimal("1.5"), "1.5"),
        ([1], "[1]"),
    ],
)
def test_to_scalar_is_json_safe(stored: object, plain: object) -> None:
    result = to_scalar(stored)
    assert result == plain
    assert type(result) is type(plain)


def test_runs_and_reads_share_the_one_coercion() -> None:
    assert views.to_value is to_scalar


def test_unknown_names_its_reason_and_where() -> None:
    unknown = Unknown(UnknownCode.NO_PARTITION, "rollups/instrument/earnings@v1 has no partition")
    assert unknown.code == "NO_PARTITION"
    assert [c.value for c in UnknownCode] == [
        "NO_PARTITION", "NO_ROW", "NULL", "NOT_IN_CATALOGUE", "LICENCE", "NOT_RUN", "PRE_SNAPSHOT",
    ]  # fmt: skip
    with pytest.raises(AttributeError):
        unknown.code = UnknownCode.NULL  # type: ignore[misc]
