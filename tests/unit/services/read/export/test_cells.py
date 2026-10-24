"""CSV injection: a cell a spreadsheet would run as a formula is neutralised; a number is not."""

import pytest

from algotrade.services.read.export import surfaces
from algotrade.services.read.export.cells import cell
from algotrade.services.read.export.file import ExportFile, export_file
from algotrade.services.read.export.surfaces import Exported
from tests.unit.services.read.export.test_file import context, rows_of


@pytest.mark.parametrize("text", ['=HYPERLINK("x")', "+SUM(A1)", "@cmd", "-cmd", "\tx", "\rx"])
def test_a_formula_start_is_prefixed(text: str) -> None:
    assert cell(text) == "'" + text


@pytest.mark.parametrize("text", ["-0.5", "+3", "1e-5", "12", "abc", "", "a=b", ".5"])
def test_numbers_and_plain_text_are_unchanged(text: str) -> None:
    assert cell(text) == text


def test_the_file_neutralises_a_company_name_and_keeps_a_negative_number(
    monkeypatch: pytest.MonkeyPatch, reader: object
) -> None:
    def fake(ctx: object, filters: object, params: object) -> Exported:
        return Exported(("symbol", "company", "value"), (("A", '=HYPERLINK("x")', "-0.5"),), 1)

    monkeypatch.setitem(surfaces.SURFACES, "ideas", fake)
    found: ExportFile = export_file(context(reader, user="me"), "ideas", None)  # type: ignore[arg-type]
    row = rows_of(found)[0]
    assert row["company"] == '\'=HYPERLINK("x")' and row["value"] == "-0.5"
