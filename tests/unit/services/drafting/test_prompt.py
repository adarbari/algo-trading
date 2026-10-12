"""The prompt (ADR 0041): the catalogue rendered in its order with types, units, descriptions
and category values; the phrasebook after it, each entry with only the fields this catalogue
has; the field guide after that (entries and situations over this catalogue's fields, no
sources); every section stable;
has; the worked examples; stable bytes for the same inputs; the sentence with the current
criteria. Fitness: every field the shipped phrasebook and the examples name is in the site
catalogue."""

from algotrade.config.site.drafting.backlog import PROMPT_LIMIT
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
    PROMPT_VERSION,
    TASK,
    catalogue_line,
    index_line,
    phrase_line,
    prefix_text,
    relevant_keys,
    situation_line,
    slice_guide_line,
    sliced_system_prompt,
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


def test_sliced_prompt_sorts_the_index_and_is_stable() -> None:
    infos = [info("rollup.b@v1.x"), info("instrument.a", "str")]
    first = sliced_system_prompt(infos, "b things")
    assert (
        first
        == sliced_system_prompt(infos, "b things")
        == sliced_system_prompt(infos[::-1], "b things")
    )
    assert first.index("instrument.a") < first.index("rollup.b@v1.x")
    assert "ONE JSON object" in first and "tie_break" in first
    assert "Example 1" in first and "Example 2" in first and "Phrasebook" not in first
    assert "Field guide (" not in first and "Field guide (" not in sliced_system_prompt(
        infos, "b things", (), FieldGuideSettings()
    )
    assert first.index("Example 2") < first.index("Field index (")


def test_phrasebook_keeps_only_this_catalogues_fields() -> None:
    momentum = Phrase(("momentum", "trending up"), ("rollup.b@v1.x", "feature.nope"), "x gt  0")
    elsewhere = Phrase(("yield",), ("feature.nope",), "")
    names = {"rollup.b@v1.x"}
    assert phrase_line(momentum, names) == "momentum / trending up | rollup.b@v1.x | x gt 0"
    assert phrase_line(elsewhere, names) is None
    text = sliced_system_prompt([info("rollup.b@v1.x")], "momentum", [momentum, elsewhere])
    assert text.index("Detail (") < text.index("Phrasebook (")
    assert text.endswith("momentum / trending up | rollup.b@v1.x | x gt 0\n")
    assert "yield" not in text


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
    # Every phrase, guide entry and situation renders over the site catalogue.
    assert all(phrase_line(p, catalogue) for p in book)
    guide = load_field_guide(store)
    assert all(slice_guide_line(e, catalogue) for e in guide.fields)
    assert all(situation_line(s, catalogue) for s in guide.situations)
    assert not any("http" in (slice_guide_line(e, catalogue) or "") for e in guide.fields)


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
    assert slice_guide_line(ELSEWHERE, names) is None
    assert (
        situation_line(DEAL, names)
        == "pending takeover | flat tape | affects: rollup.b@v1.x | drop it"
    )
    assert situation_line(NOWHERE, names) is None
    guide = FieldGuideSettings((RSI, ELSEWHERE), (DEAL, NOWHERE))
    pull = [Phrase(("b",), ("rollup.b@v1.x",))]
    text = sliced_system_prompt([info("rollup.b@v1.x")], "b", pull, guide)
    assert "Wilder" not in text
    assert text.index("Detail (") < text.index("Field guide (") < text.index("Situations that fool")
    assert text.endswith("pending takeover | flat tape | affects: rollup.b@v1.x | drop it\n")
    assert "feature.nope" not in text.split("Field guide (")[1].split("Situations")[0]
    only_fields = sliced_system_prompt(
        [info("rollup.b@v1.x")], "b", pull, FieldGuideSettings((RSI,), (NOWHERE,))
    )
    assert "Field guide (" in only_fields and "Situations that fool" not in only_fields


def test_users_share_the_site_prefix_and_own_features_come_last() -> None:
    site = [info("rollup.b@v1.x"), info("instrument.a", "str")]
    mine = info("feature.mine", scope="user", owner="u1")
    other = info("feature.zeta", scope="user", owner="u2")
    momentum = Phrase(("mine",), ("feature.mine", "rollup.b@v1.x"), "x gt 0")
    first = sliced_system_prompt([site[0], mine, site[1]], "mine", [momentum])
    second = sliced_system_prompt([other, *site], "mine", [momentum])
    marker = "\nYour own features ("
    assert "feature.zeta" not in second.split(marker)[0]
    assert first.split("Detail (")[0] == second.split("Detail (")[0] == prefix_text(site) + "\n"
    plain = sliced_system_prompt(site, "mine")
    assert marker not in plain
    assert first.endswith(catalogue_line(mine) + "\n")
    assert first.count("\n" + catalogue_line(mine) + "\n") == 1  # once, in full


def test_the_sliced_prompt_is_an_index_then_only_the_slice() -> None:
    assert PROMPT_VERSION == "4"
    names = {"rollup.b@v1.x"}
    assert (
        index_line(info("instrument.a", "str", unit="category")) == "instrument.a | str | category"
    )
    assert slice_guide_line(RSI, names) == (
        "rollup.b@v1.x | use: oversold: lt 30 soft tolerance 5.0 (with a trend); "
        'liquid: gte 50000000.0 soft tolerance {"relative": 0.2} on_miss LIQUIDITY_RISK; '
        'known: not_null hard; high: eq "HIGH" hard | caveat: pinned by a deal.'
    )  # no "reads"
    long = FieldGuideEntry(
        name="rollup.b@v1.x",
        theme="t",
        reads="r",
        caveats=(
            "A big move lifts it. Check feature.other first. Do not gate hard on a large value.",
            "Sector talk. Null after a gap in the last 60 sessions.",
            "Filler words only.",
            "Pair with feature.nope or rollup.b@v1.x itself.",
        ),
    )
    # lead sentence, sentences naming a field, the null rule or how to use it; no filler
    assert slice_guide_line(long, {"rollup.b@v1.x", "feature.other"}) == (
        "rollup.b@v1.x | use: - | caveat: A big move lifts it. Check feature.other first. "
        "Do not gate hard on a large value. Null after a gap in the last 60 sessions. "
        "Pair with feature.nope or rollup.b@v1.x itself."
    )
    assert slice_guide_line(ELSEWHERE, names) is None
    infos = [info("rollup.b@v1.x"), info("feature.other"), info("feature.c", description="rsi")]
    guide = FieldGuideSettings((RSI,), (DEAL, NOWHERE))
    text = sliced_system_prompt(infos, "oversold b names", (), guide)
    assert text.index("Field index") < text.index("Detail (") < text.index("Field guide (")
    index = text.split("Detail (")[0]
    assert all(f"{i.name} | float | -" in index for i in infos)  # every field is indexed
    assert "feature.other | float | - | x" not in text  # but only the slice has detail
    assert "pending takeover" in text and "Phrasebook (" not in text


def test_a_slice_keeps_every_caveat_sentence_that_says_how_to_use_the_field() -> None:
    entry = FieldGuideEntry(
        name="rollup.b@v1.x",
        theme="t",
        reads="r",
        caveats=(
            "Lead sentence. Background talk. A hard 'gt 10' rejects every ETF; use soft.",
            "Never a one-sided upper bound. Use adv_usd_20d for a gate.",
            "Check market.market_trend@v2 first. More background.",
            "Pure filler.",
        ),
    )
    line = slice_guide_line(entry, {"rollup.b@v1.x"})
    assert line is not None
    caveat = line.split("caveat: ")[1]
    assert caveat == (
        "Lead sentence. A hard 'gt 10' rejects every ETF; use soft. "
        "Never a one-sided upper bound. Use adv_usd_20d for a gate. "
        "Check market.market_trend@v2 first."
    )


def test_the_task_states_the_contract_and_what_a_formula_can_express() -> None:
    for word in ('"formulas"', '"missing"', '"unresolved"', "draft_<slug>", "ROLLUP_FROM_STORED"):
        assert word in TASK
    for function in ("if(", "abs", "min", "max", "log", "sqrt", "ncdf", "clip", "coalesce",
                     "is_null", "one_of", "exists"):  # fmt: skip
        assert function in TASK
    assert "No lag, window" in TASK and "over time" in TASK


def test_the_open_backlog_keys_are_in_the_prefix_every_sentence_shares() -> None:
    site = [info("rollup.b@v1.x")]
    keys = (("a_key", "what a is"), ("b_key", "what\nb   is"))
    first = sliced_system_prompt(site, "b", open_keys=keys)
    second = sliced_system_prompt(site, "something else", open_keys=keys)
    prefix = prefix_text(site)
    assert first.startswith(prefix) and second.startswith(prefix)  # the prefix has no keys
    assert "Open requests (" not in prefix
    assert "a_key | what a is\nb_key | what b is\n" in first  # equal relevance: by key
    assert "Open requests (" not in sliced_system_prompt(site, "b")  # no keys, no section


def test_open_keys_shown_are_the_most_relevant_then_by_key_and_capped() -> None:
    keys = [(f"k{n:02}", "plain") for n in range(30)] + [
        ("zz_support_history", "time near support")
    ]
    got = relevant_keys("held near support for years", keys)
    assert got[0][0] == "zz_support_history"  # the sentence's words first
    assert [k for k, _ in got[1:]] == [f"k{n:02}" for n in range(PROMPT_LIMIT - 1)]
    assert len(got) == PROMPT_LIMIT
    assert relevant_keys("x", keys, limit=2) == [("k00", "plain"), ("k01", "plain")]
    assert relevant_keys("x", reversed(keys)) == relevant_keys("x", keys)  # deterministic
