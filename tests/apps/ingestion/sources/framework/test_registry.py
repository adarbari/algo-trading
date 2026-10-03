"""The source registry (``sources/framework/registry.py``): every source declared once and
built from ``sources.toml`` + the environment, with one limiter and circuit breaker per vendor key.

Fitness: every registered source has a ``sources.toml`` section and a limiter key, sources
sharing a key read one section, and no vendor module paces itself (``time.sleep``)."""

import ast
import tomllib
from dataclasses import replace
from functools import partial
from pathlib import Path

import pytest

from algotrade.config.site.settings import SourcesSettings
from algotrade_ingestion.sources.framework import registry
from algotrade_ingestion.sources.framework.http import Http
from algotrade_ingestion.sources.framework.registry import (
    RAW_SECTIONS,
    SESSION_SOURCES,
    SOURCES,
    build_sources,
    limiter_keys,
    raw_sections,
    raw_source,
)
from tests.conftest import REPO_ROOT

SITE_SOURCES = tomllib.loads((REPO_ROOT / "config" / "site" / "sources.toml").read_text())
SOURCES_DIR = REPO_ROOT / "apps" / "ingestion" / "algotrade_ingestion" / "sources"
# The two modules that may wait: the limiter (pacing) and http.py (retry backoff).
MAY_SLEEP = {"limiter.py", "http.py"}
ENV = {"ALGOTRADE_MASSIVE_API_KEY": "key", "ALGOTRADE_SEC_CONTACT": "ops@example.org"}


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


def test_one_limiter_and_breaker_per_key_with_configured_or_default_pace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    http: dict[str, Http] = {}
    for name, spec in SOURCES.items():
        keep = partial(http.setdefault, name)
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
    from algotrade_ingestion.sources.framework.base import FixtureSource  # noqa: PLC0415
    from algotrade_ingestion.sources.framework.registry import (  # noqa: PLC0415
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
    from algotrade_ingestion.sources.framework.base import SessionSource  # noqa: PLC0415
    from algotrade_ingestion.sources.vendors.ibkr.market_data import IbkrSource  # noqa: PLC0415

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
