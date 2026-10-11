"""Retrieval (plan "Token and latency budget"): the slice of fields a sentence gets in the
drafting prompt. The guard is RECALL over the golden set: a field a case expects that exists in
the catalogue is always in the slice, so a missed field never becomes a false "missing". Also the
token budget (<= 15k estimated tokens, chars / 4), the byte-identical prefix, determinism, own
features, and the phrasebook short-cut."""

import pytest

from algotrade.config.site.field_guide import FieldGuideEntry, FieldGuideSettings
from algotrade.config.site.llm import Phrase
from algotrade.config.site.settings import load_field_guide, load_phrasebook
from algotrade.config.user import UserContext
from algotrade.services.drafting.golden import GoldenCase, load_cases
from algotrade.services.drafting.prompt import prefix_text, sliced_system_prompt
from algotrade.services.drafting.retrieval import (
    CORE_FIELDS,
    MAX_FIELDS,
    content_words,
    name_words,
    phrase_matches,
    resolves_without_model,
    select_slice,
    stem,
    words_of,
)
from algotrade.services.read.context import open_context
from algotrade.services.read.instruments.catalogue import FeatureFormat, FeatureInfo, feature_infos
from algotrade.storage.factory import open_config_store
from tests.conftest import REPO_ROOT
from tests.unit.services.drafting.test_screens import ALICE, DAY, seeded

ROOT = REPO_ROOT / "tests" / "fixtures" / "drafting" / "golden"
CASES = load_cases(ROOT)
BUDGET_TOKENS = 15_000


@pytest.fixture(scope="module")
def site() -> tuple[list[FeatureInfo], tuple[Phrase, ...], FieldGuideSettings]:
    reader, _ = seeded()
    store = open_config_store(REPO_ROOT / "config")
    ctx = open_context(reader, store, UserContext(ALICE), DAY)
    infos = list(feature_infos(ctx.features).values())
    return infos, load_phrasebook(store).phrases, load_field_guide(store)


def ids(case: GoldenCase) -> str:
    return case.id


@pytest.mark.parametrize("case", CASES, ids=ids)
def test_every_expected_field_that_exists_is_in_the_slice(case: GoldenCase, site) -> None:
    infos, book, guide = site
    names = {i.name for i in infos}
    chosen = set(select_slice(case.sentence, infos, book, guide).fields)
    for part in case.parts:
        existing = [f for f in part["fields"] if f in names]
        if existing:
            assert chosen & set(existing), f"{case.id}: {part['span']!r} lost {existing}"


def test_the_golden_set_has_the_new_train_cases() -> None:
    train = {c.id for c in CASES if c.split == "train"}
    assert {"pe-and-revenue-growth", "uptrend-no-earnings", "iv-over-realised"} <= train
    assert {"above-sma50-wide-range"} <= train


@pytest.mark.parametrize("case", CASES, ids=ids)
def test_the_sliced_prompt_is_within_the_token_budget(case: GoldenCase, site) -> None:
    infos, book, guide = site
    prompt = sliced_system_prompt(infos, case.sentence, book, guide)
    assert len(prompt) // 4 <= BUDGET_TOKENS, f"{case.id}: {len(prompt) // 4} tokens"
    assert prompt.startswith(prefix_text(infos))


def test_the_prefix_is_identical_across_sentences_and_the_slice_is_smaller(site) -> None:
    infos, book, guide = site
    prefix = prefix_text(infos)
    prompts = [sliced_system_prompt(infos, c.sentence, book, guide) for c in CASES]
    assert all(p.startswith(prefix) for p in prompts)
    assert len({p[len(prefix) :] for p in prompts}) == len(prompts)  # the slice is per sentence
    for info in infos:
        assert f"{info.name} | " in prefix  # every field is in the index


def test_the_slice_is_deterministic_and_ignores_catalogue_order(site) -> None:
    infos, book, guide = site
    sentence = CASES[0].sentence
    first = select_slice(sentence, infos, book, guide)
    assert first == select_slice(sentence, infos[::-1], book, guide)
    assert sliced_system_prompt(infos, sentence, book, guide) == sliced_system_prompt(
        infos[::-1], sentence, book, guide
    )
    assert list(first.fields) == sorted(first.fields)


def test_the_slice_is_capped_and_always_has_the_core_fields(site) -> None:
    infos, book, guide = site
    names = {i.name for i in infos}
    sentence = "volume price trend momentum volatility earnings options liquidity"
    chosen = select_slice(sentence, infos, book, guide).fields
    core = {f for f in CORE_FIELDS if f in names}
    assert core <= set(chosen)
    phrase_fields = {
        f for p in select_slice(sentence, infos, book, guide).phrases for f in p.fields
    }
    assert len(set(chosen) - core) <= MAX_FIELDS + len(phrase_fields & names)
    assert core == set(select_slice("", infos, book, guide).fields)


def test_a_phrase_the_sentence_says_brings_all_its_fields_and_its_entry() -> None:
    a, b = info("rollup.a@v1.x"), info("feature.b")
    other = info("feature.c")
    say = Phrase(("near the lows",), ("rollup.a@v1.x", "feature.b"), "a lt 1")
    chosen = select_slice("shares near the lows", [a, b, other], [say])
    assert chosen.phrases == (say,) and {"rollup.a@v1.x", "feature.b"} <= set(chosen.fields)
    assert "feature.c" not in chosen.fields
    assert select_slice("nothing relevant", [a, b, other], [say]).phrases == ()


def test_a_cross_reference_in_a_caveat_adds_the_field() -> None:
    a, b = info("feature.alpha"), info("feature.beta")
    guide = FieldGuideSettings(
        (FieldGuideEntry("feature.alpha", "t", "r", caveats=("pair with feature.beta.",)),), ()
    )
    assert "feature.beta" in select_slice("alpha names", [a, b], (), guide).fields
    assert "feature.beta" not in select_slice("alpha names", [a, b], (), None).fields


def test_a_users_own_feature_the_sentence_names_is_in_the_prompt(site) -> None:
    infos, book, guide = site
    mine = info("feature.my_quality_score", scope="user", owner="alice", description="my score")
    sentence = "stocks with my quality score above 3"
    chosen = select_slice(sentence, [*infos, mine], book, guide)
    assert "feature.my_quality_score" in chosen.fields
    prompt = sliced_system_prompt([*infos, mine], sentence, book, guide)
    own = prompt.split("\nYour own features (")[1]
    assert "feature.my_quality_score | float" in own
    assert prompt.startswith(prefix_text(infos))  # the prefix ignores the user's feature


def test_words_stem_join_units_and_drop_noise() -> None:
    assert stem("gainers") == "gainer" and stem("rising") == "rising" and stem("up") == "up"
    assert {"200d", "200"} <= set(words_of("above the 200 day average"))
    assert {"52w", "52"} <= set(words_of("a 52-week high"))
    assert content_words("the stocks with") == set()
    assert name_words("rollup.price_stats@v2.ret_20d") == {"price", "stat", "ret", "20d", "20"}
    assert phrase_matches("breaking out now", Phrase(("breaking out",), ("x",)))
    assert not phrase_matches("outbreaking", Phrase(("breaking out",), ("x",)))


BOOK = [
    Phrase(("price floor",), ("rollup.a@v1.close",), "close gt 5"),
    Phrase(("liquid",), ("rollup.a@v1.adv",), "adv gte 50000000"),
    Phrase(("momentum",), ("rollup.a@v1.ret", "rollup.a@v1.rsi"), "gate: ret gt 0"),
    Phrase(("calm",), ("rollup.a@v1.hv", "rollup.a@v1.atr"), "hv lt 0.2"),
]
CATALOGUE = {"rollup.a@v1.close", "rollup.a@v1.adv", "rollup.a@v1.ret", "rollup.a@v1.rsi"}


def test_a_sentence_every_clause_of_which_the_phrasebook_pins_resolves_without_the_model() -> None:
    got = resolves_without_model("price floor and liquid", BOOK, CATALOGUE)
    assert got == [
        {
            "id": "close",
            "field": "rollup.a@v1.close",
            "op": "gt",
            "value": 5,
            "mode": "hard",
            "why": "price floor",
        },
        {
            "id": "adv",
            "field": "rollup.a@v1.adv",
            "op": "gte",
            "value": 50000000,
            "mode": "hard",
            "why": "liquid",
        },
    ]


def test_one_clause_the_phrasebook_cannot_pin_leaves_it_to_the_model() -> None:
    assert resolves_without_model("liquid, with momentum", BOOK, CATALOGUE) is None  # 2 fields
    assert resolves_without_model("liquid and cheap", BOOK, CATALOGUE) is None  # no phrase
    assert resolves_without_model("calm", BOOK, CATALOGUE) is None  # field not in the catalogue
    assert resolves_without_model("", BOOK, CATALOGUE) is None


def info(name: str, **kw: object) -> FeatureInfo:
    base: dict[str, object] = {
        "kind": "rollup",
        "source": "t",
        "dtype": "float",
        "format": FeatureFormat.NUMBER,
        "description": "x",
        "null_meaning": "n",
    }
    return FeatureInfo(name=name, **{**base, **kw})  # type: ignore[arg-type]
