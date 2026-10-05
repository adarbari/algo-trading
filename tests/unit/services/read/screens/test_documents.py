"""A user's rule screens as the Builder reads them: the listing (finalised and draft-only),
one screen's detail (draft and whether it would finalise, versions, preset pin, working copy)
and its versions; the site user owns none, and an unknown screen is ``None``."""

import tomllib
from datetime import date
from typing import Any

import pytest

from algotrade.config.user import SITE_USER, UserContext
from algotrade.core.model.errors import ConfigurationError
from algotrade.services.read.context import ReadContext, ResultCache
from algotrade.services.read.screens import documents
from algotrade.services.read.session import Session
from algotrade.storage.configs.writer import MemoryConfigWriter

SELECTION = """name = "all_active"
[where]
all = [{field = "instrument.status", op = "eq", value = "ACTIVE"}]
"""
PRESET = """id = "vrp"
kind = "screener"
impl = "rules"
version = 3
selection = "all_active"

[criteria.price]
field = "rollup.price_stats@v2.close"
op = "gt"
value = 5
"""
OWN: dict[str, Any] = {
    "kind": "screener",
    "impl": "rules",
    "selection": "all_active",
    "criteria": {"price": {"field": "rollup.price_stats@v2.close", "op": "gt", "value": 10}},
}
ALICE = UserContext("alice")


@pytest.fixture
def writer() -> MemoryConfigWriter:
    return MemoryConfigWriter(
        {
            ("site", "selections", "all_active"): tomllib.loads(SELECTION),
            ("site", "screeners", "vrp@3"): tomllib.loads(PRESET),
        }
    )


def _ctx(writer: MemoryConfigWriter, user: UserContext) -> ReadContext:
    day = date(2026, 10, 1)
    session = Session(day, None, True, day, day, False, (), ())
    return ReadContext(None, writer, user, session, None, ResultCache())  # type: ignore[arg-type]


def test_the_listing_has_finalised_and_draft_only_screens(writer: MemoryConfigWriter) -> None:
    assert documents.load_screen_listings(_ctx(writer, ALICE)) == ()
    writer.save_draft("alice", "mine", {"id": "mine", **OWN})
    writer.add_version("alice", "mine", 1, {"id": "mine", **OWN, "version": 1})
    writer.save_draft("alice", "vrp", {"id": "vrp", "extends": "vrp@3"})  # the preset's id
    listed = {s.screener_id: s for s in documents.load_screen_listings(_ctx(writer, ALICE))}
    assert list(listed) == ["mine", "vrp"]
    mine, vrp = listed["mine"], listed["vrp"]
    assert (mine.status, mine.latest, mine.has_draft, mine.preset_id) == ("FINAL", 1, True, None)
    assert (vrp.status, vrp.latest, vrp.has_draft, vrp.preset_id) == ("DRAFT", None, True, "vrp")
    assert documents.screen_listings(writer, UserContext("bob")) == ()
    assert documents.screen_listings(writer, UserContext(SITE_USER)) == ()


def test_an_uncopied_preset_names_itself_and_its_version(writer: MemoryConfigWriter) -> None:
    detail = documents.load_screen_detail(_ctx(writer, ALICE), "vrp")
    assert detail is not None and detail.draft is None and detail.versions == ()
    assert detail.preset == documents.PresetPin("vrp", None, 3, False)
    assert detail.layers[0] == "site/screeners/vrp" and detail.working is not None


def test_a_draft_that_would_not_finalise_says_why(writer: MemoryConfigWriter) -> None:
    writer.add_version("alice", "mine", 1, {"id": "mine", **OWN, "version": 1})
    writer.save_draft("alice", "mine", {"id": "mine", **OWN, "selection": "nope"})
    detail = documents.load_screen_detail(_ctx(writer, ALICE), "mine")
    assert detail is not None and detail.draft_error and "nope" in detail.draft_error
    assert (detail.versions, detail.latest, detail.error) == ((1,), 1, None)
    assert detail.working is not None  # the latest version's rules: the draft does not resolve
    assert detail.working["criteria"]["price"]["value"] == 10
    versions = documents.load_screen_versions(_ctx(writer, ALICE), "mine")
    assert [(v.version, v.document["version"]) for v in versions] == [(1, 1)]


def test_a_stale_pin_offers_a_rebase(writer: MemoryConfigWriter) -> None:
    writer.save_draft("alice", "my_vrp", {"id": "my_vrp", "extends": "vrp@3"})
    writer._docs[("site", "screeners", "vrp@4")] = tomllib.loads(PRESET) | {"version": 4}
    detail = documents.screen_detail(writer, ALICE, "my_vrp")
    assert detail is not None and detail.preset == documents.PresetPin("vrp", 3, 4, True)


def test_no_such_screen_is_none(writer: MemoryConfigWriter) -> None:
    assert documents.load_screen_detail(_ctx(writer, ALICE), "nothing") is None
    assert documents.screen_detail(writer, UserContext(SITE_USER), "vrp") is None
    assert documents.screen_versions(writer, UserContext(SITE_USER), "vrp") == ()
    with pytest.raises(ConfigurationError):
        documents.screen_detail(writer, ALICE, "Bad..id")
