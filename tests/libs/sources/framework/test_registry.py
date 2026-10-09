"""The source registry (``sources/framework/registry.py``): every source declared once and
built from ``sources.toml`` + the environment, with one limiter and circuit breaker per vendor key.

Fitness: every registered source has a ``sources.toml`` section and a limiter key, sources
sharing a key read one section, and no vendor module paces itself (``time.sleep``)."""

import ast
import tomllib
from collections.abc import Callable
from dataclasses import replace
from functools import partial
from pathlib import Path

import pytest

from algotrade.config.site.settings import SourcesSettings
from algotrade.core.model.errors import ConfigurationError
from algotrade_sources.framework import registry
from algotrade_sources.framework.base import FetchRequest
from algotrade_sources.framework.http import Http
from algotrade_sources.framework.registry import (
    RAW_SECTIONS,
    SESSION_SOURCES,
    SOURCES,
    build_sources,
    limiter_keys,
    raw_sections,
    raw_source,
)
from algotrade_sources.framework.series import SeriesRequest
from tests.conftest import REPO_ROOT
from tests.helpers.payloads import fred as fred_payloads

SITE_SOURCES = tomllib.loads((REPO_ROOT / "config" / "site" / "sources.toml").read_text())
SOURCES_DIR = REPO_ROOT / "libs" / "sources" / "algotrade_sources"
# The two modules that may wait: the limiter (pacing) and http.py (retry backoff).
MAY_SLEEP = {"limiter.py", "http.py"}
ENV = {
    "ALGOTRADE_MASSIVE_API_KEY": "key",
    "ALGOTRADE_SEC_CONTACT": "ops@example.org",
    "ALGOTRADE_FRED_API_KEY": "fred-key",
    "ALGOTRADE_TIINGO_API_KEY": "tiingo-key",
}


def keep_http(kept: dict[str, Http], name: str, http: Http, **options: object) -> Http:
    """A ``build`` that keeps the ``Http`` the registry made, for the test to inspect."""
    return kept.setdefault(name, http)


def settings(doc: dict[str, object] | None = None) -> SourcesSettings:
    return SourcesSettings.from_document(doc if doc is not None else SITE_SOURCES)


def test_every_source_is_built_when_configured(tmp_path: Path) -> None:
    built = build_sources(settings(), ENV.get, limits_dir=tmp_path)
    assert set(built.sources) == set(SOURCES)
    # IBKR is enabled on site (owner runs IB Gateway); CI has no gateway env, so it is skipped
    # with the reason that tells the owner what to set.
    assert set(built.skipped) == {"ibkr"}
    assert "ALGOTRADE_IBKR_HOST" in built.skipped["ibkr"] or "disabled" in built.skipped["ibkr"]
    assert list(tmp_path.iterdir()) == []  # limiter files appear on first request only


def test_disabled_sections_and_missing_credentials_are_skipped_with_a_reason(
    tmp_path: Path,
) -> None:
    doc = {**SITE_SOURCES, "cboe": {"enabled": False}}
    built = build_sources(settings(doc), lambda name: None, limits_dir=tmp_path)
    assert built.skipped["cboe"] == "[cboe] is disabled in sources.toml"
    assert built.skipped["massive_bars"].startswith("ALGOTRADE_MASSIVE_API_KEY is not set")
    assert built.skipped["sec_tickers"].startswith("ALGOTRADE_SEC_CONTACT is not set")
    assert "nasdaq_trader" in built.sources and "cboe" not in built.sources
    with pytest.raises(KeyError):
        build_sources(settings(), ENV.get, ["nope"], tmp_path)


def test_fred_needs_its_key_and_sends_it_only_as_a_query_parameter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    missing = build_sources(settings(), lambda name: None, ["fred", "published"], tmp_path)
    assert missing.skipped["fred"].startswith("ALGOTRADE_FRED_API_KEY is not set")
    assert "published" in missing.sources  # published files need no key

    seen: list[str] = []

    def answer(url: str) -> bytes:
        seen.append(url)
        return fred_payloads.payload()

    def fake_transport(headers: dict[str, str] | None = None) -> Callable[[str], bytes]:
        assert "s3cret" not in str(headers)  # not a header: FRED takes it as a parameter
        return answer

    monkeypatch.setattr(registry, "urllib_transport", fake_transport)
    doc = {**SITE_SOURCES, "fred": {**SITE_SOURCES["fred"], "base_url": "https://fred.example/v1"}}
    built = build_sources(
        settings(doc), {"ALGOTRADE_FRED_API_KEY": "s3cret"}.get, ["fred"], tmp_path
    )
    source = built.sources["fred"]
    request = SeriesRequest("GDP_REAL", code="GDPC1")
    source.fetch(request)
    assert len(seen) == 1 and seen[0].endswith("&api_key=s3cret")
    assert seen[0].startswith("https://fred.example/v1/series/observations?")  # [fred] base_url
    assert "api_key" not in source.url(request)  # type: ignore[attr-defined]


def test_tiingo_needs_its_key_sends_it_as_a_token_header_and_paces_as_configured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    missing = build_sources(settings(), lambda name: None, ["tiingo_prices"], tmp_path)
    assert missing.skipped["tiingo_prices"].startswith("ALGOTRADE_TIINGO_API_KEY is not set")

    sent: list[dict[str, str] | None] = []
    urls: list[str] = []

    def fake_transport(headers: dict[str, str] | None = None) -> Callable[[str], bytes]:
        sent.append(headers)

        def answer(url: str) -> bytes:
            urls.append(url)
            return b"[]"

        return answer

    monkeypatch.setattr(registry, "urllib_transport", fake_transport)
    env = {"ALGOTRADE_TIINGO_API_KEY": "s3cret"}.get
    built = build_sources(settings(), env, ["tiingo_prices"], tmp_path)
    built.sources["tiingo_prices"].fetch(FetchRequest("AAPL:2018-01-01:2018-02-01"))
    assert sent[0] is not None and sent[0]["Authorization"] == "Token s3cret"
    assert "s3cret" not in urls[0]  # a header, never in the URL
    # the plan's pace comes from sources.toml (free tier 72 s, Power 0.4 s): never a constant here
    assert built.limiters["tiingo"].min_interval_s == SITE_SOURCES["tiingo"]["min_interval_s"]
    assert settings().tiingo_licence == "personal"


def test_one_limiter_and_breaker_per_key_with_configured_or_default_pace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    http: dict[str, Http] = {}
    for name, spec in SOURCES.items():
        keep = partial(keep_http, http, name)
        monkeypatch.setitem(registry.SOURCES, name, replace(spec, build=keep))  # type: ignore[arg-type]
    doc = {"massive": {"min_interval_s": 1.0}, "http": {"breaker_failures": 4}}
    build_sources(settings(doc), ENV.get, limits_dir=tmp_path)
    bars, actions = http["massive_bars"], http["massive_corporate_actions"]
    assert bars.limiter is actions.limiter and bars.breaker is actions.breaker
    assert bars.limiter is not http["sec_tickers"].limiter
    assert bars.limiter.min_interval_s == 1.0  # type: ignore[union-attr]
    assert http["sec_tickers"].limiter.min_interval_s == 0.2  # type: ignore[union-attr]
    assert http["sec_tickers"].policy.tries == 4 and bars.policy.max_total_s == 300.0
    assert bars.breaker is not None and bars.breaker.threshold == 4


def test_a_sources_toml_from_before_the_ssga_section_still_builds_and_paces_politely(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Older files have ``[spy_holdings]`` and no ``[ssga]``: SPY's file and the SPDR holdings
    files still build, on one limiter with the default 1 s pace."""
    http: dict[str, Http] = {}
    for name in ("spy_holdings", "ssga_holdings"):
        keep = partial(keep_http, http, name)
        monkeypatch.setitem(registry.SOURCES, name, replace(SOURCES[name], build=keep))  # type: ignore[arg-type]
    old = {k: v for k, v in SITE_SOURCES.items() if k != "ssga"}
    old["spy_holdings"] = {"enabled": True, "min_interval_s": 0.0}
    built = build_sources(settings(old), ENV.get, ["spy_holdings", "ssga_holdings"], tmp_path)
    assert set(built.sources) == {"spy_holdings", "ssga_holdings"} and not built.skipped
    assert http["spy_holdings"].limiter is http["ssga_holdings"].limiter
    assert http["ssga_holdings"].limiter.min_interval_s == 1.0  # type: ignore[union-attr]


def test_an_old_file_that_switched_spy_holdings_off_does_not_switch_it_back_on(
    tmp_path: Path,
) -> None:
    old = {k: v for k, v in SITE_SOURCES.items() if k != "ssga"}
    old["spy_holdings"] = {"enabled": False, "min_interval_s": 0.0}
    built = build_sources(settings(old), ENV.get, ["spy_holdings", "ssga_holdings"], tmp_path)
    assert built.sources == {}
    assert built.skipped["spy_holdings"] == "[ssga] is disabled in sources.toml"


def test_the_spdr_fund_files_have_their_own_switch_and_spy_membership_stays_on(
    tmp_path: Path,
) -> None:
    doc = {**SITE_SOURCES, "ssga": {**SITE_SOURCES["ssga"], "etf_files": False}}
    built = build_sources(settings(doc), ENV.get, ["spy_holdings", "ssga_holdings"], tmp_path)
    assert set(built.sources) == {"spy_holdings"}
    assert built.skipped["ssga_holdings"] == "[ssga] etf_files is false in sources.toml"
    off = {**SITE_SOURCES, "ssga": {**SITE_SOURCES["ssga"], "enabled": False}}
    assert not build_sources(settings(off), ENV.get, ["spy_holdings"], tmp_path).sources


def test_every_source_has_a_sources_toml_section_and_a_limiter_key() -> None:
    for name, spec in SOURCES.items():
        assert spec.name == name
        assert isinstance(SITE_SOURCES.get(spec.section), dict), f"{name}: no [{spec.section}]"
        assert "min_interval_s" in SITE_SOURCES[spec.section], f"{name}: [{spec.section}]"
        assert spec.limiter, f"{name}: no limiter key"
    shared = {k: v for k, v in limiter_keys().items() if len(v) > 1}
    assert not shared, f"sources sharing a limiter key must read one section: {shared}"


def test_raw_source_names_map_to_one_section_each() -> None:
    sections = raw_sections()
    assert sections == RAW_SECTIONS
    assert sections["sec_edgar"] == "sec_edgar"  # submissions, company_tickers, companyfacts
    assert sections["cboe_delayed"] == "cboe" and sections["massive"] == "massive"
    assert set(sections) == {raw_source(spec) for spec in SOURCES.values()} | {"ibkr"}
    assert sections["ibkr"] == "ibkr"
    clash = {"a": replace(SOURCES["cboe"], name="a"), "b": replace(SOURCES["cboe"], section="x")}
    with pytest.raises(ValueError, match="cboe_delayed"):
        raw_sections(clash)


def test_no_vendor_module_sleeps_or_paces_itself() -> None:
    offenders = []
    for path in sorted(SOURCES_DIR.rglob("*.py")):
        if path.name in MAY_SLEEP:
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            name = node.attr if isinstance(node, ast.Attribute) else getattr(node, "id", None)
            if name in ("sleep", "MinInterval"):
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno}")  # type: ignore[attr-defined]
    assert not offenders, f"sources never pace themselves; use the registry's limiter: {offenders}"


def test_fixture_sources_come_from_the_registry_with_their_directory(tmp_path: Path) -> None:
    from algotrade_sources.framework.base import FixtureSource  # noqa: PLC0415
    from algotrade_sources.framework.registry import (  # noqa: PLC0415
        FIXTURES,
        fixture_source,
    )

    source = fixture_source("synthetic", REPO_ROOT / "datasets" / "golden")
    assert isinstance(source, FixtureSource) and source.verify() == []
    assert "bull_trend" in source.datasets()
    built = build_sources(settings(), ENV.get, ["synthetic"], tmp_path, tmp_path / "golden")
    assert set(built.sources) == {"synthetic"} and set(FIXTURES) == {"synthetic"}
    built_source = built.sources["synthetic"]
    assert isinstance(built_source, FixtureSource)
    assert built_source.build() and built_source.verify() == []  # regenerated into tmp_path


IBKR_ENV = {
    "ALGOTRADE_IBKR_HOST": "127.0.0.1",
    "ALGOTRADE_IBKR_PORT": "4002",
    "ALGOTRADE_IBKR_CLIENT_ID": "17",
}


def test_the_ibkr_session_source_is_built_unconnected_from_settings_and_env(
    tmp_path: Path,
) -> None:
    from algotrade_sources.framework.base import SessionSource  # noqa: PLC0415
    from algotrade_sources.vendors.ibkr.market_data import IbkrSource  # noqa: PLC0415

    doc = {
        **SITE_SOURCES,
        "ibkr": {**SITE_SOURCES["ibkr"], "enabled": True, "market_data_type": 1},
    }
    built = build_sources(settings(doc), IBKR_ENV.get, ["ibkr"], tmp_path)
    source = built.sources["ibkr"]
    assert isinstance(source, IbkrSource) and isinstance(source, SessionSource)
    gateway = source.gateway
    assert (gateway.config.host, gateway.config.port, gateway.config.client_id) == (
        "127.0.0.1",
        4002,
        17,
    )
    assert gateway.config.market_data_type == 1 and gateway.config.readonly
    assert gateway._ib is None  # built unconnected: tasks open it
    assert gateway.general.min_interval_s == 0.02  # type: ignore[attr-defined]
    assert gateway.historical.min_interval_s == 10.0  # type: ignore[attr-defined]
    assert gateway.general.pacing.ceiling == 0.02  # type: ignore[attr-defined]  # fixed pace
    assert {"ibkr", "ibkr_historical"} <= set(limiter_keys())
    missing = build_sources(settings(doc), {}.get, ["ibkr"], tmp_path)
    assert missing.skipped["ibkr"].startswith("ALGOTRADE_IBKR_HOST is not set")
    assert set(SESSION_SOURCES) == {"ibkr"}


def test_ibkr_site_section_uses_ibkr_pacing() -> None:
    section = SITE_SOURCES["ibkr"]
    assert isinstance(section["enabled"], bool)  # on since the owner runs IB Gateway (read-only)
    assert section["min_interval_s"] <= 0.02 and section["historical_min_interval_s"] >= 10
    parsed = settings().ibkr
    assert parsed.market_data_type == 3 and parsed.historical_min_interval_s == 10.0


def test_the_historical_pace_is_the_setting(tmp_path: Path) -> None:
    doc = {**SITE_SOURCES, "ibkr": {**SITE_SOURCES["ibkr"], "historical_min_interval_s": 5.0}}
    built = build_sources(settings(doc), IBKR_ENV.get, ["ibkr"], tmp_path)
    gateway = built.sources["ibkr"].gateway  # type: ignore[attr-defined]
    assert gateway.historical.min_interval_s == 5.0
    assert built.limiters["ibkr_historical"].min_interval_s == 5.0


def test_each_key_gets_adaptive_pacing_from_its_section_and_http(tmp_path: Path) -> None:
    built = build_sources(settings(), ENV.get, limits_dir=tmp_path)
    cboe, massive = built.limiters["cboe"].pacing, built.limiters["massive"].pacing
    assert (cboe.min_interval_s, cboe.ceiling, cboe.start) == (1.05, 5.0, 1.05)
    assert (cboe.backoff_factor, cboe.error_window, cboe.speedup_after) == (1.5, 50, 100)
    assert (massive.min_interval_s, massive.ceiling) == (12.5, 50.0)  # default: 4 x floor
    assert set(built.limiters) == {spec.limiter for spec in SOURCES.values()}  # ibkr: off
    bad = {**SITE_SOURCES, "massive": {"max_interval_s": 1.0}}  # below the default floor
    with pytest.raises(ConfigurationError, match=r"\[massive\]: max_interval_s 1.0 is below"):
        build_sources(settings(bad), ENV.get, ["massive_bars"], tmp_path)
