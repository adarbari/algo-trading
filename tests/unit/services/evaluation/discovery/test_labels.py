"""``labels``: the winners are the top of the excess return over COMPLETE and DELISTED rows, a
session with too many missing rows is refused."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from algotrade.core.model.errors import MissingDataError
from algotrade.services.evaluation.discovery.labels import label_winners, read_labels
from tests.helpers.rollup_store import store
from tests.unit.services.evaluation.discovery.conftest import settings

S = date(2014, 3, 3)


def rows(excess: list[float], status: str = "COMPLETE", start: int = 0) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "instrument_id": [f"EQ:{start + i:03d}" for i in range(len(excess))],
            "fwd_excess_return": excess,
            "outcome_status": status,
        }
    )


def test_threshold_includes_delisted() -> None:
    """The delisted are measured to their last bar and counted: the top-2% cut is taken over
    them too, and a delisted name can itself be a winner. Catches: dropping DELISTED rows (the
    worst losers) before the threshold, which lifts it."""
    complete = rows([i / 100 for i in range(97)])
    delisted = rows([-0.95, -0.9, 3.0], "DELISTED", start=97)
    out = pd.concat([complete, delisted], ignore_index=True)
    ids = out["instrument_id"].tolist()
    got = label_winners(out, ids, S, settings(top_fraction=0.02, max_missing_fraction=0.0))
    every = out["fwd_excess_return"].to_numpy()
    assert got.threshold == pytest.approx(float(np.quantile(every, 0.98)))
    only_complete = float(np.quantile(complete["fwd_excess_return"], 0.98))
    assert got.threshold != pytest.approx(only_complete)
    assert "EQ:099" in got.winners  # the delisted +300% name
    assert got.measured == 100 and got.missing_fraction == 0.0


def test_only_eligible_names_with_a_counted_row_are_considered() -> None:
    """A row of a name that is not eligible at S, or whose status is neither COMPLETE nor
    DELISTED, never sets the threshold or wins. Catches: the label reading the whole outcome
    partition instead of the eligible names."""
    out = pd.concat(
        [
            rows([i / 100 for i in range(50)]),
            rows([9.0], "PENDING", start=50),
            rows([8.0], start=51),
        ],
        ignore_index=True,
    )
    eligible = [f"EQ:{i:03d}" for i in range(51)]  # EQ:050 PENDING, EQ:051 not eligible
    got = label_winners(out, eligible, S, settings(max_missing_fraction=0.02))
    assert got.winners == {"EQ:049"} and got.measured == 50 and got.eligible == 51


def test_a_session_with_too_many_missing_rows_is_refused() -> None:
    """More than ``max_missing_fraction`` of the eligible names with no counted row: a threshold
    over survivors is not the study's, so the session raises (ADR 0008). Catches: labelling a
    thin sample."""
    out = rows([i / 100 for i in range(90)])
    ids = [f"EQ:{i:03d}" for i in range(100)]  # 10% have no row
    with pytest.raises(MissingDataError, match="no COMPLETE or DELISTED outcome"):
        label_winners(out, ids, S, settings(max_missing_fraction=0.02))
    got = label_winners(out, ids, S, settings(max_missing_fraction=0.10))
    assert got.missing_fraction == pytest.approx(0.1)


def test_missing_grid_session_raises() -> None:
    """A grid session whose outcomes were never written (the 504 backfill has not reached it)
    is an error naming the table, never an empty label set. Catches: a silent empty winner
    list."""
    _, reader = store()
    with pytest.raises(MissingDataError, match="outcomes"):
        read_labels(reader, S, ["EQ:000"], settings())
    with pytest.raises(MissingDataError, match="no eligible"):
        label_winners(rows([]), [], S, settings())
