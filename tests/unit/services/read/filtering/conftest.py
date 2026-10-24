"""Builders for the filtering tests: a small surface and its frame."""

import pytest

from algotrade.config.filters.definitions import parse_filter_set

SURFACE = {
    "label": "Things",
    "column": [{"id": "tag", "dtype": "str", "source": "tag"}],
    "filter": [
        {"id": "tag", "label": "Tag", "group": "setup", "kind": "pick", "field": "column:tag",
         "options": "values", "guide": "term:t"},
        {"id": "size", "label": "Size", "group": "setup", "kind": "range", "field": "feature.size",
         "bins": [0, 10, 20], "guide": "term:t"},
        {"id": "ok", "label": "Ok", "group": "more", "kind": "toggle", "field": "feature.ok",
         "guide": "term:t"},
        {"id": "soon", "label": "Soon", "group": "coming_up", "kind": "window",
         "field": "feature.soon", "window_unit": "sessions", "guide": "term:t"},
        {"id": "grade", "label": "Grade", "group": "tradeable", "kind": "select",
         "field": "feature.grade", "options": "static",
         "option": [{"value": "A", "label": "A"}, {"value": "B", "label": "B"}], "guide": "term:t"},
    ],
}  # fmt: skip


@pytest.fixture
def filter_set():
    return parse_filter_set("things", SURFACE)


FRAME = {
    "column:tag": ["x", "y", ("x", "y"), None, "x", "z"],
    "feature.size": [1.0, 5.0, 12.0, None, 20.0, 0.0],
    "feature.ok": [True, False, True, None, True, False],
    "feature.soon": [0, 3, None, 9, 5, 1],
    "feature.grade": ["A", "B", "A", None, "B", "A"],
}
SIZE = 6
