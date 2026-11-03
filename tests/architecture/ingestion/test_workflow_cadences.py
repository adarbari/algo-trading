"""The three ingestion cadences (ADR 0039, WF4): market-daily (the ``nightly`` job), the weekly
``reference`` workflow and the post-session / enrichment workflow own disjoint steps, each a
registry task or a declared job step, and the workflows stay one engine.
"""

from algotrade_ingestion.cli.main import WORKFLOW_ALIASES
from algotrade_ingestion.tasks.framework.registry import TASKS
from algotrade_ingestion.workflows.nightly.nightly import FINALLY, NIGHTLY
from algotrade_ingestion.workflows.post_session.post_session import POST_SESSION
from algotrade_ingestion.workflows.reference.reference import REFERENCE

# Steps that are a job (one job per screener, edge or user), not an ingestion task.
JOB_STEPS = {"screens", "edge-signals", "edge-eval"}
# Registry tasks in no workflow: run by hand, by their own agent or as backfills.
NO_WORKFLOW = {"bars-history", "ibkr-iv-repair", "compact-runs"}


def _names(steps: tuple) -> list[str]:  # type: ignore[type-arg]
    return [s.name for s in steps]


def test_the_cadences_own_disjoint_steps() -> None:
    """One step name is in one workflow; the exception is ``etf-holdings``, one task in two
    modes (ADR 0039 WF4): the daily share-count files nightly, the weekly slots in ``reference``."""
    market, weekly, enrichment = _names(NIGHTLY + FINALLY), _names(REFERENCE), _names(POST_SESSION)
    for a, b in ((market, weekly), (market, enrichment), (weekly, enrichment)):
        assert set(a) & set(b) <= {"etf-holdings"}, sorted(set(a) & set(b))
    nightly = next(s for s in NIGHTLY if s.name == "etf-holdings")
    reference = next(s for s in REFERENCE if s.name == "etf-holdings")
    assert nightly.params == {"daily_only": True} and reference.params == {"weekly": True}


def test_every_workflow_step_is_a_registry_task_or_a_declared_job_step() -> None:
    steps = {*_names(NIGHTLY + FINALLY), *_names(REFERENCE), *_names(POST_SESSION)}
    assert not (steps - set(TASKS) - JOB_STEPS), steps - set(TASKS) - JOB_STEPS


def test_the_reference_and_enrichment_steps_are_not_critical() -> None:
    assert not any(s.critical for s in (*REFERENCE, *POST_SESSION))


def test_the_workflow_names_of_the_adr_are_commands() -> None:
    assert WORKFLOW_ALIASES == {"market-daily": "nightly", "enrichment": "post-session"}
