"""``EdgeResult.regimes`` and ``EdgeResult.horizons`` serve the read model's figures, flags, dates
and states as they are: a state says why a figure is missing (null, never a zero)."""

from datetime import date

from algotrade.services.read.edge_evidence.slices import figures, horizons, regimes
from algotrade_api.graphql.schema import schema
from algotrade_api.graphql.types.evaluation.edge_slices import EdgeHorizons, EdgeRegimes


def test_regimes_serve_the_stored_figure_and_the_missing_sides_as_null() -> None:
    whole = figures.SliceFigure("all", "measured", 0.6, 0.4, 20.0, 9, True)
    gone = figures.SliceFigure("in_sample", "not_stored", None, None, None, None, False)
    served = EdgeRegimes.of(
        regimes.EdgeRegimes("measured", "momo", 20, (regimes.RegimeRow("CALM", (whole, gone)),))
    )
    (row,) = served.rows
    assert (served.state, served.variant, served.horizon, row.regime) == (
        "measured", "momo", 20, "CALM"
    )  # fmt: skip
    assert (row.figures[0].lift_pts, row.figures[0].trades, row.figures[0].thin) == (20.0, 9, True)
    assert row.figures[1].state == "not_stored" and row.figures[1].win_rate is None


def test_horizons_serve_the_basis_mark_and_the_expected_date() -> None:
    fig = figures.SliceFigure("out_of_sample", "measured", 0.52, 0.5, 2.0, 30, True)
    by = horizons.OosBy("projected", 40, 30, 10, date(2026, 10, 10), 1.0)
    served = EdgeHorizons.of(
        horizons.EdgeHorizons("measured", "momo", 40, (horizons.HorizonRow(5, True, (fig,), by),))
    )
    (row,) = served.rows
    assert (served.needed, row.horizon, row.basis) == (40, 5, True)
    assert (row.oos_by.state, row.oos_by.expected_by, row.oos_by.remaining) == (
        "projected", date(2026, 10, 10), 10
    )  # fmt: skip


def test_the_result_has_both_slice_sections_and_the_types_have_no_derived_field() -> None:
    sdl = schema.as_str()
    result = sdl[sdl.index("type EdgeResult {") :].split("\n}")[0]
    assert "  regimes: EdgeRegimes!" in result and "  horizons: EdgeHorizons!" in result
    row = sdl[sdl.index("type HorizonRow {") :].split("\n}")[0]
    assert "oosBy: OosBy!" in row and "basis: Boolean!" in row
