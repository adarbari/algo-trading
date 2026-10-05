"""etf-holdings second review: one global due list, rejected reads that can succeed, layout
changes that fail loudly."""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import pandas as pd
import pytest

from algotrade.data.resolver import SymbolResolver
from algotrade.storage.runs import RunStatus
from algotrade_ingestion.tasks.market.etf_holdings import (
    HoldingsSources,
    Previous,
    Rejection,
    confirmed,
    fund_frame,
    plan_due,
    retry_days,
    sanity_problem,
)
from algotrade_sources.framework.holdings import holdings_frame
from tests.apps.ingestion.tasks.market.test_etf_holdings import (
    DAY,
    holdings,
    ishares,
    nport,
    run,
    ssga,
    world,
)
from tests.apps.ingestion.tasks.market.test_etf_holdings_checks import LATER, Rows, xlk_file


@dataclass(frozen=True)
class Fake:
    name: str
    cadence_days: int


STATE_STREET, ISHARES, N_PORT = Fake("ssga", 1), Fake("ishares", 1), Fake("nport", 90)
ISSUERS = [STATE_STREET, ISHARES, N_PORT]
UNIVERSE = {
    **{f"S{i:03d}": STATE_STREET for i in range(181)},
    **{f"I{i:03d}": ISHARES for i in range(480)},
    **{f"N{i:03d}": N_PORT for i in range(480)},
}


def simulate(
    cap: int, weekdays: int = 252
) -> tuple[dict[str, date], dict[str, int], dict[str, int]]:
    """Read ``cap`` funds a weekday for a year -> (first read, longest gap, reads) per fund."""
    read: dict[str, date] = {}
    first: dict[str, date] = {}
    gaps: dict[str, int] = {}
    reads = dict.fromkeys(UNIVERSE, 0)
    day, done = date(2026, 1, 5), 0
    while done < weekdays:
        if day.weekday() < 5:
            done += 1
            for fund in plan_due(UNIVERSE, ISSUERS, read, day, 7)[:cap]:
                if fund in read:
                    gaps[fund] = max(gaps.get(fund, 0), (day - read[fund]).days)
                first.setdefault(fund, day)
                read[fund] = day
                reads[fund] += 1
        day += timedelta(days=1)
    return first, gaps, reads


@pytest.mark.parametrize("cap", [100, 200])
def test_the_nightly_cap_never_starves_the_n_port_funds(cap: int) -> None:
    """Capping each issuer's list before merging read State Street and iShares first, every night,
    and never reached N-PORT (a year of due_keys simulated)."""
    first, _, reads = simulate(cap)
    n_port = [f for f in UNIVERSE if f.startswith("N")]
    assert set(first) == set(UNIVERSE)  # every fund was read
    assert all(reads[f] >= 3 for f in n_port)  # quarterly, about 4 a year
    assert max(first[f] for f in UNIVERSE) <= date(2026, 1, 5) + timedelta(days=21)


def test_two_hundred_a_night_reads_weekly_funds_every_week_or_so() -> None:
    _, gaps, reads = simulate(200)
    daily = [f for f in UNIVERSE if not f.startswith("N")]
    assert max(gaps[f] for f in daily) <= 8
    assert min(reads[f] for f in daily) >= 50
    assert max(gaps[f] for f in UNIVERSE if f.startswith("N")) <= 95


def test_the_list_is_new_funds_first_then_the_oldest_with_issuer_priority_on_ties() -> None:
    covered = {"S1": STATE_STREET, "I1": ISHARES, "N1": N_PORT, "I2": ISHARES, "S2": STATE_STREET}
    read = {"I2": date(2026, 1, 1), "S2": date(2026, 1, 3)}
    order = plan_due(covered, ISSUERS, read, date(2026, 2, 1), 7)
    assert order == ["S1", "I1", "N1", "I2", "S2"]  # new by issuer priority, then oldest first
    held = plan_due(covered, ISSUERS, read, date(2026, 2, 1), 7, hold={"S1": date(2026, 2, 3)})
    assert "S1" not in held and "I1" in held  # a rejected fund waits
    forced = plan_due(covered, ISSUERS, read, date(2026, 2, 1), 7, True, {"S1": date(2026, 2, 3)})
    assert "S1" in forced


def test_a_rejected_fund_waits_two_days_a_quarterly_one_longer() -> None:
    assert (retry_days(STATE_STREET), retry_days(N_PORT)) == (2, 30)


def soft(as_of: date) -> Rejection:
    return Rejection(as_of, as_of, True)


def test_three_consistent_reads_confirm_a_collapsed_position_count() -> None:
    assert not confirmed([], DAY)
    assert not confirmed([soft(DAY)], DAY + timedelta(days=2))  # one earlier read is not enough
    assert not confirmed([soft(DAY), soft(DAY)], DAY)  # the same day twice is one read
    two = [soft(DAY), soft(DAY + timedelta(days=2))]
    assert confirmed(two, DAY + timedelta(days=4))
    assert not confirmed(two, DAY + timedelta(days=1))  # an older file does not count
    assert not confirmed(
        [Rejection(DAY, DAY, False), Rejection(DAY, DAY + timedelta(days=1), False)],
        DAY + timedelta(days=9),
    )


def cut(rows: Rows) -> Rows:
    header = next(i for i, r in enumerate(rows) if r[0] == "Name")
    return [*rows[: header + 4], rows[-1]]  # three holdings and the disclaimer


def dated(rows: Rows, as_of: str) -> Rows:
    return [
        tuple(v.replace("01-Oct-2026", as_of) if isinstance(v, str) else v for v in r) for r in rows
    ]


def reread(writer: Any, sources: HoldingsSources, day: date, **kwargs: Any) -> Any:
    return run(writer, sources, day, **kwargs)


def cut_on(as_of: str) -> bytes:
    return xlk_file(lambda rows: dated(cut(rows), as_of))


def sources_with(files: dict[str, bytes]) -> HoldingsSources:
    return HoldingsSources([ssga(files=files), ishares(), nport()], 7, 100, "optionable", False)


def test_a_real_rebalance_wins_after_three_consistent_reads() -> None:
    """XLK goes from 12 positions to 3: rejected twice (a week and two days apart), accepted on
    the third read, so the fund is not PARTIAL forever."""
    writer, base = world()
    run(writer, base)
    assert len(holdings(writer, "XLK")) == 12
    outcomes = []
    for offset, as_of in ((8, "08-Oct-2026"), (10, "10-Oct-2026"), (12, "12-Oct-2026")):
        day = DAY + timedelta(days=offset)
        record = reread(writer, sources_with({"xlk.xlsx": cut_on(as_of)}), day)
        outcomes.append(record.items["XLK"])
    assert outcomes[0].startswith("FAILED: 3 positions, was 12") and "soft" in outcomes[0]
    assert outcomes[1].startswith("FAILED: 3 positions, was 12")
    assert outcomes[2].startswith("OK: 3 lines") and "confirmed" in outcomes[2]
    assert len(holdings(writer, "XLK", DAY + timedelta(days=12))) == 3


def test_a_rejected_fund_is_not_fetched_again_the_next_day() -> None:
    writer, base = world()
    run(writer, base)
    files = {"xlk.xlsx": cut_on("08-Oct-2026")}
    first = reread(writer, sources_with(files), DAY + timedelta(days=8))
    assert first.items["XLK"].startswith("FAILED")
    next_day = reread(writer, sources_with(files), DAY + timedelta(days=9))
    assert "XLK" not in next_day.items  # waits two days
    two_days = reread(writer, sources_with(files), DAY + timedelta(days=10))
    assert two_days.items["XLK"].startswith("FAILED")


def test_an_older_file_is_never_accepted_however_often_it_repeats() -> None:
    writer, base = world()
    run(writer, base)
    for offset in (8, 10, 12, 14):
        files = {"xlk.xlsx": xlk_file(lambda rows: dated(rows, "24-Sep-2026"))}
        record = reread(writer, sources_with(files), DAY + timedelta(days=offset))
        assert record.items["XLK"].startswith("FAILED: as of 2026-09-24, older")
        assert "hard" in record.items["XLK"]
    assert set(holdings(writer, "XLK", DAY + timedelta(days=14))["as_of"]) == {date(2026, 10, 1)}


def test_force_accepts_what_it_reads_without_the_checks() -> None:
    writer, base = world()
    run(writer, base)
    forced = reread(
        writer, sources_with({"xlk.xlsx": cut_on("08-Oct-2026")}), LATER, force=True, only=("XLK",)
    )
    assert forced.items["XLK"].startswith("OK: 3 lines") and forced.status is RunStatus.COMPLETE
    assert len(holdings(writer, "XLK", LATER)) == 3


def test_a_changed_state_street_date_line_fails_loudly_and_keeps_the_rows() -> None:
    def no_date(rows: Rows) -> Rows:
        return [
            tuple("Holdings changed" if v == "Holdings:" else v for v in r)
            for r in dated(rows, "-")
        ]

    writer, base = world()
    run(writer, base)
    record = reread(writer, sources_with({"xlk.xlsx": xlk_file(no_date)}), LATER)
    assert (
        record.items["XLK"].startswith("FETCH_ERROR") and "date it is as of" in record.items["XLK"]
    )
    assert record.status is RunStatus.PARTIAL and len(holdings(writer, "XLK", LATER)) == 12


def test_a_blank_column_before_weight_does_not_hide_the_whole_table() -> None:
    """openpyxl rows keep the empty cell, so the position of Weight in the header and in each
    row must agree (dropping the empty header cell shifted every later column by one)."""

    def gap(rows: Rows) -> Rows:
        header = next(i for i, r in enumerate(rows) if r[0] == "Name")
        out = []
        for i, row in enumerate(rows):
            if i < header or i > len(rows) - 2:
                out.append(row)
            else:
                out.append((*row[:4], None, *row[4:]))  # an empty column before Weight
        return out

    writer, _ = world()
    record = reread(writer, sources_with({"xlk.xlsx": xlk_file(gap)}), DAY)
    assert record.items["XLK"].startswith("OK: 12 lines")
    assert holdings(writer, "XLK")["weight"].iloc[0] == pytest.approx(0.15470648)


# --- the file's own weights, the S&P 500 floor, CUSIP ids --------------------------------------


def lines(*weights: float) -> pd.DataFrame:
    return holdings_frame(
        {"holding_name": f"L{i}", "weight": w, "asset_class": "Equity", "us_listed": False}
        for i, w in enumerate(weights)
    )


def test_an_ishares_file_cut_short_fails_on_its_own_published_weights() -> None:
    """Market-value weights always add up to 100%, so a truncated file passes the sum check. The
    published column (sum 0.91 for 300 of 500 lines) does not."""
    whole = lines(0.5, 0.5)
    assert sanity_problem(whole, DAY, None, False, True, published=0.999) is None
    cut_short = sanity_problem(whole, DAY, None, False, True, published=0.91)
    assert cut_short is not None and "cut short" in cut_short.text and not cut_short.soft
    assert sanity_problem(whole, DAY, None, True, True, published=0.91) is None  # geared funds
    assert sanity_problem(whole, DAY, None, False, True, published=None) is None  # bond funds


def test_a_recycled_ticker_does_not_move_a_stored_cusip_to_another_company() -> None:
    """The map keeps the instrument written with the line: 'OLD' is today another company."""
    resolver = SymbolResolver(ids={"OLD": "EQ:NEW"}, symbols={"EQ:NEW": "OLD"})
    frame = holdings_frame(
        [{"holding_name": "Old Co", "weight": 1.0, "asset_class": "Equity", "us_listed": False}]
    ).assign(identifier="037833100", filed=None, holding_symbol=None, sector=None, shares=None)
    rows = fund_frame("EQ:F", "F", DAY, frame, 100, resolver, {"037833100": ("OLD", "EQ:OLD")})
    assert list(rows["holding_id"]) == ["EQ:OLD"] and list(rows["holding_symbol"]) == ["OLD"]


def test_previous_is_compared_on_positions_only_for_daily_files() -> None:
    few = lines(0.5, 0.5)
    quarterly = sanity_problem(few, DAY, Previous(DAY, 300), False, False, check_count=False)
    assert quarterly is None  # a new quarterly report may be a different size
    daily = sanity_problem(few, DAY, Previous(DAY, 300), False, False)
    assert daily is not None and daily.soft
