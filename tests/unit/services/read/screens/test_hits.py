from algotrade.config.user import UserContext
from algotrade.data import StoreReader
from algotrade.services.read.context import ReadContext, open_context
from algotrade.services.read.screens.hits import load_screener_hits
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
