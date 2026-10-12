"""``PartRedraftCap`` (owner decisions 2026-10-11 and 2026-10-12, ADR 0041 amended 2026-10-12): a
user's part re-drafts of the exchange day are counted from the usage log, so a restart does not
reset them; only a call that returned a draft uses up a place (a failed, refused or unavailable
one gives it back); the calls this process made that the background recorder has not written yet
count too (once, when they reach the log); requests that arrive together cannot pass the last
place; a count that cannot be read refuses."""

import threading
from datetime import UTC, date, datetime
from typing import Any

import pandas as pd
import pytest

from algotrade.core.model.errors import DailyLimitError, ModelUnavailableError
from algotrade.data import StoreReader
from algotrade.data.usage import LLM_CALLS
from algotrade.services.drafting.redraft.cap import CODE, USE_CASE, PartRedraftCap
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.stored_frames import stamped

NOW = datetime(2026, 10, 12, 15, 0, tzinfo=UTC)  # 11:00 in New York
DAY = date(2026, 10, 12)


def row(
    call_id: str,
    user: str = "abhi",
    use_case: str = USE_CASE,
    day: date = DAY,
    outcome: str = "ok",
    second: int = 0,
) -> dict[str, Any]:
    return {
        "ts": pd.Timestamp(day, tz="UTC") + pd.Timedelta(hours=15, seconds=second),
        "provider": "claude", "model": "m", "use_case": use_case, "user": user,
        "input_tokens": 10, "output_tokens": 5, "latency_s": 1.0, "cost_usd": 0.1,
        "cost_basis": "price", "outcome": outcome, "fell_back_from": None, "call_id": call_id,
    }  # fmt: skip


class Store:
    """A usage log the test writes to, as the API's recorder would."""

    def __init__(self) -> None:
        self.backend = MemoryBackend()
        self.reader = StoreReader(self.backend)
        self.runs = 0

    def log(self, *rows: dict[str, Any], day: date = DAY) -> None:
        self.runs += 1
        run = f"r{self.runs}"
        StoreWriter(self.backend).write_table(LLM_CALLS, day, run, stamped(list(rows), day, run))


def cap(store: Store, limit: int = 3, now: datetime = NOW) -> PartRedraftCap:
    return PartRedraftCap(store.reader, lambda: limit, lambda: now)


def use(c: PartRedraftCap, user: str = "abhi", call_id: str | None = None) -> None:
    with c.slot(user) as slot:
        slot.note(call_id)


def test_a_user_may_re_draft_up_to_the_limit_then_the_limit_is_reached() -> None:
    c = cap(Store(), limit=3)
    for n in range(3):
        use(c, call_id=f"c{n}")
    with pytest.raises(DailyLimitError) as reached:
        use(c, call_id="c3")
    error = reached.value
    assert (error.code, error.limit) == (CODE, 3) == ("part_redraft_limit", 3)
    assert "daily limit of 3" in str(error) and error.retry_after_s == 13 * 3600  # to midnight, NY
    use(c, user="bea")  # another user has their own count


def test_the_count_is_read_from_the_usage_log_so_a_restart_does_not_reset_it() -> None:
    store = Store()
    store.log(row("a"), row("b", second=1), row("c", second=2))
    fresh = cap(store, limit=3)  # a new process: no memory of its own
    with pytest.raises(DailyLimitError):
        use(fresh)
    store.log(row("d", user="bea"), row("e", use_case="screener-draft"))  # not this user's count
    with pytest.raises(DailyLimitError):
        use(cap(store, limit=3))
    use(cap(store, limit=4))  # the limit is read for each request: a raised limit applies


def test_only_answered_calls_of_the_log_count_not_failed_or_skipped_attempts() -> None:
    store = Store()
    store.log(row("a"), row("a", second=1), row("b", outcome="failed", second=2),
              row("c", outcome="skipped_budget", second=3))  # fmt: skip
    c = cap(store, limit=3)
    use(c, call_id="x")  # a and x: two; b failed and c was never asked
    use(c, call_id="y")  # three
    with pytest.raises(DailyLimitError):
        use(c)


def test_a_call_not_yet_in_the_log_counts_and_counts_once_when_it_reaches_it() -> None:
    store = Store()
    c = cap(store, limit=2)
    use(c, call_id="made-now")
    use(c, call_id="then-this")
    with pytest.raises(DailyLimitError):  # the recorder has written neither
        use(c)
    store.log(row("made-now"), row("then-this", second=1))  # now they are in the log
    with pytest.raises(DailyLimitError):
        use(c)
    assert len(c._made[("abhi", DAY)]) == 2  # still two, not four


def test_a_call_with_no_known_id_still_counts() -> None:
    c = cap(Store(), limit=1)
    use(c, call_id=None)
    with pytest.raises(DailyLimitError):
        use(c)


def test_a_re_draft_in_flight_holds_its_place() -> None:
    c = cap(Store(), limit=1)
    with (
        c.slot("abhi"),
        pytest.raises(DailyLimitError),
        c.slot("abhi"),
    ):  # a request at the same time
        pass


def test_a_failure_before_the_model_was_asked_gives_the_place_back() -> None:
    c = cap(Store(), limit=1)
    with pytest.raises(ValueError), c.slot("abhi"):
        raise ValueError("the request was refused before the model")
    use(c, call_id="ok")  # the place was free again


def test_a_failure_after_the_model_answered_gives_the_place_back_too() -> None:
    """Owner decision 2026-10-12: only a call that returned a draft counts."""
    c = cap(Store(), limit=1)
    with pytest.raises(ValueError), c.slot("abhi") as slot:
        slot.note("c1")
        raise ValueError("the merge failed")
    assert c._made[("abhi", DAY)] == set()
    use(c, call_id="c2")  # the place was free again
    with pytest.raises(DailyLimitError):
        use(c)


def test_a_model_that_failed_even_with_a_call_id_gives_the_place_back() -> None:
    class FailedError(ModelUnavailableError):
        pass

    c = cap(Store(), limit=1)
    with_id = FailedError("every attempt failed")
    with_id.call_id = "c9"  # the failed attempts are in the log, which counts no failed call
    with pytest.raises(FailedError), c.slot("abhi"):
        raise with_id
    use(c, call_id="c10")


def test_noting_the_call_swaps_the_token_for_its_id_so_the_log_row_is_not_counted_twice() -> None:
    store = Store()
    c = cap(store, limit=2)
    with c.slot("abhi") as slot:
        assert len(c._made[("abhi", DAY)]) == 1 and slot.key.startswith("pending-")
        slot.note("c1")
        assert c._made[("abhi", DAY)] == {"c1"} and slot.key == "c1"
        slot.note(None)  # a model that gives no id leaves it as it is
        assert c._made[("abhi", DAY)] == {"c1"}
    store.log(row("c1"))  # the recorder has now written it
    use(c, call_id="c2")  # still room for one more: c1 was counted once, not twice
    with pytest.raises(DailyLimitError):
        use(c)


def test_requests_that_arrive_together_cannot_pass_the_last_places() -> None:
    limit, threads = 3, 10
    c = cap(Store(), limit=limit)
    start, done = threading.Barrier(threads), threading.Event()
    admitted: list[int] = []
    refused: list[int] = []
    settled = threading.Semaphore(0)

    def request(n: int) -> None:
        start.wait()
        try:
            with c.slot("abhi"):
                admitted.append(n)
                settled.release()
                done.wait(5)  # hold the place, as a model call in flight does
        except DailyLimitError:
            refused.append(n)
            settled.release()

    workers = [threading.Thread(target=request, args=(n,)) for n in range(threads)]
    for w in workers:
        w.start()
    for _ in range(threads):
        assert settled.acquire(timeout=5)  # every request has been admitted or refused
    done.set()
    for w in workers:
        w.join(5)
    assert len(admitted) == limit and len(refused) == threads - limit


def test_the_day_is_the_exchange_date_and_yesterdays_calls_do_not_count() -> None:
    store = Store()
    store.log(row("old1", day=date(2026, 10, 11)), row("old2", day=date(2026, 10, 11), second=1),
              day=date(2026, 10, 11))  # fmt: skip
    c = cap(store, limit=2, now=NOW)
    use(c, call_id="today1")
    # 01:00 UTC on the 13th is still the 12th in New York: one more of the same day
    late = PartRedraftCap(store.reader, lambda: 2, lambda: datetime(2026, 10, 13, 1, tzinfo=UTC))
    late._made = c._made
    use(late, call_id="today2")
    with pytest.raises(DailyLimitError):
        use(late)
    # 05:00 UTC on the 13th is the 13th in New York: a new day, the count starts again
    next_day = PartRedraftCap(
        store.reader, lambda: 2, lambda: datetime(2026, 10, 13, 5, tzinfo=UTC)
    )
    next_day._made = c._made
    use(next_day, call_id="tomorrow1")
    assert all(day >= date(2026, 10, 13) for _, day in next_day._made)  # yesterday forgotten


def test_a_limit_of_zero_turns_part_re_drafts_off() -> None:
    with pytest.raises(DailyLimitError, match="daily limit of 0"):
        use(cap(Store(), limit=0))


def test_a_count_that_cannot_be_read_refuses_rather_than_allows() -> None:
    class Broken:
        def table_range(self, *args: Any, **kwargs: Any) -> Any:
            raise OSError("the store is gone")

    c = PartRedraftCap(Broken(), lambda: 30, lambda: NOW)  # type: ignore[arg-type]
    with pytest.raises(ModelUnavailableError, match="the daily limit cannot be checked"):
        use(c)
    assert c._made == {}  # nothing was admitted


def test_the_retry_after_is_at_least_a_second_just_before_midnight() -> None:
    almost = datetime(2026, 10, 13, 3, 59, 59, 900000, tzinfo=UTC)  # 23:59:59.9 in New York
    with pytest.raises(DailyLimitError) as reached:
        use(cap(Store(), limit=0, now=almost))
    assert reached.value.retry_after_s == 1
