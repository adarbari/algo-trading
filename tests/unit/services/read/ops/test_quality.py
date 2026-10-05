"""The session's data-quality checks and live verification: exactly the session (ADR 0036),
NOT_RUN / NO_PARTITION otherwise, never an earlier session's."""

from datetime import UTC, date, datetime

from algotrade.config.user import UserContext
from algotrade.data import StoreReader
from algotrade.services.read.context import ReadContext, open_context
from algotrade.services.read.ops.quality import QualityReport, load_quality, load_verification
from algotrade.services.read.values import UnknownCode
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import MemoryConfigStore
from algotrade.storage.runs import start_run
from algotrade_api.deps import ReadStore

NOW = datetime(2026, 10, 3, 2, tzinfo=UTC)
GOLDEN = date(2022, 11, 23)


def _golden(api_golden: tuple[ReadStore, dict[str, str]], day: date | None = None) -> ReadContext:
    store = api_golden[0]
    return open_context(store.reader, store.configs, store.user, day)


def test_quality_of_the_session(api_golden: tuple[ReadStore, dict[str, str]]) -> None:
    report = load_quality(_golden(api_golden))
    assert (report.session, report.status, report.unknown) == (GOLDEN, "complete", None)
    assert [(c.name, c.status) for c in report.checks] == [
        ("bars_fresh", "PASS"),
        ("chains_stale", "WARN"),
    ]


def test_quality_falls_back_to_items_and_never_reads_an_earlier_session() -> None:
    backend = MemoryBackend()
    run = start_run("data_quality", date(2026, 10, 1), NOW)
    run.items = {"bars_fresh": "FAIL"}
    backend.runs.save(run.finish(NOW))
    reader = StoreReader(backend)

    def report(day: date) -> QualityReport:
        ctx = open_context(reader, MemoryConfigStore({}), UserContext("local"), day)
        return load_quality(ctx)

    found = report(date(2026, 10, 1))
    assert [(c.name, c.status, c.detail) for c in found.checks] == [("bars_fresh", "FAIL", "")]
    later = report(date(2026, 10, 2))  # the 1st's run exists and is not shown
    assert later.unknown is not None and later.unknown.code is UnknownCode.NOT_RUN
    assert (later.run_id, later.checks) == (None, ())


def test_verification_counts_and_failing_rows(api_golden: tuple[ReadStore, dict[str, str]]) -> None:
    found = load_verification(_golden(api_golden))
    assert (found.session, found.instruments, found.unknown) == (GOLDEN, 3, None)
    assert found.counts == {"PASS": 1, "WARN": 1, "FAIL": 2, "NA": 1}
    assert [c.check for c in found.by_check] == ["low", "close", "div_yield"]
    assert found.by_check[0].counts["FAIL"] == 2
    failing = [(r["symbol"], r["check"], r["status"]) for r in found.failing]
    assert failing == [("BBB", "low", "FAIL"), ("AAA", "low", "FAIL"), ("BBB", "close", "WARN")]
    assert set(found.failing[0]) >= {"instrument_id", "ours", "theirs", "diff", "tolerance"}
    assert "run_id" not in found.failing[0] and found.run_ids


def test_verification_is_unknown_for_another_session(
    api_golden: tuple[ReadStore, dict[str, str]],
) -> None:
    for day in (date(2022, 11, 22), date(2022, 11, 24)):  # before; after (23rd's is not used)
        found = load_verification(_golden(api_golden, day))
        assert found.unknown is not None and found.unknown.code is UnknownCode.NO_PARTITION
        assert (found.session, found.counts, found.failing) == (day, {}, ())
