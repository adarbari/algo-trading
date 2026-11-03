"""The model source of ``attribution``: headlines for the movers without an 8-K, through a scripted
model (no network, no real model): rows with the cited headline, the cap, the skips with their
reasons, a restricted provider never used, and the filing rows untouched."""

from typing import Any

import pandas as pd

from algotrade.core.model.completion import Completion
from algotrade.core.model.errors import ModelUnavailableError
from algotrade.data import StoreReader
from algotrade.storage.configs.files import MemoryConfigStore
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.events.attribution.run import TABLE, ingest_attribution
from algotrade_ingestion.tasks.framework.registry import task
from algotrade_sources.vendors.massive.news import MassiveNews
from tests.apps.ingestion.tasks.events.attribution.test_run import BARE, BIG, NEWS, SESSION, _store
from tests.conftest import REPO_ROOT
from tests.helpers.ingest_fakes import http_for, task_ctx
from tests.helpers.stored_frames import stamped

PAYLOAD = (REPO_ROOT / "tests/fixtures/sources/massive/news_AAA.json").read_bytes()
ANSWER = '{"cause": "guidance", "headline": 1, "confidence": 0.7}'


class Scripted:
    """A text model with scripted answers (an Exception is raised); keeps its calls and closes."""

    def __init__(self, *answers: object) -> None:
        self.answers, self.calls, self.closed = list(answers), [], False

    def complete(self, system: str, user: str, *, tag: Any = None, **_: Any) -> Completion:
        self.calls.append((user, tag))
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return Completion(str(answer), "m1", "p1")

    def close(self) -> None:
        self.closed = True


def _writer_with_symbols() -> StoreWriter:
    writer = _store()
    rows = [
        {"instrument_id": i, "symbol": s, "asset_class": "EQ", "security_type": "COMMON_STOCK",
         "multiplier": 1.0, "status": "ACTIVE"}
        for i, s in ((BIG, "BIG"), (NEWS, "NEWS"), (BARE, "BARE"), ("EQ:QUIET", "QUIET"))
    ]  # fmt: skip
    writer.write_table("instruments/reference", SESSION, "ref", stamped(rows, SESSION, "ref"))
    return writer


def _ctx(writer: StoreWriter, model: object | None, per_night: int = 40, news: bool = True) -> Any:
    configs = MemoryConfigStore({("site", "events", "attribution"): {"news_per_night": per_night}})
    ctx = task_ctx(writer)
    ctx.configs = configs
    if news:
        ctx.sources = {"massive_news": MassiveNews(http_for(lambda url: PAYLOAD))}
    ctx.text_model_factory = lambda: (model, "the text model is off") if model else (None, "off")  # type: ignore[assignment, return-value]
    return ctx


def _stored(writer: StoreWriter) -> pd.DataFrame:
    frame = StoreReader(writer._backend).table(TABLE, SESSION)
    assert frame is not None
    return frame


def test_a_mover_without_an_8k_gets_a_model_row_citing_its_headline() -> None:
    writer, model = _writer_with_symbols(), Scripted(ANSWER, ANSWER)
    record = ingest_attribution(_ctx(writer, model), SESSION)
    out = _stored(writer).set_index(["instrument_id", "source"])
    assert out.loc[(BIG, "filing"), "cause_class"] == "results"  # the 8-K row stays
    row = out.loc[(NEWS, "model")]
    assert (
        row["cause_class"] == "guidance"
        and row["evidence"] == "AAA cuts full-year guidance on weak demand"
    )
    assert row["model"] == "p1:m1" and row["prompt_version"] == "attributing/v1"
    assert pd.Timestamp(row["known_from"]).date() == SESSION and row["confidence"] == 0.7
    assert len(model.calls) == 2 and model.closed  # NEWS and BARE; BIG has its filing
    assert record.stats["model"]["asked"] == 2  # type: ignore[index]


def test_the_cap_limits_the_requests_and_a_restricted_chain_is_never_asked_for() -> None:
    writer, model = _writer_with_symbols(), Scripted(ANSWER)
    record = ingest_attribution(_ctx(writer, model, per_night=1), SESSION)
    assert record.stats["model"]["asked"] == 1 and len(model.calls) == 1  # type: ignore[index]


def test_the_source_is_skipped_with_its_reason_and_the_filing_rows_stay() -> None:
    for ctx_args, reason in (
        ({"model": None}, "off"),
        ({"model": Scripted(), "news": False}, "massive_news is not built"),
        ({"model": Scripted(), "per_night": 0}, "news_per_night is 0"),
    ):
        writer = _writer_with_symbols()
        record = ingest_attribution(_ctx(writer, **ctx_args), SESSION)  # type: ignore[arg-type]
        assert reason in str(record.stats["model"]["skipped"])  # type: ignore[index]
        assert list(_stored(writer)["source"]) == ["filing"]


def test_answers_that_fail_the_check_store_nothing_and_a_spent_budget_stops_the_night() -> None:
    writer = _writer_with_symbols()
    model = Scripted(
        '{"cause": "alien", "headline": 1, "confidence": 0.5}',
        ModelUnavailableError("budget spent"),
    )
    record = ingest_attribution(_ctx(writer, model), SESSION)
    stats = record.stats["model"]
    assert stats["stored"] == 0  # type: ignore[index]
    assert any("taxonomy" in k for k in stats["dropped"]) and any(
        "ModelUnavailableError" in k for k in stats["dropped"]
    )  # type: ignore[index]
    assert list(_stored(writer)["source"]) == ["filing"] and model.closed


def test_the_task_builds_the_news_source_it_declares() -> None:
    assert "massive_news" in task("attribution").optional_sources
