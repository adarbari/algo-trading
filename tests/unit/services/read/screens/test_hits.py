import pytest

from algotrade.config.user import UserContext
from algotrade.data import StoreReader
from algotrade.services.read.context import ReadContext, open_context, weigh
from algotrade.services.read.screens import results
from algotrade.services.read.screens.hits import ScreenerHit, load_screener_hits
from algotrade.services.read.screens.results import load_results, load_run_changes
from algotrade.services.read.screens.runs import is_picked, load_latest_runs, run_rows
from algotrade.services.read.screens.screeners import load_screeners
from tests.unit.services.read.screens.conftest import D0, context


def _hits(found: dict[str, tuple], iid: str) -> list[tuple[str, str]]:  # type: ignore[type-arg]
    return [(h.screener.id, h.result.decision) for h in found[iid]]


def test_the_screeners_that_picked_each_instrument_in_the_session(ctx: ReadContext) -> None:
    found = load_screener_hits(ctx, ["EQ:AAA", "EQ:BBB", "EQ:CCC", "EQ:DDD", "EQ:AAA"])
    assert list(found) == ["EQ:AAA", "EQ:BBB", "EQ:CCC", "EQ:DDD"]
    assert _hits(found, "EQ:AAA") == [("alpha", "QUALIFIED")]  # beta SKIPPED it: no hit
    assert _hits(found, "EQ:BBB") == [("alpha", "WATCH"), ("beta", "QUALIFIED")]
    assert _hits(found, "EQ:CCC") == []  # alpha rejected it; gamma ran only on D0
    assert _hits(found, "EQ:DDD") == [("beta", "QUALIFIED")]
    hit = found["EQ:BBB"][1]
    assert (hit.screener.owner, hit.result.run_id, hit.result.score) == ("me", "rb", 90.0)
    assert found["EQ:AAA"][0].result.change == "new"  # alpha rejected it on D0


def test_an_earlier_session_has_its_own_hits(reader: StoreReader) -> None:
    base = context(reader)
    earlier = open_context(reader, base.configs, UserContext("me"), D0)
    found = load_screener_hits(earlier, ["EQ:CCC", "EQ:AAA"])
    assert _hits(found, "EQ:CCC") == [("alpha", "QUALIFIED"), ("gamma", "QUALIFIED")]
    assert _hits(found, "EQ:AAA") == []
    assert load_screener_hits(earlier, []) == {}


def test_an_instrument_asked_again_reads_nothing_and_a_new_one_reads_only_its_own_values(
    ctx: ReadContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every ticker opened in Explore used to be served from an index of every pick's stored
    values (331 MB on the real store): an instrument's results are read for it alone, once."""
    asked: list[list[str]] = []
    real = results._read_values

    def counting(ctx_: ReadContext, runs: object, ids: list[str] | None, wanted: object) -> object:
        asked.append(sorted(ids or []))
        return real(ctx_, runs, ids, wanted)  # type: ignore[arg-type]

    monkeypatch.setattr(results, "_read_values", counting)
    load_screener_hits(ctx, ["EQ:AAA"])
    assert asked == [["EQ:AAA"]]
    load_screener_hits(ctx, ["EQ:AAA"])  # kept
    assert asked == [["EQ:AAA"]]
    load_screener_hits(ctx, ["EQ:DDD", "EQ:CCC"])  # CCC was picked by nobody: not read
    assert asked == [["EQ:AAA"], ["EQ:DDD"]]


# ---- the whole-session index this replaced, kept as the oracle ----------------------------------


def _old_session_hits(ctx: ReadContext) -> dict[str, tuple[ScreenerHit, ...]]:
    """Every pick of the user's screeners with its full result, built at once (what
    ``_session_hits`` / ``_build`` did before the index held only who picked what)."""
    screeners = load_screeners(ctx)
    latest = load_latest_runs(ctx, [(s.owner, s.id) for s in screeners])
    runs = [(s, r) for s in screeners if (r := latest[(s.owner, s.id)].run) is not None]
    changes = {run.run_id: load_run_changes(ctx, run) for _, run in runs}
    picked = {
        run.run_id: [
            str(i)
            for i, d in zip(run_rows(ctx, run)["instrument_id"], run_rows(ctx, run)["decision"],
                            strict=True)
            if is_picked(str(d))
        ]
        for _, run in runs
    }  # fmt: skip
    found = load_results(ctx, picked, [run for _, run in runs], changes)
    out: dict[str, list[ScreenerHit]] = {}
    for screener, run in runs:
        for iid in picked[run.run_id]:
            result = found.get((run.run_id, iid))
            if result is not None and is_picked(result.decision):
                out.setdefault(iid, []).append(ScreenerHit(screener, result))
    return {i: tuple(hits) for i, hits in out.items()}


@pytest.mark.parametrize("viewer", ["me", "trader"])  # a personal-data licence, and none
def test_the_hits_of_every_instrument_are_what_the_whole_session_index_gave(
    reader: StoreReader, viewer: str
) -> None:
    ids = ["EQ:AAA", "EQ:BBB", "EQ:CCC", "EQ:DDD", "EQ:ZZZ"]
    oracle = _old_session_hits(context(reader, user=viewer))
    one_by_one = context(reader, user=viewer)
    together = context(reader, user=viewer)
    found = load_screener_hits(together, ids)
    for iid in ids:
        want = oracle.get(iid, ())
        assert found[iid] == want
        assert load_screener_hits(one_by_one, [iid])[iid] == want
    assert any(oracle.values())  # the store has hits to compare


def test_the_index_weighs_who_picked_what_not_their_results(reader: StoreReader) -> None:
    ctx = context(reader)
    load_screener_hits(ctx, [])
    index = [w for k, w in ctx.cache._weights.items() if k[-1] == "index"]
    assert len(index) == 1 and 0 < index[0] < 5_000
    assert weigh(_old_session_hits(ctx)) > 10 * index[0]  # the old entry held every result
