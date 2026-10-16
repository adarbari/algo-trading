"""Which sources a task needs and whether they are available: the source lists of the
holdings and description tasks and the skip predicates workflows use (a task whose source is
not built is skipped with a WARN, never failed)."""

from algotrade_ingestion.tasks.framework.run import TaskContext
from algotrade_sources.framework.base import HoldingsSource, SessionSource

HOLDINGS_ISSUERS = (
    "ssga_holdings",
    "ishares_holdings",
    "proshares_holdings",
    "sec_nport_holdings",
)  # priority order


def holdings_issuers(ctx: TaskContext) -> list[HoldingsSource]:
    found = [ctx.sources[n] for n in HOLDINGS_ISSUERS if n in ctx.sources]
    return [s for s in found if isinstance(s, HoldingsSource)]


def no_holdings_source(ctx: TaskContext) -> str | None:
    if not ctx.settings.vendor("etf_holdings").enabled:
        return "skipped: [etf_holdings] is disabled in sources.toml"
    if holdings_issuers(ctx):
        return None
    reasons = sorted({ctx.unavailable.get(n, f"{n} is not configured") for n in HOLDINGS_ISSUERS})
    return f"skipped: {'; '.join(reasons)}"


DESCRIPTION_SOURCES = (
    "massive_overview",
    "sec_fund_tickers",
    "sec_fund_objectives",
    "sec_fund_series",
)  # every source the task may read: the CLI builds only the ones a task declares


def no_description_source(ctx: TaskContext) -> str | None:
    """Workflows skip ``descriptions`` when neither Massive nor the SEC sources are built."""
    if any(name in ctx.sources for name in DESCRIPTION_SOURCES):
        return None
    reasons = sorted(
        {ctx.unavailable.get(n, f"{n} is not configured") for n in DESCRIPTION_SOURCES}
    )
    return f"skipped: {'; '.join(reasons)}"


def ibkr_source(ctx: TaskContext) -> SessionSource:
    source = ctx.sources["ibkr"]
    if not isinstance(source, SessionSource):
        raise TypeError("ibkr must be a SessionSource (IB Gateway)")
    return source


def gateway_down(ctx: TaskContext) -> str | None:
    """Workflows skip the IBKR tasks (with a WARN) when nothing listens on the gateway port."""
    source = ctx.sources.get("ibkr")
    reason = source.probe() if isinstance(source, SessionSource) else None
    return f"skipped: WARN: {reason}" if reason else None
