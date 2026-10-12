"""A curated golden case waits for its recorded answer only briefly: ``golden curate`` writes
``"recorded": false`` and its ``curated`` date, ``golden run --record`` clears the flag, and a case
still unrecorded after 14 days fails here (the replay skips it meanwhile)."""

from datetime import UTC, date, datetime, timedelta

from algotrade.services.drafting.golden import GoldenCase, load_cases
from tests.conftest import REPO_ROOT

GRACE_DAYS = 14
ROOT = REPO_ROOT / "tests" / "fixtures" / "drafting" / "golden"


def overdue(cases: tuple[GoldenCase, ...], today: date) -> list[str]:
    """The ids of the unrecorded cases curated more than ``GRACE_DAYS`` ago (or with no date)."""
    late = []
    for case in cases:
        if case.recorded:
            continue
        when = date.fromisoformat(case.curated) if case.curated else None
        if when is None or today - when > timedelta(days=GRACE_DAYS):
            late.append(case.id)
    return late


def case(id: str, recorded: bool, curated: str | None) -> GoldenCase:
    return GoldenCase(id, "s", "train", (), frozenset(), recorded=recorded, curated=curated)


def test_the_check_names_a_case_unrecorded_for_more_than_14_days() -> None:
    today = date(2026, 10, 30)
    cases = (case("fresh", False, "2026-10-20"), case("edge", False, "2026-10-16"),
             case("late", False, "2026-10-15"), case("undated", False, None),
             case("done", True, "2026-01-01"))  # fmt: skip
    assert overdue(cases, today) == ["late", "undated"]


def test_no_curated_case_waits_for_its_recording_longer_than_the_grace() -> None:
    assert overdue(load_cases(ROOT), datetime.now(UTC).date()) == []
