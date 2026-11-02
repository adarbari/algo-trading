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


def test_a_company_name_that_is_a_formula_is_neutralised_and_a_negative_value_stays_numeric() -> (
    None
):
    from dataclasses import replace  # noqa: PLC0415

    backend = MemoryBackend()
    write_run(backend, "site1", FROZEN, 0.6, trades=LEDGER)
    ctx = context(named(backend), "owner", reference=OCT)
    row = load_edge_trades(ctx, edge_of(ctx), Period.ALL, limit=None).rows[0]
    row = replace(
        row,
        company=replace(row.company, value='=HYPERLINK("x")'),
        value=replace(row.value, value=-0.5),
    )
    lines = list(csv_lines((row,)))
    header = lines[0].strip().split(",")
    cells = lines[1].strip().split(",")
    assert cells[header.index("company")].startswith("\"'=") or cells[
        header.index("company")
    ].startswith("'=")
    assert cells[header.index("value")] == "-0.5"


def test_an_option_trade_lists_its_contract_columns_under_its_value_licence() -> None:
    """E11: the ledger's option columns (how it closed, what its return is on, the return on
    collateral before and after cost, the collateral, an option's hedged and stock returns and
    wing cost) in the file and the graph alike; a bought-history trade's figures are personal,
    so a viewer without that licence sees LICENCE, never the number."""
    from tests.unit.services.read.edge_ledger.conftest import pick  # noqa: PLC0415

    option = {
        "exit_kind": "TAKE_PROFIT", "capital_basis": "cash_secured", "return_on_capital": 0.012,
        "return_on_capital_gross": 0.015, "capital": 95.0, "max_adverse": -0.03,
        "hedged_roc": 0.004, "stock_roc": None, "wing_cost": None, "value_licence": "personal",
    }  # fmt: skip
    trades = [pick(LEDGER[0]["decision_session"], "EQ:B", 1, True, **option)]
    for user, shown in (("owner", "0.012"), ("me", "LICENCE")):
        backend = MemoryBackend()
        write_run(backend, "site1", FROZEN, 0.6, trades=trades)
        ctx = context(named(backend), user, reference=OCT)
        page = load_edge_trades(ctx, edge_of(ctx), Period.ALL, limit=None)
        header, cells = (line.strip().split(",") for line in list(csv_lines(page.rows))[:2])
        got = dict(zip(header, cells, strict=True))
        assert (got["exit_kind"], got["capital_basis"]) == ("TAKE_PROFIT", "cash_secured")
        assert got["return_on_capital"] == shown
        if user == "owner":  # a figure not stored is empty, never 0
            assert (got["capital"], got["return_on_capital_gross"]) == ("95.0", "0.015")
            assert got["stock_roc"] == ""
