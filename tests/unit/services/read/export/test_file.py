"""The filter bar's Export (ADR 0082 decision 6): the file has what the viewer can see and nothing
else. The licence leak test (a non-holder's file says ``LICENCE`` and never the personal value; the
holder has it), the filters identical to the page's (same rows for the same ``f``), the notice, the
cap, UNKNOWN cells and the surface registry."""

import csv
import io

import pytest

from algotrade.core.model.errors import ConfigurationError
from algotrade.data import StoreReader
from algotrade.services.read.context import NotFoundError
from algotrade.services.read.export import surfaces
from algotrade.services.read.export.file import NOTICE, ExportFile, export_file
from algotrade.services.read.export.surfaces import Exported, Params
from algotrade.services.read.filtering.codec import decode_filters
from algotrade.services.read.filtering.definitions import FilterRefusedError
from algotrade.services.read.screens.ideas import load_ideas
from algotrade.services.read.screens.results import load_result_page
from algotrade.services.read.screens.runs import latest_run
from algotrade.storage.backends.memory import MemoryBackend
from tests.unit.services.read.screens.conftest import context
from tests.unit.services.read.screens.test_ideas import (  # noqa: F401  (fixtures)
    filter_backend,
    view,
)

PERSONAL = "high"  # alpha's stored ``iv30`` value, under the personal licence (screens conftest)


def rows_of(found: ExportFile) -> list[dict[str, str]]:
    body = "".join(line for line in found.lines if not line.startswith("#"))
    return list(csv.DictReader(io.StringIO(body)))


def test_a_non_holder_gets_licence_never_the_personal_value_and_the_holder_the_value(
    reader: StoreReader,
) -> None:
    holder = export_file(context(reader, user="me"), "screener_results", None, Params("alpha"))
    other = export_file(context(reader, user="trader"), "screener_results", None, Params("alpha"))
    seen = {r["symbol"]: r for r in rows_of(holder)}
    assert f"iv30={PERSONAL}" in seen["AAA"]["metrics"] and seen["AAA"]["score"] == "50.0"
    hidden = {r["symbol"]: r for r in rows_of(other)}
    assert hidden["AAA"]["metrics"].endswith("iv30=LICENCE")
    assert (hidden["AAA"]["rank"], hidden["AAA"]["score"], hidden["AAA"]["reasons"]) == (
        "LICENCE",
        "LICENCE",
        "LICENCE",
    )
    assert hidden["AAA"]["decision"] == "QUALIFIED"  # names and decisions stay
    text = "".join(other.lines)
    assert PERSONAL not in text and "50.0" not in text


def test_ideas_a_withheld_run_is_no_row_and_leaks_nothing(reader: StoreReader) -> None:
    other = export_file(context(reader, user="trader"), "ideas", None)
    assert rows_of(other) == [] and PERSONAL not in "".join(other.lines)
    holder = export_file(context(reader, user="me"), "ideas", None)
    assert any(f"iv30={PERSONAL}" in r["metrics"] for r in rows_of(holder))


def test_the_file_is_the_page_for_the_same_f(filter_backend: MemoryBackend) -> None:  # noqa: F811
    ctx = view(filter_backend)
    f = "dollar_volume:50000000.."
    page = load_ideas(ctx, 100, None, decode_filters(f))
    every = load_ideas(ctx, 100)
    assert export_file(ctx, "ideas", None).row_count == every.total > 4
    same = export_file(ctx, "ideas", f)
    assert [r["instrument_id"] for r in rows_of(same)] == [i.instrument_id for i in page.items]
    assert len(page.items) == 4 == same.row_count  # a narrower file than the unfiltered list


def test_a_more_filters_feature_filter_exports_the_pages_rows(
    filter_backend: MemoryBackend,  # noqa: F811
) -> None:
    """Found in the production check: Export after a More-filters filter answered 403 (the file
    resolved the surface's filters without the requested ``feature:<field>`` ones)."""
    ctx = view(filter_backend)
    f = "feature%3Arollup.volume@v1.dollar_volume:50000000.."
    page = load_ideas(ctx, 100, None, decode_filters(f))
    same = export_file(ctx, "ideas", f)
    assert 0 < page.total < load_ideas(ctx, 100).total
    assert [r["instrument_id"] for r in rows_of(same)] == [i.instrument_id for i in page.items]


def test_screener_results_have_the_pages_rows_for_the_same_f(reader: StoreReader) -> None:
    ctx = context(reader, user="me")
    run = latest_run(ctx, "site", "alpha").run
    assert run is not None
    f = "decision:QUALIFIED"
    page = load_result_page(ctx, run, None, (), 1, 100, decode_filters(f))
    found = export_file(ctx, "screener_results", f, Params("alpha"))
    assert [r["instrument_id"] for r in rows_of(found)] == [r.instrument_id for r in page.results]
    assert found.row_count == page.total >= 1


def test_the_first_line_is_the_notice_and_the_audit_fields_are_recorded(
    reader: StoreReader,
) -> None:
    ctx = context(reader, user="trader")
    found = export_file(ctx, "screener_results", "decision:QUALIFIED", Params("alpha"))
    assert found.lines[0] == (
        f"# algotrade export, session {ctx.session.date}, viewer trader, licences held: [open]; "
        f"{NOTICE}\r\n"
    ) or found.lines[0].startswith("# algotrade export, session ")
    assert "viewer trader" in found.lines[0] and found.lines[0].rstrip().endswith(NOTICE)
    assert (found.viewer, found.surface) == ("trader", "screener_results")
    assert found.filter_hash != "" and found.licences == tuple(sorted(ctx.licences))


def test_no_filter_has_an_empty_hash_and_a_switched_off_one_counts_for_nothing(
    reader: StoreReader,
) -> None:
    ctx = context(reader, user="me")
    plain = export_file(ctx, "screener_results", None, Params("alpha"))
    off = export_file(ctx, "screener_results", "!decision:QUALIFIED", Params("alpha"))
    assert plain.filter_hash == off.filter_hash == "" and plain.row_count == off.row_count


def test_a_filter_the_viewer_is_not_offered_is_refused_before_anything_is_read(
    reader: StoreReader,
) -> None:
    with pytest.raises(FilterRefusedError):
        export_file(context(reader, user="me"), "ideas", "no_such_filter:1..2")


def test_an_unknown_surface_or_screener_is_not_found(reader: StoreReader) -> None:
    ctx = context(reader, user="me")
    with pytest.raises(NotFoundError):
        export_file(ctx, "nothing", None)
    with pytest.raises(NotFoundError):
        export_file(ctx, "screener_results", None, Params("nope"))
    with pytest.raises(ConfigurationError):
        export_file(ctx, "screener_results", None)


def test_a_list_past_the_cap_is_cut_and_says_so(
    reader: StoreReader, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = context(reader, user="me")
    monkeypatch.setattr(surfaces, "ROW_CAP", 2)
    from algotrade.services.read.export import file  # noqa: PLC0415

    monkeypatch.setattr(file, "ROW_CAP", 2)
    found = export_file(ctx, "screener_results", None, Params("alpha"))
    total = latest_run(ctx, "site", "alpha").run
    assert total is not None and found.row_count == 2
    assert found.lines[1].startswith("# cut at 2 of ") and len(rows_of(found)) == 2


def test_unknown_and_not_stored_cells_are_their_kind_or_empty() -> None:
    assert surfaces.text(None) == "" and surfaces.text(0) == "0" and surfaces.text(True) == "true"
    assert surfaces._kinded(None, surfaces.UnavailableKind.NOT_STORED) == "NOT_STORED"
    assert surfaces._kinded(3.5, None) == "3.5"


def test_every_surface_registered_has_a_filter_file() -> None:
    from tests.conftest import REPO_ROOT  # noqa: PLC0415

    for name in surfaces.SURFACES:
        assert (REPO_ROOT / "config" / "site" / "filters" / f"{name}.toml").is_file()
    assert Exported  # the registry's return type
