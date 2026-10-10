from datetime import UTC, date, datetime

from algotrade.services.run_items import chain_coverage, failed_items, normalise, status_code
from algotrade.storage.runs import RunRecord, RunStatus


def test_normalise_drops_the_key_urls_dates_and_numbers() -> None:
    message = "FETCH_ERROR: AAPL giving up on https://x.test/a?b=1 for 2026-10-02 after 3 tries"
    assert (
        normalise(message, "AAPL")
        == "FETCH_ERROR: <id> giving up on <url> for <date> after <n> tries"
    )


def test_normalise_replaces_the_key_only_as_a_whole_token() -> None:
    # A one-letter ticker inside a status code stays put.
    assert (
        normalise("STALE_DATA: chain is for 2026-10-01", "E") == "STALE_DATA: chain is for <date>"
    )
    assert normalise("NO_CHAIN for E", "E") == "NO_CHAIN for <id>"


def test_failed_items_groups_one_cause_across_keys() -> None:
    items = {
        "E": "STALE_DATA: chain is for 2026-10-01",
        "AB": "STALE_DATA: chain is for 2026-09-30",
    }
    items |= {"OK1": "OK"}
    [(reason, rows)] = failed_items(items)
    assert reason == "STALE_DATA: chain is for <date>"
    assert [k for k, _ in rows] == ["AB", "E"]
    assert status_code(rows[0][1]) == "STALE_DATA"


# --- chain coverage -------------------------------------------------------------------------


def _chains(day: date, items: dict[str, str], **stats: object) -> RunRecord:
    now = datetime(day.year, day.month, day.day, 22, tzinfo=UTC)
    return RunRecord(
        run_id=f"option_chains-{day}", job="option_chains", session_date=day, started_at=now,
        finished_at=now, status=RunStatus.COMPLETE, items=items, stats=dict(stats),
    )  # fmt: skip


DAYS = [date(2026, 10, d) for d in (1, 2, 5, 6, 7, 8, 9)]


def _night(day: date, stale: int, ok: int = 100) -> RunRecord:
    items = {f"EQ:S{i}": "STALE_DATA: chain is for 2026-09-01" for i in range(stale)}
    items |= {f"EQ:K{i}": "OK" for i in range(ok)}
    return _chains(day, items, order_tiers={"liquidity": 90, "rest": 10})


def test_coverage_and_chronic_count_from_sample_run_records() -> None:
    # S0 is stale on 5 of 6 nights, S1 on 2, S2 on 3 (the last three), S3 only today
    stale_on = {"EQ:S0": DAYS[1:], "EQ:S1": DAYS[5:], "EQ:S2": DAYS[4:], "EQ:S3": DAYS[-1:]}
    records = []
    for day in DAYS[1:]:
        items = {k: "STALE_DATA: chain is for 2026-09-01" for k, d in stale_on.items() if day in d}
        items |= {f"EQ:K{i}": "OK" for i in range(16)} | {"EQ:N": "NO_CHAIN"}
        records.append(_chains(day, items, order_tiers={"liquidity": 10, "rest": 10}))
    found = chain_coverage(records, DAYS[1:])
    assert found is not None
    assert (found.total, found.ok) == (21, 16)
    assert found.share == 16 / 21
    assert dict(found.statuses) == {"OK": 16, "STALE_DATA": 4, "NO_CHAIN": 1}
    assert dict(found.tiers) == {"liquidity": 10, "rest": 10}
    assert found.chronic == 2  # S0 (5 of the 5 in the window) and S2 (3); S1 has 2, S3 has 1
    assert found.chronic_top == ("EQ:S0", "EQ:S2")


def test_no_chains_record_for_the_session_is_none() -> None:
    assert chain_coverage([_night(DAYS[0], 1)], DAYS[1:2]) is None


def test_drift_warns_when_coverage_falls_below_its_median_or_chronic_jumps() -> None:
    steady = [_night(d, 10) for d in DAYS[:-1]]  # 100 / 110 OK each night
    flat = chain_coverage([*steady, _night(DAYS[-1], 10)], DAYS)
    assert flat is not None and flat.drift() == ()
    dropped = chain_coverage([*steady, _night(DAYS[-1], 25)], DAYS)  # 100 / 125 = 80% vs 90.9%
    assert dropped is not None
    assert any("points below its median" in w for w in dropped.drift())
    small = chain_coverage([*steady, _night(DAYS[-1], 12)], DAYS)  # 100 / 112 = 89.3%: 1.6 points
    assert small is not None and small.drift() == ()


def test_drift_warns_when_the_chronic_count_rises_by_more_than_fifty() -> None:
    quiet = [_night(d, 0) for d in DAYS[:4]]
    stale_now = [_night(d, 60) for d in DAYS[4:]]  # 60 names stale on the last three nights
    found = chain_coverage([*quiet, *stale_now], DAYS)
    assert found is not None
    assert (found.previous_chronic, found.chronic) == (0, 60)
    assert any("chronic stale chains rose to 60 from 0" in w for w in found.drift())
