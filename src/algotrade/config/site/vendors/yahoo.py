"""``sources.toml [yahoo]``: the analyst snapshot's Yahoo step, validated (ADR 0080).

Read by ``SourcesSettings.from_document`` (``config/site/settings.py``), the one loader; it lives
in its own module to keep that file under the length limit. ``licence`` is the owner-only tag
``yahoo`` (Yahoo's terms forbid scraping: personal use, never served to another viewer).
"""

from dataclasses import dataclass
from datetime import date

from algotrade.config.site.fields import Table
from algotrade.config.site.macro import HELD_LICENCES
from algotrade.core.model.errors import ConfigurationError

LICENCE = "yahoo"
YAHOO_KEYS = (
    "licence",
    "per_night",
    "refresh_days",
    "standby_days",
    "nightly_ceiling",
    "events_enabled",
    "cycle_anchor",
    "run_budget_s",
    "backfill_batch",
    "backfill_min_interval_s",
    "cache_dir",
)


@dataclass(frozen=True)
class YahooSettings:
    licence: str = LICENCE  # what its analyst data is licensed for: the owner only
    per_night: int = 360  # baseline names asked a night (one call each, stalest, then largest cap)
    refresh_days: int = 14  # a name FMP does not answer is asked again after this many days
    standby_days: int = 45  # a name FMP answers (the reader prefers FMP) is asked this rarely
    nightly_ceiling: int = 400  # every Yahoo call a night, event pulls and baseline together
    events_enabled: bool = True  # false: only the rolling baseline (the event pulls are off)
    cycle_anchor: date = date(2026, 10, 23)  # day 0 of the rolling cycles (the backfill's day)
    run_budget_s: int = 900  # its own time cap: after it no further call is made
    backfill_batch: int = 500  # names one ``analyst-backfill`` run asks (one batch, then it ends)
    backfill_min_interval_s: float = 0.3  # the backfill's pacing floor (adapts up to 3 s on errors)
    cache_dir: str = "var/cache/yahoo"  # yfinance's cookie and timezone caches


def parse_yahoo(section: Table) -> YahooSettings:
    """The typed ``[yahoo]`` keys beyond the vendor keys (``enabled``, ``min_interval_s``, ...)."""
    d = YahooSettings()
    return YahooSettings(
        licence=section.choice("licence", d.licence, HELD_LICENCES),
        per_night=section.integer("per_night", d.per_night, 0),
        refresh_days=section.integer("refresh_days", d.refresh_days, 1),
        standby_days=section.integer("standby_days", d.standby_days, 1),
        nightly_ceiling=section.integer("nightly_ceiling", d.nightly_ceiling, 0),
        events_enabled=section.boolean("events_enabled", d.events_enabled),
        cycle_anchor=anchor(section, d.cycle_anchor),
        run_budget_s=section.integer("run_budget_s", d.run_budget_s, 1),
        backfill_batch=section.integer("backfill_batch", d.backfill_batch, 1),
        backfill_min_interval_s=section.number(
            "backfill_min_interval_s", d.backfill_min_interval_s, 0
        ),
        cache_dir=section.text("cache_dir", d.cache_dir),
    )


def anchor(section: Table, default: date) -> date:
    """``cycle_anchor``: an ISO date (``2026-10-23``)."""
    raw = section.raw("cycle_anchor")
    if raw is None:
        return default
    try:
        return raw if isinstance(raw, date) else date.fromisoformat(str(raw))
    except ValueError:
        raise ConfigurationError(
            f"{section.where} cycle_anchor: expected an ISO date, got {raw!r}"
        ) from None
