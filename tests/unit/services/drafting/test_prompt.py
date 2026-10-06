"""The prompt (ADR 0041): the catalogue rendered in its order with types, units, descriptions
and category values; stable bytes for the same catalogue; the sentence with the current
criteria; nothing but the sentence and the catalogue."""

from algotrade.services.drafting.prompt import catalogue_line, system_prompt, user_prompt
from algotrade.services.read.instruments.catalogue import FeatureFormat, FeatureInfo


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


def test_user_prompt_carries_the_sentence_and_current_criteria() -> None:
    assert user_prompt("my_screen", "  stocks over  $5 ", None) == (
        "Screener id: my_screen\nCurrent criteria: none\nSentence: stocks over  $5\n"
    )
    current = {"id": "my_screen", "criteria": {"p": {"field": "instrument.x", "op": "gt"}}}
    assert '"p": {"field": "instrument.x", "op": "gt"}' in user_prompt("my_screen", "s", current)
