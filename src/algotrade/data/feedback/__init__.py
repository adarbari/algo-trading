"""Reads of the feedback grain (``feedback/``, ADR 0066): the Describe-it events the API
recorded, over a date range. Importable only by the read model's loader
(``services/read/ops/feedback.py``), which applies the privacy rule."""

from algotrade.data.feedback.reading import DRAFTING_EVENTS, read_drafting_events

__all__ = ["DRAFTING_EVENTS", "read_drafting_events"]
