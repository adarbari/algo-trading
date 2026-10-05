"""What earlier nightly attempts of a session already did (ADR 0039: resume, expiry).

A FAILED session is retried (the hourly watchdog, or the next night) from where it stopped:
a step that SUCCEEDED or was WAIVED in an earlier attempt is not run again; its stored result
is reused. A step that ran and FAILED is remembered, so a latest-only step
(a source that serves only the current snapshot) whose session is no longer the latest FAILS
as expired instead of being SKIPPED: the session stays FAILED until it is waived by hand.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from algotrade.data import StoreReader
from algotrade_ingestion.workflows.nightly.sessions import NIGHTLY_RUN
from algotrade_ingestion.workflows.nightly.steps import StepStatus, parse_status

DONE = (StepStatus.SUCCEEDED, StepStatus.WAIVED)


@dataclass(frozen=True)
class Attempts:
    done: dict[str, dict[str, Any]] = field(default_factory=dict)  # step -> stored result
    tried: frozenset[str] = frozenset()  # steps an earlier attempt ran and saw FAIL


def _current(steps: dict[str, Any]) -> bool:
    """Whether a record's steps were judged under ADR 0039 (they carry ``critical``). Older
    records called a step COMPLETE without acceptance checks (rollups with no bars input),
    so they are never reused: a rerun of such a session runs every step."""
    return all(isinstance(step, dict) and "critical" in step for step in steps.values())


def earlier_attempts(reader: StoreReader, session: date) -> Attempts:
    """The session's earlier ``nightly`` attempts, oldest first: the steps done (with the run
    id that did them) and the steps that FAILED. A step held back (NOT_RUN) was never tried,
    so a latest-only one (screens behind failed bars) is SKIPPED later, not expired."""
    done: dict[str, dict[str, Any]] = {}
    tried: set[str] = set()
    for record in sorted(reader.runs(NIGHTLY_RUN, session), key=lambda r: r.started_at):
        steps = record.stats.get("steps")
        if not isinstance(steps, dict) or not _current(steps):
            continue
        for name, step in steps.items():
            status = parse_status(str(step.get("status")))
            if status in DONE:
                done[name] = {**step, "status": status.value, "run_id": record.run_id}
            elif status is StepStatus.FAILED:  # ran and failed; NOT_RUN was never tried
                tried.add(name)
    return Attempts(done, frozenset(tried - set(done)))
