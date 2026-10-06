"""The prompt (ADR 0041): the catalogue rendered in its order with types, units, descriptions
and category values; the phrasebook after it, each entry with only the fields this catalogue
has; the field guide after that (entries and situations over this catalogue's fields, no
sources); every section stable;
has; the worked examples; stable bytes for the same inputs; the sentence with the current
criteria. Fitness: every field the shipped phrasebook and the examples name is in the site
catalogue."""

from algotrade.config.site.field_guide import (
    FieldGuideEntry,
    FieldGuideSettings,
    GuideUse,
    Situation,
)
from algotrade.config.site.llm import Phrase
from algotrade.config.site.settings import load_field_guide, load_phrasebook
from algotrade.services.configs import field_catalog
from algotrade.services.drafting.prompt import (
    EXAMPLES,
    catalogue_line,
    guide_line,
    phrase_line,
    situation_line,
    system_prompt,
    use_text,
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
    assert "Field guide (" not in first and "Field guide (" not in system_prompt(
        infos, (), FieldGuideSettings()
    )
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
    # And every field guide entry and situation.
    guide = load_field_guide(store)
    text = system_prompt([info(n) for n in sorted(catalogue)], book, guide)
    fields, situations = (
        text.index("Field guide ("),
        text.index("Situations that fool a threshold ("),
    )
    assert text.index("Phrasebook (") < fields < situations
    assert text.count("\n", fields, situations) == len(guide.fields) + 2
    assert text.count("\n", situations) == len(guide.situations) + 1
    assert "Sources:" not in text and "http" not in text[fields:]


def test_user_prompt_carries_the_sentence_and_current_criteria() -> None:
    assert user_prompt("my_screen", "  stocks over  $5 ", None) == (
        "Screener id: my_screen\nCurrent criteria: none\nSentence: stocks over  $5\n"
    )
    current = {"id": "my_screen", "criteria": {"p": {"field": "instrument.x", "op": "gt"}}}
    assert '"p": {"field": "instrument.x", "op": "gt"}' in user_prompt("my_screen", "s", current)


RSI = FieldGuideEntry(
    name="rollup.b@v1.x",
    theme="momentum",
    reads="0 to 100",
    uses=(
        GuideUse("oversold", "lt", 30, "soft", 5.0, "", "with a trend"),
        GuideUse("liquid", "gte", 5e7, "soft", {"relative": 0.2}, "LIQUIDITY_RISK"),
        GuideUse("known", "not_null"),
        GuideUse("high", "eq", "HIGH"),
    ),
    caveats=("pinned by a deal.", "thin names."),
    sources=("Wilder (1978)",),
)
ELSEWHERE = FieldGuideEntry(name="feature.nope", theme="t", reads="r")
DEAL = Situation("pending takeover", "flat tape", ("feature.nope", "rollup.b@v1.x"), "drop it")
NOWHERE = Situation("ipo", "young", ("feature.nope",), "soft")


def test_guide_lines_keep_only_this_catalogues_fields_and_no_sources() -> None:
    names = {"rollup.b@v1.x"}
    assert use_text(RSI.uses[0]) == "oversold: lt 30 soft tolerance 5.0 (with a trend)"
    assert (
        use_text(RSI.uses[1])
        == 'liquid: gte 50000000.0 soft tolerance {"relative": 0.2} on_miss LIQUIDITY_RISK'
    )
    assert use_text(RSI.uses[2]) == "known: not_null hard"
    assert use_text(RSI.uses[3]) == 'high: eq "HIGH" hard'
    assert guide_line(RSI, names) == (
        "rollup.b@v1.x | 0 to 100 | use: oversold: lt 30 soft tolerance 5.0 (with a trend); "
        'liquid: gte 50000000.0 soft tolerance {"relative": 0.2} on_miss LIQUIDITY_RISK; '
        'known: not_null hard; high: eq "HIGH" hard | caveats: pinned by a deal. thin names.'
    )
    assert guide_line(ELSEWHERE, names) is None
    assert (
        situation_line(DEAL, names)
        == "pending takeover | flat tape | affects: rollup.b@v1.x | drop it"
    )
    assert situation_line(NOWHERE, names) is None
    guide = FieldGuideSettings((RSI, ELSEWHERE), (DEAL, NOWHERE))
    text = system_prompt([info("rollup.b@v1.x")], (), guide)
    assert "Phrasebook (" not in text and "Wilder" not in text
    assert (
        text.index("Catalogue (") < text.index("Field guide (") < text.index("Situations that fool")
    )
    assert text.endswith("pending takeover | flat tape | affects: rollup.b@v1.x | drop it\n")
    assert "feature.nope" not in text.split("Field guide (")[1].split("Situations")[0]
    assert text == system_prompt([info("rollup.b@v1.x")], (), guide)
    only_fields = system_prompt([info("rollup.b@v1.x")], (), FieldGuideSettings((RSI,), (NOWHERE,)))
    assert "Field guide (" in only_fields and "Situations that fool" not in only_fields
