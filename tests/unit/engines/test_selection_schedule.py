from datetime import date
from itertools import pairwise

import pytest

from algotrade.core.model.errors import ConfigurationError
from algotrade.core.time.calendar import sessions_between
from algotrade.engines.selection.evaluate import SelectionResult
from algotrade.engines.selection.schedule import (
    LISTED,
    Rebalance,
    diff,
    members_hash,
    rebalance_sessions,
    turnover,
)

START, END = date(2024, 1, 10), date(2024, 3, 31)
SESSIONS = sessions_between(START, END)


def result(*ids: str) -> SelectionResult:
    return SelectionResult("s", 10, tuple(sorted(ids)), 0, 0, ())


def test_none_is_only_the_start() -> None:
    assert rebalance_sessions(START, SESSIONS, "none") == [START]


def test_monthly_is_the_first_session_of_each_later_month() -> None:
    assert rebalance_sessions(START, SESSIONS, "monthly") == [
        START,
        date(2024, 2, 1),
        date(2024, 3, 1),
    ]


def test_weekly_is_the_first_session_of_each_later_iso_week() -> None:
    picked = rebalance_sessions(START, SESSIONS, "weekly")
    assert picked[:3] == [START, date(2024, 1, 16), date(2024, 1, 22)]  # 15th: MLK day
    assert all(d.isocalendar()[1] != e.isocalendar()[1] for d, e in pairwise(picked))


def test_every_n_sessions() -> None:
    picked = rebalance_sessions(START, SESSIONS, "5d")
    later = [s for s in SESSIONS if s > START]
    assert picked == [START, *later[4::5]]


@pytest.mark.parametrize("bad", ["0d", "daily", "d", "-1d"])
def test_unknown_frequency_fails(bad: str) -> None:
    with pytest.raises(ConfigurationError, match="rebalance_selection"):
        rebalance_sessions(START, SESSIONS, bad)


def test_diff_and_hash() -> None:
    assert diff(frozenset({"A", "B"}), result("B", "C")) == (("C",), ("A",))
    assert members_hash(["B", "A"]) == members_hash(["A", "B"]) != members_hash(["A"])


def test_audit_lists_small_changes_and_counts_large_ones() -> None:
    many = tuple(f"I{i:03d}" for i in range(LISTED + 1))
    first = Rebalance(START, START, result(*many), many, (), False)
    row = first.as_dict()
    assert row["added_count"] == LISTED + 1 and "added" not in row
    assert row["removed"] == [] and row["selected"] == LISTED + 1
    assert row["funnel"]["selection"] == "s" and row["effective"] == START.isoformat()
    later = Rebalance(END, None, result("I000"), (), many[1:], True)
    assert later.as_dict()["effective"] is None and later.as_dict()["survivorship_bias"]
    assert later.members == frozenset({"I000"})


def test_turnover_is_the_mean_share_added() -> None:
    a = Rebalance(START, START, result("A", "B"), ("A", "B"), (), False)
    b = Rebalance(START, START, result("A", "C"), ("C",), ("B",), False)
    c = Rebalance(START, START, result("A", "C"), (), (), False)
    assert turnover([a, b, c]) == pytest.approx(0.25)
    assert turnover([a]) == 0.0
