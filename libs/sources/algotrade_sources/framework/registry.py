"""The source registry: every vendor source declared ONCE (ADR 0019 R3, ``source-construction``).

A ``SourceSpec`` names the source (``ctx.sources[name]`` in tasks), its ``config/site/
sources.toml`` section (``enabled``, ``min_interval_s`` / ``max_interval_s`` /
``start_interval_s``), the environment variable it needs (if any) and how that becomes
request headers, its limiter key and default pacing floor, its retry policy and the class that
builds it from an ``Http`` client.

Session sources (IB Gateway) hold a stateful connection, not HTTP: a ``SessionSpec`` names
the source, its section, its limiter keys and default pacing, the environment variables it
needs, and builds it UNCONNECTED from ``SessionInputs`` (settings, environment, limiters);
tasks open and close it (``base.opened``).

Fixture sources (the synthetic golden CSVs) are not vendors: ``FIXTURES`` builds them from a
directory, with no transport, pacing or ``sources.toml`` section (``fixture_source``).

``build_sources(settings, env)`` builds every available source: one ``Limiter`` per limiter
key (adaptive ``Pacing`` from the section and ``[http]``, shared across threads and processes,
``sources/framework/limiter.py``) and one ``CircuitBreaker`` per key; ``Built.limiters``
lets the entry point hand them to ``TaskContext.pacing`` (pacing stats per run). A source
whose section is disabled or whose variable is missing is left out, with the reason in
``Built.skipped``; tasks that need it are skipped with that reason.
"""

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from algotrade.config import env as env_names
from algotrade.core.model.errors import ConfigurationError
from algotrade_sources.fixtures.source import golden_source
from algotrade_sources.framework.base import FixtureSource, Source
from algotrade_sources.framework.http import (
    BROWSER_USER_AGENT,
    CircuitBreaker,
    Http,
    HttpError,
    RetryPolicy,
    json_post_transport,
    urllib_transport,
)
from algotrade_sources.framework.limiter import Limiter, Pacing
from algotrade_sources.llm.chat import ChatCompletions
from algotrade_sources.vendors.cboe.option_chains import CboeOptionsSource, missing_chain
from algotrade_sources.vendors.ibkr.gateway import GatewayConfig, IbkrMarketData
from algotrade_sources.vendors.ibkr.market_data import IbkrSource
from algotrade_sources.vendors.ishares.etf_holdings import IsharesHoldings, no_file
from algotrade_sources.vendors.massive.bars import MassiveDailyBars
from algotrade_sources.vendors.massive.corporate_actions import MassiveCorporateActions
from algotrade_sources.vendors.massive.overview import MassiveOverview
from algotrade_sources.vendors.massive.tickers import MassiveTickers
from algotrade_sources.vendors.nasdaq.earnings import NasdaqEarningsSource
from algotrade_sources.vendors.nasdaq.symbol_directory import NasdaqTraderSource
from algotrade_sources.vendors.proshares.etf_holdings import ProsharesHoldings
from algotrade_sources.vendors.sec.company_facts import SecCompanyFacts
from algotrade_sources.vendors.sec.edgar import SecSubmissions, SecTickerMap, user_agent
from algotrade_sources.vendors.sec.fund_objectives import (
    SecFundObjectives,
    SecFundSeries,
    SecFundTickerMap,
)
from algotrade_sources.vendors.sec.nport_holdings import NportHoldings
from algotrade_sources.vendors.ssga.etf_holdings import SsgaHoldings
from algotrade_sources.vendors.ssga.spy_holdings import SpyHoldingsSource
from algotrade_sources.vendors.treasury.par_yields import TreasuryParYields

type Env = Callable[[str], str | None]  # variable name -> value (``env.credential``)
MASSIVE_KEY = "ALGOTRADE_MASSIVE_API_KEY"
SEC_CONTACT = "ALGOTRADE_SEC_CONTACT"


class VendorConfig(Protocol):
    @property
    def enabled(self) -> bool: ...

    @property
    def min_interval_s(self) -> float | None: ...

    @property
    def max_interval_s(self) -> float | None: ...

    @property
    def start_interval_s(self) -> float | None: ...

    @property
    def switches(self) -> Mapping[str, bool]: ...


class IbkrOptions(Protocol):
    """``[ibkr]`` beyond enabled / min_interval_s (``config.site.settings.IbkrSettings``)."""

    @property
    def historical_min_interval_s(self) -> float: ...

    @property
    def market_data_type(self) -> int: ...

    @property
    def connect_timeout_s(self) -> float: ...

    @property
    def request_timeout_s(self) -> float: ...

    @property
    def stream_wait_s(self) -> float: ...


class RegistrySettings(Protocol):
    """What the registry reads from ``RegistrySettings`` (sources never import settings)."""

    @property
    def http_max_retry_s(self) -> float: ...

    @property
    def http_breaker_failures(self) -> int: ...

    @property
    def limits_dir(self) -> str: ...

    @property
    def ibkr(self) -> IbkrOptions: ...

    @property
    def http_backoff_factor(self) -> float: ...

    @property
    def http_speedup_factor(self) -> float: ...

    @property
    def http_speedup_after(self) -> int: ...

    @property
    def http_error_window(self) -> int: ...

    @property
    def http_max_error_rate(self) -> float: ...

    def vendor(self, section: str) -> VendorConfig: ...


def _no_headers(_: str | None) -> dict[str, str]:
    return {}


@dataclass(frozen=True)
class SourceSpec:
    name: str
    section: str  # config/site/sources.toml section: enabled, min_interval_s
    limiter: str  # one shared limiter (and circuit breaker) per key
    build: Callable[[Http], Source]
    min_interval_s: float = 0.0  # default floor when the section does not set min_interval_s
    env_var: str | None = None  # required credential or contact
    env_hint: str = "add it to .env"
    headers: Callable[[str | None], dict[str, str]] = _no_headers  # from the env value
    tries: int = 7
    not_found: Callable[[HttpError], bool] | None = None  # vendor's "no such object" errors
    switch: str | None = None  # a further on/off key of the section that must not be false


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
        SourceSpec("cboe", "cboe", "cboe", CboeOptionsSource, not_found=missing_chain),
        SourceSpec("nasdaq_trader", "nasdaq_trader", "nasdaqtrader", NasdaqTraderSource),
        SourceSpec("spy_holdings", "ssga", "ssga", SpyHoldingsSource, 1.0),
        SourceSpec("ssga_holdings", "ssga", "ssga", SsgaHoldings, 1.0, switch="etf_files"),
        SourceSpec(
            "ishares_holdings", "ishares", "ishares", IsharesHoldings, 1.0, not_found=no_file
        ),
        SourceSpec("proshares_holdings", "proshares", "proshares", ProsharesHoldings, 1.0),
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
        _massive("massive_overview", MassiveOverview),
        _sec("sec_tickers", SecTickerMap),
        _sec("sec_submissions", SecSubmissions),
        _sec("sec_company_facts", SecCompanyFacts),
        _sec("sec_nport_holdings", NportHoldings),
        _sec("sec_fund_tickers", SecFundTickerMap),
        _sec("sec_fund_objectives", SecFundObjectives),
        _sec("sec_fund_series", SecFundSeries),
        SourceSpec("treasury", "treasury", "treasury", TreasuryParYields, 1.0),
    )
}


@dataclass(frozen=True)
class SessionInputs:
    """What a session source is built from: settings, the environment and the shared
    limiters (``limiter(key, min_interval_s)``: one per key, across threads and processes)."""

    settings: RegistrySettings
    env: Env
    limiter: Callable[[str, float], Limiter]
    interval: float  # the section's min_interval_s (or the spec's default)


@dataclass(frozen=True)
class SessionSpec:
    """A source over a stateful session (a local gateway socket), built unconnected."""

    name: str
    section: str
    limiter: str  # every message waits on this key
    build: Callable[[SessionInputs], Source]
    kind: type  # the class ``build`` returns; its ``name`` is the raw-store source name
    min_interval_s: float = 0.0
    env_vars: tuple[str, ...] = ()  # all required
    env_hint: str = "add it to .env"
    more_limiters: tuple[str, ...] = ()  # further limiter keys ``build`` uses (same section)


IBKR_HISTORICAL = "ibkr_historical"  # second limiter key: historical-data requests


def _ibkr(inputs: SessionInputs) -> Source:
    """IB Gateway, read-only (ADR 0026): host / port / client id from the environment."""
    options = inputs.settings.ibkr
    config = GatewayConfig(
        host=str(inputs.env(env_names.IBKR_HOST)),
        port=int(str(inputs.env(env_names.IBKR_PORT))),
        client_id=int(str(inputs.env(env_names.IBKR_CLIENT_ID))),
        market_data_type=options.market_data_type,
        connect_timeout_s=options.connect_timeout_s,
        request_timeout_s=options.request_timeout_s,
        stream_wait_s=options.stream_wait_s,
    )
    gateway = IbkrMarketData(
        config,
        general=inputs.limiter("ibkr", inputs.interval),
        historical=inputs.limiter(IBKR_HISTORICAL, options.historical_min_interval_s),
    )
    return IbkrSource(gateway)


SESSION_SOURCES: dict[str, SessionSpec] = {
    s.name: s
    for s in (
        SessionSpec(
            "ibkr",
            "ibkr",
            "ibkr",
            _ibkr,
            IbkrSource,
            0.02,
            (env_names.IBKR_HOST, env_names.IBKR_PORT, env_names.IBKR_CLIENT_ID),
            "run IB Gateway (read-only API) and set it in .env (README, Live verification)",
            (IBKR_HISTORICAL,),
        ),
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
    limiters: dict[str, Limiter] = field(default_factory=dict)  # by limiter key


def unavailable(spec: SourceSpec | SessionSpec, settings: RegistrySettings, env: Env) -> str | None:
    if not settings.vendor(spec.section).enabled:
        return f"[{spec.section}] is disabled in sources.toml"
    switch = None if isinstance(spec, SessionSpec) else spec.switch
    if switch and not settings.vendor(spec.section).switches.get(switch, True):
        return f"[{spec.section}] {switch} is false in sources.toml"
    names = spec.env_vars if isinstance(spec, SessionSpec) else (spec.env_var,)
    for name in names:
        if name is not None and env(name) is None:
            return f"{name} is not set: {spec.env_hint}"
    return None


def interval(spec: SourceSpec | SessionSpec, settings: RegistrySettings) -> float:
    """The pacing floor: the section's ``min_interval_s``, else the spec's default."""
    configured = settings.vendor(spec.section).min_interval_s
    return spec.min_interval_s if configured is None else configured


DEFAULT_CEILING = 4.0  # max_interval_s when a section does not set it: 4 x the floor


def pacing(spec: SourceSpec, settings: RegistrySettings) -> Pacing:
    """The key's adaptive pacing: floor / ceiling / start from its section, the rest from
    ``[http]``. A ceiling or start that does not fit the floor fails with the section."""
    vendor, floor = settings.vendor(spec.section), interval(spec, settings)
    ceiling = (
        vendor.max_interval_s if vendor.max_interval_s is not None else DEFAULT_CEILING * floor
    )
    try:
        return Pacing(
            min_interval_s=floor,
            max_interval_s=ceiling,
            start_interval_s=vendor.start_interval_s,
            backoff_factor=settings.http_backoff_factor,
            speedup_factor=settings.http_speedup_factor,
            speedup_after=settings.http_speedup_after,
            error_window=settings.http_error_window,
            max_error_rate=settings.http_max_error_rate,
        )
    except ValueError as exc:
        raise ConfigurationError(f"sources.toml [{spec.section}]: {exc}") from exc


def build_sources(
    settings: RegistrySettings,
    env: Env,
    names: Iterable[str] | None = None,
    limits_dir: Path | None = None,
    fixture_dir: Path | None = None,
) -> Built:
    """Build the named sources (default: every vendor source, HTTP and session); a named
    fixture source reads ``fixture_dir``. Unknown names raise ``KeyError``."""
    wanted = list(dict.fromkeys([*SOURCES, *SESSION_SOURCES] if names is None else names))
    directory = limits_dir or Path(settings.limits_dir)
    breakers: dict[str, CircuitBreaker] = {}
    built = Built()
    limiters = built.limiters

    def limiter(key: str, pace: Pacing | float) -> Limiter:
        if key not in limiters:
            limiters[key] = Limiter(key, pace, directory)
        return limiters[key]

    for name in wanted:
        if name in FIXTURES:
            built.sources[name] = fixture_source(name, fixture_dir)
            continue
        if name in SESSION_SOURCES:
            session = SESSION_SOURCES[name]
            reason = unavailable(session, settings, env)
            if reason is not None:
                built.skipped[name] = reason
                continue
            inputs = SessionInputs(settings, env, limiter, interval(session, settings))
            built.sources[name] = session.build(inputs)
            continue
        spec = SOURCES[name]
        reason = unavailable(spec, settings, env)
        if reason is not None:
            built.skipped[name] = reason
            continue
        key = spec.limiter
        if key not in breakers:
            limiter(key, pacing(spec, settings))
            breakers[key] = CircuitBreaker(key, settings.http_breaker_failures)
        secret = env(spec.env_var) if spec.env_var else None
        http = Http(
            urllib_transport(headers=spec.headers(secret)),
            RetryPolicy(
                tries=spec.tries,
                max_total_s=settings.http_max_retry_s,
                not_found=spec.not_found,
            ),
            limiters[key],
            breakers[key],
        )
        built.sources[name] = spec.build(http)
    return built


def raw_source(spec: SourceSpec) -> str:
    """The name ``spec``'s source stores raw responses under: its class's ``name``
    (``raw/source=<name>/...``), which several specs may share (the SEC sources)."""
    name = getattr(spec.build, "name", None)
    if not isinstance(name, str):
        raise TypeError(f"source {spec.name!r}: its class declares no raw source name")
    return name


def raw_sections(
    specs: Mapping[str, SourceSpec] = SOURCES,
    sessions: Mapping[str, SessionSpec] = SESSION_SOURCES,
) -> dict[str, str]:
    """raw source name -> the sources.toml section its specs read (one each, by design;
    ``raw_retention_days`` there sets how long its raw responses are kept)."""
    out: dict[str, str] = {}
    pairs = [(raw_source(spec), spec.section) for spec in specs.values()]
    pairs += [(str(getattr(s.kind, "name", "")), s.section) for s in sessions.values()]
    for name, section in pairs:
        if out.setdefault(name, section) != section:
            raise ValueError(f"raw source {name!r} is in sections {out[name]} and {section}")
    return out


# Fixed at import from the declared source classes (tests that swap a spec's ``build`` for a
# fake do not change where the real source stores its raw responses).
RAW_SECTIONS: Mapping[str, str] = raw_sections()


def limiter_keys(
    specs: Mapping[str, SourceSpec] = SOURCES,
    sessions: Mapping[str, SessionSpec] = SESSION_SOURCES,
) -> dict[str, set[str]]:
    """limiter key -> the sources.toml sections its sources read (one each, by design)."""
    out: dict[str, set[str]] = {}
    pairs = [(spec.limiter, spec.section) for spec in specs.values()]
    for session in sessions.values():
        pairs += [(key, session.section) for key in (session.limiter, *session.more_limiters)]
    for key, section in pairs:
        out.setdefault(key, set()).add(section)
    return out


def build_text_model(
    base_url: str, model: str, timeout_s: float, max_tokens: int, credential: str | None
) -> ChatCompletions:
    """The text model behind screener drafts (ADR 0040): an OpenAI-compatible chat client at
    ``base_url`` for ``model``, the credential (``$ALGOTRADE_LLM_API_KEY``; a local server
    needs none) as a bearer header, never in the URL. Built here, like every vendor client,
    so the API imports only the registry."""
    headers = {"Authorization": f"Bearer {credential}"} if credential else {}
    transport = json_post_transport(timeout=timeout_s, headers=headers)
    return ChatCompletions(base_url, model, transport, max_tokens)
