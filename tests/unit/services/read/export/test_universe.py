"""The universe surface's file: catalogue columns by name under the viewer's licences (a personal
IBKR value is ``LICENCE`` to a non-holder, the value to the holder) and the page's filters."""

from algotrade.services.read.export.file import export_file
from algotrade.services.read.export.surfaces import Params
from tests.unit.services.read.export.test_file import rows_of
from tests.unit.services.read.instruments.conftest import (
    IBKR_IV30,
    context_as,
    store_with,
    with_ibkr,
)
from tests.unit.services.read.instruments.test_table import _universe

CLOSE = "rollup.price_stats@v2.close"


def test_the_universe_file_has_the_columns_and_hides_a_personal_value_from_a_non_holder() -> None:
    reader = store_with(_universe, with_ibkr)
    params = Params(columns=(CLOSE, IBKR_IV30))
    mine = rows_of(export_file(context_as(reader, "owner"), "universe", None, params))
    theirs = export_file(context_as(reader, "trader"), "universe", None, params)
    assert [r["symbol"] for r in mine] == ["AAA", "ETFX"]
    assert mine[0][IBKR_IV30] == "0.42" and mine[0][CLOSE] == "51.0"
    other = {r["symbol"]: r for r in rows_of(theirs)}
    assert other["AAA"][IBKR_IV30] == "LICENCE" and "0.42" not in "".join(theirs.lines)
    assert other["AAA"][CLOSE] == "51.0"  # an open value is the same for everyone
