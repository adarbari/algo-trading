"""Typed L3 site settings: every ``config/site/*.toml`` is loaded and validated HERE only.

ADR 0019 ``site-settings``. Each file becomes a frozen dataclass that apps receive as is:

    sources.toml   -> SourcesSettings   (vendors, [http], [quality], retention; [ibkr])
    verification.toml -> VerificationSettings (live verification vs IBKR)
    llm.toml       -> LlmSettings       (the text model behind screener drafts, ADR 0041)
    phrasebook.toml -> PhrasebookSettings (trader vocabulary -> catalogue fields, ADR 0041)
    field_guide/*.toml -> FieldGuideSettings (how to read a field, thresholds, caveats, ADR 0041)
    macro.toml     -> MacroSettings     (config/site/macro.py: macro series, index levels; ADR 0048)
    universe.toml  -> UniverseSettings  (+ overrides/leveraged_etfs.csv, overrides/figi.csv)
    nightly.toml   -> NightlySettings
    verdict.toml   -> VerdictSettings   (config/edges/verdict.py: the edge verdict's thresholds)
    users.toml     -> UsersSettings     (config/site/users.py: the user registry, ADR 0040)
    users/<id>/identity.toml -> the user's sign-in email / subject on its UserRecord (git-ignored)
    rollups.toml   -> each rollup's params dataclass (declared by the rollup, typed here)
    features/<kind>/<theme>.toml -> FeatureDefinition per expression feature (ADR 0023 step 3)
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
from dataclasses import dataclass, field
from typing import Any, Protocol

from algotrade.config.edges.verdict import VerdictSettings
from algotrade.config.site.coverage import DEFAULT_COVERAGE, CoverageRule, load_coverage
from algotrade.config.site.features.definitions import (
    SCALARS,
    FeatureDefinition,
    feature_definitions,
)
from algotrade.config.site.field_guide import FieldGuideSettings
from algotrade.config.site.fields import Table
from algotrade.config.site.holdings import KEYS as ETF_KEYS
from algotrade.config.site.holdings import (
    LEGACY_SECTIONS,
    OWN_KEYS_ONLY,
    VENDOR_FLAGS,
    EtfHoldingsSettings,
)
from algotrade.config.site.ibkr import IbkrSettings as IbkrSettings  # noqa: PLC0414 - re-export
from algotrade.config.site.ibkr import load_ibkr
from algotrade.config.site.llm import LlmSettings as LlmSettings  # noqa: PLC0414 - re-export
from algotrade.config.site.llm import PhrasebookSettings as PhrasebookSettings  # noqa: PLC0414
from algotrade.config.site.macro import LICENCES
from algotrade.config.site.macro import MacroSettings as MacroSettings  # noqa: PLC0414 - re-export
from algotrade.config.site.nightly import (
    NightlySettings as NightlySettings,  # noqa: PLC0414 - re-export
)
from algotrade.config.site.users import IDENTITY, identity
from algotrade.config.site.users import UsersSettings as UsersSettings  # noqa: PLC0414 - re-export
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
    "fred": ("base_url",),
    "tiingo": ("licence", "monthly_symbol_budget"),
    "etf_holdings": ETF_KEYS,
    **VENDOR_FLAGS,
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
    switches: Mapping[str, bool] = field(default_factory=dict)  # VENDOR_FLAGS: more on/off keys


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
    fred_base_url: str = "https://api.stlouisfed.org/fred"  # [fred] base_url (ADR 0048)
    tiingo_licence: str = "personal"  # [tiingo] licence: what its bars are licensed for (ADR 0028)
    tiingo_monthly_symbol_budget: int = (
        450  # [tiingo] monthly_symbol_budget: distinct tickers a month
    )
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
    max_type_disagreement: float = 0.10  # reference_classification (ADR 0045)
    max_name_over_vendor: float = 0.02
    max_bar_unresolved: float = 0.01
    min_bar_close: float = 0.01  # bar-quality (ADR 0061): a close below this is flagged
    max_bar_jump: float = 10.0  # a one-day close ratio above this (either way) is a jump
    split_window_sessions: int = 5  # a jump within this many bars of a split event is explained
    max_bad_bar_share: float = 0.02  # bar-quality: FAIL if over 2% of the bars are flagged
    max_bounded_return: float = 10.0  # outcomes: a COMPLETE fwd_return above this (h <= 60) FAILs
    max_chain_fetch_failures: float = 0.02
    max_chain_stale_share: float = 0.20  # the "rest" tier
    max_chain_stale_share_core: float = 0.02  # core tier (tasks/market/tiers.py)
    max_chain_stale_sessions: int = 5  # older STALE_DATA chains are fetch failures (data/chains.py)
    max_verify_failures: float = 0.10
    max_ibkr_vol_rejected: float = 0.02  # ibkr-iv: share of the session's rows with a vol nulled
    max_macro_stale_share: float = 0.20  # macro series (ADR 0048)
    min_calendar_future_dates: int = 1  # macro-calendar: dates each FRED release must list ahead
    max_filings_failed: float = 0.05  # filings: share of CIKs whose SEC fetch failed
    filings_backfill_per_night: int = 50  # filings: CIKs new to the universe read in full a night
    coverage: tuple[CoverageRule, ...] = DEFAULT_COVERAGE  # [quality.coverage.<group>.<column>]
    ibkr: IbkrSettings = field(default_factory=IbkrSettings)
    etf: EtfHoldingsSettings = field(default_factory=EtfHoldingsSettings)  # [etf_holdings]

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
                "max_type_disagreement",
                "max_name_over_vendor",
                "max_bar_unresolved",
                *("min_bar_close", "max_bar_jump", "split_window_sessions", "max_bad_bar_share"),
                "max_bounded_return",
                "max_chain_fetch_failures",
                *("max_chain_stale_share", "max_chain_stale_share_core"),
                "max_chain_stale_sessions",
                "max_verify_failures",
                "max_ibkr_vol_rejected",
                *("max_macro_stale_share", "min_calendar_future_dates", "max_filings_failed"),
                "filings_backfill_per_night",
                "coverage",
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
            vendors=_renamed(
                {
                    name: _vendor(t, name not in OFF_BY_DEFAULT, VENDOR_FLAGS.get(name, ()))
                    for name, t in vendors.items()
                }
            ),
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
            fred_base_url=_extra(vendors, "fred").text("base_url", d.fred_base_url),
            tiingo_licence=_extra(vendors, "tiingo").choice("licence", d.tiingo_licence, LICENCES),
            tiingo_monthly_symbol_budget=_extra(vendors, "tiingo").integer(
                "monthly_symbol_budget", d.tiingo_monthly_symbol_budget, 0
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
            max_name_over_vendor=quality.fraction("max_name_over_vendor", d.max_name_over_vendor),
            max_type_disagreement=quality.fraction(
                "max_type_disagreement", d.max_type_disagreement
            ),
            max_bar_unresolved=quality.fraction("max_bar_unresolved", d.max_bar_unresolved),
            min_bar_close=quality.number("min_bar_close", d.min_bar_close, 0),
            max_bar_jump=quality.number("max_bar_jump", d.max_bar_jump, 1),
            split_window_sessions=quality.integer(
                "split_window_sessions", d.split_window_sessions, 0
            ),
            max_bad_bar_share=quality.fraction("max_bad_bar_share", d.max_bad_bar_share),
            max_bounded_return=quality.number("max_bounded_return", d.max_bounded_return, 0),
            max_chain_fetch_failures=quality.fraction(
                "max_chain_fetch_failures", d.max_chain_fetch_failures
            ),
            max_chain_stale_share=quality.fraction(
                "max_chain_stale_share", d.max_chain_stale_share
            ),
            max_chain_stale_share_core=quality.fraction(
                "max_chain_stale_share_core", d.max_chain_stale_share_core
            ),
            max_chain_stale_sessions=quality.integer(
                "max_chain_stale_sessions", d.max_chain_stale_sessions, 1
            ),
            max_verify_failures=quality.fraction("max_verify_failures", d.max_verify_failures),
            max_ibkr_vol_rejected=quality.fraction(
                "max_ibkr_vol_rejected", d.max_ibkr_vol_rejected
            ),
            max_macro_stale_share=quality.fraction(
                "max_macro_stale_share", d.max_macro_stale_share
            ),
            min_calendar_future_dates=quality.integer(
                "min_calendar_future_dates", d.min_calendar_future_dates, 0
            ),
            max_filings_failed=quality.fraction("max_filings_failed", d.max_filings_failed),
            filings_backfill_per_night=quality.integer(
                "filings_backfill_per_night", d.filings_backfill_per_night, 0
            ),
            coverage=load_coverage(quality, d.coverage),
            ibkr=load_ibkr(_extra(vendors, "ibkr")),
            etf=EtfHoldingsSettings.from_table(_extra(vendors, "etf_holdings")),
        )


def _renamed(vendors: dict[str, VendorSettings]) -> dict[str, VendorSettings]:
    """A file with only a renamed section's old name keeps its on/off switch (not its pacing)."""
    for new, old in LEGACY_SECTIONS.items():
        if new not in vendors and old in vendors:
            vendors[new] = VendorSettings(enabled=vendors[old].enabled)
    return vendors


def _vendor_keys(section: str) -> tuple[str, ...]:
    if section in OWN_KEYS_ONLY:
        return OWN_KEYS_ONLY[section]
    if section in FIXED_PACE:
        return tuple(k for k in VENDOR_KEYS if k not in ADAPTIVE_KEYS)
    return VENDOR_KEYS


def _vendor(section: Table, enabled: bool = True, extra: tuple[str, ...] = ()) -> VendorSettings:
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
        switches={key: section.boolean(key, True) for key in extra},
    )


def _optional_integer(section: Table, key: str, minimum: int) -> int | None:
    """``key`` as an integer >= ``minimum``, or ``None`` when the section does not set it."""
    return None if section.raw(key) is None else section.integer(key, minimum, minimum)


def _extra(vendors: Mapping[str, Table], name: str) -> Table:
    return vendors.get(name) or Table(None, name)


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
            if type(getattr(defaults, f.name)) in SCALARS
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


def load_verdict(configs: SiteDocuments) -> VerdictSettings:
    return VerdictSettings.from_document(site_document(configs.load, "verdict"))


def load_users(configs: SiteDocuments) -> UsersSettings:
    """The declared users and roles (``config/site/users.toml``, ADR 0040; the single-user
    defaults without it), each with the email (and pinned subject) of its git-ignored
    ``config/users/<id>/identity.toml`` when there is one."""
    users = UsersSettings.from_document(site_document(configs.load, "users"))
    found = {
        u.user_id: identity(configs.load(u.user_id, IDENTITY, IDENTITY), u.user_id)
        for u in users.users
        if u.user_id != SITE_USER
    }
    return users.with_identities(found)


def load_verification(configs: SiteDocuments) -> VerificationSettings:
    return VerificationSettings.from_document(site_document(configs.load, "verification"))


def load_llm(configs: SiteDocuments) -> LlmSettings:
    """``llm.toml`` (ADR 0041); missing: drafting off."""
    return LlmSettings.from_document(site_document(configs.load, "llm"))


def load_phrasebook(configs: SiteDocuments) -> PhrasebookSettings:
    """``phrasebook.toml`` (ADR 0041); missing: no phrases."""
    return PhrasebookSettings.from_document(site_document(configs.load, "phrasebook"))


# By store identity (the store kept alive): site config changes with a release, as the site
# feature catalogue does (``features.site``); every Guide read and help button needs it, and
# parsing it each time held the GIL for 0.12 s a request.
_FIELD_GUIDES: dict[int, tuple[SiteDocuments, FieldGuideSettings]] = {}


def load_field_guide(configs: SiteDocuments) -> FieldGuideSettings:
    """``config/site/field_guide/*.toml`` (ADR 0041, amended): how to read each field, in
    file-name order; none without files. Read once per store."""
    built = _FIELD_GUIDES.get(id(configs))
    if built is None or built[0] is not configs:
        names = configs.names("site", "field_guide")
        documents = {n: configs.load("site", "field_guide", n) for n in names}
        built = (configs, FieldGuideSettings.from_documents(documents))
        _FIELD_GUIDES[id(configs)] = built
    return built[1]


def load_macro(configs: SiteDocuments) -> MacroSettings:
    """``macro.toml`` (ADR 0048); missing: no series."""
    return MacroSettings.from_document(site_document(configs.load, "macro"))


def load_rollups(
    configs: SiteDocuments, declared: Mapping[str, Any | None]
) -> dict[str, Any | None]:
    """Each declared rollup's params from ``rollups.toml`` (defaults when missing)."""
    return rollup_params(site_document(configs.load, "rollups"), declared)


def load_rollup(configs: SiteDocuments, key: str, defaults: Any) -> Any:
    """One rollup's params (``rollups.toml`` section ``key`` over ``defaults``), that section
    only: a reader of one group's thresholds (the read model) need not know the others."""
    doc = site_document(configs.load, "rollups") or {}
    return rollup_params({key: doc[key]} if key in doc else {}, {key: defaults})[key]


def load_features(configs: SiteDocuments) -> tuple[FeatureDefinition, ...]:
    """The site's expression features (``config/site/features/*/*.toml``; none without files)."""
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
