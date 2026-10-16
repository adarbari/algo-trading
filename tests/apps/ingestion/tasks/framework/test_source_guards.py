"""The source guards: a task whose source is not built is skipped with a WARN, never failed."""

from types import SimpleNamespace
from typing import Any, cast

from algotrade_ingestion.tasks.framework import source_guards
from algotrade_ingestion.tasks.framework.run import TaskContext


def _ctx(sources: dict[str, Any], unavailable: dict[str, str] | None = None) -> TaskContext:
    return cast(TaskContext, SimpleNamespace(sources=sources, unavailable=unavailable or {}))


def test_descriptions_run_when_any_description_source_is_built() -> None:
    assert source_guards.no_description_source(_ctx({"massive_overview": object()})) is None


def test_descriptions_skip_names_why_every_source_is_missing() -> None:
    skip = source_guards.no_description_source(_ctx({}, {"massive_overview": "no API key"}))
    assert skip is not None and skip.startswith("skipped: ")
    assert "no API key" in skip and "sec_fund_tickers is not configured" in skip


def test_the_gateway_guard_skips_when_no_ibkr_source_answers() -> None:
    assert source_guards.gateway_down(_ctx({})) is None
