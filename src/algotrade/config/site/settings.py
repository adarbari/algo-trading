"""Typed L3 site settings: every ``config/site/*.toml`` is loaded and validated HERE only.

ADR 0019 ``site-settings``. Each file becomes a frozen dataclass that apps receive as is:

    sources.toml   -> SourcesSettings   (vendors, [http], [quality], retention)
    universe.toml  -> UniverseSettings  (+ overrides/leveraged_etfs.csv)
    nightly.toml   -> NightlySettings
    rollups.toml   -> each rollup's params dataclass (declared by the rollup, typed here)
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

from algotrade.config.site.fields import Table
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
PRICE_ADJUSTMENTS = ("none", "splits", "total_return")
# ``[backtest] rebalance_selection``: never, the first session of each month / ISO week, or
# every N sessions (``"21d"``). Interpreted by ``engines.selection.schedule``.
REBALANCE_SELECTION = re.compile(r"^(none|monthly|weekly|[1-9][0-9]*d)$")
# Per-vendor keys beyond ``enabled`` / ``min_interval_s`` (sections are config keys; the
# vendor code that reads them stays in apps/ingestion/sources).
VENDOR_KEYS = ("enabled", "min_interval_s")
VENDOR_EXTRAS = {
    "cboe": ("workers",),
    "nasdaq_earnings": ("days",),
    "massive": ("corporate_actions_window",),
    "sec_edgar": ("refresh_days", "facts_refresh_days"),
    "treasury": ("lookback_days",),
}


class SiteDocuments(Protocol):
    """What the loader needs from a config store (``storage.configs.store.ConfigStore``)."""

    def load(self, scope: str, kind: str, name: str) -> Mapping[str, Any] | None: ...

    def overrides(self, name: str) -> list[dict[str, str]]: ...


# ----------------------------------------------------------------------------- sources.toml


@dataclass(frozen=True)
class VendorSettings:
    """One vendor section of ``sources.toml``: on/off and its pacing (``None``: the
    registry's default for that source)."""

    enabled: bool = True
    min_interval_s: float | None = None


@dataclass(frozen=True)
class SourcesSettings:
    raw_retention_days: int = 90
    staging_retention_days: int = 14
    vendors: Mapping[str, VendorSettings] = field(default_factory=dict)  # by section name
    cboe_workers: int = 4
    earnings_days: int = 60
    actions_window: tuple[int, int] = (-7, 30)
    sec_refresh_days: int = 30
    sec_facts_refresh_days: int = 30
    treasury_lookback_days: int = 10
    http_max_retry_s: float = 300.0
    http_breaker_failures: int = 10
    limits_dir: str = "var/run/limits"
    max_bar_count_drop: float = 0.10
    max_universe_change: float = 0.05
    min_chain_coverage: float = 0.95

    def vendor(self, section: str) -> VendorSettings:
        """``[section]`` of sources.toml (defaults when the section is missing)."""
        return self.vendors.get(section, VendorSettings())

    @classmethod
    def from_document(
        cls, doc: Mapping[str, Any] | None, where: str = "sources.toml"
    ) -> "SourcesSettings":
        d = cls()
        root = Table(doc, where)
        sections = [k for k in root.names() if isinstance(root.raw(k), Mapping)]
        root.only(["raw_retention_days", "staging_retention_days", *sections])
        http = root.table("http", ["max_retry_s", "breaker_failures", "limits_dir"])
        quality = root.table(
            "quality", ["max_bar_count_drop", "max_universe_change", "min_chain_coverage"]
        )
        vendors = {
            name: root.table(name, [*VENDOR_KEYS, *VENDOR_EXTRAS.get(name, ())])
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
            vendors={name: _vendor(t) for name, t in vendors.items()},
            cboe_workers=_extra(vendors, "cboe").integer("workers", d.cboe_workers, 1),
            earnings_days=_extra(vendors, "nasdaq_earnings").integer("days", d.earnings_days, 1),
            actions_window=(window[0], window[1]),
            sec_refresh_days=_extra(vendors, "sec_edgar").integer(
                "refresh_days", d.sec_refresh_days, 0
            ),
            sec_facts_refresh_days=_extra(vendors, "sec_edgar").integer(
                "facts_refresh_days", d.sec_facts_refresh_days, 0
            ),
            treasury_lookback_days=_extra(vendors, "treasury").integer(
                "lookback_days", d.treasury_lookback_days, 1
            ),
            http_max_retry_s=http.number("max_retry_s", d.http_max_retry_s, 0),
            http_breaker_failures=http.integer("breaker_failures", d.http_breaker_failures, 1),
            limits_dir=http.text("limits_dir", d.limits_dir),
            max_bar_count_drop=quality.fraction("max_bar_count_drop", d.max_bar_count_drop),
            max_universe_change=quality.fraction("max_universe_change", d.max_universe_change),
            min_chain_coverage=quality.fraction("min_chain_coverage", d.min_chain_coverage),
        )


def _vendor(section: Table) -> VendorSettings:
    return VendorSettings(
        enabled=section.boolean("enabled", True),
        min_interval_s=section.number("min_interval_s", None, 0),
    )


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

    @classmethod
    def from_document(
        cls, doc: Mapping[str, Any] | None, where: str = "nightly.toml"
    ) -> "NightlySettings":
        d = cls()
        root = Table(doc, where)
        root.only(["sessions", "alerts", "notify"])
        sessions = root.table("sessions", ["settle_minutes", "max_catch_up"])
        alerts = root.table("alerts", ["max_duration_minutes"])
        notify = root.table("notify", ["enabled", "desktop", "summary_path"])
        return cls(
            settle_minutes=sessions.integer("settle_minutes", d.settle_minutes, 0),
            max_catch_up=sessions.integer("max_catch_up", d.max_catch_up, 1),
            max_duration_minutes=alerts.number("max_duration_minutes", d.max_duration_minutes, 0),
            notify_enabled=notify.boolean("enabled", d.notify_enabled),
            notify_desktop=notify.boolean("desktop", d.notify_desktop),
            summary_path=notify.text("summary_path", d.summary_path),
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


# ----------------------------------------------------------------------------- universe.toml


@dataclass(frozen=True)
class UniverseSettings:
    """``config/site/universe.toml`` (coverage) + the curated ``overrides/leveraged_etfs.csv``.
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

    @classmethod
    def from_documents(
        cls,
        doc: Mapping[str, Any] | None,
        overrides: Iterable[Mapping[str, str]] = (),
        where: str = "universe.toml",
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
        )


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


def load_rollups(
    configs: SiteDocuments, declared: Mapping[str, Any | None]
) -> dict[str, Any | None]:
    """Each declared rollup's params from ``rollups.toml`` (defaults when missing)."""
    return rollup_params(site_document(configs.load, "rollups"), declared)


def load_universe(configs: SiteDocuments) -> UniverseSettings:
    """``universe.toml`` + curated overrides. Missing file: CSV import mode."""
    doc = site_document(configs.load, "universe")
    return UniverseSettings.from_documents(doc, configs.overrides("leveraged_etfs"))
