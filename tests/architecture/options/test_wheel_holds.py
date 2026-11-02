"""A wheel's ``horizon_sessions`` are the gaps the exchange calendar makes and one less (an
entry the session after an assignment), a fitness test over ``config/site/edges``.

Each hold ends on a monthly expiry, so for an entry session S exactly one hold's window ends on
the put's expiry (INTRINSIC exit), and the book picks it by expiry alone. The set is derived here
from ``monthly_expiry`` and the exchange sessions, never hand-picked: a gap missing from the
document leaves an entry with no hold ending on its expiry; a gap the calendar never makes is a
row nothing reads."""

import tomllib
from itertools import pairwise

import pytest

from algotrade.core.time.calendar import monthly_expiry, sessions_between
from algotrade.core.time.windows import WINDOW_GAPS, WINDOW_LONGEST_GAPS
from tests.conftest import REPO_ROOT

WINDOW = "after_monthly_expiry"
FIRST_YEAR, LAST_YEAR = 2000, 2040  # the bought history (2002 on) feeds the same rows


def expiry_gaps(first_year: int, last_year: int) -> set[int]:
    """The sessions from one monthly expiry (the entry session S) to the next, over the years."""
    expiries = [
        monthly_expiry(y, m) for y in range(first_year, last_year + 1) for m in range(1, 13)
    ]
    gaps = {len(sessions_between(a, b)) - 1 for a, b in pairwise(expiries)}
    return gaps | {gap - 1 for gap in gaps}  # an entry the session after an assignment is one less


def wheels() -> list[tuple[str, dict]]:  # type: ignore[type-arg]
    found = []
    for path in sorted((REPO_ROOT / "config/site/edges").glob("*/edge.toml")):
        doc = tomllib.loads(path.read_text())
        if "wheel" in doc.get("outcome", {}):
            found.append((path.parent.name, doc))
    return found


def test_the_declared_window_gap_bounds_are_the_calendars() -> None:
    gaps = expiry_gaps(2000, 2040)
    assert (min(gaps) + 1, max(gaps)) == (WINDOW_GAPS[WINDOW], WINDOW_LONGEST_GAPS[WINDOW])


@pytest.mark.parametrize(("edge_id", "doc"), wheels() or [pytest.param("none", {}, id="no wheel")])
def test_a_wheels_holds_are_the_expiry_gaps_of_the_calendar(edge_id: str, doc: dict) -> None:  # type: ignore[type-arg]
    if not doc:
        pytest.skip("no wheel edge on the site yet")
    derived = expiry_gaps(FIRST_YEAR, LAST_YEAR)
    assert doc["schedule"] == f"calendar:{WINDOW}", edge_id
    assert set(doc["outcome"]["horizon_sessions"]) == derived, (
        f"{edge_id}: horizon_sessions must be {sorted(derived)} (the gaps between monthly "
        f"expiries from {FIRST_YEAR} to {LAST_YEAR})"
    )
