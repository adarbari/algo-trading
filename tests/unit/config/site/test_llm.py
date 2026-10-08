"""``llm.toml`` (ADR 0041): defaults (off, a local server), typed keys, https for anything that
is not this machine, no secrets in the file. ``phrasebook.toml``: phrases in file order, each
with words, fields and a hint; errors name the entry."""

import shutil
from pathlib import Path
from typing import Any

import pytest

from algotrade.config.site.llm import BudgetSettings, LlmSettings, Phrase, PhrasebookSettings, Rate
from algotrade.config.site.settings import load_llm, load_phrasebook
from algotrade.core.model.errors import ConfigurationError
from algotrade.storage.configs.files import FileConfigStore, MemoryConfigStore
from tests.conftest import REPO_ROOT
from tests.unit.config.site.test_settings import site


def test_defaults_are_off_and_local() -> None:
    d = LlmSettings.from_document(None)
    (only,) = d.providers
    assert not d.enabled and only.base_url == "http://localhost:11434/v1" and only.local
    assert (only.timeout_s, only.answer_limit, only.retries) == (60.0, 8000, 2)
    assert d.legacy and d.deadline_s == 220.0  # 3 x 60 s + two 20 s pauses


def test_the_shipped_file_is_off() -> None:
    assert not LlmSettings.from_document(site("llm")).enabled
    assert not load_llm(MemoryConfigStore({})).enabled


def test_a_remote_provider() -> None:
    s = LlmSettings.from_document(
        {
            "enabled": True,
            "base_url": "https://api.groq.com/openai/v1/",
            "model": "llama-3.3-70b-versatile",
            "timeout_s": 20,
            "answer_limit": 800,
            "retries": 0,
            "price": [{"model": "llama-3.3-70b-versatile", "free": True}],
        }
    )
    (p,) = s.providers
    assert s.rate(p) == Rate("free")
    assert s.enabled and s.legacy and p.base_url == "https://api.groq.com/openai/v1"
    assert (p.model, p.timeout_s, p.answer_limit) == ("llama-3.3-70b-versatile", 20.0, 800)
    assert p.retries == 0 and not p.local


@pytest.mark.parametrize(
    ("doc", "message"),
    [
        ({"base_url": "http://api.example.com/v1"}, "must use https"),
        ({"base_url": "ftp://localhost/v1"}, "expected an http"),
        ({"base_url": ""}, "non-empty string"),
        ({"timeout_s": 0}, "timeout_s"),
        ({"answer_limit": 0}, "answer_limit"),
        ({"retries": -1}, "retries"),
        ({"api_key": "sk-123"}, "looks like a secret"),
        ({"provider": "groq"}, r"\[\[provider\]\]"),
        ({"nonsense": 1}, "unknown keys"),
    ],
)
def test_errors_name_the_key(doc: dict[str, Any], message: str) -> None:
    with pytest.raises(ConfigurationError, match=message):
        LlmSettings.from_document(doc)


def test_plain_http_is_fine_on_this_machine() -> None:
    for host in ("localhost", "127.0.0.1", "[::1]"):
        assert LlmSettings.from_document({"base_url": f"http://{host}:11434/v1"}).enabled is False


def test_phrasebook_entries_in_file_order() -> None:
    book = PhrasebookSettings.from_document(
        {
            "phrase": [
                {
                    "say": ["momentum", " trending up "],
                    "fields": ["rollup.a@v1.x"],
                    "hint": " gate:  x gt 0 ",
                },
                {"say": ["cheap"], "fields": ["rollup.a@v1.close", "feature.p"]},
            ]
        }
    )
    assert book.phrases == (
        Phrase(("momentum", "trending up"), ("rollup.a@v1.x",), "gate:  x gt 0"),
        Phrase(("cheap",), ("rollup.a@v1.close", "feature.p"), ""),
    )
    assert PhrasebookSettings.from_document(None).phrases == ()
    assert load_phrasebook(MemoryConfigStore({})).phrases == ()


def test_the_shipped_phrasebook_loads() -> None:
    book = PhrasebookSettings.from_document(site("phrasebook"))
    assert len(book.phrases) >= 10
    assert any("momentum" in p.say for p in book.phrases)
    assert all(p.hint for p in book.phrases)


@pytest.mark.parametrize(
    ("doc", "message"),
    [
        ({"phrase": {"say": ["x"]}}, r"expected a list of tables"),
        ({"phrase": [{"fields": ["a"]}]}, r"\[\[phrase\]\]\[0\] say"),
        ({"phrase": [{"say": ["x"]}]}, r"\[\[phrase\]\]\[0\] fields"),
        ({"phrase": [{"say": ["x"], "fields": [""]}]}, r"fields: expected"),
        ({"phrase": [{"say": "x", "fields": ["a"]}]}, r"a list of strings"),
        ({"phrase": [{"say": ["x"], "fields": ["a"], "mean": "y"}]}, r"unknown keys"),
        ({"phrases": []}, r"unknown keys"),
    ],
)
def test_phrasebook_errors_name_the_entry(doc: dict[str, Any], message: str) -> None:
    with pytest.raises(ConfigurationError, match=message):
        PhrasebookSettings.from_document(doc)


def test_request_extras_pass_through_but_never_the_adapters_keys() -> None:
    s = LlmSettings.from_document({"request": {"reasoning_effort": "low", "seed": 7}})
    assert s.providers[0].request == {"reasoning_effort": "low", "seed": 7}
    with pytest.raises(TypeError):
        s.providers[0].request["seed"] = 8  # type: ignore[index]
    assert LlmSettings.from_document({}).providers[0].request == {}
    with pytest.raises(ConfigurationError, match=r"the adapter sets \['model', 'temperature'\]"):
        LlmSettings.from_document({"request": {"model": "x", "temperature": 1}})
    with pytest.raises(ConfigurationError, match="expected a table"):
        LlmSettings.from_document({"request": "low"})


@pytest.mark.parametrize(
    "value", [{"effort": "low"}, ["low"], [{"effort": "low"}]], ids=["table", "array", "tables"]
)
def test_request_extras_are_strings_numbers_or_booleans(value: Any) -> None:
    with pytest.raises(ConfigurationError, match=r"\[request\] thinking: expected a string"):
        LlmSettings.from_document({"request": {"thinking": value}})
    ok = LlmSettings.from_document({"request": {"a": "x", "b": 1, "c": 0.5, "d": True}})
    assert dict(ok.providers[0].request) == {"a": "x", "b": 1, "c": 0.5, "d": True}


def test_request_extras_refuse_a_secret_looking_key() -> None:
    with pytest.raises(ConfigurationError, match="looks like a secret"):
        LlmSettings.from_document({"request": {"api_key": "x"}})


CHAIN: dict[str, Any] = {
    "enabled": True,
    "timeout_s": 30,
    "retries": 1,
    "request": {"reasoning_effort": "low"},
    "price": [
        {"model": "claude-haiku-4-5", "input_per_mtok": 1.0, "output_per_mtok": 5.0},
        {"model": "gemini-2.5-flash", "free": True},
    ],
    "provider": [
        {"id": "claude", "base_url": "https://api.anthropic.com/v1/", "model": "claude-haiku-4-5"},
        {
            "id": "gemini",
            "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
            "model": "gemini-2.5-flash",
            "timeout_s": 90,
            "request": {},
        },
    ],
}


def test_a_chain_is_the_provider_tables_in_order_over_the_top_level_defaults() -> None:
    s = LlmSettings.from_document(CHAIN)
    claude, gemini = s.providers
    assert s.enabled and not s.legacy
    assert (claude.id, claude.base_url, claude.model) == (
        "claude",
        "https://api.anthropic.com/v1",
        "claude-haiku-4-5",
    )
    assert (claude.timeout_s, claude.retries, claude.answer_limit) == (30.0, 1, 8000)
    assert claude.request == {"reasoning_effort": "low"}  # the file's default
    assert (gemini.timeout_s, gemini.retries) == (90.0, 1) and gemini.request == {}


def test_both_forms_in_one_file_are_refused() -> None:
    for top in ({"base_url": "http://localhost:11434/v1"}, {"model": "llama3.1"}):
        with pytest.raises(ConfigurationError, match=r"use one form"):
            LlmSettings.from_document(CHAIN | top)


@pytest.mark.parametrize(
    ("providers", "message"),
    [
        ([], r"a list of tables"),
        ("claude", r"a list of tables"),
        ([{"id": "Claude", "base_url": "https://a.io/v1", "model": "m"}], r"id: expected"),
        ([{"base_url": "https://a.io/v1", "model": "m"}], r"id: expected"),
        ([{"id": "a", "model": "m"}], r"base_url and model are required"),
        ([{"id": "a", "base_url": "https://a.io/v1"}], r"base_url and model are required"),
        ([{"id": "a", "base_url": "http://a.io/v1", "model": "m"}], r"must use https"),
        (
            [{"id": "a", "base_url": "https://a.io/v1", "model": "m", "enabled": True}],
            r"unknown keys",
        ),
        (
            [{"id": "a", "base_url": "https://a.io/v1", "model": "m"}] * 2,
            r"'a' is used twice",
        ),
    ],
)
def test_provider_errors_name_the_entry(providers: Any, message: str) -> None:
    with pytest.raises(ConfigurationError, match=message):
        LlmSettings.from_document({"provider": providers})


def test_the_deadline_is_every_providers_worst_case_unless_it_would_cut_off_the_fallback() -> None:
    s = LlmSettings.from_document(CHAIN)
    needed = s.providers[0].worst_case_s
    assert needed == 30 * 2 + 20  # claude: timeout_s 30, retries 1, one 20 s pause
    assert s.deadline_s == needed + (90 * 2 + 20)  # unset: both worst cases added up
    ok = LlmSettings.from_document(CHAIN | {"deadline_s": needed + 1})
    assert ok.deadline_s == needed + 1
    with pytest.raises(ConfigurationError, match=r"deadline_s: 80 s is shorter"):
        LlmSettings.from_document(CHAIN | {"deadline_s": needed})
    with pytest.raises(ConfigurationError, match="deadline_s"):  # the old default of 120 s
        LlmSettings.from_document(
            {"provider": CHAIN["provider"], "deadline_s": 120}  # 60 s x 3 attempts + pauses
        )


def test_a_machine_file_adds_the_chain_over_the_shipped_file(tmp_path: Path) -> None:
    """``llm.local.toml`` is overlaid on the shipped ``llm.toml`` (``merge_local``): the shipped
    file must not set ``base_url`` / ``model``, or a local ``[[provider]]`` would be both forms."""
    site_dir = tmp_path / "site"
    site_dir.mkdir()
    shutil.copy(REPO_ROOT / "config" / "site" / "llm.toml", site_dir / "llm.toml")
    (site_dir / "llm.local.toml").write_text(
        'enabled = true\n[[provider]]\nid = "claude"\n'
        'base_url = "https://api.anthropic.com/v1"\nmodel = "claude-haiku-4-5"\n'
        '[[provider]]\nid = "gemini"\n'
        'base_url = "https://generativelanguage.googleapis.com/v1beta/openai"\n'
        'model = "gemini-2.5-flash"\n'
        '[[price]]\nmodel = "claude-haiku-4-5"\ninput_per_mtok = 1\noutput_per_mtok = 5\n'
        '[[price]]\nmodel = "gemini-2.5-flash"\nfree = true\n'
    )
    s = load_llm(FileConfigStore(tmp_path))
    assert s.enabled and not s.legacy
    assert [p.id for p in s.providers] == ["claude", "gemini"]
    # and a machine file with the single-provider keys still works over the shipped one
    (site_dir / "llm.local.toml").write_text(
        'enabled = true\nbase_url = "https://x.example/v1"\nmodel = "m"\n'
        '[[price]]\nmodel = "m"\nfree = true\n'
    )
    assert load_llm(FileConfigStore(tmp_path)).providers[0].model == "m"


CLI: dict[str, Any] = {
    "id": "claude_cli",
    "kind": "claude-cli",
    "command": "/Users/o/.local/bin/claude",
    "model": "haiku",
    "only_users": ["abhi"],
}
GEMINI: dict[str, Any] = {
    "id": "gemini",
    "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
    "model": "gemini-2.5-flash",
}


def test_a_claude_cli_provider_has_a_command_a_model_no_retries_and_its_users() -> None:
    s = LlmSettings.from_document({"provider": [CLI, GEMINI | {"only_users": ["abhi", "bob"]}]})
    cli, gemini = s.providers
    assert (cli.kind, cli.command, cli.model, cli.only_users) == (
        "claude-cli",
        "/Users/o/.local/bin/claude",
        "haiku",
        ("abhi",),
    )
    assert (cli.retries, cli.timeout_s, cli.local) == (0, 60.0, True)  # no key, no pauses
    assert cli.worst_case_s == 60.0
    assert (gemini.kind, gemini.only_users) == ("openai", ("abhi", "bob"))  # any kind may have it
    assert s.deadline_s == 60 + gemini.worst_case_s


def test_a_claude_cli_provider_may_set_its_own_timeout_and_retries() -> None:
    s = LlmSettings.from_document({"provider": [CLI | {"timeout_s": 90, "retries": 1}, GEMINI]})
    assert (s.providers[0].timeout_s, s.providers[0].retries) == (90.0, 1)


@pytest.mark.parametrize(
    ("entry", "message"),
    [
        ({"only_users": None}, r"needs only_users"),
        ({"only_users": []}, r"only_users: expected one or more user ids"),
        ({"only_users": [" "]}, r"only_users: expected one or more user ids"),
        ({"command": "claude"}, r"absolute path of claude"),
        ({"command": None}, r"absolute path of claude"),
        ({"model": None}, r"model is required"),
        ({"base_url": "https://a.io/v1"}, r"do not apply to kind"),
        ({"request": {"a": 1}}, r"do not apply to kind"),
        ({"kind": "codex"}, r"kind: expected one of"),
    ],
)
def test_claude_cli_errors_name_the_entry(entry: dict[str, Any], message: str) -> None:
    doc = {k: v for k, v in (CLI | entry).items() if v is not None}
    with pytest.raises(ConfigurationError, match=message):
        LlmSettings.from_document({"provider": [doc, GEMINI]})


def test_command_belongs_to_claude_cli_only() -> None:
    with pytest.raises(ConfigurationError, match=r"command belongs to kind"):
        LlmSettings.from_document({"provider": [GEMINI | {"command": "/bin/claude"}]})


PAID = {"id": "p", "base_url": "https://a.io/v1", "model": "m"}


def test_rates_are_a_price_free_or_reported_and_a_paid_model_without_a_price_is_refused() -> None:
    s = LlmSettings.from_document(CHAIN)
    claude, gemini = s.providers
    assert s.rate(claude) == Rate("price", 1.0, 5.0) and s.rate(claude).spends
    assert s.rate(gemini) == Rate("free") and not s.rate(gemini).spends
    local = LlmSettings.from_document({"enabled": True})  # a loopback server needs no entry
    assert local.rate(local.providers[0]) == Rate("free")
    cli = {"id": "c", "kind": "claude-cli", "command": "/x/claude", "model": "haiku"}
    with_cli = LlmSettings.from_document(
        {"enabled": True, "provider": [cli | {"only_users": ["a"]}]}
    )
    assert with_cli.rate(with_cli.providers[0]) == Rate("reported")
    with pytest.raises(ConfigurationError, match=r"provider p: no \[\[price\]\] for model 'm'"):
        LlmSettings.from_document({"enabled": True, "provider": [PAID]})
    off = LlmSettings.from_document({"provider": [PAID]})  # a disabled file is not checked
    assert not off.enabled


@pytest.mark.parametrize(
    ("price", "message"),
    [
        ({"input_per_mtok": 1, "output_per_mtok": 2}, "model is required"),
        ({"model": "m", "input_per_mtok": 1}, "input_per_mtok and output_per_mtok"),
        ({"model": "m", "free": True, "input_per_mtok": 1}, "a free model has no price"),
        ({"model": "m", "input_per_mtok": -1, "output_per_mtok": 2}, "input_per_mtok"),
        ({"model": "m", "input_per_mtok": 1, "output_per_mtok": 2, "cost": 1}, "unknown keys"),
    ],
)
def test_price_errors_name_the_entry(price: dict[str, Any], message: str) -> None:
    with pytest.raises(ConfigurationError, match=message):
        LlmSettings.from_document({"price": [price]})
    with pytest.raises(ConfigurationError, match="a list of tables"):
        LlmSettings.from_document({"price": "free"})
    twice = [{"model": "m", "free": True}] * 2
    with pytest.raises(ConfigurationError, match="priced twice"):
        LlmSettings.from_document({"price": twice})


def test_the_budget_is_optional_typed_and_daily_cannot_exceed_monthly() -> None:
    assert LlmSettings.from_document({}).budget == BudgetSettings(None, None, "free")
    b = LlmSettings.from_document({"budget": {"daily_usd": 1, "monthly_usd": 15, "over": "refuse"}})
    assert b.budget == BudgetSettings(1.0, 15.0, "refuse")
    for doc, message in [
        ({"over": "ignore"}, "over: expected one of"),
        ({"daily_usd": -1}, "daily_usd"),
        ({"daily_usd": 20, "monthly_usd": 15}, "above monthly_usd"),
        ({"limit": 3}, "unknown keys"),
    ]:
        with pytest.raises(ConfigurationError, match=message):
            LlmSettings.from_document({"budget": doc})
