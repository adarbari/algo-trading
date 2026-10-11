"""The CSV file of the ledger (ADR 0064 decision 11): the page's rows, the ticker beside the id, an
unknown ticker empty (its public kind), never the id in its place."""

from algotrade.services.read.edge_ledger.trades import Period, load_edge_trades
from algotrade.services.read.edge_ledger.trades_csv import csv_lines
from algotrade.storage.backends.memory import MemoryBackend
from tests.unit.services.read.edge_ledger.conftest import LEDGER, context
from tests.unit.services.read.edge_ledger.test_trades import OCT, edge_of, named
from tests.unit.services.read.evaluation.conftest import FROZEN, write_run


def test_the_file_has_the_ticker_and_company_and_an_unnamed_pick_has_neither() -> None:
    backend = MemoryBackend()
    write_run(backend, "site1", FROZEN, 0.6, trades=LEDGER)
    ctx = context(named(backend), "owner", reference=OCT)
    page = load_edge_trades(ctx, edge_of(ctx), Period.ALL, limit=None)
    lines = "".join(csv_lines(page.rows)).splitlines()
    header = lines[0].split(",")
    at = header.index("symbol")
    assert header[at + 1] == "company"
    rows = [line.split(",") for line in lines[1:]]
    assert rows[0][at : at + 2] == ["OLD", "Old Inc"]  # the ticker at the decision session
    assert rows[2][at : at + 2] == ["NOT_STORED", "NOT_STORED"]  # the public kind, never the id
