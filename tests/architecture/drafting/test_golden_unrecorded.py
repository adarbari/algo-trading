"""A curated golden case may wait for its recorded answer (the replay skips it), so the wait is
bounded structurally: ``"recorded": false`` only on a case that names its source events and has
NO answer file, with a ``curated`` date that is not in the future and not later than the commit
that added the file (a shallow clone or an uncommitted file skips that date check). How long a
case has waited is not a CI failure (it would block unrelated PRs): ``make status`` warns about a
case unrecorded for more than 14 days."""

import json
import subprocess
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path

from algotrade.services.drafting.golden import recorded_answers
from tests.conftest import REPO_ROOT

ROOT = REPO_ROOT / "tests" / "fixtures" / "drafting" / "golden"


def added_on(path: Path) -> date | None:
    """The date of the commit that added ``path``; ``None`` in a shallow clone or when untracked."""

    def git(*args: str) -> str:
        done = subprocess.run(
            ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=False
        )
        return done.stdout.strip() if done.returncode == 0 else ""

    if git("rev-parse", "--is-shallow-repository") == "true":
        return None
    stamps = git("log", "--diff-filter=A", "--format=%cs", "--", str(path)).splitlines()
    return date.fromisoformat(stamps[-1]) if stamps else None


def problems(root: Path, today: date, added: Callable[[Path], date | None]) -> list[str]:
    """What is wrong with the unrecorded cases under ``root``."""
    found = []
    for path in sorted((root / "cases").glob("*.json")):
        raw = json.loads(path.read_text())
        if raw.get("recorded", True):
            continue
        name = path.stem
        if not (raw.get("source_events") or raw.get("source_event")):
            found.append(f"{name}: unrecorded but not curated (no source_events)")
        if recorded_answers(root, raw["id"]):
            found.append(f"{name}: has answer files but is still marked unrecorded")
        try:
            curated = date.fromisoformat(raw["curated"])
        except (KeyError, TypeError, ValueError):
            found.append(f"{name}: unrecorded with no valid curated date")
            continue
        if curated > today:
            found.append(f"{name}: curated {curated} is in the future")
        when = added(path)
        if when is not None and curated > when:
            found.append(f"{name}: curated {curated} is later than the commit that added it")
    return found


def write(root: Path, case_id: str, **raw: object) -> None:
    (root / "cases").mkdir(exist_ok=True, parents=True)
    body = {"id": case_id, "recorded": False, "curated": "2026-10-01", "source_events": ["e"]}
    (root / "cases" / f"{case_id}.json").write_text(json.dumps({**body, **raw}))


def test_the_check_names_each_way_a_case_can_hide_in_the_unrecorded_state(tmp_path: Path) -> None:
    write(tmp_path, "fine")
    write(tmp_path, "recorded", recorded=True, curated=None, source_events=None)
    write(tmp_path, "hand", source_events=None)
    write(tmp_path, "answered")
    (tmp_path / "answers" / "m").mkdir(parents=True)
    (tmp_path / "answers" / "m" / "answered.json").write_text("{}")
    write(tmp_path, "future", curated="2026-12-01")
    write(tmp_path, "undated", curated="soon")
    write(tmp_path, "backdated", curated="2026-10-05")
    found = problems(tmp_path, date(2026, 10, 11), lambda path: date(2026, 10, 2))
    assert {f.split(":")[0] for f in found} == {
        "hand",
        "answered",
        "future",
        "undated",
        "backdated",
    }
    assert problems(tmp_path / "none", date(2026, 10, 11), lambda p: None) == []


def test_the_committed_unrecorded_cases_are_structurally_sound() -> None:
    assert problems(ROOT, datetime.now(UTC).date(), added_on) == []
