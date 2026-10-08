"""The event loop stays free (ADR 0037): a top-level field's blocking resolver runs in the read
pool (``offload.OffLoop``), an async resolver never calls a blocking context open, and the
read pool is not the pool the sync routes (``/health``) wait on. Found on the real store: the
hosted API answered ``/health`` in 28-36 s during a page load, because plain ``def`` resolvers
ran their parquet reads on the loop."""

import ast
import asyncio
import threading
import time
from pathlib import Path
from typing import Any

import strawberry
from anyio import to_thread

import algotrade_api.graphql.types.query as query_module
from algotrade_api.graphql.offload import INLINE, READ_THREADS, OffLoop, off_loop, read_limiter
from algotrade_api.graphql.schema import schema as served


@strawberry.type
class Leaf:
    @strawberry.field
    def thread(self) -> str:  # a nested field: a mapping, it stays on the loop
        return str(threading.get_ident())


@strawberry.type
class Slow:
    @strawberry.field
    def slow(self) -> str:  # a plain def that blocks, as every read resolver is
        time.sleep(0.3)
        return str(threading.get_ident())

    @strawberry.field
    async def waits(self) -> str:  # an async resolver awaits on the loop
        await asyncio.sleep(0.01)
        return str(threading.get_ident())

    @strawberry.field(metadata=INLINE)  # type: ignore[untyped-decorator]
    def quick(self) -> str:  # declared free of I/O: stays on the loop
        return str(threading.get_ident())

    @strawberry.field
    def leaf(self) -> Leaf:
        return Leaf()

    @strawberry.field
    def boom(self) -> int:
        raise ValueError("no such thing")


small = strawberry.Schema(Slow, extensions=[OffLoop])


def _run(query: str) -> tuple[Any, int]:
    """The result of ``query`` and how many 10 ms ticks the loop made while it ran."""

    async def main() -> tuple[Any, int]:
        ticks = 0
        done = asyncio.Event()

        async def ticker() -> None:
            nonlocal ticks
            while not done.is_set():
                await asyncio.sleep(0.01)
                ticks += 1

        task = asyncio.create_task(ticker())
        result = await small.execute(query)
        done.set()
        await task
        return result, ticks

    return asyncio.run(main())


def test_a_blocking_top_level_resolver_runs_off_the_loop_and_the_loop_keeps_ticking() -> None:
    result, ticks = _run("{ slow }")
    assert result.errors is None and result.data["slow"] != str(threading.get_ident())
    assert ticks >= 15  # a 0.3 s block on the loop would leave one or two


def test_nested_fields_and_async_resolvers_stay_on_the_loop() -> None:
    result, _ = _run("{ waits leaf { thread } }")
    assert result.errors is None
    assert result.data["waits"] == result.data["leaf"]["thread"] == str(threading.get_ident())


def test_a_field_declared_inline_stays_on_the_loop() -> None:
    result, _ = _run("{ quick slow }")
    assert result.errors is None
    assert result.data["quick"] == str(threading.get_ident()) != result.data["slow"]


def test_a_resolver_error_is_still_the_fields_error_and_siblings_answer() -> None:
    result, _ = _run("{ boom waits }")
    assert [e.message for e in result.errors or []] == ["no such thing"]
    assert result.data is None or result.data.get("waits") is not None


def test_the_served_schema_runs_its_top_level_fields_off_the_loop() -> None:
    assert OffLoop in served.extensions


def test_the_read_pool_is_not_the_pool_the_sync_routes_wait_on() -> None:
    async def tokens() -> tuple[float, float]:
        await off_loop(lambda: None)
        return read_limiter().total_tokens, to_thread.current_default_thread_limiter().total_tokens

    reads, routes = asyncio.run(tokens())
    assert reads == READ_THREADS < routes  # 40 by default: /health and the caller guard queue there


def test_an_async_resolver_never_opens_a_context_on_the_loop() -> None:
    # ``read`` / ``stores`` list parquet partitions; an async resolver awaits ``aread`` /
    # ``astores`` (off the loop) instead
    tree = ast.parse(Path(query_module.__file__).read_text())
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef):
            for call in ast.walk(node):
                if (
                    isinstance(call, ast.Call)
                    and isinstance(call.func, ast.Attribute)
                    and call.func.attr in ("read", "stores")
                    and isinstance(call.func.value, ast.Attribute)
                    and call.func.value.attr == "context"
                ):
                    found.append(f"{node.name} calls context.{call.func.attr}()")
    assert found == []


def test_top_level_fields_hand_back_together_so_dataloaders_batch_across_siblings() -> None:
    # (the loader contract itself: tests/apps/api/graphql/test_loaders.py, aliased instruments)
    result, _ = _run("{ a: slow b: waits }")
    assert result.errors is None and result.data is not None
    assert sorted(result.data) == ["a", "b"]
