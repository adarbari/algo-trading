"""Retrieval (plan "Token and latency budget"): the slice of fields a sentence gets in the
drafting prompt. The guard is RECALL over the golden set: a field a case expects that exists in
the catalogue is always in the slice, so a missed field never becomes a false "missing". Also the
token budget (<= 15k estimated tokens, chars / 4), the byte-identical prefix, determinism, own
features, joined tokens and numbers."""

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


def test_a_users_own_feature_is_always_in_the_prompt_in_full(site) -> None:
    infos, book, guide = site
    mine = info("feature.my_quality_score", scope="user", owner="alice", description="my score")
    sentence = "stocks with my quality score above 3"
    assert (
        "feature.my_quality_score" not in select_slice(sentence, [*infos, mine], book, guide).fields
    )
    prompt = sliced_system_prompt([*infos, mine], sentence, book, guide)
    own = prompt.split("\nYour own features (")[1]
    assert "feature.my_quality_score | float" in own
    assert prompt.startswith(prefix_text(infos))  # the prefix ignores the user's feature


def test_words_stem_join_units_and_drop_noise() -> None:
    assert stem("gainers") == "gainer" and stem("rising") == "rising" and stem("up") == "up"
    assert {"200d", "200"} <= set(words_of("above the 200 day average"))
    assert {"52w", "52"} <= set(words_of("a 52-week high"))
    assert content_words("the stocks with") == set()
    assert words_of("SMA50 and RSI14") == ["sma", "and", "rsi"]  # digits only beside a field word
    vocab = {"sma", "rsi", "iv"}
    assert words_of("SMA50, RSI14 under 30", vocab) == ["sma", "50", "rsi", "14", "under"]
    assert "30" in words_of("IV 30", vocab) and "30" not in words_of("under 30", vocab)
    assert name_words("rollup.momentum@v1.rsi_14") == {"momentum", "rsi", "14"}
    assert name_words("rollup.iv30@v1.iv30") >= {"iv", "30"}
    assert name_words("rollup.price_stats@v2.ret_20d") == {"price", "stat", "ret", "20d", "20"}
    assert phrase_matches("breaking out now", Phrase(("breaking out",), ("x",)))
    assert not phrase_matches("outbreaking", Phrase(("breaking out",), ("x",)))


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


def test_joined_and_spaced_tokens_find_the_same_fields() -> None:
    sma, rsi, iv, other = (
        info("feature.pct_vs_sma_50"),
        info("rollup.momentum@v1.rsi_14"),
        info("rollup.iv30@v1.iv30"),
        info("feature.pct_vs_sma_200"),
    )
    infos = [sma, rsi, iv, other]
    for text in ("above SMA50, RSI14 under 30", "above sma 50 and rsi 14 under 30"):
        chosen = select_slice(text, infos).fields
        assert {sma.name, rsi.name} <= set(chosen)
    first = select_slice("IV 30 above 40", infos).fields
    assert iv.name in first


def test_the_cap_leaves_phrasebook_fields_whole_and_ranking_skips_own_features() -> None:
    many = [info(f"feature.vol_{n:02d}") for n in range(40)]
    say = Phrase(("calm",), tuple(f"feature.vol_{n:02d}" for n in range(30)), "x")
    chosen = select_slice("calm vol", many, [say]).fields
    assert {f"feature.vol_{n:02d}" for n in range(30)} <= set(chosen)  # all 30, over the cap
    assert len(chosen) <= 30 + MAX_FIELDS
    mine = info("feature.vol_mine", scope="user", owner="u")
    assert "feature.vol_mine" not in select_slice("vol", [*many, mine]).fields


def test_a_brief_field_has_no_caveats_and_a_full_one_keeps_its_checks(site) -> None:
    infos, book, guide = site
    case = CASES[0]
    chosen = select_slice(case.sentence, infos, book, guide)
    prompt = sliced_system_prompt(infos, case.sentence, book, guide)
    guide_text = prompt.split("Field guide (")[1].split("\nSituations")[0]
    lines = {line.split(" | ")[0]: line for line in guide_text.splitlines()[1:]}
    briefs = [n for n in chosen.brief if n in lines]
    assert briefs and all("caveat:" not in lines[n] for n in briefs)
    full = [n for n in lines if n not in chosen.brief and "caveat:" in lines[n]]
    assert full  # the sentence's own fields keep theirs


def test_a_number_after_a_comparison_word_names_no_field() -> None:
    vocab = {"above", "sma", "iv", "high"}
    assert words_of("above 20", vocab) == ["above"]
    assert words_of("over 20 and high 52", {"over", "high"}) == ["over", "and", "high", "52"]
    sma20, other = info("feature.pct_vs_sma_20"), info("rollup.a@v1.ret_20d")
    # "above 20" must not pull in the fields named for 20; "sma 20" must
    assert not select_slice("price above 20", [sma20, other]).fields
    assert sma20.name in select_slice("sma 20 rising", [sma20, other]).fields
