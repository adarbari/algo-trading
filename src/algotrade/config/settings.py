"""Typed L3 site settings: every ``config/site/*.toml`` is loaded and validated HERE only.

ADR 0019 ``site-settings``. Each file becomes a frozen dataclass that apps receive as is:

    sources.toml   -> SourcesSettings   (vendors, [http], [quality], retention)
    universe.toml  -> UniverseSettings  (+ overrides/leveraged_etfs.csv)
    nightly.toml   -> NightlySettings
    defaults.toml  -> ScreeningSettings, BacktestSettings (layered per config by ``resolve``)

Documents come from the config store, so this module does no I/O: ``load_*`` take anything
with ``load(scope, kind, name)`` (a ``ConfigStore``). A missing file or key falls back to the
defaults below; an unknown key, a wrong type or an out-of-range value fails with its path,
e.g. ``sources.toml [massive] min_interval_s: expected a number >= 0, got 'fast'``. The
types live in the library (not the app that reads them) so the one loader can check every key.
"""

import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from algotrade.config.settings_fields import Table
from algotrade.core.errors import ConfigurationError

type DocumentLoader = Callable[[str, str, str], Mapping[str, Any] | None]

# A leveraged / inverse ETF always says so in its name. Absence of these markers is what lets
# a plain ETF be marked not leveraged; presence without a curated override means UNKNOWN.
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
UNIVERSE_SOURCES = ("nasdaq_trader", "csv_import")
PRICE_ADJUSTMENTS = ("none", "splits", "total_return")
# Per-vendor keys beyond ``enabled`` / ``min_interval_s`` (sections are config keys; the
# vendor code that reads them stays in apps/ingestion/sources).
VENDOR_KEYS = ("enabled", "min_interval_s")
VENDOR_EXTRAS = {
    "cboe": ("workers",),
    "nasdaq_earnings": ("days",),
    "massive": ("corporate_actions_window",),
    "sec_edgar": ("refresh_days",),
}


class SiteDocuments(Protocol):
    """What the loader needs from a config store (``storage.config_store.ConfigStore``)."""

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
            ]
        )
        markers = root.strings("leverage_markers", d.leverage_markers)
        for i, marker in enumerate(markers):
            try:
                re.compile(marker)
            except re.error as exc:
                raise ConfigurationError(f"{where} leverage_markers[{i}]: {exc}") from exc
        return cls(
            source=root.choice("source", d.source, UNIVERSE_SOURCES),
            security_types=root.strings("security_types", d.security_types),
            exclude_test_issues=root.boolean("exclude_test_issues", d.exclude_test_issues),
            include_symbols=frozenset(s.upper() for s in root.strings("include_symbols", ())),
            exclude_symbols=frozenset(s.upper() for s in root.strings("exclude_symbols", ())),
            leverage_markers=markers,
            overrides=tuple(overrides),
        )


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


@dataclass(frozen=True)
class BacktestSettings:
    """``[backtest]``: simulated account, costs and risk limits; price adjustment on read."""

    initial_cash: float = 100_000.0
    cash_buffer: float = 0.01
    lot_size: float = 1.0
    periods_per_year: int = 252
    price_adjustment: str = "splits"
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


def load_universe(configs: SiteDocuments) -> UniverseSettings:
    """``universe.toml`` + curated overrides. Missing file: CSV import mode."""
    doc = site_document(configs.load, "universe")
    return UniverseSettings.from_documents(doc, configs.overrides("leveraged_etfs"))
