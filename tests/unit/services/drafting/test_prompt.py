"""The prompt (ADR 0041): the catalogue rendered in its order with types, units, descriptions
and category values; the phrasebook after it, each entry with only the fields this catalogue
has; the worked examples; stable bytes for the same inputs; the sentence with the current
criteria. Fitness: every field the shipped phrasebook and the examples name is in the site
catalogue."""

from algotrade.config.site.llm import Phrase
from algotrade.config.site.settings import load_phrasebook
from algotrade.services.configs import field_catalog
from algotrade.services.drafting.prompt import (
    EXAMPLES,
    catalogue_line,
    phrase_line,
    system_prompt,
    user_prompt,
)
from algotrade.services.read.instruments.catalogue import FeatureFormat, FeatureInfo
from algotrade.storage.factory import open_config_store
from tests.conftest import REPO_ROOT


def info(name: str, dtype: str = "float", **kw: object) -> FeatureInfo:
    base: dict[str, object] = {
        "kind": "rollup",
        "source": "t",
        "dtype": dtype,
        "format": FeatureFormat.NUMBER,
        "description": "x",
        "null_meaning": "n",
    }
    return FeatureInfo(name=name, **{**base, **kw})  # type: ignore[arg-type]


def test_catalogue_line_has_type_unit_description_and_values() -> None:
    line = catalogue_line(
        info(
            "instrument.status",
            "str",
            unit="category",
            categories=("ACTIVE", "DELISTED"),
            description="Listing   status\nof the instrument",
        )
    )
    assert line == (
        "instrument.status | str | category | Listing status of the instrument | "
        "values: ACTIVE, DELISTED"
    )
    assert catalogue_line(info("rollup.a@v1.b", description="")) == "rollup.a@v1.b | float | - | -"


def test_a_long_description_is_cut() -> None:
    line = catalogue_line(info("f", description="w " * 200))
    assert line.endswith("…") and len(line) < 200


def test_system_prompt_keeps_catalogue_order_and_is_stable() -> None:
    infos = [info("rollup.b@v1.x"), info("instrument.a", "str")]
    first = system_prompt(infos)
    assert first == system_prompt(infos)
    assert first.index("rollup.b@v1.x") < first.index("instrument.a")
    assert "ONE JSON object" in first and "tie_break" in first
    assert "Example 1" in first and "Example 2" in first and "Phrasebook" not in first
    assert first.index("Example 2") < first.index("Catalogue (")


def test_phrasebook_keeps_only_this_catalogues_fields() -> None:
    momentum = Phrase(("momentum", "trending up"), ("rollup.b@v1.x", "feature.nope"), "x gt  0")
    elsewhere = Phrase(("yield",), ("feature.nope",), "")
    names = {"rollup.b@v1.x"}
    assert phrase_line(momentum, names) == "momentum / trending up | rollup.b@v1.x | x gt 0"
    assert phrase_line(elsewhere, names) is None
    text = system_prompt([info("rollup.b@v1.x")], [momentum, elsewhere])
    assert text.index("Catalogue (") < text.index("Phrasebook (")
    assert text.endswith("momentum / trending up | rollup.b@v1.x | x gt 0\n")
    assert "yield" not in text and text == system_prompt(
        [info("rollup.b@v1.x")], [momentum, elsewhere]
    )


def test_shipped_phrasebook_and_examples_name_catalogue_fields() -> None:
    store = open_config_store(REPO_ROOT / "config")
    catalogue = set(field_catalog(store).fields)
    book = load_phrasebook(store).phrases
    unknown = {f for p in book for f in p.fields if f not in catalogue}
    assert not unknown, f"phrasebook names fields the site catalogue lacks: {sorted(unknown)}"
    for sentence, answer in EXAMPLES:
        for c in answer["criteria"]:
            assert c["field"] in catalogue, f"example {sentence!r}: {c['field']}"
        assert answer["tie_break"]["field"] in catalogue
    # Every phrase survives in a prompt over the site catalogue.
    text = system_prompt([info(n) for n in sorted(catalogue)], book)
    assert text.count("\n", text.index("Phrasebook (")) == len(book) + 1


def test_user_prompt_carries_the_sentence_and_current_criteria() -> None:
    assert user_prompt("my_screen", "  stocks over  $5 ", None) == (
        "Screener id: my_screen\nCurrent criteria: none\nSentence: stocks over  $5\n"
    )
    current = {"id": "my_screen", "criteria": {"p": {"field": "instrument.x", "op": "gt"}}}
    assert '"p": {"field": "instrument.x", "op": "gt"}' in user_prompt("my_screen", "s", current)
