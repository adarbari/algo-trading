"""The event-schedule vocabulary and parsing split out of ``document.py``: the names stay
importable from ``document`` and a schedule is read, and refused, as before."""

import pytest

from algotrade.config.edges import document
from algotrade.config.edges.schedules import events
from algotrade.config.site.fields import Table
from algotrade.core.model.errors import ConfigurationError


def test_document_reexports_the_same_objects() -> None:
    for name in ("EVENT_CLASSES", "EVENT_SUBTYPES", "SUBTYPE_REQUIRED", "ON_EVENT",
                 "event_class", "event_subtype"):  # fmt: skip
        assert getattr(document, name) is getattr(events, name)


def test_schedule_parts() -> None:
    assert events.event_class("on_event:filing_8k:5.02") == "filing_8k"
    assert events.event_subtype("on_event:filing_8k:5.02") == "5.02"
    assert events.event_subtype("on_event:index_change") is None
    assert events.event_class("month_end") is None


def test_subtype_rules_fail_closed() -> None:
    t = Table({}, "edge.toml")
    assert events.event_schedule_ok(t, "on_event:index_change:addition")
    assert not events.event_schedule_ok(t, "on_event:nope")
    with pytest.raises(ConfigurationError, match="needs a subtype"):
        events.event_schedule_ok(t, "on_event:filing_8k")
    with pytest.raises(ConfigurationError, match="not a subtype"):
        events.event_schedule_ok(t, "on_event:index_change:sideways")
