"""Every rejected or blocked site edge has a ``plain_reason`` for the Guide reader (ADR 0051): one
sentence of at most 30 words, with no path, ADR number or code name; the Guide shows it and never
the technical ``rejection_reason``."""

import re

from algotrade.config.edges.document import CLOSED
from algotrade.config.edges.loading import load_edges
from algotrade.storage.configs.files import FileConfigStore
from tests.conftest import REPO_ROOT

JARGON = re.compile(
    r"src/|config/|docs/|\.py|\.toml|ADR|[a-z]+_[a-z_]+|@v\d|EVENT_|\d{4}-\d\d-\d\d"
)
SENTENCE_BREAK = re.compile(r"[.!?]\s+[A-Z]")


def _closed() -> list:
    return [e for e in load_edges(FileConfigStore(REPO_ROOT / "config")) if e.status in CLOSED]


def test_every_closed_site_edge_has_a_plain_reason() -> None:
    closed = _closed()
    assert closed
    assert [e.id for e in closed if not e.plain_reason] == []


def test_a_plain_reason_is_one_short_sentence_without_internals() -> None:
    bad = [
        e.id
        for e in _closed()
        if len(e.plain_reason.split()) > 30
        or JARGON.search(e.plain_reason)
        or SENTENCE_BREAK.search(e.plain_reason)
        or not e.plain_reason.endswith(".")
    ]
    assert bad == []
