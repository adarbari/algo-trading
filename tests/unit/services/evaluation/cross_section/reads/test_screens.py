"""``ScreenCache`` and its use by ``SessionReads`` (ADR 0059 amendment, ADR 0063): a screen
computed for one edge is read back by the next edge of the run with the reads it logged, and a
run with the cache gives the legs and rows of one without."""

from datetime import date
from pathlib import Path
from typing import Any

from algotrade.config.user import UserContext
from algotrade.data import CapturedReads
from algotrade.services.evaluation.cross_section import picks
from algotrade.services.evaluation.cross_section.harness import (
    _variants,
    evaluate_edge,
    screen_uses,
)
from algotrade.services.evaluation.cross_section.measuring import Variant as MeasuringVariant
from algotrade.services.evaluation.cross_section.reads.screens import (
    CachedScreen,
    ScreenCache,
    shared_screens,
)
from algotrade.services.evaluation.cross_section.reads.session import SessionReads
from tests.unit.services.evaluation.cross_section.conftest import DAYS, World, edge
from tests.unit.services.evaluation.cross_section.legs.test_reuse import SPLIT, T1, same

OWNER = "site"


def _first_variant(world: World) -> MeasuringVariant:
    return _variants(world.configs, UserContext(OWNER), edge())[0]


def test_shared_screens_keeps_the_pairs_more_than_one_use_names() -> None:
    uses = [("site", "a"), ("site", "b"), ("site", "a"), ("u1", "a")]
    assert shared_screens(uses) == {("site", "a")}


def test_a_cache_returns_what_was_put_for_a_wanted_pair_only(world: World, tmp_path: Path) -> None:
    variant = _first_variant(world)
    run = picks.screen_variant(world.reader, variant.config, DAYS[0])
    got = CachedScreen(run, CapturedReads(7, ()))
    cache = ScreenCache(tmp_path, {(OWNER, variant.config.hash)})
    assert cache.get(OWNER, variant.config.hash, DAYS[0]) is None
    cache.put(OWNER, variant.config.hash, DAYS[0], got)
    assert cache.get(OWNER, variant.config.hash, DAYS[0]) == got
    assert cache.get("u1", variant.config.hash, DAYS[0]) is None  # another owner's screen
    other = ScreenCache(tmp_path, set())
    other.put(OWNER, variant.config.hash, DAYS[1], got)
    assert not list(tmp_path.rglob(f"{DAYS[1].isoformat()}*"))  # not shared: never written


def test_the_second_session_reads_back_the_screen_and_its_reads(
    world: World, tmp_path: Path, monkeypatch: Any
) -> None:
    variant = _first_variant(world)
    cache = ScreenCache(tmp_path, {(OWNER, variant.config.hash)})
    first = SessionReads(world.reader, "label", cache, OWNER)
    with first.attribute(DAYS[0]):
        ran = first.run(variant, DAYS[0])
    calls: list[date] = []
    real = picks.screen_variant
    monkeypatch.setattr(
        "algotrade.services.evaluation.cross_section.reads.session.screen_variant",
        lambda *a, **k: calls.append(a[2]) or real(*a, **k),
    )
    second = SessionReads(world.reader, "label", cache, OWNER)
    with second.attribute(DAYS[0]):
        hit = second.run(variant, DAYS[0])
    assert calls == [] and hit == ran
    assert second.day_reads(DAYS[0]).reads == first.day_reads(DAYS[0]).reads
    assert second.day_reads(DAYS[0]).inputs_seq == first.day_reads(DAYS[0]).inputs_seq
    assert second.snapshots() == first.snapshots()
    assert second.day_reads(DAYS[0]).screened == first.day_reads(DAYS[0]).screened


def test_a_run_with_the_cache_gives_the_rows_and_legs_of_one_without(
    world: World, tmp_path: Path
) -> None:
    """Two evaluations of the same edge sharing a cache (the second one reads every screen back)
    equal the evaluation with none, rows, series and stored legs alike."""
    changes = {**SPLIT}
    plain = evaluate_edge(
        world.reader, world.results, world.configs, UserContext(OWNER), edge(**changes),
        DAYS[0], DAYS[-1], T1, full=True,
    )  # fmt: skip
    uses = screen_uses(world.configs, [edge(**changes), edge(**changes)])
    cache = ScreenCache(tmp_path, shared_screens(uses))
    runs = [
        evaluate_edge(
            world.reader,
            world.results,
            world.configs,
            UserContext(OWNER),
            edge(**changes),
            DAYS[0],
            DAYS[-1],
            T1,
            full=True,
            screens=cache,
        )
        for _ in range(2)
    ]
    assert list(tmp_path.rglob("*.pkl"))  # the first computed and stored its screens
    for ev in runs:
        same(plain, ev)
        assert _legs(ev) == _legs(plain)


def _legs(ev: Any) -> list[str]:
    """The stored leg rows of a run without what says which run wrote them, in a fixed order."""
    drop = {"run_id", "ts", "knowledge_ts", "outcomes_as_of", "inputs_seq", "outcome_seq"}
    return sorted(
        repr(sorted((k, repr(v)) for k, v in r.items() if k not in drop)) for r in ev.leg_rows
    )
