"""``services.events.scope``: the tier A / B names, the site list and the funds' references, each
with its reasons; symbols resolve through the reference snapshot and the ones it does not know
are reported."""

from datetime import date

from algotrade.data import StoreReader
from algotrade.services.events.scope import (
    FUND_REFERENCE,
    LIQUIDITY,
    ScopedInstruments,
    scoped_instruments,
)
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import MemoryConfigStore
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.stored_frames import stamped, write_reference

D1, D2, D3 = date(2026, 10, 1), date(2026, 10, 2), date(2026, 10, 5)
IDS = {s: f"EQ:{s}" for s in ("AAA", "BBB", "CCC", "TSLA", "TSLL", "ZZZ")}
LIST = {("site", "events", "scope"): {"name": [
    {"symbol": s, "added_on": date(2026, 10, 6)} for s in ("TSLL", "AAA", "NOPE")
]}}  # fmt: skip


def world(
    tiers: dict[date, dict[str, bool]] | None = None,
    links: dict[date, dict[str, str | None]] | None = None,
    reference_day: date = D1,
) -> tuple[StoreReader, MemoryConfigStore]:
    writer = StoreWriter(MemoryBackend())
    write_reference(writer, reference_day, IDS)
    for day, ok in (tiers or {}).items():
        rows = [{"instrument_id": f"EQ:{s}", "short_put_ok": v} for s, v in ok.items()]
        writer.write_table(LIQUIDITY, day, "t", stamped(rows, day, "t"))
    for day, found in (links or {}).items():
        rows = [
            {"instrument_id": f"EQ:{f}", "reference_instrument_id": s and f"EQ:{s}"}
            for f, s in found.items()
        ]
        writer.write_table(FUND_REFERENCE, day, "f", stamped(rows, day, "f"))
    return StoreReader(writer._backend), MemoryConfigStore(LIST)


def reasons(found: ScopedInstruments) -> dict[str, tuple[str, ...]]:
    return {n.symbol: n.reasons for n in found.names}


def test_list_tier_and_reference_each_carry_their_reason() -> None:
    reader, configs = world(
        tiers={D2: {"BBB": True, "CCC": False, "AAA": True}},
        links={D2: {"TSLL": "TSLA", "AAA": None}},
    )
    found = scoped_instruments(reader, configs, D3)
    assert reasons(found) == {
        "TSLL": ("list",),
        "AAA": ("tier", "list"),  # in the list and a short-put name: once, both reasons
        "BBB": ("tier",),
        "TSLA": ("reference",),  # the stock TSLL tracks
    }
    assert found.instrument_ids == ("EQ:TSLL", "EQ:AAA", "EQ:BBB", "EQ:TSLA")
    assert found.reasons("EQ:BBB") == ("tier",) and found.reasons("EQ:CCC") == ()
    assert (found.session, found.reference_snapshot) == (D3, D1)
    assert (found.tier_session, found.link_session) == (D2, D2)


def test_symbols_the_reference_does_not_know_are_reported_never_built() -> None:
    reader, configs = world()
    found = scoped_instruments(reader, configs, D3, requested=["zzz", "ghost", "AAA"])
    assert found.unresolved == ("NOPE", "GHOST")  # the list's, then the requested
    assert reasons(found) == {"TSLL": ("list",), "AAA": ("list",), "ZZZ": ("requested",)}
    assert not any("NOPE" in i or "GHOST" in i for i in found.instrument_ids)


def test_a_session_sees_only_the_tiers_and_links_stored_by_then() -> None:
    reader, configs = world(tiers={D3: {"BBB": True}}, links={D3: {"TSLL": "TSLA"}})
    early = scoped_instruments(reader, configs, D2)  # both stored after this session
    assert reasons(early) == {"TSLL": ("list",), "AAA": ("list",)}
    assert (early.tier_session, early.link_session) == (None, None)
    late = scoped_instruments(reader, configs, date(2026, 10, 9))  # the newest on or before
    assert (late.tier_session, late.link_session) == (D3, D3)
    assert reasons(late)["BBB"] == ("tier",) and reasons(late)["TSLA"] == ("reference",)


def test_no_list_and_no_stored_tiers_is_an_empty_scope() -> None:
    reader, _ = world()
    found = scoped_instruments(reader, None, D3)
    assert found.names == () and found.unresolved == ()
    assert found.reference_snapshot == D1


def test_an_empty_store_resolves_nothing() -> None:
    reader = StoreReader(MemoryBackend())
    found = scoped_instruments(reader, MemoryConfigStore(LIST), D3)
    assert found.names == () and found.reference_snapshot is None
    assert found.unresolved == ("TSLL", "AAA", "NOPE")
