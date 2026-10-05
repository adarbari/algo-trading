"""Typed L3 site settings: every ``config/site/*.toml`` is loaded and validated HERE only.

ADR 0019 ``site-settings``. Each file becomes a frozen dataclass that apps receive as is:

    sources.toml   -> SourcesSettings   (vendors, [http], [quality], retention; [ibkr])
    verification.toml -> VerificationSettings (live verification vs IBKR)
    universe.toml  -> UniverseSettings  (+ overrides/leveraged_etfs.csv, overrides/figi.csv)
    nightly.toml   -> NightlySettings
    rollups.toml   -> each rollup's params dataclass (declared by the rollup, typed here)
    features/<theme>.toml -> FeatureDefinition per expression feature (ADR 0023 step 3)
    users/<id>/features/<theme>.toml -> the same, owned by a user (always virtual; step 4)
    defaults.toml  -> ScreeningSettings, BacktestSettings (layered per config by ``resolve``)

Documents come from the config store, so this module does no I/O: ``load_*`` take anything
with ``load(scope, kind, name)`` (a ``ConfigStore``). A missing file or key falls back to the
defaults below; an unknown key, a wrong type or an out-of-range value fails with its path,
e.g. ``sources.toml [massive] min_interval_s: expected a number >= 0, got 'fast'``. The
types live in the library (not the app that reads them) so the one loader can check every key.
"""

import dataclasses
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field, replace
from typing import Any, Protocol

from algotrade.config.site.fields import Table, reject_secrets
from algotrade.config.user import SITE_USER
from algotrade.core.model.errors import ConfigurationError

type DocumentLoader = Callable[[str, str, str], Mapping[str, Any] | None]

# Leverage rules (docs/data/instruments.md "Flagging leveraged and inverse ETFs"); every
# pattern is matched case-insensitively against the security name. A leveraged / inverse ETF
# always says so in its name: absence of these markers is what lets a plain ETF be marked not
# leveraged; presence without a curated override, a parsed leverage or an exclusion means UNKNOWN.
DEFAULT_LEVERAGE_MARKERS = (
    r"\b-?\d(\.\d)?x\b",
    r"\bultra",
    r"\bbull\b",
    r"\bbear\b",
    r"\binverse\b",
    r"\bshort\b",
    r"\bleveraged\b",
    r"\bdaily\b",
)
# Fund-family naming conventions with a fixed leverage; the first match wins.
DEFAULT_LEVERAGE_CONVENTIONS: tuple[tuple[str, float], ...] = (
    (r"^(ProShares\s+)?UltraPro\s+Short\b", -3.0),
    (r"^(ProShares\s+)?UltraPro\b", 3.0),
    (r"^ProShares\s+UltraShort\b", -2.0),
    (r"^ProShares\s+Ultra\b", 2.0),
    (r"^ProShares\s+Short\b", -1.0),
)
# A stated multiple: group ``n`` is the number; the sign comes from a minus or an inverse marker.
_N = r"(?<![\w.])(?P<n>-?\d(?:\.\d+)?)"
_WORDS = r"(long|short|bull|bear|inverse|leveraged|daily|target)"
DEFAULT_LEVERAGE_PATTERNS = (
    rf"{_N}x\s+{_WORDS}\b",  # "2X Short", "3x Leveraged", "2x Daily"
    rf"\b{_WORDS}\s+{_N}x\b",  # "Bull 3X", "Daily 2X", "Daily Target 2X"
    rf"^{_N}x\s",  # "2x Bitcoin ETF"
    rf"{_N}x\s+ET[FN]s?$",  # "XRP 2X ETF"
    rf"{_N}\s+(inverse\s+)?leveraged\b",  # "-3 Inverse Leveraged ETNs"
)
DEFAULT_INVERSE_MARKERS = (r"\bshort\b", r"\bbear\b", r"\binverse\b")
# Phrases that use a marker word without meaning leverage. They are blanked out before the
# markers are checked again: a name with no marker left is unleveraged, one with a marker left
# (e.g. "Inverse VIX Short-Term Futures") still needs review.
DEFAULT_LEVERAGE_EXCLUSIONS = (
    r"\b(ultra[- ]?)?short[- ](term|duration|maturity|horizon)\b",
    r"\bultra[- ]?short\s+(bond|income|treasury|t-bill|muni\w*|fixed|government|investment|tax)",
    r"\bshort\s+(muni\w*|high yield muni|bond|treasury)",
    r"\b(ultra\s+)?buffer\b",
    r"\b(daily\s+)?putwrite\b",
    r"\b(ultra\s+)?option income\b",
    r"\bcovered call\b",
    r"\bpremium income\b",
    r"\bdaily income\b",
    r"\blong[/ -]short\b",
    r"\bleveraged loans?\b",
    r"\bultra dividend\b",
    r"\bultra[- ]small\b",
)
UNIVERSE_SOURCES = ("nasdaq_trader", "csv_import")
# A composite FIGI: 12 characters, the third always "G" (e.g. BBG000B9XRY4).
FIGI = re.compile(r"^[A-Z]{2}G[A-Z0-9]{9}$")
FIGI_OVERRIDE_COLUMNS = ("symbol", "figi", "note")
PRICE_ADJUSTMENTS = ("none", "splits", "total_return")
# ``[backtest] rebalance_selection``: never, the first session of each month / ISO week, or
# every N sessions (``"21d"``). Interpreted by ``engines.selection.schedule``.
REBALANCE_SELECTION = re.compile(r"^(none|monthly|weekly|[1-9][0-9]*d)$")
# Per-vendor keys beyond ``enabled`` / ``min_interval_s`` (sections are config keys; the
# vendor code that reads them stays in libs/sources/algotrade_sources).
VENDOR_KEYS = (
    "enabled",
    "min_interval_s",
    "max_interval_s",
    "start_interval_s",
    "raw_retention_days",
)
# Sections whose sources pace at a fixed min_interval_s (session sources, e.g. IB Gateway:
# no HTTP responses to adapt to), so the adaptive keys are not accepted there.
FIXED_PACE = ("ibkr",)
ADAPTIVE_KEYS = ("max_interval_s", "start_interval_s")
VENDOR_EXTRAS = {
    "cboe": ("workers", "priority_symbols"),
    "nasdaq_earnings": ("days", "lookback_days"),
    "massive": ("corporate_actions_window", "descriptions_per_night", "descriptions_refresh_days"),
    "sec_edgar": ("refresh_days", "facts_refresh_days", "fund_quarters"),
    "treasury": ("lookback_days",),
    "ibkr": (
        "historical_min_interval_s",
        "market_data_type",
        "connect_timeout_s",
        "request_timeout_s",
        "stream_wait_s",
        "contracts_refresh_days",
        "contracts_batch",
        "iv_batch",
        "iv_history_days",
        "iv_backfill_per_night",
        *("live_cache_s", "live_strikes", "live_max_strikes", "live_timeout_s", "live_retry_s"),
    ),
}
# Vendors that stay off unless their section says ``enabled = true`` (a missing section or key
# means disabled): IBKR needs the owner's gateway, set up read-only (ADR 0026).
OFF_BY_DEFAULT = ("ibkr",)
# IB market data types: 1 live (needs a subscription), 3 delayed (free, 15-20 minutes).
IBKR_MARKET_DATA_TYPES = (1, 2, 3, 4)


class SiteDocuments(Protocol):
    """What the loader needs from a config store (``storage.configs.store.ConfigStore``)."""

    def load(self, scope: str, kind: str, name: str) -> Mapping[str, Any] | None: ...

    def names(self, scope: str, kind: str) -> list[str]: ...

    def overrides(self, name: str) -> list[dict[str, str]]: ...


# ----------------------------------------------------------------------------- sources.toml


@dataclass(frozen=True)
class VendorSettings:
    """One vendor section of ``sources.toml``: on/off, its pacing and how long its raw
    responses are kept (``None``: the global ``raw_retention_days``).

    Pacing (sources/framework/limiter.py): ``min_interval_s`` is the floor, the fastest the
    adaptive limiter ever goes (``None``: the registry's default for that source);
    ``max_interval_s`` the ceiling it backs off to (``None``: 4 x the floor);
    ``start_interval_s`` where each run starts (``None``: the floor)."""

    enabled: bool = True
    min_interval_s: float | None = None
    max_interval_s: float | None = None
    start_interval_s: float | None = None
    raw_retention_days: int | None = None


@dataclass(frozen=True)
class IbkrSettings:
    """``[ibkr]`` beyond ``enabled`` / ``min_interval_s`` (the IB Gateway session; host, port
    and client id come from the environment, ``config/env.py``). Pacing follows IBKR's rules:
    every message waits ``min_interval_s`` (50 messages/s), every historical-data request also
    waits ``historical_min_interval_s`` (60 requests per 10 minutes, and >= 10 s between
    identical requests)."""

    historical_min_interval_s: float = 10.0
    market_data_type: int = 3  # 1 live, 3 delayed
    connect_timeout_s: float = 10.0
    request_timeout_s: float = 60.0
    stream_wait_s: float = 4.0  # how long a streamed tick (dividends) may take to arrive
    # IBKR enrichment (ADR 0028): contract ids, IB's IV history and the nightly IV snapshot
    contracts_refresh_days: int = 30  # re-resolve each conid once per window (spread by key)
    contracts_batch: int = 25  # contracts qualified per request
    iv_batch: int = 50  # IV streams open together (under the account's market-data lines)
    iv_history_days: int = 730  # calendar days of IV history a backfill fetches per underlying
    iv_backfill_per_night: int = 100  # underlyings without IV history the nightly backfills
    # The API's live option quotes (ADR 0028): cache, strikes per request, failing fast
    live_cache_s: float = (
        60.0  # an answer is reused for this long (per underlying, expiry, strikes)
    )
    live_strikes: int = 10  # strikes nearest the underlying asked for when none are named
    live_max_strikes: int = 20  # most strikes one request may name (x 2 rights = contracts)
    live_timeout_s: float = 20.0  # longest a request waits for IB Gateway before the fallback
    live_retry_s: float = 30.0  # after the gateway fails, requests fall back at once this long


@dataclass(frozen=True)
class SourcesSettings:
    raw_retention_days: int = 90
    staging_retention_days: int = 14
    live_retention_days: int = 7  # live/option_quotes partitions older than this are purged
    vendors: Mapping[str, VendorSettings] = field(default_factory=dict)  # by section name
    cboe_workers: int = 4
    cboe_priority_symbols: tuple[str, ...] = ()  # fetched first (with S&P 500 members)
    earnings_days: int = 60
    earnings_lookback_days: int = 7
    actions_window: tuple[int, int] = (-7, 30)
    sec_refresh_days: int = 30
    sec_facts_refresh_days: int = 30
    sec_fund_quarters: int = 6  # SEC prospectus data sets read for ETF descriptions (ADR 0034)
    descriptions_per_night: int = 100  # Massive ticker overviews the nightly requests (0: none)
    descriptions_refresh_days: int = 365  # refetch a stock's description after this many days
    treasury_lookback_days: int = 10
    http_max_retry_s: float = 300.0
    http_breaker_failures: int = 10
    limits_dir: str = "var/run/limits"
    # Adaptive pacing, every vendor (sources/framework/limiter.py ``Pacing``)
    http_backoff_factor: float = 1.5
    http_speedup_factor: float = 1.05
    http_speedup_after: int = 100
    http_error_window: int = 50
    http_max_error_rate: float = 0.10
    max_bar_count_drop: float = 0.10
    max_universe_change: float = 0.05
    max_chain_fetch_failures: float = 0.05
    max_chain_stale_share: float = 0.20
    max_verify_failures: float = 0.10
    ibkr: IbkrSettings = IbkrSettings()

    def vendor(self, section: str) -> VendorSettings:
        """``[section]`` of sources.toml (defaults when the section is missing)."""
        return self.vendors.get(section, VendorSettings(enabled=section not in OFF_BY_DEFAULT))

    @classmethod
    def from_document(
        cls, doc: Mapping[str, Any] | None, where: str = "sources.toml"
    ) -> "SourcesSettings":
        d = cls()
        root = Table(doc, where)
        sections = [k for k in root.names() if isinstance(root.raw(k), Mapping)]
        root.only(
            ["raw_retention_days", "staging_retention_days", "live_retention_days", *sections]
        )
        http = root.table(
            "http",
            [
                "max_retry_s",
                "breaker_failures",
                "limits_dir",
                "backoff_factor",
                "speedup_factor",
                "speedup_after",
                "error_window",
                "max_error_rate",
            ],
        )
        quality = root.table(
            "quality",
            [
                "max_bar_count_drop",
                "max_universe_change",
                "max_chain_fetch_failures",
                "max_chain_stale_share",
                "max_verify_failures",
            ],
        )
        vendors = {
            name: root.table(name, [*_vendor_keys(name), *VENDOR_EXTRAS.get(name, ())])
            for name in sections
            if name not in ("http", "quality")
        }
        window = vendors.get("massive", Table(None, f"{where} [massive]")).integers(
            "corporate_actions_window", d.actions_window, length=2
        )
        return cls(
            raw_retention_days=root.integer("raw_retention_days", d.raw_retention_days, 1),
            staging_retention_days=root.integer(
                "staging_retention_days", d.staging_retention_days, 1
            ),
            live_retention_days=root.integer("live_retention_days", d.live_retention_days, 1),
            vendors={name: _vendor(t, name not in OFF_BY_DEFAULT) for name, t in vendors.items()},
            cboe_workers=_extra(vendors, "cboe").integer("workers", d.cboe_workers, 1),
            cboe_priority_symbols=tuple(
                s.upper() for s in _extra(vendors, "cboe").strings("priority_symbols", ())
            ),
            earnings_days=_extra(vendors, "nasdaq_earnings").integer("days", d.earnings_days, 1),
            earnings_lookback_days=_extra(vendors, "nasdaq_earnings").integer(
                "lookback_days", d.earnings_lookback_days, 0
            ),
            actions_window=(window[0], window[1]),
            sec_refresh_days=_extra(vendors, "sec_edgar").integer(
                "refresh_days", d.sec_refresh_days, 0
            ),
            sec_facts_refresh_days=_extra(vendors, "sec_edgar").integer(
                "facts_refresh_days", d.sec_facts_refresh_days, 0
            ),
            sec_fund_quarters=_extra(vendors, "sec_edgar").integer(
                "fund_quarters", d.sec_fund_quarters, 0
            ),
            descriptions_per_night=_extra(vendors, "massive").integer(
                "descriptions_per_night", d.descriptions_per_night, 0
            ),
            descriptions_refresh_days=_extra(vendors, "massive").integer(
                "descriptions_refresh_days", d.descriptions_refresh_days, 0
            ),
            treasury_lookback_days=_extra(vendors, "treasury").integer(
                "lookback_days", d.treasury_lookback_days, 1
            ),
            http_max_retry_s=http.number("max_retry_s", d.http_max_retry_s, 0),
            http_breaker_failures=http.integer("breaker_failures", d.http_breaker_failures, 1),
            limits_dir=http.text("limits_dir", d.limits_dir),
            http_backoff_factor=http.number("backoff_factor", d.http_backoff_factor, 1),
            http_speedup_factor=http.number("speedup_factor", d.http_speedup_factor, 1),
            http_speedup_after=http.integer("speedup_after", d.http_speedup_after, 1),
            http_error_window=http.integer("error_window", d.http_error_window, 1),
            http_max_error_rate=http.fraction("max_error_rate", d.http_max_error_rate),
            max_bar_count_drop=quality.fraction("max_bar_count_drop", d.max_bar_count_drop),
            max_universe_change=quality.fraction("max_universe_change", d.max_universe_change),
            max_chain_fetch_failures=quality.fraction(
                "max_chain_fetch_failures", d.max_chain_fetch_failures
            ),
            max_chain_stale_share=quality.fraction(
                "max_chain_stale_share", d.max_chain_stale_share
            ),
            max_verify_failures=quality.fraction("max_verify_failures", d.max_verify_failures),
            ibkr=_ibkr(_extra(vendors, "ibkr")),
        )


def _ibkr(section: Table) -> IbkrSettings:
    d = IbkrSettings()
    kind = section.integer("market_data_type", d.market_data_type, 1)
    if kind not in IBKR_MARKET_DATA_TYPES:
        raise ConfigurationError(
            f"{section.where} market_data_type: expected 1 (live), 2 (frozen), 3 (delayed) "
            f"or 4 (delayed frozen), got {kind}"
        )
    return IbkrSettings(
        historical_min_interval_s=section.number(
            "historical_min_interval_s", d.historical_min_interval_s, 0
        ),
        market_data_type=kind,
        connect_timeout_s=section.number("connect_timeout_s", d.connect_timeout_s, 0),
        request_timeout_s=section.number("request_timeout_s", d.request_timeout_s, 0),
        stream_wait_s=section.number("stream_wait_s", d.stream_wait_s, 0),
        contracts_refresh_days=section.integer(
            "contracts_refresh_days", d.contracts_refresh_days, 0
        ),
        contracts_batch=section.integer("contracts_batch", d.contracts_batch, 1),
        iv_batch=section.integer("iv_batch", d.iv_batch, 1),
        iv_history_days=section.integer("iv_history_days", d.iv_history_days, 1),
        iv_backfill_per_night=section.integer("iv_backfill_per_night", d.iv_backfill_per_night, 0),
        live_cache_s=section.number("live_cache_s", d.live_cache_s, 0),
        live_strikes=section.integer("live_strikes", d.live_strikes, 1),
        live_max_strikes=section.integer("live_max_strikes", d.live_max_strikes, 1),
        live_timeout_s=section.number("live_timeout_s", d.live_timeout_s, 0),
        live_retry_s=section.number("live_retry_s", d.live_retry_s, 0),
    )


def _vendor_keys(section: str) -> tuple[str, ...]:
    if section in FIXED_PACE:
        return tuple(k for k in VENDOR_KEYS if k not in ADAPTIVE_KEYS)
    return VENDOR_KEYS


def _vendor(section: Table, enabled: bool = True) -> VendorSettings:
    floor = section.number("min_interval_s", None, 0)
    ceiling = section.number("max_interval_s", None, 0)
    start = section.number("start_interval_s", None, 0)
    if floor is not None and ceiling is not None and ceiling < floor:
        raise ConfigurationError(
            f"{section.where} max_interval_s: expected >= min_interval_s ({floor}), got {ceiling}"
        )
    if start is not None and (
        (floor is not None and start < floor) or (ceiling is not None and start > ceiling)
    ):
        raise ConfigurationError(
            f"{section.where} start_interval_s: expected between min_interval_s and "
            f"max_interval_s, got {start}"
        )
    return VendorSettings(
        enabled=section.boolean("enabled", enabled),
        min_interval_s=floor,
        max_interval_s=ceiling,
        start_interval_s=start,
        raw_retention_days=_optional_integer(section, "raw_retention_days", 1),
    )


def _optional_integer(section: Table, key: str, minimum: int) -> int | None:
    """``key`` as an integer >= ``minimum``, or ``None`` when the section does not set it."""
    return None if section.raw(key) is None else section.integer(key, minimum, minimum)


def _extra(vendors: Mapping[str, Table], name: str) -> Table:
    return vendors.get(name) or Table(None, name)


# ----------------------------------------------------------------------------- nightly.toml


@dataclass(frozen=True)
class NightlySettings:
    """``config/site/nightly.toml``: sessions, catch-up, the duration alert, notification."""

    settle_minutes: int = 30
    max_catch_up: int = 5
    max_duration_minutes: float = 40.0
    notify_enabled: bool = True
    notify_desktop: bool = True
    summary_path: str = "var/logs/nightly-latest.json"
    # [notify.email]: the daily summary email (addresses + credentials: config/env.py only)
    email_enabled: bool = False
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    email_max_examples: int = 5

    @classmethod
    def from_document(
        cls, doc: Mapping[str, Any] | None, where: str = "nightly.toml"
    ) -> "NightlySettings":
        d = cls()
        root = Table(doc, where)
        root.only(["sessions", "alerts", "notify"])
        sessions = root.table("sessions", ["settle_minutes", "max_catch_up"])
        alerts = root.table("alerts", ["max_duration_minutes"])
        notify = root.table("notify", ["enabled", "desktop", "summary_path", "email"])
        email = notify.table("email", ["enabled", "smtp_host", "smtp_port", "max_examples"])
        return cls(
            settle_minutes=sessions.integer("settle_minutes", d.settle_minutes, 0),
            max_catch_up=sessions.integer("max_catch_up", d.max_catch_up, 1),
            max_duration_minutes=alerts.number("max_duration_minutes", d.max_duration_minutes, 0),
            notify_enabled=notify.boolean("enabled", d.notify_enabled),
            notify_desktop=notify.boolean("desktop", d.notify_desktop),
            summary_path=notify.text("summary_path", d.summary_path),
            email_enabled=email.boolean("enabled", d.email_enabled),
            smtp_host=email.text("smtp_host", d.smtp_host),
            smtp_port=email.integer("smtp_port", d.smtp_port, 1),
            email_max_examples=email.integer("max_examples", d.email_max_examples, 0),
        )


# ----------------------------------------------------------------------------- verification.toml

DEFAULT_CORE = ("AAPL", "SPY", "QQQ", "IWM", "KO", "TQQQ", "TSM", "NVO", "JNJ", "RPGL")


@dataclass(frozen=True)
class VerificationSettings:
    """``config/site/verification.toml``: the nightly live verification against IBKR (which
    instruments, how many rotating, the tolerances of each check). Defaults reuse the
    reconciliation suite's tolerances (``docs/testing.md``)."""

    core_symbols: tuple[str, ...] = DEFAULT_CORE
    rotating: int = 10  # extra instruments per session, chosen by a hash of the session
    option_symbols: tuple[str, ...] = ("AAPL", "SPY")  # names whose option quotes are checked
    options_per_symbol: int = 2
    bar_sessions: int = 260  # IBKR daily bars requested (one year + the HV window)
    close_rel: float = 0.002  # split-adjusted closes
    range_rel: float = 0.005  # daily highs / lows (IBKR bars use a narrower trade set: ~0.3% wicks)
    hv_rel: float = 0.005  # hv20 vs close-to-close HV20 on IBKR closes
    high_52w_rel: float = 0.0005
    extreme_rel: float = 0.0005  # slack on the dividend-gap rule (52-week low)
    yield_abs: float = 0.0005  # dividend yield, decimal
    iv_abs: float = 0.025  # implied vol, decimal (2.5 vol points)
    spread_band: float = 1.0  # option mids may differ by this many half-spreads
    max_missing_sessions: int = 0  # IBKR sessions in the window without our bar
    warn_multiple: float = 2.0  # over tolerance but within this multiple: WARN, beyond: FAIL

    @classmethod
    def from_document(
        cls, doc: Mapping[str, Any] | None, where: str = "verification.toml"
    ) -> "VerificationSettings":
        d = cls()
        root = Table(doc, where)
        root.only(["sample", "tolerances"])
        sample = root.table(
            "sample",
            ["core_symbols", "rotating", "option_symbols", "options_per_symbol", "bar_sessions"],
        )
        tol = root.table(
            "tolerances",
            [
                "close_rel",
                "range_rel",
                "hv_rel",
                "high_52w_rel",
                "extreme_rel",
                "yield_abs",
                "iv_abs",
                "spread_band",
                "max_missing_sessions",
                "warn_multiple",
            ],
        )
        warn = tol.number("warn_multiple", d.warn_multiple, 1)
        return cls(
            core_symbols=tuple(s.upper() for s in sample.strings("core_symbols", d.core_symbols)),
            rotating=sample.integer("rotating", d.rotating, 0),
            option_symbols=tuple(
                s.upper() for s in sample.strings("option_symbols", d.option_symbols)
            ),
            options_per_symbol=sample.integer("options_per_symbol", d.options_per_symbol, 0),
            bar_sessions=sample.integer("bar_sessions", d.bar_sessions, 30),
            close_rel=tol.number("close_rel", d.close_rel, 0),
            range_rel=tol.number("range_rel", d.range_rel, 0),
            hv_rel=tol.number("hv_rel", d.hv_rel, 0),
            high_52w_rel=tol.number("high_52w_rel", d.high_52w_rel, 0),
            extreme_rel=tol.number("extreme_rel", d.extreme_rel, 0),
            yield_abs=tol.number("yield_abs", d.yield_abs, 0),
            iv_abs=tol.number("iv_abs", d.iv_abs, 0),
            spread_band=tol.number("spread_band", d.spread_band, 0),
            max_missing_sessions=tol.integer("max_missing_sessions", d.max_missing_sessions, 0),
            warn_multiple=warn,
        )


# ----------------------------------------------------------------------------- rollups.toml
_SCALARS = (bool, int, float, str)


def rollup_params(
    doc: Mapping[str, Any] | None, declared: Mapping[str, Any | None], where: str = "rollups.toml"
) -> dict[str, Any | None]:
    """``rollups.toml``: one ``["<name>@v<N>"]`` section per rollup with parameters.

    ``declared`` maps each rollup to its params dataclass instance holding the defaults
    (``None``: the rollup takes no parameters, so a section for it is an error). Each scalar
    field (bool, int, float, str) is a key typed by its default; other fields (e.g. tier
    tables) are fixed by the definition. A params ``__post_init__`` that raises ``ValueError``
    fails with the section's path."""
    root = Table(doc, where)
    root.only([k for k, v in declared.items() if v is not None])
    out: dict[str, Any | None] = {}
    for key, defaults in declared.items():
        if defaults is None:
            out[key] = None
            continue
        keys = [
            f.name
            for f in dataclasses.fields(defaults)
            if type(getattr(defaults, f.name)) in _SCALARS
        ]
        section = root.table(key, keys)
        values = {name: _typed(section, name, getattr(defaults, name)) for name in keys}
        try:
            out[key] = dataclasses.replace(defaults, **values)
        except ValueError as exc:
            raise ConfigurationError(f"{section.where}: {exc}") from exc
    return out


def _typed(section: Table, key: str, default: Any) -> Any:
    if isinstance(default, bool):
        return section.boolean(key, default)
    if isinstance(default, int):
        return section.integer(key, default, 0)
    if isinstance(default, float):
        return section.number(key, default)
    return section.text(key, default)


# ----------------------------------------------------------------------------- features/*.toml
FEATURE_KEYS = (
    "expr",
    "dtype",
    "unit",
    "description",
    "null_meaning",
    "kind",
    "valid_range",
    "categories",
    "materialise",
    "version",
    "params",
)
FEATURE_KINDS = ("expression", "label")
_FEATURE_TEXT = ("expr", "dtype", "unit", "description", "null_meaning")  # required
type ParamValue = float | str | bool


@dataclass(frozen=True)
class FeatureDefinition:
    """One ``[<name>]`` section of ``config/site/features/<theme>.toml``: an expression feature.

    ``expr`` is a formula over stored features (``group.column``), other expression features
    (by name) and ``params`` (named constants, by name); ``algotrade.features.expressions``
    parses, type checks and evaluates it. ``valid_range`` is ``[min, max]`` (``inf`` / ``-inf``:
    open); ``materialise`` stores it as ``rollups/instrument/<name>@v<version>`` (otherwise it
    is computed on read). The structure is typed here; the formula, dtype and unit are checked
    against the feature catalogue when the features are built.

    ``owner``: ``None`` for a site feature, else the user whose
    ``config/users/<owner>/features/<theme>.toml`` declares it (a user feature is never
    materialised)."""

    name: str
    theme: str
    expr: str
    dtype: str
    unit: str
    description: str
    null_meaning: str
    kind: str = "expression"
    valid_range: tuple[float | None, float | None] | None = None
    categories: tuple[str, ...] = ()
    materialise: bool = False
    version: int = 1
    params: Mapping[str, ParamValue] = field(default_factory=dict)
    owner: str | None = None

    @property
    def scope(self) -> str:
        """``site`` or ``user``."""
        return "site" if self.owner is None else "user"

    @property
    def where(self) -> str:
        return f"{features_dir(self.owner)}/{self.theme}.toml [{self.name}]"

    def canonical(self) -> dict[str, Any]:
        """What changes its values (for a config hash): formula, params, type and version."""
        return {
            "expr": " ".join(self.expr.split()),
            "params": dict(sorted(self.params.items())),
            "dtype": self.dtype,
            "kind": self.kind,
            "categories": list(self.categories),
            "version": self.version,
        }


def features_dir(owner: str | None) -> str:
    """Where a scope's expression features live (``config/site/features``,
    ``config/users/<owner>/features``)."""
    return "config/site/features" if owner is None else f"config/users/{owner}/features"


def _bound(value: Any) -> float | None:
    return None if value in (float("inf"), float("-inf")) else float(value)


def _valid_range(t: Table) -> tuple[float | None, float | None] | None:
    value = t.raw("valid_range")
    if value is None:
        return None
    numeric = all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in value)
    if not isinstance(value, list) or len(value) != 2 or not numeric:
        raise ConfigurationError(
            f"{t.where} valid_range: expected [min, max] (inf: open), got {value!r}"
        )
    return (_bound(value[0]), _bound(value[1]))


def _params(t: Table) -> dict[str, ParamValue]:
    value = t.raw("params")
    if value is None:
        return {}
    if not isinstance(value, Mapping) or not all(isinstance(v, _SCALARS) for v in value.values()):
        raise ConfigurationError(f"{t.where} params: expected a table of numbers, strings or bools")
    return dict(value)


def feature_definitions(
    docs: Mapping[str, Mapping[str, Any] | None], owner: str | None = None
) -> tuple[FeatureDefinition, ...]:
    """Every ``[<name>]`` of every ``features/<theme>.toml`` document, in file then key order.
    ``owner``: the user the documents belong to (``None``: the site). A user's documents may
    not hold secrets or ``materialise`` (user features are always computed on read)."""
    out = []
    for theme, doc in sorted(docs.items()):
        root = Table(doc, f"{features_dir(owner)}/{theme}.toml")
        if owner is not None and doc is not None:
            reject_secrets(doc, root.where)
        for name in root.names():
            t = root.table(name, FEATURE_KEYS)
            if owner is not None and t.raw("materialise") is not None:
                raise ConfigurationError(
                    f"{t.where} materialise: a user feature is always virtual (computed on "
                    "read); ask for a site feature to store it"
                )
            d = FeatureDefinition(name, theme, "", "", "", "", "", owner=owner)
            text = {
                k: t.text(k, "") for k in ("expr", "dtype", "unit", "description", "null_meaning")
            }
            missing = [k for k, v in text.items() if not v]
            if missing:
                raise ConfigurationError(f"{t.where}: missing {missing}")
            out.append(
                replace(
                    d,
                    **text,
                    kind=t.choice("kind", d.kind, FEATURE_KINDS),
                    valid_range=_valid_range(t),
                    categories=t.strings("categories", d.categories),
                    materialise=t.boolean("materialise", d.materialise),
                    version=t.integer("version", d.version, 1),
                    params=_params(t),
                )
            )
    return tuple(out)


# ----------------------------------------------------------------------------- universe.toml


@dataclass(frozen=True)
class UniverseSettings:
    """``config/site/universe.toml`` (coverage) + the curated ``overrides/leveraged_etfs.csv``
    + the owner's ``overrides/figi.csv`` (``figi_overrides``: symbol -> the FIGI its id must
    use, ``None`` for "no FIGI, symbol id"; ADR 0018).
    ``source``: "nasdaq_trader" (built nightly) or "csv_import" (also when the file is missing).
    """

    source: str = "csv_import"
    security_types: tuple[str, ...] = ("COMMON_STOCK", "ADR", "ETF")
    exclude_test_issues: bool = True
    include_symbols: frozenset[str] = frozenset()
    exclude_symbols: frozenset[str] = frozenset()
    leverage_markers: tuple[str, ...] = DEFAULT_LEVERAGE_MARKERS
    leverage_conventions: tuple[tuple[str, float], ...] = DEFAULT_LEVERAGE_CONVENTIONS
    leverage_patterns: tuple[str, ...] = DEFAULT_LEVERAGE_PATTERNS
    inverse_markers: tuple[str, ...] = DEFAULT_INVERSE_MARKERS
    leverage_exclusions: tuple[str, ...] = DEFAULT_LEVERAGE_EXCLUSIONS
    overrides: tuple[Mapping[str, str], ...] = field(default=())
    figi_overrides: Mapping[str, str | None] = field(default_factory=dict)

    @classmethod
    def from_documents(
        cls,
        doc: Mapping[str, Any] | None,
        overrides: Iterable[Mapping[str, str]] = (),
        where: str = "universe.toml",
        figi_overrides: Iterable[Mapping[str, str]] = (),
    ) -> "UniverseSettings":
        d = cls()
        root = Table(doc, where)
        root.only(
            [
                "source",
                "security_types",
                "exclude_test_issues",
                "include_symbols",
                "exclude_symbols",
                "leverage_markers",
                "leverage_conventions",
                "leverage_patterns",
                "inverse_markers",
                "leverage_exclusions",
            ]
        )
        patterns = _regexes(root, "leverage_patterns", d.leverage_patterns)
        for i, pattern in enumerate(patterns):
            if "n" not in re.compile(pattern).groupindex:
                raise ConfigurationError(
                    f"{where} leverage_patterns[{i}]: needs a named group (?P<n>...)"
                )
        return cls(
            source=root.choice("source", d.source, UNIVERSE_SOURCES),
            security_types=root.strings("security_types", d.security_types),
            exclude_test_issues=root.boolean("exclude_test_issues", d.exclude_test_issues),
            include_symbols=frozenset(s.upper() for s in root.strings("include_symbols", ())),
            exclude_symbols=frozenset(s.upper() for s in root.strings("exclude_symbols", ())),
            leverage_markers=_regexes(root, "leverage_markers", d.leverage_markers),
            leverage_conventions=_conventions(root, d.leverage_conventions),
            leverage_patterns=patterns,
            inverse_markers=_regexes(root, "inverse_markers", d.inverse_markers),
            leverage_exclusions=_regexes(root, "leverage_exclusions", d.leverage_exclusions),
            overrides=tuple(overrides),
            figi_overrides=_figi_overrides(figi_overrides),
        )


def _figi_overrides(rows: Iterable[Mapping[str, str]]) -> dict[str, str | None]:
    """``overrides/figi.csv`` rows (symbol, figi, note) -> symbol -> FIGI (blank: ``None``).
    Fails on an unknown column, a malformed FIGI, or a symbol or FIGI listed twice."""
    where = "overrides/figi.csv"
    out: dict[str, str | None] = {}
    for n, row in enumerate(rows, start=2):  # line 1 is the header
        unknown = sorted(str(k) for k in set(row) - set(FIGI_OVERRIDE_COLUMNS))
        if unknown:
            raise ConfigurationError(
                f"{where} line {n}: unknown column(s) {unknown}; "
                f"expected {list(FIGI_OVERRIDE_COLUMNS)}"
            )
        symbol = (row.get("symbol") or "").strip().upper()
        figi = (row.get("figi") or "").strip().upper()
        if not symbol:
            raise ConfigurationError(f"{where} line {n}: symbol is required")
        if figi and not FIGI.match(figi):
            raise ConfigurationError(
                f"{where} line {n}: figi {figi!r} is not a composite FIGI (e.g. BBG000B9XRY4)"
            )
        if symbol in out:
            raise ConfigurationError(f"{where} line {n}: {symbol} is listed twice")
        if figi and figi in out.values():
            raise ConfigurationError(f"{where} line {n}: {figi} is forced for two symbols")
        out[symbol] = figi or None
    return out


def _regexes(root: Table, key: str, default: tuple[str, ...]) -> tuple[str, ...]:
    """A list of regular expressions; one that does not compile fails with its index."""
    values = root.strings(key, default)
    for i, value in enumerate(values):
        try:
            re.compile(value)
        except re.error as exc:
            raise ConfigurationError(f"{root.where} {key}[{i}]: {exc}") from exc
    return values


def _conventions(
    root: Table, default: tuple[tuple[str, float], ...]
) -> tuple[tuple[str, float], ...]:
    """``leverage_conventions = [{pattern = '...', leverage = -2}, ...]`` (order kept)."""
    key = "leverage_conventions"
    value = root.raw(key)
    if value is None:
        return default
    if not isinstance(value, list):
        raise ConfigurationError(f"{root.where} {key}: expected a list of tables, got {value!r}")
    out = []
    for i, entry in enumerate(value):
        if not isinstance(entry, Mapping) or set(entry) != {"pattern", "leverage"}:
            raise ConfigurationError(
                f"{root.where} {key}[{i}]: expected {{pattern = '...', leverage = N}}, "
                f"got {entry!r}"
            )
        item = Table(entry, f"{root.where} {key}[{i}]")
        pattern = item.text("pattern", "")
        try:
            re.compile(pattern)
        except re.error as exc:
            raise ConfigurationError(f"{item.where} pattern: {exc}") from exc
        leverage = item.number("leverage", 0.0)
        if leverage == 0:
            raise ConfigurationError(f"{item.where} leverage: expected a non-zero number")
        out.append((pattern, leverage))
    return tuple(out)


# ----------------------------------------------------------------------------- defaults.toml


@dataclass(frozen=True)
class ScreeningSettings:
    """``[screening]``: when a screen run is PARTIAL or UNIVERSE_INCOMPLETE."""

    min_coverage: float = 0.98
    max_universe_age_days: int = 45

    @classmethod
    def parse(cls, doc: Mapping[str, Any] | None, where: str) -> "ScreeningSettings":
        d = cls()
        t = Table(doc, where)
        t.only(["min_coverage", "max_universe_age_days"])
        return cls(
            min_coverage=t.fraction("min_coverage", d.min_coverage),
            max_universe_age_days=t.integer("max_universe_age_days", d.max_universe_age_days, 0),
        )


@dataclass(frozen=True)
class CostSettings:
    commission_bps: float = 1.0
    min_commission: float = 0.0
    slippage_bps: float = 5.0


@dataclass(frozen=True)
class LimitSettings:
    max_position_weight: float = 1.0
    max_gross_exposure: float = 1.0
    allow_short: bool = False


def _rebalance(t: Table, default: str) -> str:
    value = t.text("rebalance_selection", default)
    if not REBALANCE_SELECTION.match(value):
        raise ConfigurationError(
            f"{t.where} rebalance_selection: expected none, monthly, weekly or '<N>d' "
            f"(N sessions >= 1), got {value!r}"
        )
    return value


@dataclass(frozen=True)
class BacktestSettings:
    """``[backtest]``: simulated account, costs and risk limits; price adjustment on read."""

    initial_cash: float = 100_000.0
    cash_buffer: float = 0.01
    lot_size: float = 1.0
    periods_per_year: int = 252
    price_adjustment: str = "splits"
    rebalance_selection: str = "none"  # none | monthly | weekly | <N>d (sessions)
    selection_lag_sessions: int = 1  # a selection evaluated on D takes effect D + lag
    costs: CostSettings = CostSettings()
    limits: LimitSettings = LimitSettings()

    @classmethod
    def parse(cls, doc: Mapping[str, Any] | None, where: str) -> "BacktestSettings":
        d, c, lim = cls(), CostSettings(), LimitSettings()
        t = Table(doc, where)
        t.only([*(f for f in d.__dataclass_fields__), "costs", "limits"])
        costs = t.table("costs", list(c.__dataclass_fields__))
        limits = t.table("limits", list(lim.__dataclass_fields__))
        return cls(
            initial_cash=t.number("initial_cash", d.initial_cash, 0),
            cash_buffer=t.fraction("cash_buffer", d.cash_buffer),
            lot_size=t.number("lot_size", d.lot_size, 0),
            periods_per_year=t.integer("periods_per_year", d.periods_per_year, 1),
            price_adjustment=t.choice("price_adjustment", d.price_adjustment, PRICE_ADJUSTMENTS),
            rebalance_selection=_rebalance(t, d.rebalance_selection),
            selection_lag_sessions=t.integer("selection_lag_sessions", d.selection_lag_sessions, 1),
            costs=CostSettings(
                commission_bps=costs.number("commission_bps", c.commission_bps, 0),
                min_commission=costs.number("min_commission", c.min_commission, 0),
                slippage_bps=costs.number("slippage_bps", c.slippage_bps, 0),
            ),
            limits=LimitSettings(
                max_position_weight=limits.number(
                    "max_position_weight", lim.max_position_weight, 0
                ),
                max_gross_exposure=limits.number("max_gross_exposure", lim.max_gross_exposure, 0),
                allow_short=limits.boolean("allow_short", lim.allow_short),
            ),
        )


# ----------------------------------------------------------------------------- loading


def site_document(load: DocumentLoader, name: str) -> Mapping[str, Any] | None:
    """``config/site/<name>.toml`` (``None`` when the file is missing)."""
    return load("site", "settings", name)


def site_defaults(load: DocumentLoader) -> Mapping[str, Any]:
    """``config/site/defaults.toml`` as a document: ``resolve`` layers it under each config."""
    return load("site", "defaults", "defaults") or {}


def load_sources(configs: SiteDocuments) -> SourcesSettings:
    return SourcesSettings.from_document(site_document(configs.load, "sources"))


def load_nightly(configs: SiteDocuments) -> NightlySettings:
    return NightlySettings.from_document(site_document(configs.load, "nightly"))


def load_verification(configs: SiteDocuments) -> VerificationSettings:
    return VerificationSettings.from_document(site_document(configs.load, "verification"))


def load_rollups(
    configs: SiteDocuments, declared: Mapping[str, Any | None]
) -> dict[str, Any | None]:
    """Each declared rollup's params from ``rollups.toml`` (defaults when missing)."""
    return rollup_params(site_document(configs.load, "rollups"), declared)


def load_features(configs: SiteDocuments) -> tuple[FeatureDefinition, ...]:
    """The site's expression features (``config/site/features/*.toml``; none without files)."""
    names = configs.names("site", "features")
    return feature_definitions({n: configs.load("site", "features", n) for n in names})


def load_user_features(configs: SiteDocuments, user: str) -> tuple[FeatureDefinition, ...]:
    """``user``'s expression features (``config/users/<user>/features/*.toml``; none
    without files; none for the ``site`` user). Typed exactly like the site's; see
    ``feature_definitions``."""
    if user == SITE_USER:
        return ()
    names = configs.names(user, "features")
    return feature_definitions({n: configs.load(user, "features", n) for n in names}, user)


def load_universe(configs: SiteDocuments) -> UniverseSettings:
    """``universe.toml`` + curated overrides. Missing file: CSV import mode."""
    doc = site_document(configs.load, "universe")
    return UniverseSettings.from_documents(
        doc, configs.overrides("leveraged_etfs"), figi_overrides=configs.overrides("figi")
    )
