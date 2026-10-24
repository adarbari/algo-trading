"""``frame_of``: a surface's frame from its row objects by the declared column sources."""

from dataclasses import dataclass
from enum import Enum

import pytest

from algotrade.config.filters.definitions import FilterColumn, parse_filter_set
from algotrade.core.model.errors import ConfigurationError
from algotrade.services.read.availability.cause import Cause
from algotrade.services.read.filtering.definitions import resolve_definitions
from algotrade.services.read.filtering.rows import cell_of, frame_of
from algotrade.services.read.values import Unknown, UnknownCode


class Colour(Enum):
    RED = "red"


@dataclass(frozen=True)
class Part:
    name: str
    weight: float | None = None


@dataclass(frozen=True)
class Row:
    colour: Colour | None
    part: Part | None
    parts: tuple[Part, ...] = ()
    gap: Unknown | None = None


def col(source: str) -> FilterColumn:
    return FilterColumn.parse("c", "str", source, "t")


def test_a_path_is_walked_and_an_enum_is_its_value() -> None:
    row = Row(Colour.RED, Part("p", 2.0))
    assert cell_of(row, col("colour")) == "red"
    assert cell_of(row, col("part.weight")) == 2.0


def test_a_missing_step_is_missing_never_zero() -> None:
    row = Row(None, None, gap=Unknown(UnknownCode.NOT_RUN, Cause(())))
    assert cell_of(row, col("part.weight")) is None
    assert cell_of(row, col("colour")) is None
    assert cell_of(row, col("gap")) is None
    assert cell_of(row, col("gap.code")) is None
    assert cell_of(Row(None, Part("p")), col("part.weight")) is None


def test_a_path_through_a_tuple_is_a_tuple_and_len_counts_it() -> None:
    row = Row(None, None, (Part("a", 1.0), Part("b")))
    assert cell_of(row, col("parts.name")) == ("a", "b")
    assert cell_of(row, col("parts.weight")) == (1.0, None)
    assert cell_of(row, col("len(parts)")) == 2
    assert cell_of(Row(None, None), col("len(parts)")) == 0
    assert cell_of(Row(None, None), col("len(part)")) is None  # len of a missing path


@pytest.mark.parametrize("source", ["", "a..b", "len(a", "A.b", "a.b()", "len(len(a))", "a b"])
def test_a_malformed_source_is_refused_by_name(source: str) -> None:
    with pytest.raises(ConfigurationError, match="source"):
        FilterColumn.parse("c", "str", source, "filters/x.toml")


def test_the_parsed_source() -> None:
    assert col("len(a.b)").path == ("a", "b") and col("len(a.b)").count
    assert col("a.b").path == ("a", "b") and not col("a.b").count


SET = parse_filter_set("rows", {
    "label": "Rows",
    "column": [{"id": "w", "dtype": "float", "source": "part.weight"}],
    "filter": [
        {"id": "w", "label": "W", "group": "setup", "kind": "range", "field": "column:w",
         "bins": [0, 1, 2], "guide": "term:t"},
        {"id": "size", "label": "S", "group": "setup", "kind": "range", "field": "feature.size",
         "bins": [0, 1], "guide": "term:t"},
    ],
})  # fmt: skip


@dataclass
class Known:
    licence: str = "open"


class Catalogue:
    def feature(self, name: str) -> Known:
        return Known()


def test_the_frame_has_a_column_per_filter_and_wants_catalogue_values() -> None:
    resolved = resolve_definitions(SET, Catalogue(), ("open",))  # type: ignore[arg-type]
    rows = [Row(None, Part("a", 1.5)), Row(None, None)]
    frame = frame_of(rows, resolved, SET.columns, {"feature.size": [0.5, None]})
    assert frame == {"column:w": [1.5, None], "feature.size": [0.5, None]}
    with pytest.raises(ConfigurationError, match=r"feature\.size"):
        frame_of(rows, resolved, SET.columns)
