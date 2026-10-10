"""``EdgeRun`` serves the run's trigger (None for a run from before it was recorded, never an
invented one) and the legacy owner beside its owner (ADR 0059 amendment 2026-10-10)."""

from datetime import UTC, date, datetime

from algotrade.services.read.evaluation.runs import EdgeRun as Domain
from algotrade_api.graphql.schema import schema
from algotrade_api.graphql.types.evaluation.edge import EdgeRun


def domain(**changes: object) -> Domain:
    fields: dict[str, object] = {
        "run_id": "r1", "edge_id": "drift", "owner": "site", "status": "COMPLETE",
        "range_from": date(2026, 1, 1), "range_to": date(2026, 2, 1), "split_from": None,
        "exploratory": False, "knowledge_ts": datetime(2026, 2, 2, tzinfo=UTC), "as_of": None,
        "trials_counted": 1,
    }  # fmt: skip
    return Domain(**{**fields, **changes})  # type: ignore[arg-type]


def test_the_run_serves_trigger_and_legacy_owner() -> None:
    old = EdgeRun.of(domain(legacy_owner="local"), None)  # type: ignore[arg-type]
    assert (old.owner, old.legacy_owner, old.trigger) == ("site", "local", None)
    new = EdgeRun.of(domain(trigger="nightly"), None)  # type: ignore[arg-type]
    assert (new.legacy_owner, new.trigger) == (None, "nightly")


def test_the_schema_declares_both_fields() -> None:
    sdl = schema.as_str()
    block = sdl[sdl.index("type EdgeRun") :].split("}")[0]
    assert "trigger: String" in block and "legacyOwner: String" in block
