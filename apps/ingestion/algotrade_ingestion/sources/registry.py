"""The source registry: every vendor source declared ONCE (ADR 0019 R3, ``source-construction``).

A ``SourceSpec`` names the source (``ctx.sources[name]`` in tasks), its ``config/site/
sources.toml`` section (``enabled``, ``min_interval_s``), the environment variable it needs
(if any) and how that becomes request headers, its limiter key and default pacing, its retry
policy and the class that builds it from an ``Http`` client.

Fixture sources (the synthetic golden CSVs) are not vendors: ``FIXTURES`` builds them from a
directory, with no transport, pacing or ``sources.toml`` section (``fixture_source``).

``build_sources(settings, env)`` builds every available source: one ``Limiter`` per limiter
key (shared across threads and processes, ``sources/limiter.py``) and one ``CircuitBreaker``
per key. A source whose section is disabled or whose variable is missing is left out, with
the reason in ``Built.skipped``; tasks that need it are skipped with that reason.
"""

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from algotrade_ingestion.sources.base import FixtureSource, Source
from algotrade_ingestion.sources.cboe import CboeOptionsSource
from algotrade_ingestion.sources.http import (
    BROWSER_USER_AGENT,
    CircuitBreaker,
    Http,
    RetryPolicy,
    urllib_transport,
)
from algotrade_ingestion.sources.limiter import Limiter
from algotrade_ingestion.sources.massive import (
    MassiveCorporateActions,
    MassiveDailyBars,
    MassiveTickers,
)
from algotrade_ingestion.sources.nasdaq_earnings import NasdaqEarningsSource
from algotrade_ingestion.sources.nasdaq_trader import NasdaqTraderSource
from algotrade_ingestion.sources.sec_edgar import SecSubmissions, SecTickerMap, user_agent
from algotrade_ingestion.sources.spy_holdings import SpyHoldingsSource
from algotrade_ingestion.sources.synthetic.source import golden_source

type Env = Callable[[str], str | None]  # variable name -> value (``env.credential``)
MASSIVE_KEY = "ALGOTRADE_MASSIVE_API_KEY"
SEC_CONTACT = "ALGOTRADE_SEC_CONTACT"


class VendorConfig(Protocol):
    @property
    def enabled(self) -> bool: ...

    @property
    def min_interval_s(self) -> float | None: ...


class RegistrySettings(Protocol):
    """What the registry reads from ``RegistrySettings`` (sources never import settings)."""

    @property
    def http_max_retry_s(self) -> float: ...

    @property
    def http_breaker_failures(self) -> int: ...

    @property
    def limits_dir(self) -> str: ...

    def vendor(self, section: str) -> VendorConfig: ...


def _no_headers(_: str | None) -> dict[str, str]:
    return {}


@dataclass(frozen=True)
class SourceSpec:
    name: str
    section: str  # config/site/sources.toml section: enabled, min_interval_s
    limiter: str  # one shared limiter (and circuit breaker) per key
    build: Callable[[Http], Source]
    min_interval_s: float = 0.0  # default when the section does not set min_interval_s
    env_var: str | None = None  # required credential or contact
    env_hint: str = "add it to .env"
    headers: Callable[[str | None], dict[str, str]] = _no_headers  # from the env value
    tries: int = 7


def _bearer(key: str | None) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}  # in a header, never in URLs or logs


def _sec_agent(contact: str | None) -> dict[str, str]:
    return {"User-Agent": user_agent(str(contact))}


def _browser(_: str | None) -> dict[str, str]:
    return {"User-Agent": BROWSER_USER_AGENT}  # api.nasdaq.com rejects other agents


def _massive(name: str, build: Callable[[Http], Source]) -> SourceSpec:
    hint = "create a free Massive account and add the key to .env"
    return SourceSpec(name, "massive", "massive", build, 12.5, MASSIVE_KEY, hint, _bearer)


def _sec(name: str, build: Callable[[Http], Source]) -> SourceSpec:
    hint = "SEC EDGAR requires a contact email; add it to .env"
    return SourceSpec(name, "sec_edgar", "sec", build, 0.2, SEC_CONTACT, hint, _sec_agent, 4)


SOURCES: dict[str, SourceSpec] = {
    s.name: s
    for s in (
        SourceSpec("cboe", "cboe", "cboe", CboeOptionsSource),
        SourceSpec("nasdaq_trader", "nasdaq_trader", "nasdaqtrader", NasdaqTraderSource),
        SourceSpec("spy_holdings", "spy_holdings", "ssga", SpyHoldingsSource),
        SourceSpec(
            "nasdaq_earnings",
            "nasdaq_earnings",
            "nasdaq",
            NasdaqEarningsSource,
            0.5,
            headers=_browser,
        ),
        _massive("massive_bars", MassiveDailyBars),
        _massive("massive_corporate_actions", MassiveCorporateActions),
        _massive("massive_tickers", MassiveTickers),
        _sec("sec_tickers", SecTickerMap),
        _sec("sec_submissions", SecSubmissions),
    )
}


# Fixture sources by name: directory (None: the default) -> source.
FIXTURES: dict[str, Callable[[Path | None], FixtureSource]] = {"synthetic": golden_source}


def fixture_source(name: str, directory: Path | None = None) -> FixtureSource:
    """The fixture source ``name`` over ``directory``. Unknown names raise ``KeyError``."""
    return FIXTURES[name](directory)


@dataclass
class Built:
    """Sources by name, and why each unavailable one was left out."""

    sources: dict[str, Source] = field(default_factory=dict)
    skipped: dict[str, str] = field(default_factory=dict)


def unavailable(spec: SourceSpec, settings: RegistrySettings, env: Env) -> str | None:
    if not settings.vendor(spec.section).enabled:
        return f"[{spec.section}] is disabled in sources.toml"
    if spec.env_var is not None and env(spec.env_var) is None:
        return f"{spec.env_var} is not set: {spec.env_hint}"
    return None


def interval(spec: SourceSpec, settings: RegistrySettings) -> float:
    configured = settings.vendor(spec.section).min_interval_s
    return spec.min_interval_s if configured is None else configured


def build_sources(
    settings: RegistrySettings,
    env: Env,
    names: Iterable[str] | None = None,
    limits_dir: Path | None = None,
    fixture_dir: Path | None = None,
) -> Built:
    """Build the named sources (default: every vendor source); a named fixture source reads
    ``fixture_dir``. Unknown names raise ``KeyError``."""
    wanted = list(dict.fromkeys(SOURCES if names is None else names))
    directory = limits_dir or Path(settings.limits_dir)
    limiters: dict[str, Limiter] = {}
    breakers: dict[str, CircuitBreaker] = {}
    built = Built()
    for name in wanted:
        if name in FIXTURES:
            built.sources[name] = fixture_source(name, fixture_dir)
            continue
        spec = SOURCES[name]
        reason = unavailable(spec, settings, env)
        if reason is not None:
            built.skipped[name] = reason
            continue
        key = spec.limiter
        if key not in limiters:
            limiters[key] = Limiter(key, interval(spec, settings), directory)
            breakers[key] = CircuitBreaker(key, settings.http_breaker_failures)
        secret = env(spec.env_var) if spec.env_var else None
        http = Http(
            urllib_transport(headers=spec.headers(secret)),
            RetryPolicy(tries=spec.tries, max_total_s=settings.http_max_retry_s),
            limiters[key],
            breakers[key],
        )
        built.sources[name] = spec.build(http)
    return built


def limiter_keys(specs: Mapping[str, SourceSpec] = SOURCES) -> dict[str, set[str]]:
    """limiter key -> the sources.toml sections its sources read (one each, by design)."""
    out: dict[str, set[str]] = {}
    for spec in specs.values():
        out.setdefault(spec.limiter, set()).add(spec.section)
    return out
