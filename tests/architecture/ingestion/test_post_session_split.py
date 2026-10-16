"""The nightly / post-session split (ADR 0070): what decides a session's COMPLETE record and what
does not.

A session is served (ADR 0062) once its ``nightly`` record is COMPLETE, so a step may stay in the
nightly only if what it writes is read bound to the session: a session-grain partition, a
snapshot, an event or an issuer-dated table. ``edge-eval``, ``descriptions`` and ``verify`` are
read as the latest row per instrument or on their own run, never for a session, so they run in
``post-session`` after it; this test keeps them out of the nightly and keeps new steps honest.
"""

import pytest

from algotrade.services.read.session import GRAINS, Grain, grain_of
from algotrade_ingestion.tasks.framework.registry import TASKS
from algotrade_ingestion.workflows.nightly.nightly import NIGHTLY
from algotrade_ingestion.workflows.post_session.post_session import POST_SESSION

POST_ONLY = {"edge-eval", "descriptions", "verify"}
SESSION_BOUND = {Grain.SESSION, Grain.SNAPSHOT, Grain.EVENT, Grain.ISSUER_DATED}
NOT_NIGHTLY = ("verification/", "live/")  # never produced nightly, never expected for a session


def test_edge_eval_descriptions_and_verify_are_not_nightly_steps() -> None:
    assert not POST_ONLY & {s.name for s in NIGHTLY}
    assert {s.name for s in POST_SESSION} == POST_ONLY


def test_edge_signals_stays_in_the_nightly() -> None:
    """``edge_paper`` is read as of ``knowledge_ts <= cutoff``: the picks must be written before
    the session's record completes, so the step is not moved."""
    names = [s.name for s in NIGHTLY]
    assert "edge-signals" in names and names.index("screens") < names.index("edge-signals")


def _steps_after_the_first_critical() -> list[str]:
    first = next(i for i, s in enumerate(NIGHTLY) if s.critical)
    return [s.name for s in NIGHTLY[first + 1 :]]


@pytest.mark.parametrize("step", _steps_after_the_first_critical())
def test_every_nightly_step_after_the_first_critical_one_writes_tables_read_session_bound(
    step: str,
) -> None:
    spec = TASKS.get(step)  # the screens and edge-signals jobs write results/*, session grain
    for table in spec.tables if spec else ():
        assert not table.startswith(NOT_NIGHTLY), f"{step} writes {table}: not a nightly table"
        try:
            grain = grain_of(table)
        except ValueError:  # no read model reads it by a grain: a feature input, read by rollups
            continue
        assert grain in SESSION_BOUND, (
            f"{step} writes {table}, read as {grain.value}, not bound to a session: a step like "
            "that does not decide a session's COMPLETE record and belongs in post_session "
            "(ADR 0070)"
        )


def test_the_tables_the_moved_steps_write_are_what_the_rule_excludes() -> None:
    """The rule has teeth: the descriptions are read incrementally and verify's rows are not
    nightly tables, which is why they moved."""
    written = {t for name in ("descriptions", "verify") for t in TASKS[name].tables}
    assert any(grain_of(t) is Grain.INCREMENTAL for t in written if _declared(t))
    assert any(t.startswith(NOT_NIGHTLY) for t in written)


def _declared(table: str) -> bool:
    return any(table == key or (key.endswith("/") and table.startswith(key)) for key, _ in GRAINS)
